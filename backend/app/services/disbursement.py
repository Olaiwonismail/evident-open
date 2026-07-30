import json
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.expense import Expense
from app.models.ledger import LedgerEntry
from app.models.member import Member
from app.models.collective import Collective
from app.services import payments

logger = logging.getLogger(__name__)


async def _current_balance(collective_id: str, db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.collective_id == collective_id)
        .order_by(LedgerEntry.timestamp.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return Decimal(str(last.balance_after)) if last else Decimal("0")


async def _reverse_expense_debit(expense: Expense, db: AsyncSession, entry_type: str = "expense_failed") -> None:
    """Append a credit entry cancelling the debit written before the transfer attempt.

    The ledger is append-only, so a failed disbursement is corrected by a new
    reversing entry rather than deleting the original debit.
    """
    current_balance = await _current_balance(expense.collective_id, db)
    amount = Decimal(str(expense.amount))
    db.add(LedgerEntry(
        collective_id=expense.collective_id,
        type=entry_type,
        ref_id=expense.id,
        amount=amount,
        balance_after=current_balance + amount,
        description=f"Reversal — transfer for '{expense.reason[:60]}' did not complete",
        actor_name="system",
    ))


async def disburse_expense(expense_id: str, approver_id: str, db: AsyncSession) -> Expense:
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense or expense.status != "pending":
        raise ValueError("Expense not found or not in pending state")

    approver_result = await db.execute(select(Member).where(Member.id == approver_id))
    approver = approver_result.scalar_one_or_none()
    if not approver or approver.role not in ("committee", "organizer"):
        raise PermissionError("Only committee members can approve expenses")

    collective_result = await db.execute(select(Collective).where(Collective.id == expense.collective_id))
    collective = collective_result.scalar_one_or_none()

    current_balance = await _current_balance(expense.collective_id, db)
    if Decimal(str(expense.amount)) > current_balance:
        raise ValueError("Insufficient collective balance")

    # BMoni has no client-supplied idempotency key (the previous provider's
    # merchantTxRef), so this guard IS the double-payout protection: an expense
    # that already produced a payout reference is never sent again.
    if expense.transfer_ref:
        raise ValueError(f"Expense already has payout {expense.transfer_ref}")

    expense.status = "disbursing"
    expense.approved_by = approver_id
    await db.flush()

    narration = f"{collective.name} — {expense.reason[:50]}"

    # write ledger entry BEFORE the transfer call so intent is always recorded
    new_balance = current_balance - Decimal(str(expense.amount))

    # Publish the AI's verdict beside the human decision. The ledger is
    # append-only and public, so "flagged, approved anyway by X" becomes part of
    # the permanent record — the model is held to the same transparency rule as
    # the committee rather than being an invisible advisor.
    actor = approver.name
    if expense.ai_status == "flagged" and expense.ai_flags:
        try:
            flags = json.loads(expense.ai_flags)
            headline = next((f for f in flags if f.get("severity") == "high"), flags[0])
            actor = f"{approver.name} — approved despite AI flag: {headline['message'][:120]}"
        except (ValueError, KeyError, IndexError):
            actor = f"{approver.name} — approved despite AI flag"

    ledger_entry = LedgerEntry(
        collective_id=expense.collective_id,
        type="expense",
        ref_id=expense.id,
        amount=-Decimal(str(expense.amount)),
        balance_after=new_balance,
        description=f"Expense: {expense.reason[:80]}",
        actor_name=actor,
    )
    db.add(ledger_entry)
    await db.commit()

    try:
        transfer_result = await payments.transfer_to_bank(
            amount_naira=float(expense.amount),
            account_number=expense.recipient_account,
            account_name=expense.recipient_name,
            bank_code=expense.recipient_bank_code,
            expense_id=expense.id,
            narration=narration,
            sender_name=collective.name,
            collective=collective,
        )
    except Exception as exc:
        # the debit was already committed, so reverse it before re-raising —
        # append-only means a new credit entry, never deleting the original.
        logger.error("Transfer call failed for expense %s: %s", expense_id, exc)
        expense.status = "failed"
        await _reverse_expense_debit(expense, db)
        await db.commit()
        raise

    transfer_status = transfer_result.get("status", "PENDING")
    expense.transfer_ref = transfer_result.get("id")

    if transfer_status == "SUCCESS":
        expense.status = "paid"
    elif transfer_status in ("FAILED", "REFUND"):
        expense.status = "failed"
        await _reverse_expense_debit(
            expense, db,
            entry_type="expense_refunded" if transfer_status == "REFUND" else "expense_failed",
        )
    else:
        # Nomba's requery poller lived here (10 attempts, 30s apart) and died with
        # the integration. It was in-memory only, so a restart stranded the expense
        # in `disbursing` — worth replacing with something durable.
        expense.status = "disbursing"

    await db.commit()
    return expense
