"""Build a demo collective with real BMoni wallets, repeatably.

Sandbox resets wipe BMoni-side balances, and demo identities need to be stable
(the phone number is what BMoni matches when crediting test funds). So this
script uses FIXED Evident ids: owner keys are derived from them, meaning the
same run always controls the same wallets.

Run:  python seed_demo.py            # create / top up the demo collective
      python seed_demo.py --show     # just print what exists

Env: DATABASE_URL, SECRET_KEY, APP_BASE_URL, BMONI_API_KEY
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from app.database import AsyncSessionLocal, init_db
from app.models.collective import Collective
from app.models.member import Member
from app.services import provisioning

# Fixed so re-running is idempotent and the derived wallet keys stay the same.
COLLECTIVE_ID = "11111111-1111-4111-8111-111111111111"
MEMBERS = [
    ("22222222-2222-4222-8222-222222222221", "Adaeze Okonkwo", "organizer"),
    ("22222222-2222-4222-8222-222222222222", "Chinedu Balogun", "committee"),
    ("22222222-2222-4222-8222-222222222223", "Funmi Adeyemi", "member"),
]

# Test funds are ~₦1,000 per wallet and hand-credited, so keep dues small enough
# that a full round of contributions is actually affordable.
DUES = 200


async def show() -> None:
    async with AsyncSessionLocal() as db:
        collective = (await db.execute(
            select(Collective).where(Collective.id == COLLECTIVE_ID)
        )).scalar_one_or_none()
        if not collective:
            print("No demo collective yet — run without --show to create it.")
            return
        print(f"{collective.name}  (dues ₦{collective.dues_amount})")
        print(f"  wallet   {collective.wallet_address}")
        print(f"  walletId {collective.smart_wallet_id}")
        print(f"  bmoni    {collective.bmoni_user_id}")
        print(f"  pay-in   {collective.bank_account_number} ({collective.bank_name}) [POOLED]")
        members = (await db.execute(
            select(Member).where(Member.collective_id == COLLECTIVE_ID)
        )).scalars().all()
        print(f"\n{len(members)} member(s):")
        for m in members:
            print(f"  {m.name:<20} {m.role:<10} {m.wallet_address}")
        print("\nFor test funds, give BMoni the phone number registered for that user:")
        for m in members:
            print(f"  {m.name}: {m.phone}")


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        collective = (await db.execute(
            select(Collective).where(Collective.id == COLLECTIVE_ID)
        )).scalar_one_or_none()

        if collective is None:
            collective = Collective(
                id=COLLECTIVE_ID,
                name="Ikeja Traders Association",
                purpose="Monthly dues and shared expenses",
                dues_amount=DUES,
                dues_frequency="monthly",
                created_by=MEMBERS[0][0],
            )
            db.add(collective)
            await db.flush()
            print(f"created collective {collective.name}")

        print("provisioning treasury wallet…")
        await provisioning.provision_entity(collective, collective.name)
        print(f"  wallet {collective.wallet_address}")

        for member_id, name, role in MEMBERS:
            member = (await db.execute(
                select(Member).where(Member.id == member_id)
            )).scalar_one_or_none()
            if member is None:
                member = Member(
                    id=member_id,
                    collective_id=COLLECTIVE_ID,
                    name=name,
                    role=role,
                )
                db.add(member)
                await db.flush()
            print(f"provisioning {name}…")
            await provisioning.provision_entity(member, f"{name} {collective.name}")
            print(f"  wallet {member.wallet_address}")

        await db.commit()

    print()
    await show()


if __name__ == "__main__":
    asyncio.run(show() if "--show" in sys.argv else main())
