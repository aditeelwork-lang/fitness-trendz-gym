
from datetime import date, timedelta

import pytest


def get_reminder_type(expiry_date: date, today: date) -> str | None:
    days_left = (expiry_date - today).days

    if days_left == 1:
        return "expiry_tomorrow"
    elif days_left == 0:
        return "expiry_today"
    elif days_left == -1:
        return "expired_1_day"
    elif days_left == -2:
        return "expired_2_days"
    else:
        return None


@pytest.mark.parametrize(
    "days_left, expected",
    [
        (1, "expiry_tomorrow"),
        (0, "expiry_today"),
        (-1, "expired_1_day"),
        (-2, "expired_2_days"),
        (2, None),
        (-3, None),
    ],
)
def test_get_reminder_type(days_left, expected):
    today = date(2026, 10, 17)
    expiry_date = today + timedelta(days=days_left)

    assert get_reminder_type(expiry_date, today) == expected
