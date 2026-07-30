import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    collective_id: Mapped[str] = mapped_column(String, ForeignKey("collectives.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("members.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    receipt_url: Mapped[str] = mapped_column(String, nullable=True)
    recipient_account: Mapped[str] = mapped_column(String, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String, nullable=False)
    recipient_bank_code: Mapped[str] = mapped_column(String, nullable=False)
    # pending | approved | rejected | disbursing | paid | failed | manual_review
    status: Mapped[str] = mapped_column(String, default="pending")
    approved_by: Mapped[str] = mapped_column(String, ForeignKey("members.id"), nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    # provider's reference for the outbound transfer, used to check its status
    transfer_ref: Mapped[str] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    collective: Mapped["Collective"] = relationship("Collective", back_populates="expenses")
