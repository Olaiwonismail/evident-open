import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    collective_id: Mapped[str] = mapped_column(String, ForeignKey("collectives.id"), nullable=False)
    # contribution | expense | expense_failed | expense_refunded
    type: Mapped[str] = mapped_column(String, nullable=False)
    ref_id: Mapped[str] = mapped_column(String, nullable=False)  # contribution.id or expense.id
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    actor_name: Mapped[str] = mapped_column(Text, nullable=True)  # member name who triggered this
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    collective: Mapped["Collective"] = relationship("Collective", back_populates="ledger_entries")
