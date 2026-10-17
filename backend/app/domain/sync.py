"""Offline sync contract (NFR-4, spec 5.14): envelope validation, processing order, result shapes."""
from ..validation import Fields, is_id, is_int, parse_ts

ACTION_TYPES = ("score_event", "roster_transfer")


def validate_envelope(b: dict) -> dict:
    f = Fields()
    if not is_id(b.get("device_id")):
        f.add("device_id")
    actions = b.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
        f.add("actions")
        f.check()
    for i, a in enumerate(actions):
        if (not isinstance(a, dict) or not is_id(a.get("action_id")) or a.get("type") not in ACTION_TYPES
                or parse_ts(a.get("queued_at")) is None or not is_int(a.get("base_version"))
                or a.get("base_version") < 0 or not isinstance(a.get("payload"), dict)):
            f.add("actions", f"actions.{i}")
    f.check()
    return {"device_id": b["device_id"], "actions": actions}


def processing_order(actions: list[dict]) -> list[int]:
    """Indices sorted by queued_at ascending; ties keep array order (stable sort)."""
    return sorted(range(len(actions)), key=lambda i: parse_ts(actions[i]["queued_at"]))


def result(action_id: str, status: str, resolution: str, error_code, order: int, version: int, signature=None) -> dict:
    return {"action_id": action_id, "status": status, "resolution": resolution, "error_code": error_code,
            "processed_order": order, "server_version": version, "signature": signature}


def applied(action_id: str, base: int, current: int, order: int, version: int, signature=None) -> dict:
    return result(action_id, "applied", "appended" if base == current else "rebased_append", None, order, version,
                  signature)


def rejected(action_id: str, code: str, order: int, version: int) -> dict:
    return result(action_id, "rejected", "server_wins", code, order, version)


def duplicate(action_id: str, order: int, version: int) -> dict:
    return result(action_id, "duplicate", "skipped_duplicate", None, order, version)


def summarize(results: list[dict]) -> dict:
    return {k: sum(1 for r in results if r["status"] == k) for k in ("applied", "rejected", "duplicate")}
