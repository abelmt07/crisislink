"""
utils.py
--------
Input validation, logging setup, and small helpers shared across modules.
"""

import logging
import os
import re
from datetime import datetime


def setup_logging():
    """Configure file + console logging. Writes to logs/crisislink.log."""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler("logs/crisislink.log"), logging.StreamHandler()],
    )


def validate_email(email: str) -> bool:
    """Return True if the string looks like a valid email address."""
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def validate_phone(phone: str) -> bool:
    """Return True if the string is exactly 10 digits."""
    return bool(re.match(r"^\d{10}$", phone))


def validate_positive_int(value) -> bool:
    """Return True if the value converts to an integer greater than zero."""
    try:
        return int(value) > 0
    except (ValueError, TypeError):
        return False


def validate_enum(value, allowed: list) -> bool:
    """Return True if value matches one of the allowed options (case-insensitive)."""
    if not value:
        return False
    return value.upper() in [a.upper() for a in allowed]


def get_valid_input(prompt, validator, error_msg, transform=None):
    """Re-prompt until the validator accepts the input, then return it (optionally transformed)."""
    while True:
        val = input(prompt).strip()
        if validator(val):
            return transform(val) if transform else val
        print(f"  x {error_msg}")


def new_event_id() -> str:
    """Timestamp-based event id, e.g. EV-20261026083000."""
    return f"EV-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def new_report_id() -> str:
    """Timestamp-based field report id, e.g. FR-20261026083000."""
    return f"FR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
