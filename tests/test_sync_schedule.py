"""NFR-4 offline-sync contract + FR-1.3 match state machine and scheduling conflicts."""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import schedule, sync
from app.errors import ApiError


def action(aid, at, typ="score_event", base=0, payload=None):
    return {"action_id": aid, "type": typ, "queued_at": at, "base_version": base, "payload": payload or {}}


def test_envelope_and_order():
    env = sync.validate_envelope({"device_id": "dev-1", "actions": [action("b", "2026-10-17T11:01:00Z"),
                                                                    action("a", "2026-10-17T11:00:00Z"),
                                                                    action("c", "2026-10-17T11:00:00Z")]})
    assert sync.processing_order(env["actions"]) == [1, 2, 0]  # ties keep array order


@pytest.mark.parametrize("body", [{"device_id": "d", "actions": []}, {"device_id": "d|x", "actions": [action("a", "2026-10-17T11:00:00Z")]},
                                  {"device_id": "d", "actions": [action("a", "yesterday")]},
                                  {"device_id": "d", "actions": [action("a", "2026-10-17T11:00:00Z", typ="other")]},
                                  {"device_id": "d", "actions": [action("a", "2026-10-17T11:00:00Z", base=-1)]},
                                  {"device_id": "d", "actions": [action("a", "2026-10-17T11:00:00Z")] * 101}])
def test_envelope_errors(body):
    with pytest.raises(ApiError) as e:
        sync.validate_envelope(body)
    assert e.value.status == 400


def test_result_shapes():
    rs = [sync.applied("a1", 3, 3, 1, 4, "sig"), sync.applied("a2", 1, 4, 2, 5), sync.rejected("a3", "SQUAD_FULL", 3, 1),
          sync.duplicate("a4", 4, 5)]
    assert rs[0] == {"action_id": "a1", "status": "applied", "resolution": "appended", "error_code": None,
                     "processed_order": 1, "server_version": 4, "signature": "sig"}
    assert rs[1]["resolution"] == "rebased_append" and rs[2]["resolution"] == "server_wins"
    assert rs[3]["resolution"] == "skipped_duplicate" and rs[3]["signature"] is None
    assert sync.summarize(rs) == {"applied": 2, "rejected": 1, "duplicate": 1}


def test_match_state_machine():
    assert schedule.can_transition("upcoming", "postponed") and schedule.can_transition("postponed", "upcoming")
    assert schedule.can_transition("in_progress", "abandoned")
    assert not schedule.can_transition("completed", "postponed") and not schedule.can_transition("cancelled", "upcoming")
    assert schedule.display_status("upcoming", "postponed") == "postponed" and schedule.display_status("completed", None) == "completed"


def test_conflict_detection():
    t0 = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
    match = {"match_id": "m1", "home_team_id": "a", "away_team_id": "b"}
    others = [{"match_id": "m2", "home_team_id": "c", "away_team_id": "d", "scheduled_at": t0, "venue_id": "v1"},
              {"match_id": "m3", "home_team_id": "a", "away_team_id": "e", "scheduled_at": t0 + timedelta(hours=1), "venue_id": "v2"},
              {"match_id": "m4", "home_team_id": "b", "away_team_id": "f", "scheduled_at": t0 + timedelta(hours=20), "venue_id": "v3"},
              {"match_id": "m5", "home_team_id": "g", "away_team_id": "h", "scheduled_at": t0, "venue_id": "v9"},
              {"match_id": "m1", "home_team_id": "a", "away_team_id": "b", "scheduled_at": t0, "venue_id": "v1"},
              {"match_id": "m6", "home_team_id": "x", "away_team_id": "y", "scheduled_at": None}]
    found = schedule.detect_conflicts(match, t0, "v1", others, venue_hours=(15, 23),
                                      squad_players={"a": {"p1"}, "g": {"p1"}})
    types = {c["type"] for c in found}
    assert types == {"venue_double_booking", "team_overlap", "min_rest_violation", "player_overlap", "venue_unavailable"}
    assert {"type": "venue_double_booking", "entity_ids": ["v1", "m2"]} in found
    assert schedule.detect_conflicts(match, t0 + timedelta(days=10), "v1", others) == []
