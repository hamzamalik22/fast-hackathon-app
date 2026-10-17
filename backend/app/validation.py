import re
from datetime import date, datetime, timezone

from .errors import validation_error

ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def is_int(v) -> bool:
    return type(v) is int  # bool is a subclass of int and must be rejected


def is_id(v) -> bool:
    return isinstance(v, str) and ID_RE.fullmatch(v) is not None


def is_str(v, min_len: int = 1, max_len: int = 10_000) -> bool:
    return isinstance(v, str) and min_len <= len(v) <= max_len


def parse_date(v) -> date | None:
    if not isinstance(v, str) or not DATE_RE.fullmatch(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def parse_ts(v) -> datetime | None:
    if not isinstance(v, str) or not TS_RE.fullmatch(v):
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> date:
    return datetime.now(timezone.utc).date()


class Fields:
    """Collects offending field names, then raises one VALIDATION_ERROR listing all of them."""

    def __init__(self):
        self.bad: list[str] = []

    def add(self, *names: str) -> None:
        for n in names:
            if n not in self.bad:
                self.bad.append(n)

    def check(self, message: str = "Request validation failed.") -> None:
        if self.bad:
            raise validation_error(self.bad, message)
