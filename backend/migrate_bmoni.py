"""One-off schema migration for the BMoni transition.

`init_db` creates missing TABLES but never alters existing ones, so a database
created before the transition is missing the BMoni identifier columns and still
has the old expense column name.

Additive and idempotent — safe to run more than once, and it does not drop or
rewrite any data. Run:  python migrate_bmoni.py
"""
import asyncio

from sqlalchemy import text

from app.database import engine

ADD_COLUMNS = [
    ("collectives", "bmoni_user_id"),
    ("collectives", "smart_wallet_id"),
    ("collectives", "wallet_address"),
    ("members", "bmoni_user_id"),
    ("members", "smart_wallet_id"),
    ("members", "wallet_address"),
]


async def _columns(conn, table: str) -> set[str]:
    rows = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": table})
    return {r[0] for r in rows}


async def main() -> None:
    async with engine.begin() as conn:
        dialect = conn.engine.dialect.name
        if dialect != "postgresql":
            print(f"Dialect is {dialect}, not postgresql — for SQLite just delete the file "
                  f"and let init_db recreate it.")
            return

        for table, column in ADD_COLUMNS:
            existing = await _columns(conn, table)
            if not existing:
                print(f"  {table}: table not found, skipping")
                continue
            if column in existing:
                print(f"  {table}.{column} already present")
                continue
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR"))
            print(f"  {table}.{column} added")

        expenses = await _columns(conn, "expenses")
        if "transfer_ref" in expenses:
            print("  expenses.transfer_ref already present")
        elif "nomba_transfer_id" in expenses:
            await conn.execute(text(
                "ALTER TABLE expenses RENAME COLUMN nomba_transfer_id TO transfer_ref"))
            print("  expenses.nomba_transfer_id -> transfer_ref")
        elif expenses:
            await conn.execute(text("ALTER TABLE expenses ADD COLUMN transfer_ref VARCHAR"))
            print("  expenses.transfer_ref added")

    print("\nMigration complete.")


if __name__ == "__main__":
    asyncio.run(main())
