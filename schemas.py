from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MemberCreate(BaseModel):
    member_code: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=20)
    plan_name: str = Field(min_length=1, max_length=60)
    duration_months: int = Field(ge=1, le=24)
    monthly_fee: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    membership_start: date
    membership_expiry: date
    reminder_opt_in: bool = False


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_code: str
    full_name: str
    phone: str
    plan_name: str
    duration_months: int
    monthly_fee: Decimal
    membership_start: date
    membership_expiry: date
    is_active: bool
    reminder_opt_in: bool