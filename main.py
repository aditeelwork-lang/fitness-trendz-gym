import os
import hmac
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import re
import urllib.error
import urllib.request
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo
from database import engine
from models import Base, Member, Payment, ReminderLog
from schemas import MemberCreate, MemberResponse
from payment_schemas import PaymentCreate, PaymentResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


app = FastAPI(title="Fitness Trendz Gym Automation", docs_url=None, redoc_url=None, openapi_url=None)
BASE_DIR = Path(__file__).resolve().parent
OWNER_PASSWORD = os.getenv("OWNER_PASSWORD")
SESSION_SECRET = os.getenv("SESSION_SECRET")
APP_ENV = os.getenv("APP_ENV", "development").lower()

if not OWNER_PASSWORD or not SESSION_SECRET:
    raise RuntimeError(
        "Missing OWNER_PASSWORD or SESSION_SECRET. Set both as environment variables."
    )

# This guard is registered before SessionMiddleware below so request.session
# is available when authorization is checked.
@app.middleware("http")
async def owner_login_required(request: Request, call_next):
    path = request.url.path
    public_paths = {"/", "/login", "/logout", "/auth/status", "/health"}
    is_asset = path.startswith("/assets/")
    if path not in public_paths and not is_asset:
        if not request.session.get("owner_authenticated"):
            return JSONResponse({"detail": "Please log in to continue."}, status_code=401)
    return await call_next(request)

from fastapi.responses import JSONResponse

# Signed session cookie. HTTPS-only when APP_ENV=production.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="ftg_owner_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=(APP_ENV == "production"),
)

app.mount(
    "/assets",
    StaticFiles(directory=BASE_DIR / "assets"),
    name="assets",
)

# Same-origin frontend/backend deployment; local CORS origins remain for development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginPayload(BaseModel):
    password: str

@app.post("/login")
def owner_login(payload: LoginPayload, request: Request):
    if not hmac.compare_digest(payload.password, OWNER_PASSWORD):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    request.session["owner_authenticated"] = True
    return {"ok": True}

@app.post("/logout")
def owner_logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/auth/status")
def auth_status(request: Request):
    return {"authenticated": bool(request.session.get("owner_authenticated"))}


# Creates missing tables. Does not modify existing table structures.
Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    with Session(engine) as db:
        yield db


def get_active_members(db: Session):
    return (
        db.query(Member)
        .filter(Member.is_active.is_(True))
        .order_by(Member.id)
        .all()
    )


# --------------------------------------------------
# MEMBERSHIP DATE CALCULATIONS
# --------------------------------------------------

