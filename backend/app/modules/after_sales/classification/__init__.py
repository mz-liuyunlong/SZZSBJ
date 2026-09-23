"""After-sales reason normalization and responsibility classification."""

from app.modules.after_sales.classification.service import (
    AfterSalesReasonClassifier,
    ClassificationResult,
)

__all__ = ["AfterSalesReasonClassifier", "ClassificationResult"]
