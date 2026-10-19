
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_code: Mapped[str] = mapped_column(
        String(30), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    plan_name: Mapped[str] = mapped_column(String(60))
    duration_months: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    monthly_fee: Mapped[float] = mapped_column(Numeric(10, 2))
    membership_start: Mapped[date] = mapped_column(Date)
    membership_expiry: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id"), index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    paid_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    receipt_message: Mapped[str] = mapped_column(String(1000))

class ReminderLog(Base):
    __tablename__ = "reminder_logs"
    __table_args__ = (
        UniqueConstraint(
            "member_id",
            "reminder_type",
            "reminder_date",
            name="uq_reminder_member_type_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id"), index=True
    )
    reminder_date: Mapped[date] = mapped_column(Date)
    reminder_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
