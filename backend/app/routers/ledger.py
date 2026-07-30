from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal
from app.database import get_db
from app.models.ledger import LedgerEntry
from app.models.collective import Collective
from app.models.contribution import Contribution
from app.models.member import Member
from app.models.unmatched import UnmatchedTransfer

router = APIRouter(prefix="/collectives", tags=["ledger"])


class ResolveUnmatchedRequest(BaseModel):
    member_id: str


@router.get("/{collective_id}/ledger")
async def get_ledger(collective_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = result.scalar_one_or_none()
    if not collective:
        raise HTTPException(status_code=404, detail="Collective not found")

    entries_result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
    )
    entries = entries_result.scalars().all()

    balance_result = await db.execute(
        select(LedgerEntry.balance_after)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
        .limit(1)
    )
    balance = balance_result.scalar_one_or_none() or Decimal("0")

    return {
        "collective_id": collective_id,
        "name": collective.name,
        "bank_account_number": collective.bank_account_number,
        "bank_name": collective.bank_name,
        "balance": float(balance),
        "entries": [
            {
                "id": e.id,
                "type": e.type,
                "amount": float(e.amount),
                "balance_after": float(e.balance_after),
                "description": e.description,
                "actor_name": e.actor_name,
                "timestamp": e.timestamp.isoformat(),
                # expense entries reference the expense — lets the UI link to its detail page
                "expense_id": e.ref_id if e.type.startswith("expense") else None,
            }
            for e in entries
        ],
    }


@router.get("/{collective_id}/unmatched")
async def list_unmatched(collective_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UnmatchedTransfer)
        .where(UnmatchedTransfer.collective_id == collective_id)
        .order_by(UnmatchedTransfer.timestamp.desc())
    )
    transfers = result.scalars().all()
    return [
        {
            "id": t.id,
            "amount": float(t.amount),
            "sender_name": t.sender_name,
            "sender_account": t.sender_account,
            "status": t.status,
            "timestamp": t.timestamp.isoformat(),
        }
        for t in transfers
    ]


@router.post("/{collective_id}/unmatched/{unmatched_id}/resolve")
async def resolve_unmatched(
    collective_id: str,
    unmatched_id: str,
    body: ResolveUnmatchedRequest,
    db: AsyncSession = Depends(get_db),
):
    """Attribute an unmatched transfer to a member: the money finally enters the
    ledger as that member's contribution, so nothing is quietly absorbed."""
    result = await db.execute(
        select(UnmatchedTransfer).where(
            UnmatchedTransfer.id == unmatched_id,
            UnmatchedTransfer.collective_id == collective_id,
        )
    )
    unmatched = result.scalar_one_or_none()
    if not unmatched or unmatched.status != "needs_review":
        raise HTTPException(status_code=404, detail="Transfer not found or already resolved")

    member_result = await db.execute(
        select(Member).where(Member.id == body.member_id, Member.collective_id == collective_id)
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    collective_result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = collective_result.scalar_one_or_none()

    amount = Decimal(str(unmatched.amount))
    expected = Decimal(str(collective.dues_amount)) if collective.dues_amount else None
    if expected is None or amount == expected:
        status = "exact"
    elif amount < expected:
        status = "partial"
    else:
        status = "excess"

    contribution = Contribution(
        collective_id=collective_id,
        member_id=member.id,
        amount=amount,
        expected_amount=expected,
        status=status,
        source_transfer_id=unmatched.source_transfer_id,
        sender_name=unmatched.sender_name,
        sender_account=unmatched.sender_account,
    )
    db.add(contribution)
    await db.flush()

    balance_result = await db.execute(
        select(LedgerEntry.balance_after)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
        .limit(1)
    )
    balance = balance_result.scalar_one_or_none() or Decimal("0")
    db.add(LedgerEntry(
        collective_id=collective_id,
        type="contribution",
        ref_id=contribution.id,
        amount=amount,
        balance_after=balance + amount,
        description=f"{member.name} paid ₦{amount:,.2f} (attributed from {unmatched.sender_name or 'unknown sender'})",
        actor_name=member.name,
    ))

    unmatched.status = "resolved"
    unmatched.resolved_by = member.id
    await db.commit()
    return {
        "id": contribution.id,
        "member_id": member.id,
        "amount": float(amount),
        "status": status,
    }


@router.get("/{collective_id}/members/{member_id}/contributions")
async def get_member_contributions(collective_id: str, member_id: str, db: AsyncSession = Depends(get_db)):
    member_result = await db.execute(select(Member).where(Member.id == member_id))
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    collective_result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = collective_result.scalar_one_or_none()

    contribs_result = await db.execute(
        select(Contribution)
        .where(Contribution.collective_id == collective_id, Contribution.member_id == member_id)
        .order_by(Contribution.timestamp.desc())
    )
    contribs = contribs_result.scalars().all()

    total_paid = sum(Decimal(str(c.amount)) for c in contribs)

    return {
        "member": {"id": member.id, "name": member.name},
        "dues_amount": float(collective.dues_amount) if collective.dues_amount else None,
        "dues_frequency": collective.dues_frequency,
        "total_paid": float(total_paid),
        "contributions": [
            {
                "id": c.id,
                "amount": float(c.amount),
                "expected_amount": float(c.expected_amount) if c.expected_amount else None,
                "status": c.status,
                "timestamp": c.timestamp.isoformat(),
            }
            for c in contribs
        ],
    }
