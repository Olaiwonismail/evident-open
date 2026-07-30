import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import collectives, ledger, expenses, banks, webhooks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

INGEST_INTERVAL_SECONDS = 20


async def _ingest_tick() -> None:
    """Poll each collective's wallet for credits we haven't recorded.

    This is the primary ingestion path, not a backstop: the BMoni webhook payload
    shape is undocumented, so polling is what's actually known to work. Once a
    real delivery is observed, this becomes the safety net instead.
    """
    from app.database import AsyncSessionLocal
    from app.services import ingest

    try:
        async with AsyncSessionLocal() as db:
            await ingest.sync_all(db)
    except Exception as exc:
        logger.error("Ingest tick failed: %s", exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.bmoni_api_key:
        scheduler.add_job(
            _ingest_tick, "interval", seconds=INGEST_INTERVAL_SECONDS,
            max_instances=1, coalesce=True,
        )
        scheduler.start()
        logger.info("Contribution ingest polling every %ss", INGEST_INTERVAL_SECONDS)
    else:
        logger.warning("BMONI_API_KEY not set — provisioning, payouts and ingest are disabled")
    logger.info("Evident backend started")
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="Evident API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collectives.router)
app.include_router(ledger.router)
app.include_router(expenses.router)
app.include_router(banks.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    # touch the DB so keep-alive pings exercise the whole path writes use —
    # a warm server with a dead connection pool used to pass this check
    from sqlalchemy import text
    from app.database import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        return {"status": "ok", "db": "unreachable"}
