"""Numeric precision guards for financial calculations.

This module provides precision-safe arithmetic for financial data processing
in LedgerLens. Stellar uses 7 decimal places (stroops), and fraud detection
requires exact decimal arithmetic to avoid floating-point errors that could
mask anomalies or produce false positives.

Key Features
------------
- Decimal arithmetic (no floating-point errors)
- Stellar stroops conversion (7 decimal places)
- Amount validation with configurable bounds
- Overflow/underflow protection
- Precision context management
- Type-safe operations

Architecture
------------
The system uses Python's `decimal.Decimal` for all financial calculations,
with validation at data ingestion boundaries and context managers for
controlling precision throughout the pipeline.

Usage
-----
Basic decimal amounts::

    from utils.decimal_guards import DecimalAmount, validate_amount

    # Create validated amount
    amount = DecimalAmount("123.4567890")

    # Arithmetic operations
    total = amount + DecimalAmount("10.5")

    # Stellar stroops conversion
    stroops = amount.to_stroops()  # 1234567890 (integer)
    recovered = DecimalAmount.from_stroops(stroops)

Validation::

    # Validate at ingestion boundary
    validate_amount("123.45", min_value="0", max_value="1000000")

    # Custom precision
    with decimal_context(precision=28):
        result = DecimalAmount("0.1") + DecimalAmount("0.2")

Stellar Integration
-------------------
Stellar represents amounts as signed 64-bit integers in stroops (10^-7).
The valid range is [-922337203685.4775808, 922337203685.4775807].

See: https://developers.stellar.org/docs/fundamentals-and-concepts/stellar-data-structures/assets
"""

from __future__ import annotations

import decimal
import warnings
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stellar precision: 7 decimal places (1 stroop = 10^-7 XLM)
STELLAR_PRECISION = 7
STROOPS_MULTIPLIER = Decimal(10) ** STELLAR_PRECISION

# Stellar amount bounds (signed 64-bit integer in stroops)
# Maximum: 9223372036854775807 stroops = 922337203685.4775807 XLM
STELLAR_MAX_AMOUNT = Decimal("922337203685.4775807")
STELLAR_MIN_AMOUNT = Decimal("-922337203685.4775807")

# Default precision context (28 digits, same as Python default)
DEFAULT_PRECISION = 28

# Maximum safe precision to prevent memory exhaustion
MAX_SAFE_PRECISION = 100


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PrecisionError(Exception):
    """Base exception for precision-related errors."""


class AmountValidationError(PrecisionError):
    """Raised when an amount fails validation."""


class PrecisionOverflowError(PrecisionError):
    """Raised when a calculation would overflow."""


class PrecisionUnderflowError(PrecisionError):
    """Raised when a value is too small to represent."""


class StroopsConversionError(PrecisionError):
    """Raised when stroops conversion fails."""


# ---------------------------------------------------------------------------
# Precision Context Management
# ---------------------------------------------------------------------------


