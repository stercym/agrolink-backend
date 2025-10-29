from __future__ import annotations

"""Utility helpers for delivery-related calculations."""

from decimal import Decimal
from typing import Iterable, Dict, Any


def estimate_delivery_cost(cart_items: Iterable[CartItem], destination: Location | None) -> Dict[str, Any]:
    """Return a delivery cost estimate for the given cart items.
    """

    total_weight = Decimal("0")
    for item in cart_items:
        # Not all products have a weight; fall back to zero for those cases.
        weight_per_unit = Decimal(str(item.product.weight_per_unit or 0))
        total_weight += weight_per_unit * Decimal(item.quantity)

    # Flat-rate strategy with a simple weight-based uplift to illustrate how
    # custom logic can slot in. Replace this with a real distance calculation.
    base_cost = Decimal("50.00")
    weight_surcharge = Decimal("0")
    if total_weight > Decimal("20"):
        weight_surcharge = Decimal("10.00")

    amount = base_cost + weight_surcharge

    return {
        "amount": float(amount),
        "currency": "KES",
        "strategy": "flat-rate-stub",
        "weight_kg": float(total_weight),
        "notes": "Replace with distance-based pricing once a delivery provider is integrated.",
        "destination": destination.to_dict() if destination else None,
    }