def add_calendar_months(value: date, months: int) -> date:
    """Add calendar months, handling months with fewer days."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def calculate_expiry(start_date: date, duration_months: int) -> date:
    """Expiry is the day before the same date after N calendar months."""
    return add_calendar_months(start_date, duration_months) - timedelta(days=1)


# --------------------------------------------------
# BASIC AND HEALTH ENDPOINTS
# --------------------------------------------------

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# --------------------------------------------------
# MEMBER ENDPOINTS
# --------------------------------------------------

@app.post(
    "/members",
    response_model=MemberResponse,
    status_code=201,
)
def create_member(
    member: MemberCreate,
    db: Session = Depends(get_db),
):
    existing_member = (
        db.query(Member)
        .filter(
            (Member.member_code == member.member_code)
            | (Member.phone == member.phone)
        )
        .first()
    )

    if existing_member:
        raise HTTPException(
            status_code=409,
            detail="A member with this member code or phone already exists.",
        )

    if member.membership_expiry < member.membership_start:
        raise HTTPException(
            status_code=400,
            detail="Membership expiry cannot be before the start date.",
        )

    expected_expiry = calculate_expiry(
        member.membership_start,
        member.duration_months,
    )

    if member.membership_expiry != expected_expiry:
        raise HTTPException(
            status_code=400,
            detail=(
                f"For {member.duration_months} month(s), "
                f"expiry must be {expected_expiry:%d-%m-%Y}."
            ),
        )

    new_member = Member(**member.model_dump())

    try:
        db.add(new_member)
        db.flush()

        receipt = (
            f"Fitness Trendz Gym payment receipt | "
            f"Member: {new_member.full_name} | "
            f"Code: {new_member.member_code} | "
            f"Amount: Rs. {member.monthly_fee:.2f} | "
            f"Period: {member.membership_start:%d-%m-%Y} "
            f"to {member.membership_expiry:%d-%m-%Y}"
        )

        initial_payment = Payment(
            member_id=new_member.id,
            amount=member.monthly_fee,
            period_start=member.membership_start,
            period_end=member.membership_expiry,
            receipt_message=receipt,
        )

        db.add(initial_payment)
        db.commit()
        db.refresh(new_member)

    except Exception:
        db.rollback()
        raise

    return new_member


@app.get("/members", response_model=list[MemberResponse])
def list_members(db: Session = Depends(get_db)):
    return db.query(Member).order_by(Member.id).all()


@app.get("/members/active", response_model=list[MemberResponse])
def list_active_members(db: Session = Depends(get_db)):
    return get_active_members(db)


@app.get("/members/{member_code}", response_model=MemberResponse)
def get_member(
    member_code: str,
    db: Session = Depends(get_db),
):
    member = (
        db.query(Member)
        .filter(Member.member_code == member_code)
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found.",
        )

    return member


# --------------------------------------------------
# PAYMENT AND RENEWAL ENDPOINTS
# --------------------------------------------------

@app.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=201,
)
def create_payment(
    payment: PaymentCreate,
    db: Session = Depends(get_db),
):
    member = (
        db.query(Member)
        .filter(Member.member_code == payment.member_code)
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found.",
        )

    if not member.is_active:
        raise HTTPException(
            status_code=400,
            detail="This member is inactive.",
        )

    # The next membership starts after the current membership expires.
    expected_start = member.membership_expiry + timedelta(days=1)

    # The NEW package determines the new expiry date.
    expected_end = calculate_expiry(
        expected_start,
        payment.duration_months,
    )

    if payment.period_start != expected_start:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The next membership must start on "
                f"{expected_start:%d-%m-%Y}."
            ),
        )

    if payment.period_end != expected_end:
        raise HTTPException(
            status_code=400,
            detail=(
                f"For {payment.duration_months} month(s), "
                f"expiry must be {expected_end:%d-%m-%Y}."
            ),
        )

    # Avoid recording a second payment for the same member and period.
    existing_payment = (
        db.query(Payment)
        .filter(
            Payment.member_id == member.id,
            Payment.period_start == payment.period_start,
            Payment.period_end == payment.period_end,
        )
        .first()
    )

    if existing_payment is not None:
        raise HTTPException(
            status_code=409,
            detail="A payment already exists for this membership period.",
        )

    paid_at = datetime.now()

    receipt = (
        "FITNESS TRENDZ GYM - PAYMENT RECEIPT\n"
        f"Member: {member.full_name}\n"
        f"Member ID: {member.member_code}\n"
        f"Previous package: {member.plan_name}\n"
        f"New package: {payment.plan_name}\n"
        f"Package duration: {payment.duration_months} month(s)\n"
        f"Amount paid: Rs. {payment.amount:.2f}\n"
        f"Payment date: {paid_at:%d-%m-%Y %H:%M}\n"
        f"Membership period: {payment.period_start:%d-%m-%Y} "
        f"to {payment.period_end:%d-%m-%Y}\n"
        "Payment status: PAID IN FULL\n"
        "Thank you for choosing Fitness Trendz Gym!"
    )

    new_payment = Payment(
        member_id=member.id,
        amount=payment.amount,
        paid_at=paid_at,
        period_start=payment.period_start,
        period_end=payment.period_end,
        receipt_message=receipt,
    )

    try:
        db.add(new_payment)

        # Record the package and actual amount paid for this renewal.
        member.plan_name = payment.plan_name
        member.duration_months = payment.duration_months
        member.monthly_fee = payment.amount
        member.membership_start = payment.period_start
        member.membership_expiry = payment.period_end

        db.commit()
        db.refresh(new_payment)

    except Exception:
        db.rollback()
        raise

    return new_payment


@app.get("/payments", response_model=list[PaymentResponse])
def list_payments(db: Session = Depends(get_db)):
    return db.query(Payment).order_by(Payment.id).all()


@app.get(
    "/members/{member_code}/payments",
    response_model=list[PaymentResponse],
)
def member_payment_history(
    member_code: str,
    db: Session = Depends(get_db),
):
    member = (
        db.query(Member)
        .filter(Member.member_code == member_code)
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found.",
        )

    return (
        db.query(Payment)
        .filter(Payment.member_id == member.id)
        .order_by(Payment.id.desc())
        .all()
    )


# --------------------------------------------------
# DEACTIVATE MEMBER
# --------------------------------------------------

@app.patch(
    "/members/{member_code}/deactivate",
    response_model=MemberResponse,
)
def deactivate_member(
    member_code: str,
    db: Session = Depends(get_db),
):
    member = (
        db.query(Member)
        .filter(Member.member_code == member_code)
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found.",
        )

    member.is_active = False

    try:
        db.commit()
        db.refresh(member)
    except Exception:
        db.rollback()
        raise

    return member
    
def normalize_indian_phone(phone: str) -> str:
    """Convert a 10-digit Indian mobile number to country-code format."""
    digits = re.sub(r"\D", "", str(phone or ""))

    if len(digits) == 10:
        return "91" + digits

    if len(digits) == 12 and digits.startswith("91"):
        return digits

    raise ValueError("Phone number must be a valid 10-digit Indian number.")


def send_whatsapp_template(member, reminder_type: str) -> tuple[bool, str]:
    """Send the approved gym_membership_reminder template via Meta Cloud API."""
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    api_version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v25.0")
    template_name = os.getenv(
        "WHATSAPP_TEMPLATE_NAME", "gym_membership_reminder"
    )
    language_code = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")

    if not token or not phone_number_id:
        return False, "Missing WhatsApp access token or phone number ID."

    try:
        recipient = normalize_indian_phone(member.phone)
    except ValueError as exc:
        return False, str(exc)

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(member.full_name)},
                        {
                            "type": "text",
                            "text": member.membership_expiry.strftime("%d %B %Y"),
                        },
                        {
                            "type": "text",
                            "text": f"{member.monthly_fee:.2f}",
                        },
                    ],
                }
            ],
        },
    }

    request = urllib.request.Request(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))

        messages = result.get("messages", [])
        if messages and messages[0].get("id"):
            return True, f"WhatsApp accepted message: {messages[0]['id']}"

        return False, "API response did not include a message ID."

    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode("utf-8")[:1000]
        except Exception:
            details = "No error details available."
        return False, f"WhatsApp API HTTP {exc.code}: {details}"

    except Exception as exc:
        return False, f"WhatsApp request failed: {type(exc).__name__}."

# --------------------------------------------------
# MEMBERSHIP EXPIRY REMINDER PREVIEW
# --------------------------------------------------

@app.get("/reminders/preview")
def preview_membership_reminders(
    days: int = 7,
    db: Session = Depends(get_db),
):
    if days < 0 or days > 90:
        raise HTTPException(
            status_code=400,
            detail="Days must be between 0 and 90.",
        )

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    start_date = today - timedelta(days=2)
    end_date = today + timedelta(days=days)

    members = (
        db.query(Member)
        .filter(
            Member.is_active.is_(True),
            Member.reminder_opt_in.is_(True),
            Member.membership_expiry >= start_date,
            Member.membership_expiry <= end_date,
        )
        .order_by(Member.membership_expiry)
        .all()
    )

    reminders = []

    for member in members:
        days_remaining = (
            member.membership_expiry - today
        ).days

        if days_remaining == 1:
            reminder_type = "expiry_tomorrow"
        elif days_remaining == 0:
            reminder_type = "expiry_today"
        elif days_remaining == -1:
            reminder_type = "expired_1_day"
        elif days_remaining == -2:
            reminder_type = "expired_2_days"
        else:
            continue

        reminders.append(
            {
                "member_code": member.member_code,
                "full_name": member.full_name,
                "phone": member.phone,
                "membership_expiry": member.membership_expiry,
                "days_remaining": days_remaining,
                "reminder_type": reminder_type,
                "whatsapp_opt_in": member.reminder_opt_in,
            }
        )

    return {
        "message": "Preview only. No messages were sent.",
        "today": today,
        "count": len(reminders),
        "reminders": reminders,
    }


# --------------------------------------------------
# VIEW REMINDER LOGS
# --------------------------------------------------

@app.get("/reminders/logs")
def get_reminder_logs(db: Session = Depends(get_db)):
    logs = (
        db.query(ReminderLog)
        .order_by(ReminderLog.created_at.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": log.id,
            "member_id": log.member_id,
            "reminder_type": log.reminder_type,
            "reminder_date": log.reminder_date,
            "status": log.status,
            "message": log.message,
            "created_at": log.created_at,
            "sent_at": log.sent_at,
        }
        for log in logs
    ]

# --------------------------------------------------
# DAILY MEMBERSHIP REMINDER CHECK — PREVIEW ONLY
# --------------------------------------------------



def run_daily_reminder_check():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    with Session(engine) as db:
        members = (
            db.query(Member)
            .filter(
                Member.is_active.is_(True),
                Member.reminder_opt_in.is_(True),
                Member.membership_expiry >= today - timedelta(days=2),
                Member.membership_expiry <= today + timedelta(days=1),
            )
            .order_by(Member.membership_expiry)
            .all()
        )

        print(
            f"\n[REMINDER PREVIEW] {today}: "
            f"{len(members)} eligible member(s) checked."
        )

       
        for member in members:
            days_left = (member.membership_expiry - today).days

            reminder_types = {
                1: "expiry_tomorrow",
                0: "expiry_today",
                -1: "expired_1_day",
                -2: "expired_2_days",
            }

            reminder_type = reminder_types.get(days_left)
            if not reminder_type:
                continue

            existing_log = (
                db.query(ReminderLog)
                .filter(
                    ReminderLog.member_id == member.id,
                    ReminderLog.reminder_type == reminder_type,
                    ReminderLog.reminder_date == today,
                )
                .first()
            )

            if existing_log:
                print(
                    f"SKIPPED {member.member_code}: "
                    f"{reminder_type} already logged today."
                )
                continue

            # Safe default: preview only until explicitly enabled in Render.
            sending_enabled = (
                os.getenv("WHATSAPP_SEND_ENABLED", "false").lower() == "true"
            )

            if not sending_enabled:
                log = ReminderLog(
                    member_id=member.id,
                    reminder_date=today,
                    reminder_type=reminder_type,
                    status="preview",
                    message=(
                        f"Preview only for {member.full_name}; "
                        f"membership expiry: {member.membership_expiry:%d-%m-%Y}"
                    ),
                )
                db.add(log)

                try:
                    db.commit()
                    print(f"PREVIEW ONLY: {member.member_code} | {reminder_type}")
                except Exception:
                    db.rollback()
                    print(f"Failed to save preview log for {member.member_code}")

                continue

            success, result_message = send_whatsapp_template(
                member, reminder_type
            )

            log = ReminderLog(
                member_id=member.id,
                reminder_date=today,
                reminder_type=reminder_type,
                status="sent" if success else "failed",
                message=result_message,
                sent_at=(
                    datetime.now(ZoneInfo("Asia/Kolkata"))
                    if success else None
                ),
            )
            db.add(log)

            try:
                db.commit()
                print(
                    f"{'SENT' if success else 'FAILED'} "
                    f"{member.member_code} | {result_message}"
                )
            except Exception:
                db.rollback()
                print(f"Failed to save reminder log for {member.member_code}")

# --------------------------------------------------
# DAILY SCHEDULER — PREVIEW ONLY
# --------------------------------------------------



scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        run_daily_reminder_check,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_membership_reminder_preview",
        replace_existing=True,
    )

    scheduler.start()
    print("Daily reminder preview scheduler started.")
    print("Scheduled jobs:", scheduler.get_jobs())

    for job in scheduler.get_jobs():
        print("Job schedule:", job.trigger)
        print("Next run:", job.next_run_time)


@app.on_event("startup")
def startup_event():
    start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("Daily reminder preview scheduler stopped.")
