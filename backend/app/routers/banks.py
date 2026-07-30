"""Bank list and recipient verification.

BMoni scopes both under `/v1/users/{userId}/...`, so a call needs a provisioned
user to ask as. The destination account is what's being checked, not the caller,
so any provisioned collective gives the same answer — `_any_provisioned_user()`
just finds one.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.collective import Collective
from app.services import payments
from app.services.bmoni_client import BmoniAPIError
from app.services.payments import PaymentProviderNotConfigured

router = APIRouter(prefix="/banks", tags=["banks"])

_banks_cache: list = []


async def _any_provisioned_user(db: AsyncSession) -> str:
    result = await db.execute(
        select(Collective.bmoni_user_id).where(Collective.bmoni_user_id.isnot(None)).limit(1)
    )
    user_id = result.scalar_one_or_none()
    if not user_id:
        raise HTTPException(
            status_code=503,
            detail="No provisioned collective yet — create one before looking up banks",
        )
    return user_id


@router.get("")
async def list_banks(db: AsyncSession = Depends(get_db)):
    global _banks_cache
    if _banks_cache:
        return _banks_cache
    user_id = await _any_provisioned_user(db)
    try:
        _banks_cache = await payments.fetch_banks(user_id)
    except PaymentProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BmoniAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _banks_cache


@router.post("/lookup")
async def lookup_account(account_number: str, bank_code: str,
                         db: AsyncSession = Depends(get_db)):
    user_id = await _any_provisioned_user(db)
    try:
        return await payments.lookup_bank_account(account_number, bank_code, user_id=user_id)
    except PaymentProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except BmoniAPIError as exc:
        # a 404 from BMoni means no such account — let the form show it plainly
        raise HTTPException(
            status_code=400,
            detail=f"Could not verify that account — check the account number and bank. ({exc})",
        )