@contextmanager
def decimal_context(
    precision: int = DEFAULT_PRECISION,
    rounding: str = decimal.ROUND_HALF_EVEN,
):
    """Context manager for controlling decimal precision.

    Args:
        precision: Number of significant digits (default: 28)
        rounding: Rounding mode (default: ROUND_HALF_EVEN / banker's rounding)

    Yields:
        decimal.Context: Active decimal context

    Example::

        with decimal_context(precision=10):
            result = DecimalAmount("1") / DecimalAmount("3")
            # result = 0.3333333333 (10 digits)
    """
    if precision > MAX_SAFE_PRECISION:
        warnings.warn(
            f"Precision {precision} exceeds MAX_SAFE_PRECISION ({MAX_SAFE_PRECISION}). "
            "This may cause performance issues.",
            stacklevel=2,
        )

    old_context = decimal.getcontext()
    new_context = decimal.Context(
        prec=precision,
        rounding=rounding,
        traps=[
            decimal.InvalidOperation,
            decimal.DivisionByZero,
            decimal.Overflow,
        ],
    )

    decimal.setcontext(new_context)
    try:
        yield new_context
    finally:
        decimal.setcontext(old_context)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_amount(
    value: str | int | float | Decimal,
    min_value: str | Decimal | None = None,
    max_value: str | Decimal | None = None,
    allow_negative: bool = False,
    name: str = "amount",
) -> Decimal:
    """Validate and convert a value to Decimal.

    Args:
        value: Value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        allow_negative: Whether negative values are allowed
        name: Field name for error messages

    Returns:
        Validated Decimal value

    Raises:
        AmountValidationError: If validation fails

    Example::

        # Validate positive amount
        amount = validate_amount("123.45", min_value="0", max_value="1000000")

        # Allow negative (for deltas)
        delta = validate_amount("-50.00", allow_negative=True)
    """
    # Convert to Decimal
    try:
        if isinstance(value, float):
            warnings.warn(
                f"Converting float to Decimal for {name}. "
                "Float inputs may have precision errors. "
                "Use string or Decimal instead.",
                stacklevel=2,
            )
            decimal_value = Decimal(str(value))
        else:
            decimal_value = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise AmountValidationError(
            f"Invalid {name}: {value!r} cannot be converted to Decimal"
        ) from e

    # Check for special values
    if decimal_value.is_nan():
        raise AmountValidationError(f"Invalid {name}: NaN is not allowed")

    if decimal_value.is_infinite():
        raise AmountValidationError(f"Invalid {name}: Infinity is not allowed")

    # Check sign
    if not allow_negative and decimal_value < 0:
        raise AmountValidationError(f"Invalid {name}: {decimal_value} is negative (not allowed)")

    # Check bounds
    if min_value is not None:
        min_decimal = Decimal(min_value)
        if decimal_value < min_decimal:
            raise AmountValidationError(f"Invalid {name}: {decimal_value} < minimum {min_decimal}")

    if max_value is not None:
        max_decimal = Decimal(max_value)
        if decimal_value > max_decimal:
            raise AmountValidationError(f"Invalid {name}: {decimal_value} > maximum {max_decimal}")

    return decimal_value


def validate_stellar_amount(value: str | int | float | Decimal) -> Decimal:
    """Validate an amount for Stellar blockchain.

    Stellar amounts must be within [-922337203685.4775807, 922337203685.4775807]
    and have at most 7 decimal places.

    Args:
        value: Amount to validate

    Returns:
        Validated Decimal value

    Raises:
        AmountValidationError: If validation fails
    """
    decimal_value = validate_amount(
        value,
        min_value=STELLAR_MIN_AMOUNT,
        max_value=STELLAR_MAX_AMOUNT,
        allow_negative=True,
        name="stellar_amount",
    )

    if isinstance(value, float):
        quantizer = Decimal(10) ** -STELLAR_PRECISION
        decimal_value = decimal_value.quantize(quantizer, rounding=decimal.ROUND_HALF_EVEN)

    # Check decimal places
    if decimal_value.as_tuple().exponent < -STELLAR_PRECISION:
        raise AmountValidationError(
            f"Invalid stellar_amount: {decimal_value} has more than "
            f"{STELLAR_PRECISION} decimal places"
        )

    return decimal_value


# ---------------------------------------------------------------------------
# DecimalAmount Class
# ---------------------------------------------------------------------------


