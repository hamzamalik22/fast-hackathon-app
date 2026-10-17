"""MinIO object store for receipt PDFs. Strictly best-effort: never delays or fails a checkout."""
import asyncio
import io
import logging

from .. import config

log = logging.getLogger("nascon.storage")
_client = None
_bucket_ready = False


def _get_client():
    global _client
    if _client is None:
        import urllib3
        from minio import Minio
        http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=1, read=3), retries=False)
        _client = Minio(config.MINIO_ENDPOINT, access_key=config.MINIO_ACCESS_KEY,
                        secret_key=config.MINIO_SECRET_KEY, secure=False, http_client=http)
    return _client


def _put(key: str, data: bytes, content_type: str) -> None:
    global _bucket_ready
    c = _get_client()
    if not _bucket_ready:
        if not c.bucket_exists(config.MINIO_BUCKET):
            c.make_bucket(config.MINIO_BUCKET)
        _bucket_ready = True
    c.put_object(config.MINIO_BUCKET, key, io.BytesIO(data), len(data), content_type=content_type)


async def _put_async(key: str, data: bytes, content_type: str) -> None:
    try:
        await asyncio.to_thread(_put, key, data, content_type)
    except Exception as exc:  # noqa: BLE001
        log.info("object store upload skipped for %s: %s", key, exc)


_tasks: set = set()


def put_receipt_background(order_id: str, pdf: bytes) -> None:
    task = asyncio.get_running_loop().create_task(_put_async(f"receipts/{order_id}.pdf", pdf, "application/pdf"))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
