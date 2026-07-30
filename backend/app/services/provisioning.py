"""Onboard a collective or member onto BMoni, end to end.

The sequence below is the one verified working against the sandbox. Order
matters — BMoni's own guide warns that calls fail when it isn't followed:

    create user → complete KYC → create wallet → activate the naira rail

Each step is idempotent at the Evident level: anything already carrying a
`smart_wallet_id` is skipped, so a retry after a partial failure resumes rather
than duplicating.
"""
import hashlib
import logging

from app.config import settings
from app.services import bmoni_client, signing

logger = logging.getLogger(__name__)

# Every BMoni user needs a unique email and phone. Real members may share neither
# (or supply nothing at all), so synthesise a stable one from the Evident id.
_PHONE_PREFIX = "+23480"


def _slug(ref: str) -> str:
    """Hash the WHOLE ref. Slicing the raw id looks equivalent but isn't — ids
    generated in a batch often share a long prefix, and BMoni 409s on a duplicate
    email or phone."""
    return hashlib.sha256(f"{settings.secret_key}:contact:{ref}".encode()).hexdigest()


def _synthetic_email(ref: str) -> str:
    return f"evident+{_slug(ref)[:12]}@example.com"


def _synthetic_phone(ref: str) -> str:
    digits = int(_slug(ref)[:12], 16) % 100_000_000
    return f"{_PHONE_PREFIX}{digits:08d}"


async def provision(*, ref: str, display_name: str, email: str | None = None,
                    phone: str | None = None, date_of_birth: str = "1995-06-15") -> dict:
    """Create the BMoni user, wallet and naira rail for one Evident entity.

    `ref` is the Evident collective/member id; it seeds the owner key, so the
    same ref always controls the same wallet.

    Returns the identifiers Evident stores. Raises BmoniAPIError on failure —
    callers decide whether that's fatal.
    """
    email = email or _synthetic_email(ref)
    phone = phone or _synthetic_phone(ref)
    first_name, _, last_name = display_name.partition(" ")

    user = await bmoni_client.get_or_create_user(first_name or "Evident", email, phone)
    user_id = user.get("bmoniUserId")
    if not user_id:
        raise bmoni_client.BmoniAPIError(f"no bmoniUserId in create-user response: {user}")
    logger.info("BMoni user created for %s: %s", ref, user_id)

    # KYC before the wallet: it's what unblocks provider provisioning downstream.
    # Non-fatal — the naira rail is driven by start-nigeria, and a KYC hiccup
    # shouldn't strand a wallet that would otherwise work.
    try:
        await bmoni_client.update_kyc(
            user_id,
            first_name=first_name or "Evident",
            last_name=last_name or "Member",
            email=email,
            phone=phone,
            date_of_birth=date_of_birth,
            bvn=settings.bmoni_test_bvn,
        )
    except Exception:
        logger.warning("KYC update failed for %s (continuing)", ref, exc_info=True)

    owner_address = signing.owner_address(ref)
    challenge = await bmoni_client.owner_proof_challenge(user_id, owner_address)
    challenge_id, message = challenge.get("challengeId"), challenge.get("message")
    if not (challenge_id and message):
        raise bmoni_client.BmoniAPIError(f"bad owner-proof challenge: {challenge}")

    signature = signing.sign_text(ref, message)
    wallet = await bmoni_client.get_or_create_wallet(
        user_id, owner_address, challenge_id, signature)
    wallet_id = wallet.get("id")
    wallet_address = wallet.get("walletAddress")
    if not (wallet_id and wallet_address):
        raise bmoni_client.BmoniAPIError(f"bad create-managed response: {wallet}")
    logger.info("BMoni wallet for %s: %s (%s)", ref, wallet_id, wallet_address)

    # Naira rail. Non-fatal: the wallet already works for wallet-to-wallet
    # contributions, which is the path the demo actually uses.
    try:
        await bmoni_client.start_nigeria(user_id, settings.bmoni_test_bvn, wallet_address)
    except Exception:
        logger.warning("start-nigeria failed for %s (continuing)", ref, exc_info=True)

    # Pooled across every user — stored for display only. It CANNOT identify who
    # paid, which is why attribution keys off wallet_address instead.
    deposit_account = {}
    try:
        accounts = await bmoni_client.deposit_accounts(user_id)
        deposit_account = accounts[0] if accounts else {}
    except Exception:
        logger.warning("deposit-account read failed for %s", ref, exc_info=True)

    return {
        "bmoni_user_id": user_id,
        "smart_wallet_id": wallet_id,
        "wallet_address": wallet_address,
        "owner_address": owner_address,
        "bank_account_number": deposit_account.get("accountNumber"),
        "bank_name": deposit_account.get("bankName"),
        "email": email,
        "phone": phone,
    }


async def provision_entity(entity, display_name: str) -> None:
    """Provision a Collective or Member row in place. Skips anything already done."""
    if getattr(entity, "smart_wallet_id", None):
        return
    result = await provision(
        ref=entity.id,
        display_name=display_name,
        email=getattr(entity, "email", None),
        phone=getattr(entity, "phone", None),
    )
    entity.bmoni_user_id = result["bmoni_user_id"]
    entity.smart_wallet_id = result["smart_wallet_id"]
    entity.wallet_address = result["wallet_address"]
    entity.bank_account_number = result["bank_account_number"]
    entity.bank_name = result["bank_name"]
    entity.virtual_account_id = result["smart_wallet_id"]
    # persist the phone actually registered — it's the handle BMoni matches when
    # crediting test funds, and recomputing it later would drift if the
    # derivation ever changes
    if hasattr(entity, "phone") and not entity.phone:
        entity.phone = result["phone"]