class DecimalAmount:
    """Precision-safe decimal amount for financial calculations.

    This class wraps Python's Decimal to provide:
    - Type-safe arithmetic operations
    - Automatic validation
    - Stellar stroops conversion
    - Comparison operators
    - String/repr for debugging

    Attributes:
        value: The underlying Decimal value

    Example::

        amount1 = DecimalAmount("100.50")
        amount2 = DecimalAmount("25.25")

        total = amount1 + amount2  # DecimalAmount("125.75")
        ratio = amount1 / amount2  # DecimalAmount("3.9801980198...")

        # Stellar conversion
        stroops = amount1.to_stroops()  # 1005000000
        recovered = DecimalAmount.from_stroops(stroops)  # "100.5000000"
    """

    __slots__ = ("_value",)

    def __init__(self, value: str | int | Decimal | DecimalAmount):
        """Initialize DecimalAmount.

        Args:
            value: Amount value (string, int, Decimal, or DecimalAmount)

        Raises:
            AmountValidationError: If value is invalid
        """
        if isinstance(value, DecimalAmount):
            self._value = value._value
        elif isinstance(value, float):
            warnings.warn(
                "DecimalAmount initialized with float. "
                "Float inputs may have precision errors. "
                "Use string or Decimal instead.",
                stacklevel=2,
            )
            self._value = Decimal(str(value))
        else:
            # DecimalAmount is also used for deltas, balances, and
            # counterfactual differences, so signed values are valid here.
            self._value = validate_amount(value, allow_negative=True, name="amount")

    @property
    def value(self) -> Decimal:
        """Get the underlying Decimal value."""
        return self._value

    # -----------------------------------------------------------------------
    # Arithmetic Operations
    # -----------------------------------------------------------------------

    def __add__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Add two amounts."""
        other_value = self._to_decimal(other)
        return DecimalAmount(self._value + other_value)

    def __radd__(self, other: str | int | Decimal) -> DecimalAmount:
        """Reverse add."""
        return self.__add__(other)

    def __sub__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Subtract two amounts."""
        other_value = self._to_decimal(other)
        return DecimalAmount(self._value - other_value)

    def __rsub__(self, other: str | int | Decimal) -> DecimalAmount:
        """Reverse subtract."""
        other_value = self._to_decimal(other)
        return DecimalAmount(other_value - self._value)

    def __mul__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Multiply two amounts."""
        other_value = self._to_decimal(other)
        return DecimalAmount(self._value * other_value)

    def __rmul__(self, other: str | int | Decimal) -> DecimalAmount:
        """Reverse multiply."""
        return self.__mul__(other)

    def __truediv__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Divide two amounts."""
        other_value = self._to_decimal(other)
        if other_value == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return DecimalAmount(self._value / other_value)

    def __rtruediv__(self, other: str | int | Decimal) -> DecimalAmount:
        """Reverse divide."""
        other_value = self._to_decimal(other)
        if self._value == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return DecimalAmount(other_value / self._value)

    def __floordiv__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Floor division."""
        other_value = self._to_decimal(other)
        if other_value == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return DecimalAmount(self._value // other_value)

    def __mod__(self, other: DecimalAmount | str | int | Decimal) -> DecimalAmount:
        """Modulo operation."""
        other_value = self._to_decimal(other)
        if other_value == 0:
            raise ZeroDivisionError("Cannot modulo by zero")
        return DecimalAmount(self._value % other_value)

    def __pow__(self, exponent: int | Decimal) -> DecimalAmount:
        """Power operation."""
        if isinstance(exponent, DecimalAmount):
            exponent = exponent._value
        elif not isinstance(exponent, (int, Decimal)):
            exponent = Decimal(exponent)
        return DecimalAmount(self._value**exponent)

    def __neg__(self) -> DecimalAmount:
        """Negation."""
        return DecimalAmount(-self._value)

    def __pos__(self) -> DecimalAmount:
        """Positive (no-op)."""
        return DecimalAmount(self._value)

    def __abs__(self) -> DecimalAmount:
        """Absolute value."""
        return DecimalAmount(abs(self._value))

    # -----------------------------------------------------------------------
    # Comparison Operations
    # -----------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, (DecimalAmount, str, int, Decimal)):
            return NotImplemented
        other_value = self._to_decimal(other)
        return self._value == other_value

    def __ne__(self, other: object) -> bool:
        """Inequality comparison."""
        return not self.__eq__(other)

    def __lt__(self, other: DecimalAmount | str | int | Decimal) -> bool:
        """Less than."""
        other_value = self._to_decimal(other)
        return self._value < other_value

    def __le__(self, other: DecimalAmount | str | int | Decimal) -> bool:
        """Less than or equal."""
        other_value = self._to_decimal(other)
        return self._value <= other_value

    def __gt__(self, other: DecimalAmount | str | int | Decimal) -> bool:
        """Greater than."""
        other_value = self._to_decimal(other)
        return self._value > other_value

    def __ge__(self, other: DecimalAmount | str | int | Decimal) -> bool:
        """Greater than or equal."""
        other_value = self._to_decimal(other)
        return self._value >= other_value

    def __hash__(self) -> int:
        """Hash for use in sets/dicts."""
        return hash(self._value)

    # -----------------------------------------------------------------------
    # Stellar Stroops Conversion
    # -----------------------------------------------------------------------

    def to_stroops(self) -> int:
        """Convert to Stellar stroops (integer with 7 decimal places).

        Returns:
            Integer stroops value

        Raises:
            StroopsConversionError: If conversion fails or value out of range

        Example::

            amount = DecimalAmount("100.5000000")
            stroops = amount.to_stroops()  # 1005000000
        """
        # Validate first
        try:
            validate_stellar_amount(self._value)
        except AmountValidationError as e:
            if self._value.as_tuple().exponent < -STELLAR_PRECISION:
                raise StroopsConversionError(
                    f"Cannot convert {self._value} to stroops: fractional stroops are not allowed"
                ) from e
            raise StroopsConversionError(f"Cannot convert {self._value} to stroops: {e}") from e

        # Convert to stroops
        stroops_decimal = self._value * STROOPS_MULTIPLIER
        stroops_int = int(stroops_decimal)

        # Verify no precision loss
        if Decimal(stroops_int) != stroops_decimal:
            raise StroopsConversionError(
                f"Precision loss in stroops conversion: {self._value} " f"has fractional stroops"
            )

        return stroops_int

    @classmethod
    def from_stroops(cls, stroops: int) -> DecimalAmount:
        """Create DecimalAmount from Stellar stroops.

        Args:
            stroops: Integer stroops value

        Returns:
            DecimalAmount

        Raises:
            StroopsConversionError: If conversion fails

        Example::

            stroops = 1005000000
            amount = DecimalAmount.from_stroops(stroops)  # "100.5000000"
        """
        if not isinstance(stroops, int):
            raise StroopsConversionError(
                f"Stroops must be an integer, got {type(stroops).__name__}"
            )

        decimal_value = Decimal(stroops) / STROOPS_MULTIPLIER

        # Validate result
        try:
            validate_stellar_amount(decimal_value)
        except AmountValidationError as e:
            raise StroopsConversionError(f"Invalid stroops value {stroops}: {e}") from e

        return cls(decimal_value)

    # -----------------------------------------------------------------------
    # Utility Methods
    # -----------------------------------------------------------------------

    def round(self, decimal_places: int = STELLAR_PRECISION) -> DecimalAmount:
        """Round to specified decimal places.

        Args:
            decimal_places: Number of decimal places (default: 7 for Stellar)

        Returns:
            Rounded DecimalAmount
        """
        quantizer = Decimal(10) ** -decimal_places
        rounded = self._value.quantize(quantizer, rounding=decimal.ROUND_HALF_EVEN)
        return DecimalAmount(rounded)

    def to_float(self) -> float:
        """Convert to float (may lose precision).

        Warning:
            This method is provided for compatibility with legacy code and
            should be avoided when precision is critical.

        Returns:
            Float representation (may have precision loss)
        """
        warnings.warn(
            "Converting DecimalAmount to float may lose precision. "
            "Use Decimal operations when possible.",
            stacklevel=2,
        )
        return float(self._value)

    def is_zero(self) -> bool:
        """Check if amount is exactly zero."""
        return self._value == 0

    def is_positive(self) -> bool:
        """Check if amount is positive (> 0)."""
        return self._value > 0

    def is_negative(self) -> bool:
        """Check if amount is negative (< 0)."""
        return self._value < 0

    @staticmethod
    def _to_decimal(value: DecimalAmount | str | int | Decimal) -> Decimal:
        """Convert value to Decimal."""
        if isinstance(value, DecimalAmount):
            return value._value
        elif isinstance(value, Decimal):
            return value
        else:
            return Decimal(value)

    # -----------------------------------------------------------------------
    # String Representation
    # -----------------------------------------------------------------------

    def __str__(self) -> str:
        """String representation."""
        return str(self._value)

    def __repr__(self) -> str:
        """Developer representation."""
        return f"DecimalAmount('{self._value}')"

    def __format__(self, format_spec: str) -> str:
        """Custom formatting."""
        return format(self._value, format_spec)


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def safe_divide(
    numerator: DecimalAmount | str | int | Decimal,
    denominator: DecimalAmount | str | int | Decimal,
    default: DecimalAmount | str | int | Decimal | None = None,
) -> DecimalAmount:
    """Safe division with zero handling.

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Value to return if denominator is zero (default: DecimalAmount("0"))

    Returns:
        Division result or default if division by zero

    Example::

        # Safe division
        result = safe_divide("100", "0", default="0")  # Returns DecimalAmount("0")

        # Normal division
        result = safe_divide("100", "5")  # Returns DecimalAmount("20")
    """
    if not isinstance(numerator, DecimalAmount):
        numerator = DecimalAmount(numerator)

    if not isinstance(denominator, DecimalAmount):
        denominator = DecimalAmount(denominator)

    if denominator.is_zero():
        if default is None:
            return DecimalAmount("0")
        return DecimalAmount(default) if not isinstance(default, DecimalAmount) else default

    return numerator / denominator


def sum_amounts(amounts: list[DecimalAmount | str | int | Decimal]) -> DecimalAmount:
    """Sum a list of amounts with precision.

    Args:
        amounts: List of amounts to sum

    Returns:
        Sum as DecimalAmount

    Example::

        amounts = [DecimalAmount("100.50"), "25.25", Decimal("10.10")]
        total = sum_amounts(amounts)  # DecimalAmount("135.85")
    """
    if not amounts:
        return DecimalAmount("0")

    total = DecimalAmount("0")
    for amount in amounts:
        if not isinstance(amount, DecimalAmount):
            amount = DecimalAmount(amount)
        total = total + amount

    return total


def safe_float_to_decimal(value: float, precision: int = STELLAR_PRECISION) -> Decimal:
    """Convert float to Decimal with controlled precision.

    This function mitigates float precision errors by:
    1. Converting float to string
    2. Rounding to specified precision
    3. Returning Decimal

    Args:
        value: Float value
        precision: Decimal places to round to (default: 7 for Stellar)

    Returns:
        Decimal with controlled precision

    Example::

        # Float precision issue
        value = 0.1 + 0.2  # 0.30000000000000004

        # Safe conversion
        decimal_value = safe_float_to_decimal(value, precision=2)  # Decimal("0.30")
    """
    warnings.warn(
        "Converting float to Decimal. Float inputs may have precision errors. "
        "Use string or Decimal input for exact precision.",
        stacklevel=2,
    )

    # Convert to string to avoid float representation errors
    str_value = f"{value:.{precision + 2}f}"  # Extra digits for rounding
    decimal_value = Decimal(str_value)

    # Round to desired precision
    quantizer = Decimal(10) ** -precision
    return decimal_value.quantize(quantizer, rounding=decimal.ROUND_HALF_EVEN)


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------


def check_precision_loss(
    original: float | Decimal,
    converted: Decimal,
    tolerance: Decimal = Decimal("1e-10"),
) -> bool:
    """Check if conversion resulted in unacceptable precision loss.

    Args:
        original: Original value
        converted: Converted Decimal value
        tolerance: Maximum acceptable difference

    Returns:
        True if precision loss is within tolerance, False otherwise

    Example::

        original = 0.1 + 0.2  # 0.30000000000000004
        converted = Decimal("0.3")
        is_ok = check_precision_loss(original, converted)  # True (within tolerance)
    """
    original_decimal = Decimal(str(original))
    difference = abs(original_decimal - converted)
    return difference <= tolerance
