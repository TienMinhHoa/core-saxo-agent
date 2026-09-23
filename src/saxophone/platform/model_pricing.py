"""Conservative token-cost estimates for direct provider models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


_MILLION = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class ModelTokenPrice:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    basis: str


# Pricing snapshot: 2026-09-23.
# DeepSeek uses peak rates so logs remain a conservative upper-bound estimate.
# Sources:
# https://api-docs.deepseek.com/quick_start/pricing
# https://developers.openai.com/api/docs/pricing
_MODEL_PRICES = {
    "deepseek-flash": ModelTokenPrice(
        input_usd_per_million=Decimal("0.30"),
        output_usd_per_million=Decimal("1.20"),
        cached_input_usd_per_million=Decimal("0.006"),
        basis="deepseek-peak-2026-09-23",
    ),
    "text-embedding-3-small": ModelTokenPrice(
        input_usd_per_million=Decimal("0.02"),
        output_usd_per_million=Decimal("0"),
        cached_input_usd_per_million=Decimal("0.02"),
        basis="openai-standard-2026-09-23",
    ),
}


def estimate_model_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float | None:
    """Estimate one provider call without hiding unsupported model pricing."""

    _validate_token_count(input_tokens, "input_tokens")
    _validate_token_count(output_tokens, "output_tokens")
    _validate_token_count(cached_input_tokens, "cached_input_tokens")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached_input_tokens must not exceed input_tokens")
    price = _MODEL_PRICES.get(model)
    if price is None:
        return None
    uncached_input_tokens = input_tokens - cached_input_tokens
    cost = (
        Decimal(uncached_input_tokens) * price.input_usd_per_million
        + Decimal(cached_input_tokens) * price.cached_input_usd_per_million
        + Decimal(output_tokens) * price.output_usd_per_million
    ) / _MILLION
    return float(cost)


def pricing_basis_for_model(model: str) -> str | None:
    price = _MODEL_PRICES.get(model)
    return None if price is None else price.basis


def _validate_token_count(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
