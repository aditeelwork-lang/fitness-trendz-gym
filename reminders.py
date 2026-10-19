
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Member, Payment, ReminderLog


def get_members_needing_reminders(
    db: Session,
    today: date | None = None,
) -> list[dict]:
    """
    Prepare and log reminders for eligible members.
    Does not send WhatsApp messages.
    """
    if today is None:
        today = date.today()

    reminders = []

    members = (
        db.query(Member)
        .filter(
            Member.is_active.is_(True),
            Member.reminder_opt_in.is_(True),
        )
        .all()
    )

    for member in members:
        payment = (
            db.query(Payment)
            .filter(
                Payment.member_id == member.id,
                Payment.period_start == member.membership_start,
                Payment.period_end == member.membership_expiry,
                Payment.amount == member.monthly_fee,
            )
            .first()
        )

        if payment is not None:
            continue

        days_until_expiry = (member.membership_expiry - today).days

        if days_until_expiry == 1:
            reminder_type = "fee_due_tomorrow"
            message = (
                f"Hello {member.full_name}, your Fitness Trendz Gym "
                f"membership expires tomorrow, "
                f"{member.membership_expiry:%d-%m-%Y}. "
                f"Please pay Rs. {member.monthly_fee:.2f} to continue "
                "your membership."
            )
        elif days_until_expiry < 0:
            reminder_type = "membership_expired"
            message = (
                f"Hello {member.full_name}, your Fitness Trendz Gym "
                f"membership expired on "
                f"{member.membership_expiry:%d-%m-%Y}. "
                f"Outstanding membership fee: "
                f"Rs. {member.monthly_fee:.2f}. "
                "Please contact the gym to renew your membership."
            )
        else:
            continue

        # Skip a reminder that has already been logged for this date.
        existing_log = (
            db.query(ReminderLog)
            .filter(
                ReminderLog.member_id == member.id,
                ReminderLog.reminder_type == reminder_type,
                ReminderLog.reminder_date == today,
            )
            .first()
        )

        if existing_log is not None:
            continue

        log_entry = ReminderLog(
            member_id=member.id,
            reminder_date=today,
            reminder_type=reminder_type,
            status="preview",
            message=message,
            created_at=datetime.now(),
        )

        try:
            db.add(log_entry)
            db.commit()
        except IntegrityError:
            # Another run may have created the same log concurrently.
            db.rollback()
            continue

        reminders.append(
            {
                "member_id": member.id,
                "member_code": member.member_code,
                "phone": member.phone,
                "reminder_type": reminder_type,
                "message": message,
                "status": "preview",
            }
        )

    return reminders
