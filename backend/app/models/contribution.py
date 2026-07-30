import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Contribution(Base):
    __tablename__ = "contributions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    collective_id: Mapped[str] = mapped_column(String, ForeignKey("collectives.id"), nullable=False)
    member_id: Mapped[str] = mapped_column(String, ForeignKey("members.id"), nullable=True)  # null = unmatched
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    expected_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    # exact | partial | excess | unmatched
    status: Mapped[str] = mapped_column(String, nullable=False, default="exact")
    source_transfer_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sender_name: Mapped[str] = mapped_column(String, nullable=True)
    sender_account: Mapped[str] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    collective: Mapped["Collective"] = relationship("Collective", back_populates="contributions")
    member: Mapped["Member"] = relationship("Member", back_populates="contributions")
