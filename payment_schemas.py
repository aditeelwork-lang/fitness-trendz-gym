
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    member_code: str = Field(min_length=1, max_length=30)
    plan_name: str = Field(min_length=1, max_length=60)
    duration_months: int = Field(ge=1, le=24)
    amount: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    period_start: date
    period_end: date


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    amount: Decimal
    paid_at: datetime
    period_start: date
    period_end: date
    receipt_message: str
