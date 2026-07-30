"""Thin wrapper over the BMoni Embedded API.

Auth is a single `x-api-key` header — no token issue/refresh cycle, unlike the
provider this replaced.

Response shapes vary: some endpoints return the object at the top level, others
nest it under `data` / `user` / `wallet`. `_unwrap()` normalises that rather than
each caller guessing. Field names used below were read off real sandbox
responses, not the docs, except where marked UNVERIFIED.
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 60
CURRENCY = "CNGN"  # wallet currency on the way in; responses call it "NGN"


class BmoniAPIError(RuntimeError):
    """A BMoni call failed. Carries the response body — that's where the reason is."""


def _headers() -> dict:
    if not settings.bmoni_api_key:
        raise BmoniAPIError("BMONI_API_KEY is not set")
    return {"x-api-key": settings.bmoni_api_key, "Content-Type": "application/json"}


def _unwrap(data: Any, *keys: str) -> dict:
    """Peel a transport envelope. Explicit keys win; otherwise try the usual ones."""
    if not isinstance(data, dict):
        return {}
    for key in (*keys, "data", "user", "wallet", "smartWallet", "result"):
        inner = data.get(key)
        if isinstance(inner, dict):
            return inner
    return data


async def _request(method: str, path: str, body: dict | None = None,
                   params: dict | None = None) -> Any:
    url = f"{settings.bmoni_base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_headers()) as client:
        resp = await client.request(method, url, json=body, params=params)
    if resp.status_code >= 400:
        # keep the body — "account not found", "insufficient funds" live there,
        # and raise_for_status() would throw it away
        raise BmoniAPIError(f"BMoni {method} {path} -> {resp.status_code}: {resp.text[:400]}")
    try:
        return resp.json()
    except ValueError:
        raise BmoniAPIError(f"BMoni {method} {path} returned non-JSON: {resp.text[:200]}")


# ── Users & KYC ───────────────────────────────────────────────────────────────

async def create_user(first_name: str, email: str, phone: str) -> dict:
    """Returns the user object. `bmoniUserId` — NOT `id` — is the path segment
    every subsequent /v1/users/{userId}/... call needs."""
    data = await _request("POST", "/v1/users", {
        "firstName": first_name,
        "email": email,
        "phoneNumber": phone,
    })
    return _unwrap(data, "user")


MAX_PAGE_SIZE = 100  # the API rejects anything larger


