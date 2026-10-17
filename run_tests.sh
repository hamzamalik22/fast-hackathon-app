#!/usr/bin/env bash
# Runs the backend unit tests and regenerates COVERAGE.json.
# Default: inside the backend's own Docker image (same Python + dependencies as production; only Docker is needed).
# Use ./run_tests.sh --local to run with the host's python3 instead.
set -euo pipefail
cd "$(dirname "$0")"

PIP="pip install -q --retries 8 --timeout 60 --disable-pip-version-check"
TESTS="python -m pytest tests -q -p no:cacheprovider --cov=backend/app/domain --cov-report=term --cov-report=json:coverage.json"
REPORT="python tests/coverage_areas.py coverage.json COVERAGE.json"

if [ "${1:-}" = "--local" ] || ! command -v docker >/dev/null 2>&1; then
  python3 -m $PIP -r backend/requirements.txt -r tests/requirements.txt
  export DAY1_SALT="${DAY1_SALT:-demo-salt}" COVERAGE_FILE=/tmp/.coverage-nascon
  python3 -m pytest tests -q -p no:cacheprovider --cov=backend/app/domain --cov-report=term --cov-report=json:coverage.json
  python3 tests/coverage_areas.py coverage.json COVERAGE.json
else
  DAY1_SALT=unit-tests docker compose build -q api
  DAY1_SALT=unit-tests docker compose run --rm --no-deps -T -v "$PWD":/work -w /work \
    -e DAY1_SALT=demo-salt -e COVERAGE_FILE=/tmp/.coverage -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    --entrypoint sh api -c "
      $PIP --root-user-action=ignore -r tests/requirements.txt &&
      $TESTS && $REPORT; status=\$?;
      chown \$HOST_UID:\$HOST_GID coverage.json COVERAGE.json 2>/dev/null; exit \$status"
fi
echo "COVERAGE.json:"
cat COVERAGE.json
