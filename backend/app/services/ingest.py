"""Detecting money arriving in a collective's treasury wallet.

With the previous provider, each member had their own NUBAN and an incoming
transfer identified its payer by the account it landed in. BMoni's naira deposit
account is pooled across every user, so that signal is gone.

What replaces it: each member has their own smart wallet, and a wallet-to-wallet
transfer carries the sender's address. That address maps to exactly one member,
so attribution is just as unambiguous — the identifier changed, not the guarantee.

Ingestion polls rather than waits for webhooks, because the webhook payload shape
is undocumented and unverified. `routers/webhooks.py` accepts deliveries too and
funnels them through the same `record_payment`, so switching over later is a
matter of trusting the webhook, not rewriting the logic.
"""
import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collective import Collective
from app.models.member import Member
from app.services import bmoni_client, contributions

logger = logging.getLogger(__name__)

# Response field names vary by endpoint and aren't fully documented, so read
# each value from any of the plausible keys rather than betting on one.
_ID_KEYS = ("id", "transactionId", "reference", "txHash", "hash")
_AMOUNT_KEYS = ("amount", "value", "transactionAmount")
_SENDER_KEYS = ("from", "fromAddress", "sender", "senderAddress", "counterpartyAddress")
_DIRECTION_KEYS = ("direction", "entryType", "type")


def _first(row: dict, keys) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _is_credit(row: dict) -> bool:
    """Only money coming IN. Absent direction is treated as a credit, since the
    caller already filtered to the collective's own wallet."""
    marker = _first(row, _DIRECTION_KEYS)
    if marker is None:
        return True
    return str(marker).upper() in ("CREDIT", "IN", "INBOUND", "RECEIVE", "DEPOSIT")


def _to_decimal(value) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount > 0 else None


async def _members_by_wallet(collective_id: str, db: AsyncSession) -> dict[str, Member]:
    result = await db.execute(select(Member).where(Member.collective_id == collective_id))
    return {
        m.wallet_address.lower(): m
        for m in result.scalars().all()
        if m.wallet_address
    }


async def sync_collective(collective: Collective, db: AsyncSession) -> int:
    """Record any wallet credits not already on the ledger. Returns how many."""
    if not (collective.bmoni_user_id and collective.smart_wallet_id):
        return 0

    try:
        rows = await bmoni_client.wallet_transactions(
            collective.bmoni_user_id, collective.smart_wallet_id)
    except Exception as exc:
        logger.error("Wallet transaction fetch failed for %s: %s", collective.id, exc)
        return 0

    by_wallet = await _members_by_wallet(collective.id, db)
    recorded = 0

    for row in rows:
        if not isinstance(row, dict) or not _is_credit(row):
            continue
        source_id = _first(row, _ID_KEYS)
        amount = _to_decimal(_first(row, _AMOUNT_KEYS))
        if not source_id or amount is None:
            continue
        if await contributions.already_recorded(str(source_id), db):
            continue

        sender = _first(row, _SENDER_KEYS) or ""
        member = by_wallet.get(str(sender).lower())
        if member and member.id == collective.created_by and str(sender).lower() == \
                (collective.wallet_address or "").lower():
            continue  # the treasury paying itself isn't a contribution

        result = await contributions.record_payment(
            collective=collective,
            member=member,
            amount=amount,
            source_transfer_id=str(source_id),
            sender_name=member.name if member else str(sender)[:42],
            sender_account=str(sender),
            db=db,
        )
        if result is not None or member is None:
            recorded += 1
    if recorded:
        logger.info("Ingest: recorded %d payment(s) for %s", recorded, collective.name)
    return recorded


async def sync_all(db: AsyncSession) -> int:
    total = 0
    for collective in (await db.execute(select(Collective))).scalars().all():
        total += await sync_collective(collective, db)
    return total