async def list_users(page: int = 1, limit: int = MAX_PAGE_SIZE) -> list:
    data = await _request("GET", "/v1/users",
                          params={"page": page, "limit": min(limit, MAX_PAGE_SIZE)})
    if isinstance(data, list):
        return data
    for key in ("users", "results", "items", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return []


async def find_user_by_email(email: str, max_pages: int = 20) -> dict | None:
    """Recover an existing user. Needed because create-user 409s on a duplicate
    email or phone, and Evident's synthetic contacts are deterministic — so a
    wiped database would otherwise be unable to re-adopt the wallets it made.

    Paginated because the sandbox key is shared and the roster is long; capped so
    a very long one can't spin forever.
    """
    target = email.strip().lower()
    for page in range(1, max_pages + 1):
        batch = await list_users(page=page)
        if not batch:
            return None
        for user in batch:
            if isinstance(user, dict) and str(user.get("email", "")).strip().lower() == target:
                return user
    return None


async def get_or_create_user(first_name: str, email: str, phone: str) -> dict:
    try:
        return await create_user(first_name, email, phone)
    except BmoniAPIError as exc:
        if "409" not in str(exc):
            raise
        existing = await find_user_by_email(email)
        if not existing:
            raise
        logger.info("Re-adopted existing BMoni user for %s", email)
        return existing


async def update_kyc(user_id: str, *, first_name: str, last_name: str, email: str,
                     phone: str, date_of_birth: str, bvn: str) -> dict:
    """Fields sit at the top level — the `profile` wrapper is invite-only.
    `state` must be a real Nigerian state; `postalCode` must be 6 digits."""
    return await _request("PATCH", f"/v1/users/{user_id}/kyc", {
        "personalInfo": {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "phoneNumber": phone,
            "dateOfBirth": date_of_birth,
            "nationality": "NG",
        },
        "address": {
            "streetLine1": "15 Admiralty Way",
            "city": "Lagos",
            "state": "Lagos",
            "postalCode": "101241",
            "countryCode": "NGA",
        },
        "identificationNumbers": [
            {"type": "bvn", "number": bvn, "issuingCountryCode": "NGA"},
        ],
    })


async def onboarding_status(user_id: str) -> dict:
    return await _request("GET", f"/v1/users/{user_id}/onboarding/status")


async def start_nigeria(user_id: str, bvn: str, wallet_address: str, wallet_index: int = 0) -> dict:
    """Activates the NGN rail. This is also what issues the deposit account —
    which is pooled across all users, so it cannot attribute a payer."""
    return await _request("POST", f"/v1/users/{user_id}/onboarding/start-nigeria", {
        "bvn": bvn,
        "ngnWalletAddress": wallet_address,
        "ngnWalletIndex": wallet_index,
    })


# ── Smart wallets ─────────────────────────────────────────────────────────────

async def owner_proof_challenge(user_id: str, owner_address: str,
                                currency: str = CURRENCY) -> dict:
    """Short-lived (10 min) EIP-191 message that must be signed by owner_address."""
    data = await _request(
        "POST", f"/v1/users/{user_id}/smart-wallets/owner-proof-challenges",
        {"currency": currency, "userOwnerAddress": owner_address},
    )
    return _unwrap(data, "challenge")


async def create_managed_wallet(user_id: str, owner_address: str, challenge_id: str,
                                signature: str, currency: str = CURRENCY) -> dict:
    """Deploys the wallet and registers the owner. Comes back already deployed
    (`pendingDeployUserOperation: null`), so there's no second signing round."""
    data = await _request("POST", f"/v1/users/{user_id}/smart-wallets/create-managed", {
        "currency": currency,
        "userOwnerAddress": owner_address,
        "ownerProofChallengeId": challenge_id,
        "ownerProofSignature": signature,
    })
    return _unwrap(data)


async def find_wallet(user_id: str, currency: str = CURRENCY) -> dict | None:
    """Locate an existing NGN wallet.

    Wallet creation 409s once a wallet exists for the currency, so re-adopting is
    the only way a wiped database can recover the wallets it already made. Note
    the currency goes in as CNGN but comes back as NGN — match either.
    """
    wanted = {currency.upper(), currency.upper().removeprefix("C"), "CNGN", "NGN"}
    try:
        listing = await account_wallets(user_id)
    except BmoniAPIError:
        listing = None

    rows = []
    if isinstance(listing, list):
        rows = listing
    elif isinstance(listing, dict):
        for key in ("wallets", "results", "items", "data"):
            if isinstance(listing.get(key), list):
                rows = listing[key]
                break

    fallback_address = None
    if not rows:
        balances = await account_balances(user_id)
        fallback_address = balances.get("smartAccountAddress")
        rows = balances.get("balances") or []

    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("currency", "")).upper() not in wanted:
            continue
        wallet_id = row.get("id") or row.get("smartWalletId")
        address = (row.get("walletAddress") or row.get("address")
                   or row.get("smartAccountAddress") or fallback_address)
        if wallet_id and address:
            return {"id": wallet_id, "walletAddress": address, "currency": row.get("currency")}
    return None


async def get_or_create_wallet(user_id: str, owner_address: str, challenge_id: str,
                               signature: str, currency: str = CURRENCY) -> dict:
    try:
        return await create_managed_wallet(user_id, owner_address, challenge_id,
                                           signature, currency)
    except BmoniAPIError as exc:
        if "409" not in str(exc):
            raise
        existing = await find_wallet(user_id, currency)
        if not existing:
            raise
        logger.info("Re-adopted existing BMoni wallet %s", existing["id"])
        return existing


async def account_balances(user_id: str) -> dict:
    data = await _request("GET", f"/v1/users/{user_id}/smart-wallets/account/balances")
    return _unwrap(data)


async def account_wallets(user_id: str) -> Any:
    return await _request("GET", f"/v1/users/{user_id}/smart-wallets/account/wallets")


async def wallet_transactions(user_id: str, wallet_id: str) -> list:
    """Credits into the collective wallet are how contributions are detected."""
    data = await _request(
        "GET", f"/v1/users/{user_id}/smart-wallets/{wallet_id}/transactions")
    if isinstance(data, list):
        return data
    inner = _unwrap(data, "transactions")
    for key in ("transactions", "results", "items", "data"):
        value = inner.get(key) if isinstance(inner, dict) else None
        if isinstance(value, list):
            return value
    return []


