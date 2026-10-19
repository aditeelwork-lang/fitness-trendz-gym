
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import engine as production_engine
from models import Base, Member, ReminderLog


def test_database_rejects_duplicate_reminder():
    test_url = production_engine.url.set(database="gym_automation")
    test_engine = create_engine(test_url)

    try:
        Base.metadata.create_all(bind=test_engine)

        with Session(test_engine) as db:
            member = Member(
                member_code="TEST-DUP-001",
                full_name="Reminder Test Member",
                phone="0000000000",
                plan_name="Test Plan",
                duration_months=1,
                monthly_fee=Decimal("100.00"),
                membership_start=date.today(),
                membership_expiry=date.today(),
                is_active=True,
                reminder_opt_in=True,
            )
            db.add(member)
            db.commit()
            db.refresh(member)

            try:
                db.add(ReminderLog(
                    member_id=member.id,
                    reminder_date=date.today(),
                    reminder_type="expiry_tomorrow",
                    status="preview",
                    message="Automated duplicate protection test",
                ))
                db.commit()

                db.add(ReminderLog(
                    member_id=member.id,
                    reminder_date=date.today(),
                    reminder_type="expiry_tomorrow",
                    status="preview",
                    message="Duplicate test entry",
                ))

                with pytest.raises(IntegrityError):
                    db.commit()
                db.rollback()

            finally:
                db.query(ReminderLog).filter(
                    ReminderLog.member_id == member.id
                ).delete(synchronize_session=False)
                db.delete(member)
                db.commit()

    finally:
        test_engine.dispose()
