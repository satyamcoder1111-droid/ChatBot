"""
Phone number utilities
"""
import re
from config import ALLOWED_NUMBERS


def clean_number(raw: str) -> str:
    """Strip country prefix (+91 / +971) for internal use."""
    return re.sub(r"^\+?(91|971)", "", str(raw)).strip()


def is_allowed(raw_number: str) -> bool:
    cleaned = clean_number(raw_number)
    return cleaned in ALLOWED_NUMBERS


def e164(raw: str) -> str:
    """Return number without leading + for CRM/API calls."""
    return str(raw).lstrip("+").strip()
