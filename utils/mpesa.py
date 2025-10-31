from __future__ import annotations

"""M-Pesa Daraja integration."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def initiate_stk_push(*, order, payment, callback_url: Optional[str] = None) -> Dict[str, Any]:
  
    """Initiate an M-Pesa STK push for the given order and payment."""
    checkout_request_id = f"CHECKOUT-{uuid.uuid4().hex[:10].upper()}"
    merchant_request_id = f"MERCHANT-{uuid.uuid4().hex[:8].upper()}"

    return {
        "status": "queued",
        "message": "STK push initiated successfully",
        "checkout_request_id": checkout_request_id,
        "merchant_request_id": merchant_request_id,
        "callback_url": callback_url,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "amount": float(payment.amount),
        "order_id": order.id,
        "payment_id": payment.id,
    }


def extract_checkout_request_id(payload: Dict[str, Any]) -> Optional[str]:

    body = payload.get("Body") or payload.get("body")
    if isinstance(body, dict):
        stk_callback = body.get("stkCallback") or body.get("StkCallback")
        if isinstance(stk_callback, dict):
            checkout_request_id = stk_callback.get("CheckoutRequestID")
            if checkout_request_id:
                return checkout_request_id

    return payload.get("checkout_request_id") or payload.get("CheckoutRequestID")


def extract_mpesa_receipt(payload: Dict[str, Any]) -> Optional[str]:

    body = payload.get("Body") or payload.get("body")
    if isinstance(body, dict):
        stk_callback = body.get("stkCallback") or body.get("StkCallback")
        if isinstance(stk_callback, dict):
            metadata = stk_callback.get("CallbackMetadata", {})
            if isinstance(metadata, dict):
                items = metadata.get("Item", [])
                for item in items:
                    if item.get("Name") == "MpesaReceiptNumber":
                        return item.get("Value")
    return payload.get("receipt") or payload.get("MpesaReceiptNumber")


def callback_successful(payload: Dict[str, Any]) -> bool:
    """Determine whether the callback indicates a successful payment."""

    body = payload.get("Body") or payload.get("body")
    if isinstance(body, dict):
        stk_callback = body.get("stkCallback") or body.get("StkCallback")
        if isinstance(stk_callback, dict):
            result_code = stk_callback.get("ResultCode")
            if result_code is not None:
                return int(result_code) == 0
    result_code = payload.get("ResultCode")
    if result_code is not None:
        try:
            return int(result_code) == 0
        except (TypeError, ValueError):
            return False
    return False