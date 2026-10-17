#!/usr/bin/env python3
"""Turns coverage.py's JSON report into COVERAGE.json (line coverage % for the six graded backend areas)."""
import json
import sys

AREAS = {
    "fixtures": ["domain/fixtures/"],
    "scoring": ["domain/scoring.py", "domain/sports.py"],
    "standings": ["domain/standings.py"],
    "store": ["domain/store.py"],
    "roster": ["domain/roster.py"],
    "rbac": ["domain/rbac.py"],
}


def main(src: str, dst: str) -> None:
    files = json.load(open(src))["files"]
    out = {}
    for area, prefixes in AREAS.items():
        stmts = covered = 0
        for path, data in files.items():
            norm = path.replace("\\", "/")
            if any(p in norm for p in prefixes):
                stmts += data["summary"]["num_statements"]
                covered += data["summary"]["covered_lines"]
        out[area] = round(100.0 * covered / stmts, 1) if stmts else 0.0
    with open(dst, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
