"""Optional softmax policy for offline experiments. The API always uses the baseline."""
from math import isfinite

import numpy as np
from scipy.special import softmax

from .policy import MODES
from .schemas import Context

FEATURES = (
    "urgency", "deadline_hours", "workload", "reported_fatigue",
    "risk", "reversible", "strategic_relevance",
)


def probabilities(context: Context, coefficients: dict[str, dict[str, float]]) -> dict[str, float]:
    if set(coefficients) != set(MODES):
        raise ValueError("Provide coefficients for all three modes")
    features = {"intercept": 1.0}
    for name in FEATURES:
        value = getattr(context, name)
        features[f"{name}_known"] = float(value is not None)
        features[name] = 0.0 if value is None else float(value)

    rows = []
    for mode in MODES:
        weights = coefficients[mode]
        if weights.keys() - features.keys() or not all(isfinite(w) for w in weights.values()):
            raise ValueError("Coefficients must use supported features and finite numbers")
        rows.append([weights.get(name, 0.0) for name in features])
    with np.errstate(over="ignore", invalid="ignore"):
        logits = np.asarray(rows, dtype=float) @ np.asarray(list(features.values()))
    if not np.isfinite(logits).all():
        raise ValueError("Nonfinite logits")
    with np.errstate(over="ignore"):
        return dict(zip(MODES, softmax(logits).tolist(), strict=True))
