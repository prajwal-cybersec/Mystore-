"""Business rules and pure policy functions for returns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Delivery lifecycle
DELIVERY_LIFECYCLE = ["placed", "shipped", "out_for_delivery", "delivered"]

# Return windows in days per category
CATEGORY_RETURN_WINDOWS = {
    "Fashion": 10,
    "Electronics": 7,
    "Mobiles": 7,
    "Appliances": 7,
    "Beauty": 3,
    "Food & Health": 3,
}

# Reason codes
REASONS = [
    {"code": "defective", "label": "Defective / Quality Issue", "requires_photos": True},
    {"code": "damaged_in_transit", "label": "Damaged in Transit", "requires_photos": True},
    {"code": "wrong_item", "label": "Wrong Item Received", "requires_photos": True},
    {"code": "not_as_described", "label": "Item Not as Described", "requires_photos": True},
    {"code": "size_fit", "label": "Size / Fit Issue (Fashion only)", "requires_photos": False},
]

VALID_REASON_CODES = {r["code"] for r in REASONS}

# Valid resolutions
RESOLUTIONS = ["refund", "replacement", "exchange"]

# Valid status transitions
TRANSITIONS: Dict[str, List[str]] = {
    "requested": ["approved", "rejected", "cancelled"],
    "approved": ["pickup_scheduled", "cancelled"],
    "pickup_scheduled": ["picked_up"],
    "picked_up": ["received"],
    "received": ["refunded", "replacement_shipped"],
}

# Action to target status mapping for admin
ADMIN_ACTION_MAP: Dict[str, str] = {
    "approve": "approved",
    "reject": "rejected",
    "schedule_pickup": "pickup_scheduled",
    "mark_picked_up": "picked_up",
    "mark_received": "received",
    "issue_refund": "refunded",
    "ship_replacement": "replacement_shipped",
}


def get_category_window_days(category: Optional[str]) -> int:
    """Return window in days for category, default 7."""
    if not category:
        return 7
    for cat_name, days in CATEGORY_RETURN_WINDOWS.items():
        if cat_name.lower() == category.strip().lower():
            return days
    return 7


def is_reason_allowed_for_category(category: Optional[str], reason_code: str) -> Tuple[bool, str]:
    """Check if reason is valid for category."""
    if reason_code not in VALID_REASON_CODES:
        return False, f"Invalid reason code: {reason_code}"

    cat_lower = (category or "").strip().lower()

    # size_fit is Fashion only
    if reason_code == "size_fit" and cat_lower != "fashion":
        return False, "Reason 'size_fit' is only available for Fashion items."

    # Beauty and Food & Health are returnable ONLY for damaged_in_transit or wrong_item
    if cat_lower in ["beauty", "food & health"]:
        if reason_code not in ["damaged_in_transit", "wrong_item"]:
            return False, f"{category} products can only be returned for 'damaged_in_transit' or 'wrong_item'."

    return True, ""


def is_resolution_allowed(category: Optional[str], reason_code: str, resolution: str) -> Tuple[bool, str]:
    """Check resolution validity for product category and reason."""
    if resolution not in RESOLUTIONS:
        return False, f"Invalid resolution: {resolution}. Must be one of {RESOLUTIONS}"

    cat_lower = (category or "").strip().lower()

    if resolution == "exchange":
        if cat_lower != "fashion" or reason_code != "size_fit":
            return False, "Exchange resolution is only available for Fashion items with 'size_fit' reason."

    if resolution == "replacement":
        if cat_lower in ["beauty", "food & health"]:
            return False, f"Replacement is not supported for {category}. Please choose refund."

    return True, ""


def check_return_window(delivered_at: Optional[datetime], category: Optional[str]) -> Tuple[bool, Optional[datetime], str]:
    """Check if the delivered order is still within the category return window."""
    if not delivered_at:
        return False, None, "Order has not been delivered yet."

    window_days = get_category_window_days(category)
    from datetime import timedelta
    deadline = delivered_at + timedelta(days=window_days)
    now = datetime.now(timezone.utc)

    # ensure delivered_at has timezone
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    if now > deadline:
        return False, deadline, f"Return window of {window_days} days expired on {deadline.strftime('%Y-%m-%d %H:%M UTC')}."

    return True, deadline, ""


def validate_photos(reason_code: str, photo_urls: List[str]) -> Tuple[bool, str]:
    """Validate photo requirements."""
    if reason_code == "size_fit":
        return True, ""

    if not photo_urls or len(photo_urls) < 1:
        return False, f"At least 1 photo is required for reason '{reason_code}'."

    if len(photo_urls) > 3:
        return False, "At most 3 photos are allowed."

    return True, ""


def validate_exchange_size(attrs: Any, exchange_size: Optional[str]) -> Tuple[bool, str]:
    """Validate exchange size against product sizes if defined, else up to 16 chars."""
    if not exchange_size or not str(exchange_size).strip():
        return False, "Exchange size must be provided when requesting an exchange."

    sz = str(exchange_size).strip()
    if len(sz) > 16:
        return False, "Exchange size must not exceed 16 characters."

    if isinstance(attrs, dict) and "sizes" in attrs and isinstance(attrs["sizes"], list) and attrs["sizes"]:
        allowed_sizes = [str(s).strip() for s in attrs["sizes"]]
        if sz not in allowed_sizes:
            return False, f"Selected size '{sz}' is not available for this product. Available sizes: {', '.join(allowed_sizes)}"

    return True, ""


def can_transition(current_status: str, next_status: str) -> bool:
    """Check whether status transition is valid according to state machine."""
    allowed = TRANSITIONS.get(current_status, [])
    return next_status in allowed
