import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.collective import Collective
from app.models.member import Member
from app.services import auth, provisioning
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
        # The organizer's credential, returned exactly once. It is what their
        # personal link carries; the members list never gives it out again.
        "organizer_token": auth.issue_token(organizer.id),
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
async def invite_member(
    collective_id: str,
    body: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    me: Member = Depends(auth.current_member),
):
    auth.require_committee(auth.require_collective(me, collective_id))
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
        # Handed to the inviter once, to pass on privately. This is the invitee's
        # credential, so it is never returned by any listing endpoint.
        "token": auth.issue_token(member.id),
    }


@router.get("/{collective_id}/me")
async def get_me(collective_id: str, me: Member = Depends(auth.current_member)):
    """Who the caller's token says they are, with their own private details.

    Identity used to be resolved by matching `?m=<id>` against the public member
    list, which meant identity was whatever the URL claimed. It comes from the
    signed token now, so this is the only endpoint that can answer it.
    """
    auth.require_collective(me, collective_id)
    return {
        "id": me.id,
        "name": me.name,
        "role": me.role,
        "email": me.email,
        "phone": me.phone,
        "bank_account_number": me.bank_account_number,
        "bank_name": me.bank_name,
        "wallet_address": me.wallet_address,
    }


@router.get("/{collective_id}/members")
async def list_members(
    collective_id: str,
    db: AsyncSession = Depends(get_db),
    viewer: Member | None = Depends(auth.optional_member),
):
    """The roster. Public by name and role; contact details are not.

    This used to return the ORM rows whole, which published every member's email,
    phone number and wallet identifiers to anyone holding the collective's link.
    Who is in the group and who can approve spending is part of the transparency
    claim. How to phone them is not.
    """
    result = await db.execute(select(Member).where(Member.collective_id == collective_id))
    members = result.scalars().all()
    privileged = (
        viewer is not None
        and viewer.collective_id == collective_id
        and viewer.role in ("committee", "organizer")
    )
    rows = []
    for m in members:
        row = {"id": m.id, "name": m.name, "role": m.role}
        if privileged:
            # the organizer manages the roster, so they see what they need to
            row |= {"email": m.email, "phone": m.phone,
                    "bank_account_number": m.bank_account_number}
        rows.append(row)
    return rows


@router.post("/{collective_id}/members/{member_id}/role")
async def set_member_role(
    collective_id: str,
    member_id: str,
    body: SetRoleRequest,
    db: AsyncSession = Depends(get_db),
    me: Member = Depends(auth.current_member),
):
    # Promotion to committee is promotion to spending authority, so it is the
    # organizer's alone — a committee member cannot recruit their own quorum.
    auth.require_collective(me, collective_id)
    if me.role != "organizer":
        raise HTTPException(status_code=403, detail="Only the organizer can change roles")
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
