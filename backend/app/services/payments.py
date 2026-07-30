"""Payment-provider seam, now backed by BMoni.

Everything the app needs from a provider routes through here: provisioning a
pay-in identity, verifying a recipient bank account, listing banks, and paying
out an approved expense.

Two BMoni facts shape this module:

* The naira deposit account is POOLED across all users, so it cannot identify a
  payer. `provision_pay_in_account` returns it for display, but attribution is
  done by smart-wallet address (see `ingest.py`).
* A payout is not one call. It is verify → register → offramp → sign, and the
  offramp returns a *proposal* that must be signed before money moves. BMoni
  co-signs server-side, so Evident produces exactly one signature.
"""
import logging

from app.config import settings
from app.services import bmoni_client, provisioning, signing
from app.services.bmoni_client import BmoniAPIError

logger = logging.getLogger(__name__)


class PaymentProviderNotConfigured(RuntimeError):
    """No API key set. Routers map this to 503."""


def _require_configured() -> None:
    if not settings.bmoni_api_key:
        raise PaymentProviderNotConfigured(
            "BMONI_API_KEY is not set — provisioning and payouts are unavailable"
        )


async def provision_pay_in_account(*, account_ref: str, account_name: str,
                                   callback_url: str) -> dict:
    """Create the BMoni user + wallet + naira rail behind an Evident entity."""
    _require_configured()
    result = await provisioning.provision(ref=account_ref, display_name=account_name)
    return {
        "accountNumber": result["bank_account_number"],
        "bankName": result["bank_name"],
        "accountId": result["smart_wallet_id"],
        "walletAddress": result["wallet_address"],
        "bmoniUserId": result["bmoni_user_id"],
    }


async def lookup_bank_account(account_number: str, bank_code: str,
                              user_id: str | None = None) -> dict:
    """Resolve a recipient account to its registered holder name.

    BMoni scopes this per user, so it needs someone to ask as. Any provisioned
    user gives the same answer — the lookup is about the destination account.
    """
    _require_configured()
    if not user_id:
        raise PaymentProviderNotConfigured(
            "Bank lookup needs a provisioned collective — create one first"
        )
    result = await bmoni_client.verify_nigerian_account(user_id, account_number, bank_code)
    name = (result.get("accountName") or result.get("accountHolderName")
            or result.get("name"))
    return {"accountName": name, "accountNumber": account_number, "bankCode": bank_code}


async def fetch_banks(user_id: str | None = None) -> list:
    _require_configured()
    if not user_id:
        raise PaymentProviderNotConfigured(
            "Bank list needs a provisioned collective — create one first"
        )
    return await bmoni_client.nigerian_banks(user_id)


async def transfer_to_bank(*, amount_naira: float, account_number: str, account_name: str,
                           bank_code: str, expense_id: str, narration: str,
                           sender_name: str, collective=None) -> dict:
    """Pay an approved expense out of the collective's treasury wallet.

    Returns {"status", "id"} shaped like the caller expects, where `id` is the
    proposal id. There is no `merchantTxRef` equivalent, so the caller is
    responsible for never offramping the same expense twice — `disbursement`
    does that by refusing an expense that already has a `transfer_ref`.

    `narration` and `sender_name` are accepted but unused: BMoni's offramp takes
    only a bank account and an amount. The recipient's statement will therefore
    show BMoni's own descriptor, not the collective's name — a visible change
    from the previous provider, which put `senderName` on the statement.
    """
    _require_configured()
    if collective is None or not collective.bmoni_user_id or not collective.smart_wallet_id:
        raise PaymentProviderNotConfigured(
            "Collective has no provisioned BMoni wallet to pay from"
        )

    user_id = collective.bmoni_user_id
    bank_name = ""
    try:
        for bank in await bmoni_client.nigerian_banks(user_id):
            if str(bank.get("code") or bank.get("bankCode")) == str(bank_code):
                bank_name = bank.get("name") or bank.get("bankName") or ""
                break
    except Exception:
        logger.warning("bank-name lookup failed; registering without it", exc_info=True)

    # Register the destination. Get-or-create, so a repeat is harmless. The holder
    # name must match what verify returned, so re-verify rather than trust input.
    verified = await bmoni_client.verify_nigerian_account(user_id, account_number, bank_code)
    holder = (verified.get("accountName") or verified.get("accountHolderName")
              or account_name)
    registered = await bmoni_client.register_withdrawal_account(
        user_id,
        account_number=account_number,
        bank_code=bank_code,
        bank_name=bank_name or verified.get("bankName") or "",
        account_holder_name=holder,
    )
    bank_account_id = registered.get("id") or registered.get("bankAccountId")
    if not bank_account_id:
        raise BmoniAPIError(f"no bankAccountId from withdrawal-account registration: {registered}")

    proposal = await bmoni_client.create_offramp(
        user_id, collective.smart_wallet_id, bank_account_id, f"{amount_naira:.2f}")
    proposal_id = proposal.get("proposalId") or proposal.get("id")
    if not proposal_id:
        raise BmoniAPIError(f"no proposalId from offramp: {proposal}")
    logger.info("Offramp proposal %s for expense %s", proposal_id, expense_id)

    # Sign it. Failure here leaves the proposal unsigned and the money unmoved,
    # so the caller's ledger reversal is still the correct response.
    payload = await bmoni_client.proposal_sign_payload(user_id, proposal_id)
    signature = signing.sign_proposal_payload(collective.id, payload)
    signed = await bmoni_client.sign_proposal(user_id, proposal_id, signature)

    status = str(signed.get("status") or proposal.get("status") or "PENDING").upper()
    return {"id": proposal_id, "status": _normalise_status(status)}


def _normalise_status(status: str) -> str:
    """Map BMoni proposal states onto the SUCCESS/FAILED/PENDING the caller expects."""
    if status in ("COMPLETED", "SUCCESS", "EXECUTED"):
        return "SUCCESS"
    if status in ("FAILED", "REJECTED", "CANCELLED", "REFUND"):
        return "FAILED"
    return "PENDING"


async def check_transfer_status(collective, transfer_ref: str) -> str:
    """Poll a proposal to a terminal state. Used to settle `disbursing` expenses."""
    _require_configured()
    proposal = await bmoni_client.get_proposal(collective.bmoni_user_id, transfer_ref)
    return _normalise_status(str(proposal.get("status") or "PENDING").upper())
