"""Merchandise store domain (FR-2.3): validation, pricing, mock gateway, receipt, PDF, order state machine."""
from fpdf import FPDF

from ..canonical import sign
from ..errors import ApiError
from ..validation import Fields, is_id, is_int

CURRENCY = "PKR"
GATEWAY_TOKENS = {"tok_success": "success", "tok_declined": "declined", "tok_capture_fail": "capture_fail"}

ORDER_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"packed", "cancelled", "refunded"},
    "packed": {"shipped", "refunded"},
    "shipped": {"delivered", "refunded"},
    "delivered": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


def validate_checkout(b: dict) -> dict:
    f = Fields()
    if not is_id(b.get("order_id")):
        f.add("order_id")
    cust = b.get("customer_id")
    if not (isinstance(cust, str) and 1 <= len(cust) <= 256):
        f.add("customer_id")
    items = b.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        f.add("items")
        items = []
    seen = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not is_id(it.get("variant_id")) or it.get("variant_id") in seen:
            f.add("items", f"items.{i}.variant_id")
            continue
        seen.add(it["variant_id"])
        q = it.get("quantity")
        if not (is_int(q) and 1 <= q <= 10):
            f.add("items", f"items.{i}.quantity")
    code = b.get("discount_code")
    if code is not None and not isinstance(code, str):
        f.add("discount_code")
    pay = b.get("payment")
    if not isinstance(pay, dict) or not isinstance(pay.get("token"), str):
        f.add("payment", "payment.token")
    f.check()
    return {"order_id": b["order_id"], "customer_id": cust,
            "items": [{"variant_id": it["variant_id"], "quantity": it["quantity"]} for it in items],
            "discount_code": code, "payment": {"token": pay["token"]}}


def price_items(items: list[dict], unit_prices: dict[str, int], discount_percent: int) -> dict:
    lines = [{"variant_id": it["variant_id"], "quantity": it["quantity"],
              "unit_price_minor": unit_prices[it["variant_id"]]} for it in items]
    subtotal = sum(line["quantity"] * line["unit_price_minor"] for line in lines)
    discount = subtotal * discount_percent // 100
    return {"items": lines, "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": subtotal - discount}


def gateway_outcome(token: str) -> str:
    """Mock payment gateway: authorization + capture simulation. Unknown tokens are declined."""
    return GATEWAY_TOKENS.get(token, "declined")


def gateway_error(outcome: str, order_id: str) -> ApiError:
    if outcome == "capture_fail":
        return ApiError(402, "PAYMENT_CAPTURE_FAILED", "Payment was authorized but capture failed; nothing was charged.",
                        {"order_id": order_id})
    return ApiError(402, "PAYMENT_DECLINED", "The payment was declined.", {"order_id": order_id})


def format_pkr(minor: int) -> str:
    return f"PKR {minor // 100}.{minor % 100:02d}"


def receipt_payload(order_id: str, customer_id: str, priced: dict, paid_at: str) -> dict:
    return {"order_id": order_id, "customer_id": customer_id, "items": priced["items"],
            "subtotal_minor": priced["subtotal_minor"], "discount_minor": priced["discount_minor"],
            "total_minor": priced["total_minor"], "currency": CURRENCY, "paid_at": paid_at}


def _pdf_text(s) -> str:
    # Core PDF fonts are latin-1 only; the stored/returned data keeps the original string.
    return str(s).encode("latin-1", "replace").decode("latin-1")


def render_receipt_pdf(payload: dict, signature: str, store_name: str = "NaSCon Club Store") -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, _pdf_text(store_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Payment receipt", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.cell(0, 7, _pdf_text(f"Order ID: {payload['order_id']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, _pdf_text(f"Customer: {payload['customer_id']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, _pdf_text(f"Paid at: {payload['paid_at']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 8, "Item", border="B")
    pdf.cell(25, 8, "Qty", border="B", align="R")
    pdf.cell(35, 8, "Unit", border="B", align="R")
    pdf.cell(40, 8, "Line total", border="B", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for line in payload["items"]:
        pdf.cell(90, 8, _pdf_text(line["variant_id"]))
        pdf.cell(25, 8, str(line["quantity"]), align="R")
        pdf.cell(35, 8, format_pkr(line["unit_price_minor"]), align="R")
        pdf.cell(40, 8, format_pkr(line["unit_price_minor"] * line["quantity"]), align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.cell(150, 8, "Subtotal", align="R")
    pdf.cell(40, 8, format_pkr(payload["subtotal_minor"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(150, 8, "Discount", align="R")
    pdf.cell(40, 8, format_pkr(payload["discount_minor"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(150, 10, "Total", align="R")
    pdf.cell(40, 10, format_pkr(payload["total_minor"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(0, 5, f"HMAC-SHA256 signature: {signature}")
    return bytes(pdf.output())


def build_receipt(order_id: str, customer_id: str, priced: dict, paid_at: str) -> tuple[dict, bytes]:
    payload = receipt_payload(order_id, customer_id, priced, paid_at)
    signature = sign(order_id, payload)
    return {"payload": payload, "signature": signature}, render_receipt_pdf(payload, signature)


def can_transition(current: str, target: str) -> bool:
    return target in ORDER_TRANSITIONS.get(current, set())