async def send_to_group(user_id: str, *, from_wallet_id: str, amount: str,
                        note: str | None = None) -> dict:
    """Send from a PERSONAL wallet into the sender's GROUP wallet.

    NOT USABLE from a partner-only integration, and worth understanding why:
    `create-managed` produces a *group* wallet (the challenge response even
    returns a `groupId`), but `fromWalletId` here must be a *personal* wallet —
    a different object, provisioned on-device by `bmoni_embedded_sdk`. This API
    exposes no way to create one, so a server cannot originate this transfer.

    Confirmed by probing: `{amount, fromWalletId}` passes validation, then 404s
    because a group-wallet id isn't a personal-wallet id. The endpoint also
    whitelists properties, so there is no recipient field to redirect it.

    Kept for the day members onboard through the BMoni app, at which point their
    personal wallet exists and this becomes the dues-payment call.
    """
    body = {"fromWalletId": from_wallet_id, "amount": amount}
    if note:
        body["note"] = note
    data = await _request("POST", f"/v1/users/{user_id}/smart-wallets/account/send", body)
    return _unwrap(data)


# ── Bank details & payouts ────────────────────────────────────────────────────

async def nigerian_banks(user_id: str) -> list:
    data = await _request("GET", f"/v1/users/{user_id}/bank-accounts/nigerian-banks")
    if isinstance(data, list):
        return data
    for key in ("banks", "results", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return []


async def verify_nigerian_account(user_id: str, account_number: str, bank_code: str) -> dict:
    """Returns the registered holder name. 404 means no such account — surface it
    and let the user fix the number rather than pushing on."""
    data = await _request(
        "POST", f"/v1/users/{user_id}/bank-accounts/verify-nigerian-account",
        {"accountNumber": account_number, "bankCode": bank_code},
    )
    return _unwrap(data)


async def register_withdrawal_account(user_id: str, *, account_number: str, bank_code: str,
                                      bank_name: str, account_holder_name: str) -> dict:
    """Get-or-create: calling again with the same account returns the existing
    record. The response `id` is the `bankAccountId` the offramp needs."""
    data = await _request(
        "POST", f"/v1/users/{user_id}/bank-accounts/withdrawal-accounts/nigeria",
        {
            "accountNumber": account_number,
            "bankCode": bank_code,
            "bankName": bank_name,
            "accountHolderName": account_holder_name,
        },
    )
    return _unwrap(data)


async def deposit_accounts(user_id: str, currency: str = "NGN") -> list:
    data = await _request(
        "GET", f"/v1/users/{user_id}/bank-accounts/deposit-accounts/{currency}")
    accounts = data.get("accounts") if isinstance(data, dict) else None
    return accounts if isinstance(accounts, list) else []


async def create_offramp(user_id: str, wallet_id: str, bank_account_id: str,
                         amount: str) -> dict:
    """Returns a PROPOSAL, not a completed payout — it still needs signing."""
    data = await _request(
        "POST", f"/v1/users/{user_id}/smart-wallets/{wallet_id}/offramp/nigeria",
        {"bankAccountId": bank_account_id, "fromAmount": amount},
    )
    return _unwrap(data)


async def proposal_sign_payload(user_id: str, proposal_id: str) -> Any:
    return await _request(
        "GET", f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign-payload")


async def sign_proposal(user_id: str, proposal_id: str, signature: str) -> dict:
    """BMoni appends its own KMS co-signature server-side, so this one signature
    is all Evident has to produce."""
    data = await _request(
        "POST", f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign",
        {"signature": signature},
    )
    return _unwrap(data)


async def get_proposal(user_id: str, proposal_id: str) -> dict:
    data = await _request(
        "GET", f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}")
    return _unwrap(data)


# ── Webhooks ──────────────────────────────────────────────────────────────────

DEPOSIT_EVENTS = ["wallet.deposit.completed", "wallet.deposit.failed", "wallet.deposit.refunded"]
WITHDRAWAL_EVENTS = ["wallet.withdrawal.completed", "wallet.withdrawal.failed",
                     "wallet.withdrawal.processing"]


async def register_webhook(callback_url: str, events: list[str] | None = None) -> dict:
    """Returns a real signing secret (`whsec_…`) — so unlike the previous
    provider, signature verification can actually be switched on."""
    data = await _request("POST", "/v1/webhooks/config", {
        "callbackUrl": callback_url,
        "events": events or DEPOSIT_EVENTS + WITHDRAWAL_EVENTS,
    })
    return _unwrap(data)


async def get_webhook_config() -> dict:
    return _unwrap(await _request("GET", "/v1/webhooks/config"))
