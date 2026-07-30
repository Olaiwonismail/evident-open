import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.collective import Collective
from app.models.member import Member
from app.services import provisioning
from app.services.payments import PaymentProviderNotConfigured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collectives", tags=["collectives"])


async def _provision_member_account(member: Member, collective_name: str) -> None:
    """Give a member their own smart wallet. Raises on failure so the caller can
    decide whether to surface it — never swallow, or members silently go
    un-provisioned and their contributions can't be attributed."""
    await provisioning.provision_entity(member, f"{member.name} {collective_name}")


class CreateCollectiveRequest(BaseModel):
    name: str
    purpose: str
    dues_amount: float | None = None
    dues_frequency: str | None = None
    organizer_name: str
    organizer_email: str | None = None
    organizer_phone: str | None = None


class InviteMemberRequest(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    role: str = "member"


class SetRoleRequest(BaseModel):
    role: str


@router.post("")
async def create_collective(body: CreateCollectiveRequest, db: AsyncSession = Depends(get_db)):
    import uuid
    collective_id = str(uuid.uuid4())

    # Create organizer member first
    organizer = Member(
        id=str(uuid.uuid4()),
        collective_id=collective_id,
        name=body.organizer_name,
        email=body.organizer_email,
        phone=body.organizer_phone,
        role="organizer",
    )

    collective = Collective(
        id=collective_id,
        name=body.name,
        purpose=body.purpose,
        dues_amount=body.dues_amount,
        dues_frequency=body.dues_frequency,
        created_by=organizer.id,
    )
    db.add(collective)
    db.add(organizer)
    await db.flush()

    # provision the treasury wallet — a collective with nowhere to hold money is
    # useless, so failure rolls the whole creation back
    try:
        await provisioning.provision_entity(collective, body.name)
        if not collective.smart_wallet_id:
            raise ValueError("provisioning returned no wallet")
    except PaymentProviderNotConfigured as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Wallet provisioning failed: {exc}")

    # the organizer is also a member who pays dues — give them their own account.
    # best-effort: the collective's own account already exists, so don't fail the
    # whole creation if this one call hiccups — but log loudly so it's never silent.
    try:
        await _provision_member_account(organizer, collective.name)
    except Exception:
        logger.error("Organizer VA provisioning failed for %s", organizer.id, exc_info=True)

    await db.commit()
    return {
        "id": collective.id,
        "name": collective.name,
        "bank_account_number": collective.bank_account_number,
        "bank_name": collective.bank_name,
        # the pay-in identity that actually attributes a payment — the bank
        # account above is pooled across every user and can't identify a payer
        "wallet_address": collective.wallet_address,
        "organizer_id": organizer.id,
    }


@router.get("/{collective_id}")
async def get_collective(collective_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = result.scalar_one_or_none()
    if not collective:
        raise HTTPException(status_code=404, detail="Collective not found")
    # the NUBAN backfill that lived here worked around Nomba create responses that
    # omitted the account number; it went with the integration.
    return collective


@router.post("/{collective_id}/members")
async def invite_member(collective_id: str, body: InviteMemberRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Collective).where(Collective.id == collective_id))
    collective = result.scalar_one_or_none()
    if not collective:
        raise HTTPException(status_code=404, detail="Collective not found")

    member = Member(
        collective_id=collective_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        role=body.role,
    )
    db.add(member)
    await db.flush()  # assign member.id before provisioning its account

    try:
        await _provision_member_account(member, collective.name)
    except Exception as exc:
        # not committed yet, so the member row rolls back — surface the real reason
        logger.error("Member VA provisioning failed for %s", member.id, exc_info=True)
        raise HTTPException(
            status_code=502, detail=f"Could not provision member pay-in account: {exc}"
        )

    await db.commit()
    return {
        "id": member.id,
        "name": member.name,
        "role": member.role,
        "bank_account_number": member.bank_account_number,
        "bank_name": member.bank_name,
        "wallet_address": member.wallet_address,
    }


@router.get("/{collective_id}/members")
async def list_members(collective_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Member).where(Member.collective_id == collective_id))
    return result.scalars().all()


@router.post("/{collective_id}/members/{member_id}/role")
async def set_member_role(
    collective_id: str,
    member_id: str,
    body: SetRoleRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ("member", "committee"):
        raise HTTPException(status_code=400, detail="Role must be 'member' or 'committee'")
    result = await db.execute(
        select(Member).where(Member.id == member_id, Member.collective_id == collective_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.role == "organizer":
        raise HTTPException(status_code=400, detail="The organizer's role can't be changed")
    member.role = body.role
    await db.commit()
    return {"id": member.id, "name": member.name, "role": member.role}
