"""BMoni webhook receiver.

Unlike the previous provider, BMoni issues a real signing secret (`whsec_…`) via
`POST /v1/webhooks/config`, so signature verification can genuinely be switched
on — set `BMONI_WEBHOOK_SECRET` and it activates.

The event payload shape is NOT documented and has not been observed yet. So this
handler deliberately does not assume a schema: it searches the payload for the
fields it needs, and if it can't find them it logs the whole body and returns
200 rather than guessing. Ingestion doesn't depend on this — `ingest.py` polls —
so a webhook we can't parse is a missed optimisation, not lost money.

Once a real delivery is seen, tighten `_extract` to the actual shape.
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.collective import Collective
from app.models.member import Member
from app.services import contributions, ingest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_DEPOSIT_EVENTS = {"wallet.deposit.completed", "employee.deposit.completed"}


def _verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.bmoni_webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def _walk(node, keys: tuple[str, ...]):
    """Depth-first search for the first matching key — the payload nests
    unpredictably and this beats hard-coding a path we haven't verified."""
    if isinstance(node, dict):
        for key in keys:
            if node.get(key) not in (None, ""):
                return node[key]
        for value in node.values():
            found = _walk(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _walk(item, keys)
            if found is not None:
                return found
    return None


@router.post("/bmoni")
async def bmoni_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()

    if settings.bmoni_webhook_secret:
        signature = (request.headers.get("x-bmoni-signature")
                     or request.headers.get("x-webhook-signature") or "")
        if not signature or not _verify_signature(raw, signature):
            logger.warning("BMoni webhook rejected: bad signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = str(_walk(payload, ("event", "eventType", "type")) or "")

    if event and event not in _DEPOSIT_EVENTS:
        return {"status": "ignored", "event": event}

    source_id = _walk(payload, ingest._ID_KEYS)
    amount = ingest._to_decimal(_walk(payload, ingest._AMOUNT_KEYS))
    sender = _walk(payload, ingest._SENDER_KEYS)
    wallet = _walk(payload, ("smartWalletId", "walletId", "toAddress", "to"))

    if not (source_id and amount):
        # Unknown shape — log it so the schema can be pinned down, and let the
        # poller pick the payment up. Returning 200 avoids a retry storm for
        # something a retry won't fix.
        logger.warning("BMoni webhook: unrecognised payload, falling back to polling: %s",
                       str(payload)[:800])
        return {"status": "unparsed"}

    collective = (await db.execute(
        select(Collective).where(
            (Collective.smart_wallet_id == str(wallet))
            | (Collective.wallet_address == str(wallet))
        )
    )).scalars().first()
    if not collective:
        logger.info("BMoni webhook for unknown wallet %s — ignoring", wallet)
        return {"status": "unknown_wallet"}

    member = None
    if sender:
        member = (await db.execute(
            select(Member).where(
                Member.collective_id == collective.id,
                Member.wallet_address.ilike(str(sender)),
            )
        )).scalars().first()

    try:
        await contributions.record_payment(
            collective=collective,
            member=member,
            amount=amount,
            source_transfer_id=str(source_id),
            sender_name=member.name if member else str(sender or "")[:42],
            sender_account=str(sender or ""),
            db=db,
        )
    except Exception as exc:
        # Non-2xx so BMoni retries; idempotency on source_transfer_id makes that safe.
        logger.error("BMoni webhook processing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="processing failed, please retry")

    return {"status": "ok"}
