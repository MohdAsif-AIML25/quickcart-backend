import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from app.models import (
    DELETABLE_ORDER_STATUSES,
    ORDER_STATUS_TRANSITIONS,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)

# Shown in the UI as "unavailable"; rejected here with a clear reason
UNAVAILABLE_PAYMENT_METHODS = {"upi", "card"}

_PHONE_SEPARATORS = re.compile(r"[\s\-().]")
_PHONE = re.compile(r"^\+?\d{7,15}$")  # E.164 allows at most 15 digits
_COUNTRY = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")
_POSTAL_CODE = re.compile(r"^[A-Z0-9][A-Z0-9 \-]*[A-Z0-9]$")
_INDIA_PIN_CODE = re.compile(r"^[1-9]\d{5}$")


def _text(min_length: int, max_length: int) -> type[str]:
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


class ShippingAddress(BaseModel):
    """Where the order is delivered. Validated here, then copied onto the order."""

    model_config = ConfigDict(extra="forbid")

    recipient_name: _text(2, 100) = Field(examples=["Asha Verma"])
    phone: _text(7, 25) = Field(
        description="7 to 15 digits, optionally starting with +. Spaces and hyphens are removed.",
        examples=["+91 98765 43210"],
    )
    address_line1: _text(3, 200) = Field(examples=["221B MG Road"])
    address_line2: str | None = Field(default=None, max_length=200, examples=["Near City Mall"])
    city: _text(2, 100) = Field(examples=["Bengaluru"])
    state: _text(2, 100) = Field(examples=["Karnataka"])
    # Declared before postal_code: the postal code rule depends on the country
    country: _text(2, 60) = Field(examples=["India"])
    postal_code: _text(3, 12) = Field(
        description="For India: a 6-digit PIN code.", examples=["560001"]
    )

    @field_validator("recipient_name", "city", "state")
    @classmethod
    def must_contain_a_letter(cls, value: str) -> str:
        if not any(char.isalpha() for char in value):
            raise ValueError("Must contain at least one letter")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = _PHONE_SEPARATORS.sub("", value)
        if not _PHONE.fullmatch(digits):
            raise ValueError("Enter a valid phone number: 7 to 15 digits, optionally starting with +")
        return digits

    @field_validator("address_line2")
    @classmethod
    def blank_line2_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("country")
    @classmethod
    def country_is_a_name(cls, value: str) -> str:
        if not _COUNTRY.fullmatch(value):
            raise ValueError("Enter a country name using letters only")
        return value

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code(cls, value: str, info: ValidationInfo) -> str:
        value = value.upper()
        if not _POSTAL_CODE.fullmatch(value):
            raise ValueError("Enter a valid postal code (letters, digits, spaces and hyphens only)")
        # info.data has no "country" when the country itself was invalid
        if info.data.get("country", "").casefold() == "india" and not _INDIA_PIN_CODE.fullmatch(value):
            raise ValueError("Enter a valid 6-digit PIN code")
        return value


class CheckoutRequest(BaseModel):
    # extra="forbid": card numbers or any other unexpected field are rejected, not ignored
    model_config = ConfigDict(extra="forbid")

    shipping_address: ShippingAddress
    payment_method: PaymentMethod = Field(
        description="Only `cod` (Cash on Delivery) is accepted. No payment gateway is integrated."
    )

    @field_validator("payment_method", mode="before")
    @classmethod
    def explain_unavailable_methods(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() in UNAVAILABLE_PAYMENT_METHODS:
            raise ValueError(
                f"Payment by {value.strip().lower()} is not available: no payment gateway is "
                "integrated yet. Choose Cash on Delivery (cod)."
            )
        return value


class AdminOrderUpdate(BaseModel):
    """PATCH body: send `status`, `estimated_delivery_date`, or both."""

    model_config = ConfigDict(extra="forbid")

    status: OrderStatus | None = None
    estimated_delivery_date: date | None = Field(
        default=None, description="Send null to clear the date.", examples=["2026-10-15"]
    )

    @model_validator(mode="after")
    def require_a_change(self) -> "AdminOrderUpdate":
        if not self.model_fields_set:
            raise ValueError("Send status, estimated_delivery_date, or both")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class ShippingAddressRead(BaseModel):
    recipient_name: str
    phone: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    country: str
    postal_code: str


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime
    payment_method: PaymentMethod | None = Field(
        description="null for orders placed before payment information was recorded"
    )
    payment_status: PaymentStatus | None = Field(
        description="Independent from `status`. null for orders placed before it was recorded."
    )
    shipping_address: ShippingAddressRead | None = Field(
        description="null for orders placed before delivery addresses were collected"
    )
    estimated_delivery_date: date | None = Field(description="null until an admin schedules it")
    delivered_at: datetime | None = Field(description="Set when the order becomes `delivered`")
    items: list[OrderItemRead]


class AdminOrderRead(OrderRead):
    user_id: int

    @computed_field
    @property
    def allowed_next_statuses(self) -> list[OrderStatus]:
        """The statuses this order may move to next (empty for a final status)."""
        return sorted(ORDER_STATUS_TRANSITIONS[self.status], key=list(OrderStatus).index)

    @computed_field
    @property
    def can_delete(self) -> bool:
        return self.status in DELETABLE_ORDER_STATUSES
