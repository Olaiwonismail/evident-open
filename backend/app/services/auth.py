"""Member identity, as a signed capability token.

Evident's threat model is specific, and it drives the design here.

The ledger is **deliberately public** — that is the product. Anyone with the
collective's link can read the balance, the contributions, the expenses and every
approval decision. Locking reads down would remove the transparency the whole
thing exists to provide. So authentication guards *writes*, not reads.

What was wrong before: a member was identified by `?m=<member_id>` in the URL, and
`GET /collectives/{id}/members` publishes every member id. An observer didn't have
to guess anything — read the list, put the organizer's id in the URL, approve a
payout to yourself. The role checks were real but the identity behind them wasn't.

What replaces it: a member's personal link carries a token that is their id plus an
HMAC over it, keyed by `SECRET_KEY`. Ids stay public and harmless; a token cannot be
produced from one without the server key. Tokens are issued exactly twice — to the
organizer when a collective is created, and to an invitee when they are invited —
and the members list never returns them.

This is capability-URL auth, the model a shared document link uses. It is chosen
knowingly: it needs no passwords, no sessions and no email delivery, which suits a
group whose members are reached by a WhatsApp link. Its cost is that the link *is*
the credential, so forwarding a personal link hands over that member's authority.
For a treasury of this size that trade is reasonable, and it is a genuine step up
from an identifier anyone could read off a public endpoint. A production deployment
would add device-bound sessions and rotation on top.
"""
import hashlib
import hmac
import logging

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.member import Member

logger = logging.getLogger(__name__)

# 128 bits of the digest. Full-length signatures make for unwieldy links, and a
# 2^-128 forgery chance is not the weak point of a scheme whose credential is a URL.
_SIG_CHARS = 32


def _signature(member_id: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        f"member:{member_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:_SIG_CHARS]


def issue_token(member_id: str) -> str:
    """The member's credential. Goes in their personal link, and nowhere else."""
    return f"{member_id}.{_signature(member_id)}"


def verify_token(token: str) -> str | None:
    """Recover the member id from a token, or None if it doesn't verify."""
    if not token or "." not in token:
        return None
    member_id, _, signature = token.rpartition(".")
    if not member_id:
        return None
    # Constant-time: a plain == leaks how much of the signature was right, which
    # is enough to forge one byte at a time.
    if not hmac.compare_digest(signature, _signature(member_id)):
        return None
    return member_id


async def current_member(
    x_member_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Member:
    """The member making this request. Raises 401 if the token is absent or bad."""
    if not x_member_token:
        raise HTTPException(status_code=401, detail="This action needs your personal link")
    member_id = verify_token(x_member_token)
    if not member_id:
        logger.warning("Rejected a member token that failed verification")
        raise HTTPException(status_code=401, detail="That link is not valid")
    member = (await db.execute(
        select(Member).where(Member.id == member_id)
    )).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=401, detail="That link is no longer valid")
    return member


async def optional_member(
    x_member_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Member | None:
    """The caller if they presented a good token, otherwise None.

    For endpoints that serve everyone but show more to a member — the member list
    is public (the group's roster is part of the transparency claim) while contact
    and bank details on it are not.
    """
    if not x_member_token:
        return None
    member_id = verify_token(x_member_token)
    if not member_id:
        return None
    return (await db.execute(
        select(Member).where(Member.id == member_id)
    )).scalar_one_or_none()


def require_collective(member: Member, collective_id: str) -> Member:
    """Confirm the token holder belongs to the collective in the path.

    Without this a valid token for collective A would authorise writes against
    collective B — the signature proves who you are, not where you belong.
    """
    if member.collective_id != collective_id:
        raise HTTPException(status_code=403, detail="You are not a member of this collective")
    return member


def require_committee(member: Member) -> Member:
    """Approvals and role changes are committee-or-organizer only."""
    if member.role not in ("committee", "organizer"):
        raise HTTPException(
            status_code=403, detail="Only committee members can decide on expenses"
        )
    return member
