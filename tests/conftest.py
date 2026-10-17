import os
import sys
from pathlib import Path

os.environ.setdefault("DAY1_SALT", "demo-salt")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
