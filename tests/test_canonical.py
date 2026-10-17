"""Appendix A test vectors (signature recipe + drawing of lots)."""
from app.canonical import canonical, lots_key, sign


def test_signature_vector_1():
    payload = {"team_id": "t1", "event_type": "goal"}
    assert canonical(payload) == '{"event_type":"goal","team_id":"t1"}'
    assert sign("evt-1", payload, salt="demo-salt") == "972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"


def test_lots_vector_2():
    assert lots_key(42, "lg-1", "t1") == "0613316991ce0ac31e88d6003e3ff4d5e21bb072ac5f81b42c0cdc6598453293"
    assert lots_key(42, "lg-1", "t2") == "e3e3a14e22727f936e1f288cf5d02a8a9362b1da13c5432725fc10b2c7955dd9"
    assert lots_key(42, "lg-1", "t3") == "c8f28e3c2f1eb6c4f636b4f57050e3362a2b39c07fda9b61742a26dd20397028"


def test_canonical_rules():
    assert canonical({"b": [3, 1], "a": {"z": True, "y": None}, "ü": 1}) == '{"a":{"y":null,"z":true},"b":[3,1],"ü":1}'
    assert sign("x", {}, salt="  spaced salt ") != sign("x", {}, salt="spaced salt")  # salt is never trimmed
