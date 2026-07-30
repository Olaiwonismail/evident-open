"""Recording money that arrives for a collective.

Provider-neutral on purpose. This used to be `webhook.py` and was written around
Nomba's `payment_success` payload — HMAC verification, and a scattergun match
across every account identifier the payload might carry. All of that went with
Nomba. What's left is the part that was never provider-specific: decide who paid,
classify the amount against the dues, and append to the ledger exactly once.

Whatever provider comes next parses its own payload and calls `record_payment()`.
"""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collective import Collective
from app.models.contribution import Contribution
from app.models.ledger import LedgerEntry
from app.models.member import Member
from app.models.unmatched import UnmatchedTransfer

logger = logging.getLogger(__name__)


async def current_balance(collective_id: str, db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return Decimal(str(last.balance_after)) if last else Decimal("0")


async def already_recorded(source_transfer_id: str, db: AsyncSession) -> bool:
    """Idempotency: a payment counts once, whether it landed as a contribution or
    got queued for review. Retries and replays must never double-count money."""
    contribution = (await db.execute(
        select(Contribution.id).where(Contribution.source_transfer_id == source_transfer_id)
    )).scalar_one_or_none()
    unmatched = (await db.execute(
        select(UnmatchedTransfer.id).where(UnmatchedTransfer.source_transfer_id == source_transfer_id)
    )).scalar_one_or_none()
    return bool(contribution or unmatched)


def classify(amount: Decimal, expected: Decimal | None) -> str:
    """Under/over-payment is preserved, never adjusted away."""
    if expected is None or amount == expected:
        return "exact"
    return "partial" if amount < expected else "excess"


async def record_payment(
    *,
    collective: Collective,
    member: Member | None,
    amount: Decimal,
    source_transfer_id: str,
    sender_name: str = "",
    sender_account: str = "",
    db: AsyncSession,
) -> Contribution | None:
    """Credit a payment to the ledger, or queue it for review if unattributed.

    Returns the Contribution, or None when the payment went to the review queue
    or was a duplicate.
    """
    if await already_recorded(source_transfer_id, db):
        logger.info("Duplicate payment %s — skipping", source_transfer_id)
        return None

    if member is None:
        db.add(UnmatchedTransfer(
            collective_id=collective.id,
            source_transfer_id=source_transfer_id,
            amount=amount,
            sender_name=sender_name,
            sender_account=sender_account,
        ))
        await db.commit()
        logger.info("Unmatched payment %s queued for review", source_transfer_id)
        return None

    expected = Decimal(str(collective.dues_amount)) if collective.dues_amount else None
    status = classify(amount, expected)

    contribution = Contribution(
        collective_id=collective.id,
        member_id=member.id,
        amount=amount,
        expected_amount=expected,
        status=status,
        source_transfer_id=source_transfer_id,
        sender_name=sender_name,
        sender_account=sender_account,
    )
    db.add(contribution)
    await db.flush()

    new_balance = await current_balance(collective.id, db) + amount

    description = f"{member.name} paid ₦{amount:,.2f}"
    if status == "partial":
        description += f" (partial — ₦{expected - amount:,.2f} still owed)"
    elif status == "excess":
        description += f" (₦{amount - expected:,.2f} credited to next period)"

    db.add(LedgerEntry(
        collective_id=collective.id,
        type="contribution",
        ref_id=contribution.id,
        amount=amount,
        balance_after=new_balance,
        description=description,
        actor_name=member.name,
    ))
    await db.commit()
    logger.info("Contribution logged: %s ₦%s status=%s", source_transfer_id, amount, status)
    return contribution
