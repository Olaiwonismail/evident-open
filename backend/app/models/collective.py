import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Collective(Base):
    __tablename__ = "collectives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    dues_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    dues_frequency: Mapped[str] = mapped_column(String, nullable=True)  # monthly, quarterly, annual
    virtual_account_id: Mapped[str] = mapped_column(String, nullable=True)
    bank_account_number: Mapped[str] = mapped_column(String, nullable=True)
    bank_name: Mapped[str] = mapped_column(String, nullable=True)
    # the treasury wallet — contributions land here, expenses are paid from it
    bmoni_user_id: Mapped[str] = mapped_column(String, nullable=True)
    smart_wallet_id: Mapped[str] = mapped_column(String, nullable=True)
    wallet_address: Mapped[str] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)  # member id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["Member"]] = relationship("Member", back_populates="collective")
    contributions: Mapped[list["Contribution"]] = relationship("Contribution", back_populates="collective")
    expenses: Mapped[list["Expense"]] = relationship("Expense", back_populates="collective")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship("LedgerEntry", back_populates="collective")
