"""BMoni sandbox probe: full NGN provisioning sequence, driven entirely server-side.

Proven by this script (2026-07-30, sandbox):
  * Wallet creation works WITHOUT their Flutter / React Native SDK. The API only
    receives an address plus an EIP-191 signature and recovers the signer, so a
    server-derived key is indistinguishable from an on-device one.
  * `bmoniUserId` — not the proxy's own `id` — is the path segment for every
    subsequent /v1/users/{userId}/... call.
  * The NGN deposit account is POOLED (`pooled-vba-1`, "Bkey Limited"). Every
    user sees the same account number, so per-member pay-in accounts — the Nomba
    behaviour Evident's attribution relied on — do not exist here. Contributions
    have to be attributed by smart-wallet address instead.

Run:  python test_bmoni_wallet.py

Env (backend/.env or inline):
  BMONI_BASE_URL=https://embedded-dev.bmoni.com
  BMONI_API_KEY=<sandbox key>      # never commit this
"""
import asyncio
import hashlib
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_URL = os.getenv("BMONI_BASE_URL", "https://embedded-dev.bmoni.com").rstrip("/")
API_KEY = os.getenv("BMONI_API_KEY", "")
CURRENCY = "CNGN"       # their guide is explicit: CNGN, never NGN, for wallet currency
TEST_BVN = "22222222222"  # sandbox only — real BVNs are rejected here


def owner_key(user_ref: str):
    """Derive the owner key deterministically from a secret + user ref: survives a
    sandbox reset, needs no key table. Use settings.secret_key in app code."""
    secret = os.getenv("SECRET_KEY", "evident-local-dev-secret")
    seed = hashlib.sha256(f"{secret}:{user_ref}".encode()).digest()
    return Account.from_key(seed)


def sign_challenge(acct, message: str) -> str:
    """EIP-191 personal_sign over the exact challenge string — what their SDK does."""
    signed = Account.sign_message(encode_defunct(text=message), private_key=acct.key)
    return "0x" + signed.signature.hex().removeprefix("0x")


async def call(client: httpx.AsyncClient, method: str, path: str, body: dict = None,
               label: str = "", allow_fail: bool = False) -> dict:
    resp = await client.request(method, f"{BASE_URL}{path}", json=body)
    print(f"  {method} {path} -> {resp.status_code}   {label}")
    text = resp.text
    try:
        data = resp.json()
        print("  ", json.dumps(data, indent=2)[:1200])
    except Exception:
        print("  raw:", text[:400])
        data = {}
    if resp.status_code >= 400 and not allow_fail:
        raise SystemExit(f"failed at {path}")
    return data


async def main() -> None:
    if not API_KEY:
        raise SystemExit("Set BMONI_API_KEY (env or backend/.env) first")

    stamp = int(time.time())
    email = f"evident+{stamp}@example.com"    # must be unique per test user
    phone = f"+23480{stamp % 100000000:08d}"  # unique too — and the handle BMoni
                                              # matches when crediting test funds
    acct = owner_key(email)
    print(f"BMoni {BASE_URL}")
    print(f"owner address {acct.address}  (derived locally, no SDK)\n")

    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:

        print("1. create user")
        user = await call(client, "POST", "/v1/users", {
            "firstName": "Evident",
            "email": email,
            "phoneNumber": phone,
        })
        user_id = user.get("user", {}).get("bmoniUserId")
        if not user_id:
            raise SystemExit("no bmoniUserId — read the JSON above")
        print(f"  bmoniUserId = {user_id}\n")

        print("2. complete the KYC profile  <-- gates provider provisioning")
        await call(client, "PATCH", f"/v1/users/{user_id}/kyc", {
            "personalInfo": {
                "firstName": "Evident",
                "lastName": "Tester",
                "email": email,
                "phoneNumber": phone,
                "dateOfBirth": "1995-06-15",
                "gender": "male",
                "placeOfBirth": "Lagos",
                "nationality": "NG",
            },
            "address": {
                "streetLine1": "15 Admiralty Way",
                "city": "Lagos",
                "state": "Lagos",       # must be a real Nigerian state
                "postalCode": "101241",  # 6 digits
                "countryCode": "NGA",
            },
            "identificationNumbers": [
                {"type": "bvn", "number": TEST_BVN, "issuingCountryCode": "NGA"},
            ],
        }, allow_fail=True)

        print("\n3. readiness check")
        await call(client, "GET", f"/v1/users/{user_id}/kyc/readiness", allow_fail=True)

        print("\n4. owner-proof challenge")
        ch = await call(
            client, "POST", f"/v1/users/{user_id}/smart-wallets/owner-proof-challenges",
            {"currency": CURRENCY, "userOwnerAddress": acct.address},
        )
        challenge_id, message = ch.get("challengeId"), ch.get("message")
        if not (challenge_id and message):
            raise SystemExit("no challengeId / message — read the JSON above")

        print("\n5. sign locally (EIP-191, no SDK)")
        signature = sign_challenge(acct, message)
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
        assert recovered.lower() == acct.address.lower(), "local recovery mismatch"
        print(f"  signature recovers to {recovered} OK")

        print("\n6. create the managed smart wallet")
        wallet = await call(client, "POST", f"/v1/users/{user_id}/smart-wallets/create-managed", {
            "currency": CURRENCY,
            "userOwnerAddress": acct.address,
            "ownerProofChallengeId": challenge_id,
            "ownerProofSignature": signature,
        })
        wallet_id = wallet.get("id")
        wallet_addr = wallet.get("walletAddress")

        print("\n7. activate the naira rail")
        await call(client, "POST", f"/v1/users/{user_id}/onboarding/start-nigeria", {
            "bvn": TEST_BVN,
            "ngnWalletAddress": wallet_addr,
            "ngnWalletIndex": 0,
        }, allow_fail=True)

        print("\n8. onboarding status  <-- watching for anchorStatus to leave not_started")
        await call(client, "GET", f"/v1/users/{user_id}/onboarding/status", allow_fail=True)

        print("\n9. naira deposit account")
        await call(client, "GET", f"/v1/users/{user_id}/bank-accounts/deposit-accounts/NGN",
                   allow_fail=True)

        print("\n10. balances")
        await call(client, "GET", f"/v1/users/{user_id}/smart-wallets/account/balances",
                   allow_fail=True)

        print("\n" + "=" * 64)
        print(f"bmoniUserId   : {user_id}")
        print(f"smartWalletId : {wallet_id}")
        print(f"walletAddress : {wallet_addr}")
        print(f"owner address : {acct.address}  (re-derivable from SECRET_KEY + {email})")
        print(f"\nfor test funds, give BMoni this phone number: {phone}")
        print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
