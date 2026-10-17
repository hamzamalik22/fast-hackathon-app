import os

# DAY1_SALT is read once from the environment at startup: never hard-coded, never trimmed.
DAY1_SALT = os.environ.get("DAY1_SALT", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "nascon-dev-jwt-secret-change-me")
JWT_TTL_SECONDS = 12 * 3600

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon@localhost:5432/nascon")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "nasconminio")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "nasconminio-secret")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "receipts")

MAX_BODY_BYTES = 1_048_576
RATE_LIMIT_MAX = 100
RATE_LIMIT_WINDOW_S = 10
DEMO_PASSWORD = "Nascon@26"
