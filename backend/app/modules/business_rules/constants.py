from __future__ import annotations

from decimal import Decimal

# The only backend default fallback for store commission.
# Store-specific rules must come from ref_store_commission_rule_versions.
DEFAULT_STORE_COMMISSION_RATE = Decimal("0.15")
