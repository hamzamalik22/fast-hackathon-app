"""Concurrency-safe checkout (NFR-3, spec 5.12).

Phase 1 (one short transaction): idempotency, lookups, then an atomic conditional reservation
    UPDATE variants SET stock = stock - q, reserved = reserved + q WHERE variant_id = v AND stock >= q
  for every item (sorted ids, so no deadlocks). Any miss rolls the whole reservation back -> 409.
Phase 2: mock gateway. Failure releases the reservation (stock purchasable again) -> 402.
Phase 3 (second transaction): commit the reservation (reserved -= q), order paid, signed receipt + PDF.
Stock can never go negative: the WHERE guard plus CHECK (stock >= 0) on the table.
"""
import base64
import logging

from .. import db
from ..canonical import canonical
from ..domain import store
from ..errors import ApiError, conflict, not_found
from ..validation import now_ts
from . import realtime, storage

log = logging.getLogger("nascon.checkout")


async def _release(items: list[dict]) -> None:
    async with db.tx() as conn:
        for it in sorted(items, key=lambda x: x["variant_id"]):
            await conn.execute("UPDATE variants SET stock = stock + %s, reserved = reserved - %s WHERE variant_id=%s",
                               (it["quantity"], it["quantity"], it["variant_id"]))


async def checkout(body: dict) -> tuple[int, dict]:
    req = store.validate_checkout(body)
    oid = req["order_id"]
    canon = canonical(req)
    items = req["items"]

    async with db.tx() as conn:
        await db.lock(conn, "order:" + oid)
        prior = await db.fetchone(conn, "SELECT request_canonical, response FROM orders WHERE order_id=%s", (oid,))
        if prior is not None:
            if prior["request_canonical"] == canon and prior["response"] is not None:
                return 200, db.lj(prior["response"])
            raise conflict("DUPLICATE_ORDER_ID", f"Order id {oid} was already used with a different request.",
                           order_id=oid)
        ids = [it["variant_id"] for it in items]
        rows = await db.fetchall(conn, "SELECT variant_id, price_minor FROM variants WHERE variant_id = ANY(%s)", (ids,))
        prices = {r["variant_id"]: r["price_minor"] for r in rows}
        for vid in ids:
            if vid not in prices:
                raise not_found("VARIANT_NOT_FOUND", f"Variant {vid} does not exist.", variant_id=vid)
        percent = 0
        if req["discount_code"] is not None:
            d = await db.fetchone(conn, "SELECT percent FROM discount_codes WHERE code=%s", (req["discount_code"],))
            if d is None:
                raise ApiError(400, "INVALID_DISCOUNT_CODE", "That discount code is not valid.",
                               {"discount_code": req["discount_code"]})
            percent = d["percent"]
        scheduled = await db.fetchall(
            conn, "SELECT DISTINCT ON (variant_id) variant_id, price_minor FROM price_schedules "
                  "WHERE variant_id = ANY(%s) AND effective_from <= now() ORDER BY variant_id, effective_from DESC",
            (ids,))
        for r in scheduled:
            prices[r["variant_id"]] = r["price_minor"]
        priced = store.price_items(items, prices, percent)

        for it in sorted(items, key=lambda x: x["variant_id"]):
            ok = await db.fetchone(conn, "UPDATE variants SET stock = stock - %s, reserved = reserved + %s "
                                         "WHERE variant_id=%s AND stock >= %s RETURNING stock",
                                   (it["quantity"], it["quantity"], it["variant_id"], it["quantity"]))
            if ok is None:
                raise conflict("OUT_OF_STOCK", f"Variant {it['variant_id']} has no stock left.",
                               variant_id=it["variant_id"])
        await conn.execute("INSERT INTO orders(order_id, customer_id, status, request_canonical, total_minor) "
                           "VALUES (%s,%s,'pending',%s,%s)", (oid, req["customer_id"], canon, priced["total_minor"]))
        await conn.execute("INSERT INTO order_events(order_id, from_status, to_status) VALUES (%s,NULL,'pending')",
                           (oid,))

    try:
        outcome = store.gateway_outcome(req["payment"]["token"])
        if outcome != "success":
            await _release(items)
            async with db.tx() as conn:
                auth = f"auth_{await db.next_counter(conn, 'auth')}" if outcome == "capture_fail" else None
                await conn.execute("INSERT INTO payments(order_id, authorization_id, state) VALUES (%s,%s,%s)",
                                   (oid, auth, "voided" if auth else "declined"))
                await conn.execute("INSERT INTO order_events(order_id, from_status, to_status) "
                                   "VALUES (%s,'pending','cancelled')", (oid,))
                await conn.execute("DELETE FROM orders WHERE order_id=%s", (oid,))  # failures are re-evaluated
            await realtime.emit_domain_event("order.status_changed",
                                             {"order_id": oid, "from": "pending", "to": "cancelled", "reason": outcome})
            raise store.gateway_error(outcome, oid)

        paid_at = now_ts()
        receipt, pdf = store.build_receipt(oid, req["customer_id"], priced, paid_at)
        receipt["pdf_base64"] = base64.b64encode(pdf).decode("ascii")
        async with db.tx() as conn:
            auth = f"auth_{await db.next_counter(conn, 'auth')}"
            cap = f"cap_{await db.next_counter(conn, 'cap')}"
            for it in sorted(items, key=lambda x: x["variant_id"]):
                await conn.execute("UPDATE variants SET reserved = reserved - %s WHERE variant_id=%s",
                                   (it["quantity"], it["variant_id"]))
            resp = {"order_id": oid, "status": "paid", "currency": store.CURRENCY, "items": priced["items"],
                    "subtotal_minor": priced["subtotal_minor"], "discount_minor": priced["discount_minor"],
                    "total_minor": priced["total_minor"],
                    "payment": {"authorization_id": auth, "capture_id": cap, "state": "captured"},
                    "receipt": receipt}
            await conn.execute("UPDATE orders SET status='paid', response=%s WHERE order_id=%s", (db.dj(resp), oid))
            await conn.execute("INSERT INTO payments(order_id, authorization_id, capture_id, state) "
                               "VALUES (%s,%s,%s,'captured')", (oid, auth, cap))
            await conn.execute("INSERT INTO order_events(order_id, from_status, to_status) "
                               "VALUES (%s,'pending','paid')", (oid,))
    except ApiError:
        raise
    except Exception:
        log.exception("checkout %s failed after reservation; releasing", oid)
        await _release(items)
        async with db.tx() as conn:
            await conn.execute("DELETE FROM orders WHERE order_id=%s AND response IS NULL", (oid,))
        raise

    await realtime.emit_domain_event("order.status_changed",
                                     {"order_id": oid, "from": "pending", "to": "paid", "at": paid_at})
    storage.put_receipt_background(oid, pdf)
    return 201, resp


async def inventory(variant_id: str) -> dict:
    async with db.tx() as conn:
        row = await db.fetchone(conn, "SELECT variant_id, stock, reserved FROM variants WHERE variant_id=%s",
                                (variant_id,))
    if row is None:
        raise not_found("VARIANT_NOT_FOUND", f"Variant {variant_id} does not exist.", variant_id=variant_id)
    return {"variant_id": row["variant_id"], "stock": row["stock"], "reserved": row["reserved"]}
