
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from reminders import get_members_needing_reminders
from database import database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

test_engine = create_engine(database_url.set(database="gym_automation"))
SessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)


def run_daily_reminder_check():
    """Preview reminders without sending messages."""
    db = SessionLocal()

    try:
        reminders = get_members_needing_reminders(db)

        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
            f"Reminder check completed. "
            f"{len(reminders)} reminder(s) need review."
        )

        for reminder in reminders:
            print(
                f"Preview: {reminder['reminder_type']} "
                f"for member {reminder['member_code']}"
            )

    except Exception as error:
        print(f"Reminder check failed: {error}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # Run daily at 9:00 AM India time.
    scheduler.add_job(
        run_daily_reminder_check,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_reminder_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    print("Daily reminder scheduler started (Asia/Kolkata, 9:00 AM).")
    print("Preview mode only; no WhatsApp messages will be sent.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
