"""FR-1.2 league structures: divisions with promotion/relegation, hybrid group stage -> seeded knockout."""
import pytest

from app.domain.leagues import hybrid_knockout, hybrid_seeds, promotion_relegation
from app.errors import ApiError


def test_promotion_relegation():
    r = promotion_relegation(["a", "b", "c", "d", "e", "f"], 2, 1)
    assert r == {"promoted": ["a", "b"], "relegated": ["f"], "stays": ["c", "d", "e"]}
    assert promotion_relegation(["a", "b"], 0, 0) == {"promoted": [], "relegated": [], "stays": ["a", "b"]}
    with pytest.raises(ApiError):
        promotion_relegation(["a", "b"], 2, 1)


def test_hybrid_seeding_crosses_groups():
    groups = {"B": ["b1", "b2", "b3"], "A": ["a1", "a2", "a3"]}
    assert hybrid_seeds(groups, 2) == ["a1", "b1", "a2", "b2"]
    ko = hybrid_knockout(groups, 2, third_place=True)
    r1 = ko["rounds"][0]["matches"]
    # order(4) = [1, 4, 2, 3]: group winners meet the other group's runner-up
    assert [(m["home"], m["away"]) for m in r1] == [("a1", "b2"), ("b1", "a2")]
    assert ko["bracket_size"] == 4 and ko["rounds"][-1]["matches"][-1]["match_id"] == "TP"


def test_hybrid_validation():
    with pytest.raises(ApiError):
        hybrid_seeds({"A": ["a1"]}, 2)
    with pytest.raises(ApiError):
        hybrid_knockout({"A": ["a1", "a2"]}, 1)
    with pytest.raises(ApiError):  # overlapping groups would pair a team against itself
        hybrid_seeds({"A": ["x", "y"], "B": ["x", "z"]}, 1)
