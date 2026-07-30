import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class UnmatchedTransfer(Base):
    __tablename__ = "unmatched_transfers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    collective_id: Mapped[str] = mapped_column(String, ForeignKey("collectives.id"), nullable=False)
    source_transfer_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    sender_name: Mapped[str] = mapped_column(String, nullable=True)
    sender_account: Mapped[str] = mapped_column(String, nullable=True)
    # needs_review | resolved
    status: Mapped[str] = mapped_column(String, default="needs_review")
    resolved_by: Mapped[str] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
