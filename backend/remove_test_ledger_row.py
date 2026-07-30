"""One-off: remove the WH-TEST-* webhook test rows from the ledger.

Deletes newest-first and only while each test row is still the most recent
entry for its collective — deleting a mid-history row would corrupt every
running balance after it, so the script aborts instead. Delete this file after.
"""
import os
import asyncio

from dotenv import dotenv_values

for k, v in dotenv_values(os.path.join(os.path.dirname(__file__), ".env")).items():
    if v is not None:
        os.environ[k] = v

from sqlalchemy import select, delete
from app.database import AsyncSessionLocal
from app.models.contribution import Contribution
from app.models.ledger import LedgerEntry

TEST_IDS = ["WH-TEST-2", "WH-TEST-1"]  # newest first


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for tx in TEST_IDS:
            c = (
                await db.execute(
                    select(Contribution).where(Contribution.source_transfer_id == tx)
                )
            ).scalar_one_or_none()
            if not c:
                print(f"{tx}: already gone")
                continue
            newest = (
                await db.execute(
                    select(LedgerEntry)
                    .where(LedgerEntry.collective_id == c.collective_id)
                    .order_by(LedgerEntry.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if newest and newest.ref_id != c.id:
                print(
                    f"{tx}: SKIP — not the newest ledger entry "
                    f"(newest ref={newest.ref_id}); deleting would corrupt balances"
                )
                continue
            await db.execute(delete(LedgerEntry).where(LedgerEntry.ref_id == c.id))
            await db.execute(delete(Contribution).where(Contribution.id == c.id))
            await db.commit()
            print(f"{tx}: deleted contribution + ledger entry")


if __name__ == "__main__":
    asyncio.run(main())
