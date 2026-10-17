"""POST /audit/v1/fixtures: pure schedule/bracket computation (FR-1.3). Custom implementations only."""
from ...validation import Fields, is_id
from . import double_elim, round_robin, single_elim, swiss

GENERATORS = {
    "round_robin": (round_robin.generate, 2, 40),
    "swiss": (swiss.generate, 2, 64),
    "single_elim": (single_elim.generate, 2, 128),
    "double_elim": (double_elim.generate, 3, 128),
}


def generate(body: dict) -> dict:
    f = Fields()
    fmt = body.get("format")
    if fmt not in GENERATORS:
        f.add("format")
    teams = body.get("teams")
    if (not isinstance(teams, list) or not all(is_id(t) for t in teams) or len(set(teams)) != len(teams)):
        f.add("teams")
    elif fmt in GENERATORS:
        _, lo, hi = GENERATORS[fmt]
        if not lo <= len(teams) <= hi:
            f.add("teams")
    params = body.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        f.add("params")
    f.check()
    return GENERATORS[fmt][0](list(teams), params)
