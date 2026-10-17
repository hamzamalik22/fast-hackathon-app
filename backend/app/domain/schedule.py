"""Match lifecycle state machine and scheduling conflict detection (FR-1.3)."""
from datetime import datetime, timedelta

TRANSITIONS = {
    "upcoming": {"in_progress", "postponed", "cancelled"},
    "in_progress": {"completed", "abandoned", "postponed"},
    "postponed": {"upcoming", "cancelled"},
    "completed": set(),
    "abandoned": set(),
    "cancelled": set(),
}
ADMIN_STATUSES = ("postponed", "abandoned", "cancelled")


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def display_status(event_status: str, admin_status: str | None) -> str:
    """Event-derived status (upcoming/in_progress/completed) unless an admin status overrides it."""
    return admin_status or event_status


def detect_conflicts(match: dict, start: datetime, venue_id: str | None, others: list[dict], *,
                     duration_min: int = 120, min_rest_hours: int = 48, venue_hours: tuple[int, int] | None = None,
                     squad_players: dict[str, set] | None = None) -> list[dict]:
    """Returns structured conflicts [{type, entity_ids}] for rescheduling `match` to `start` at `venue_id`.

    others: other matches with home_team_id, away_team_id, scheduled_at (datetime|None), venue_id, match_id.
    squad_players: team_id -> set(player_id), used to detect a player registered in two overlapping squads.
    """
    end = start + timedelta(minutes=duration_min)
    teams = {match["home_team_id"], match["away_team_id"]}
    conflicts = []
    if venue_hours is not None and not (venue_hours[0] <= start.hour and end.hour <= venue_hours[1]
                                        and end.date() == start.date()):
        conflicts.append({"type": "venue_unavailable", "entity_ids": [venue_id]})
    for o in others:
        if o["match_id"] == match["match_id"] or o.get("scheduled_at") is None:
            continue
        o_start = o["scheduled_at"]
        o_end = o_start + timedelta(minutes=duration_min)
        overlap = start < o_end and o_start < end
        o_teams = {o["home_team_id"], o["away_team_id"]}
        if overlap and venue_id is not None and o.get("venue_id") == venue_id:
            conflicts.append({"type": "venue_double_booking", "entity_ids": [venue_id, o["match_id"]]})
        shared = teams & o_teams
        if shared and overlap:
            conflicts.append({"type": "team_overlap", "entity_ids": sorted(shared) + [o["match_id"]]})
        elif shared and abs((o_start - start).total_seconds()) < min_rest_hours * 3600:
            conflicts.append({"type": "min_rest_violation", "entity_ids": sorted(shared) + [o["match_id"]]})
        if overlap and squad_players and not shared:
            mine = set().union(*(squad_players.get(t, set()) for t in teams))
            theirs = set().union(*(squad_players.get(t, set()) for t in o_teams))
            both = sorted(mine & theirs)
            if both:
                conflicts.append({"type": "player_overlap", "entity_ids": both + [o["match_id"]]})
    return conflicts
