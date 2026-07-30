import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.expense import Expense
from app.models.collective import Collective
from app.models.member import Member
from app.models.ledger import LedgerEntry
from app.services import auth, payments, disbursement
from app.services.payments import PaymentProviderNotConfigured

router = APIRouter(prefix="/collectives", tags=["expenses"])


class SubmitExpenseRequest(BaseModel):
    # `requested_by` is deliberately absent: the requester is taken from the
    # caller's token, so nobody can file an expense in someone else's name.
    amount: float
    reason: str
    receipt_url: str | None = None
    recipient_account: str
    recipient_bank_code: str
    # carried over from POST /receipts so the verification result is stored with
    # the expense and can be published on the ledger next to the human decision
    receipt_sha256: str | None = None
    receipt_fingerprint: str | None = None
    ai_status: str | None = None
    ai_extraction: dict | None = None
    ai_flags: list[dict] | None = None


class RejectExpenseRequest(BaseModel):
    # Likewise no `approver_id` — the decider is whoever holds the token, never
    # whoever the request body claims.
    reason: str


async def _member_names(collective_id: str, db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Member).where(Member.collective_id == collective_id))
    return {m.id: m.name for m in result.scalars().all()}


def _serialize_expense(e: Expense, names: dict[str, str]) -> dict:
    decided = e.status not in ("pending",)
    return {
        "id": e.id,
        "amount": float(e.amount),
        "reason": e.reason,
        "receipt_url": e.receipt_url,
        "status": e.status,
        "requested_by": e.requested_by,
        "requested_by_name": names.get(e.requested_by),
        "recipient_name": e.recipient_name,
        "recipient_account": e.recipient_account,
        "recipient_bank_code": e.recipient_bank_code,
        "timestamp": e.timestamp.isoformat(),
        "decided_by": e.approved_by,
        "decided_by_name": names.get(e.approved_by),
        "decided_at": e.updated_at.isoformat() if decided and e.updated_at else None,
        "decision_reason": e.rejection_reason,
        "paid_at": e.updated_at.isoformat() if e.status == "paid" and e.updated_at else None,
        "ai_status": e.ai_status,
        "ai_flags": json.loads(e.ai_flags) if e.ai_flags else [],
        "ai_extraction": json.loads(e.ai_extraction) if e.ai_extraction else None,
    }


@router.post("/{collective_id}/expenses")
async def submit_expense(
    collective_id: str,
    body: SubmitExpenseRequest,
    db: AsyncSession = Depends(get_db),
    me: Member = Depends(auth.current_member),
):
    auth.require_collective(me, collective_id)
    result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = result.scalar_one_or_none()
    if not collective:
        raise HTTPException(status_code=404, detail="Collective not found")
    if not collective.bmoni_user_id:
        raise HTTPException(
            status_code=503,
            detail="This collective has no provisioned wallet yet — cannot verify a recipient",
        )

    # validate recipient account before saving — the name shown on the expense is
    # the provider's answer, never user input
    try:
        lookup = await payments.lookup_bank_account(
            body.recipient_account, body.recipient_bank_code,
            user_id=collective.bmoni_user_id,
        )
        recipient_name = lookup.get("accountName")
        if not recipient_name:
            raise HTTPException(status_code=422, detail="Could not verify recipient account")
    except HTTPException:
        raise
    except PaymentProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bank account lookup failed: {exc}")

    expense = Expense(
        collective_id=collective_id,
        requested_by=me.id,
        amount=body.amount,
        reason=body.reason,
        receipt_url=body.receipt_url,
        recipient_account=body.recipient_account,
        recipient_name=recipient_name,
        recipient_bank_code=body.recipient_bank_code,
        receipt_sha256=body.receipt_sha256,
        receipt_fingerprint=body.receipt_fingerprint,
        # advisory only — a flagged expense submits exactly like a clean one
        ai_status=body.ai_status or "none",
        ai_extraction=json.dumps(body.ai_extraction) if body.ai_extraction else None,
        ai_flags=json.dumps(body.ai_flags) if body.ai_flags else None,
    )
    db.add(expense)
    await db.commit()
    names = await _member_names(collective_id, db)
    return _serialize_expense(expense, names)


@router.get("/{collective_id}/expenses")
async def list_expenses(collective_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Expense)
        .where(Expense.collective_id == collective_id)
        .order_by(Expense.timestamp.desc())
    )
    expenses = result.scalars().all()
    names = await _member_names(collective_id, db)
    return [_serialize_expense(e, names) for e in expenses]


@router.get("/{collective_id}/expenses/{expense_id}")
async def get_expense(collective_id: str, expense_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.collective_id == collective_id)
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    names = await _member_names(collective_id, db)
    return _serialize_expense(expense, names)


@router.post("/{collective_id}/expenses/{expense_id}/approve")
async def approve_expense(
    collective_id: str,
    expense_id: str,
    db: AsyncSession = Depends(get_db),
    me: Member = Depends(auth.current_member),
):
    auth.require_committee(auth.require_collective(me, collective_id))
    try:
        expense = await disbursement.disburse_expense(expense_id, me.id, db)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaymentProviderNotConfigured as exc:
        # disburse_expense has already reversed the ledger debit and marked the
        # expense failed, so the balance stays honest even with no provider wired.
        raise HTTPException(status_code=503, detail=str(exc))
    return {"id": expense.id, "status": expense.status}


@router.post("/{collective_id}/expenses/{expense_id}/reject")
async def reject_expense(
    collective_id: str,
    expense_id: str,
    body: RejectExpenseRequest,
    db: AsyncSession = Depends(get_db),
    me: Member = Depends(auth.current_member),
):
    approver = auth.require_committee(auth.require_collective(me, collective_id))
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.collective_id == collective_id)
    )
    expense = result.scalar_one_or_none()
    if not expense or expense.status != "pending":
        raise HTTPException(status_code=404, detail="Expense not found or not pending")
    if expense.requested_by == approver.id:
        raise HTTPException(
            status_code=403, detail="You cannot decide on your own request"
        )

    expense.status = "rejected"
    expense.approved_by = approver.id
    expense.rejection_reason = body.reason

    # zero-amount marker so the rejection stays visible on the public ledger
    balance_result = await db.execute(
        select(LedgerEntry.balance_after)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
        .limit(1)
    )
    balance = balance_result.scalar_one_or_none() or Decimal("0")
    db.add(LedgerEntry(
        collective_id=collective_id,
        type="expense_rejected",
        ref_id=expense.id,
        amount=Decimal("0"),
        balance_after=balance,
        description=f"Rejected: {expense.reason[:80]}",
        actor_name=f'rejected by {approver.name} — "{body.reason[:120]}"',
    ))

    await db.commit()
    return {"id": expense.id, "status": "rejected", "reason": body.reason}
