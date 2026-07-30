import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    collective_id: Mapped[str] = mapped_column(String, ForeignKey("collectives.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=True)
    phone: Mapped[str] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="member")  # organizer, committee, member
    # The naira deposit account is POOLED across all users, so it can't identify a
    # payer. What is unique per member is their smart wallet — so wallet_address,
    # not bank_account_number, is what attributes an incoming contribution.
    bank_account_number: Mapped[str] = mapped_column(String, nullable=True)
    bank_name: Mapped[str] = mapped_column(String, nullable=True)
    virtual_account_id: Mapped[str] = mapped_column(String, nullable=True)
    bmoni_user_id: Mapped[str] = mapped_column(String, nullable=True)
    smart_wallet_id: Mapped[str] = mapped_column(String, nullable=True)
    wallet_address: Mapped[str] = mapped_column(String, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    collective: Mapped["Collective"] = relationship("Collective", back_populates="members")
    contributions: Mapped[list["Contribution"]] = relationship("Contribution", back_populates="member")
