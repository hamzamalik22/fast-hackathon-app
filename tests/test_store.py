"""FR-2.3 store: checkout validation, pricing, mock gateway, signed receipt + PDF, order state machine."""
import re
import zlib

import pytest

from app.canonical import sign
from app.domain import store
from app.errors import ApiError

BODY = {"order_id": "ord-001", "customer_id": "cust-001", "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}],
        "discount_code": None, "payment": {"token": "tok_success"}}


def pdf_text(pdf: bytes) -> bytes:
    out = pdf
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            out += zlib.decompress(m.group(1))
        except zlib.error:
            pass
    return out


def test_validate_checkout_ok():
    req = store.validate_checkout({**BODY, "extra": 1})
    assert req["items"] == [{"variant_id": "var-jersey-001-M", "quantity": 1}] and "extra" not in req


@pytest.mark.parametrize("patch,field", [
    ({"order_id": "a|b"}, "order_id"), ({"customer_id": ""}, "customer_id"), ({"items": []}, "items"),
    ({"items": [{"variant_id": "v", "quantity": 0}]}, "items.0.quantity"),
    ({"items": [{"variant_id": "v", "quantity": True}]}, "items.0.quantity"),
    ({"items": [{"variant_id": "v", "quantity": 1}, {"variant_id": "v", "quantity": 1}]}, "items.1.variant_id"),
    ({"items": [{"variant_id": "v", "quantity": 1}] * 11}, "items"), ({"discount_code": 10}, "discount_code"),
    ({"payment": {}}, "payment.token"),
])
def test_validate_checkout_errors(patch, field):
    with pytest.raises(ApiError) as e:
        store.validate_checkout({**BODY, **patch})
    assert e.value.code == "VALIDATION_ERROR" and field in e.value.details["fields"]


def test_pricing_discount_floor():
    priced = store.price_items([{"variant_id": "a", "quantity": 3}], {"a": 33333}, 10)
    assert priced == {"items": [{"variant_id": "a", "quantity": 3, "unit_price_minor": 33333}],
                      "subtotal_minor": 99999, "discount_minor": 9999, "total_minor": 90000}


def test_gateway():
    assert store.gateway_outcome("tok_success") == "success"
    assert store.gateway_outcome("tok_declined") == "declined"
    assert store.gateway_outcome("tok_capture_fail") == "capture_fail"
    assert store.gateway_outcome("anything") == "declined"
    assert store.gateway_error("capture_fail", "o").code == "PAYMENT_CAPTURE_FAILED"
    assert store.gateway_error("declined", "o").status == 402 and store.gateway_error("declined", "o").code == "PAYMENT_DECLINED"


def test_receipt_signature_and_pdf():
    priced = store.price_items([{"variant_id": "var-jersey-001-M", "quantity": 1}], {"var-jersey-001-M": 450000}, 0)
    receipt, pdf = store.build_receipt("ord-001", "c'\"<script>ü", priced, "2026-10-17T11:20:05Z")
    assert receipt["payload"] == {"order_id": "ord-001", "customer_id": "c'\"<script>ü",
                                  "items": [{"variant_id": "var-jersey-001-M", "quantity": 1, "unit_price_minor": 450000}],
                                  "subtotal_minor": 450000, "discount_minor": 0, "total_minor": 450000, "currency": "PKR",
                                  "paid_at": "2026-10-17T11:20:05Z"}
    assert receipt["signature"] == sign("ord-001", receipt["payload"])
    text = pdf_text(pdf)
    assert pdf.startswith(b"%PDF") and b"ord-001" in text and b"PKR 4500.00" in text
    assert store.format_pkr(5) == "PKR 0.05" and store.format_pkr(123456789) == "PKR 1234567.89"


def test_order_state_machine():
    assert store.can_transition("pending", "paid") and store.can_transition("paid", "packed")
    assert store.can_transition("shipped", "delivered") and store.can_transition("delivered", "refunded")
    assert not store.can_transition("refunded", "paid") and not store.can_transition("pending", "shipped")
    assert not store.can_transition("nope", "paid")
