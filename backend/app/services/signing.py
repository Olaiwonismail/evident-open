"""Owner-key derivation and signing.

BMoni expects the wallet owner key to come from their Flutter / React Native SDK.
Evident is a web app, so it derives the key server-side instead. That works
because `create-managed` only ever receives an address and a signature and
validates by recovering the signer — it cannot tell what produced them. Verified
against the sandbox.

Keys are DERIVED, never stored: the same secret and reference always yield the
same key, so wallets survive a database reset with no key table to migrate.

The trade-off is real and worth naming: this makes Evident custodial, and
`settings.secret_key` becomes key material. Rotating it silently orphans every
wallet ever provisioned.
"""
import hashlib
import logging

from eth_account import Account
from eth_account.messages import encode_defunct

from app.config import settings

logger = logging.getLogger(__name__)


def owner_account(ref: str):
    """Deterministic EVM account for a collective or member reference."""
    seed = hashlib.sha256(f"{settings.secret_key}:{ref}".encode()).digest()
    return Account.from_key(seed)


def owner_address(ref: str) -> str:
    return owner_account(ref).address


def sign_text(ref: str, message: str) -> str:
    """EIP-191 personal_sign over the exact message, as create-managed requires."""
    account = owner_account(ref)
    signed = Account.sign_message(encode_defunct(text=message), private_key=account.key)
    signature = "0x" + signed.signature.hex().removeprefix("0x")

    # cheap self-check: catching a mismatch here beats a confusing 4xx from BMoni
    recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    if recovered.lower() != account.address.lower():
        raise RuntimeError(f"signature recovers to {recovered}, expected {account.address}")
    return signature


def sign_proposal_payload(ref: str, payload: dict | str) -> str:
    """Sign whatever `…/proposals/{id}/sign-payload` hands back.

    Its exact shape is undocumented and hasn't been observed yet, so this handles
    the three plausible forms rather than guessing one: a raw 32-byte hash, an
    EIP-712 typed-data object, or a plain string to personal_sign.
    """
    account = owner_account(ref)

    if isinstance(payload, dict):
        # unwrap a transport envelope if there is one
        for key in ("data", "payload", "signPayload", "typedData"):
            inner = payload.get(key)
            if isinstance(inner, (dict, str)):
                payload = inner
                break

    if isinstance(payload, dict):
        if "types" in payload and "message" in payload:
            from eth_account.messages import encode_typed_data

            signed = Account.sign_message(encode_typed_data(full_message=payload),
                                          private_key=account.key)
            return "0x" + signed.signature.hex().removeprefix("0x")
        for key in ("hash", "userOpHash", "safeTxHash", "messageHash", "digest"):
            if payload.get(key):
                payload = payload[key]
                break

    if not isinstance(payload, str):
        raise RuntimeError(f"unrecognised sign-payload shape: {type(payload).__name__}")

    text = payload
    if text.startswith("0x") and len(text) == 66:  # 32-byte hash
        signed = Account.unsafe_sign_hash(bytes.fromhex(text[2:]), private_key=account.key)
        return "0x" + signed.signature.hex().removeprefix("0x")

    signed = Account.sign_message(encode_defunct(text=text), private_key=account.key)
    return "0x" + signed.signature.hex().removeprefix("0x")
