"""Shared regression metrics with explicit IDs, coverage and undefined R²."""

import numpy as np
import pandas as pd


def regression_metrics(y_true, y_pred, *, allow_unavailable=False):
    truth, predicted = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if truth.ndim != 1 or predicted.ndim != 1 or truth.shape != predicted.shape:
        raise ValueError("Expected equally sized 1-D truth/prediction vectors")
    if not np.isfinite(truth).all() or np.isinf(predicted).any():
        raise ValueError("Targets must be observed/finite; predictions cannot be infinite")
    present = ~np.isnan(predicted)
    if not present.all() and not allow_unavailable:
        raise ValueError("Unavailable predictions require explicit coverage reporting")
    n = int(present.sum())
    result = {"n_total": len(truth), "n_scored": n, "unavailable": int((~present).sum()),
              "coverage": n/len(truth) if len(truth) else None, "MAE": None, "RMSE": None,
              "R2": None, "r2_undefined_reason": None}
    if n == 0:
        result["r2_undefined_reason"] = "no_scored_predictions"
        return result
    truth, predicted = truth[present], predicted[present]
    error = predicted-truth
    sse = float(np.sum(error**2))
    sst = float(np.sum((truth-truth.mean())**2))
    if not np.isfinite([sse, sst]).all():
        raise ValueError("Metric sums overflowed")
    result.update(MAE=float(np.mean(np.abs(error))), RMSE=float(np.sqrt(sse/n)))
    if n < 2:
        result["r2_undefined_reason"] = "fewer_than_two_predictions"
    elif sst == 0:
        result["r2_undefined_reason"] = "constant_target"
    else:
        result["R2"] = 1-sse/sst
    return result


def evaluate_predictions(predictions, expected_ids):
    """Require identical IDs/order; report primary and operational separately."""
    required = {"sample_id", "is_primary", "y_true", "y_pred", "prediction_source"}
    if not required.issubset(predictions) or predictions.sample_id.isna().any() or predictions.sample_id.duplicated().any():
        raise ValueError("Missing prediction schema or duplicate ID")
    if predictions.sample_id.tolist() != list(expected_ids):
        raise ValueError("Prediction IDs/order differ from the frozen evaluation cohort")
    results = {}
    for name, group in (("primary", predictions.loc[predictions.is_primary]), ("operational", predictions)):
        values = regression_metrics(group.y_true, group.y_pred, allow_unavailable=True)
        fallback = int(group.prediction_source.ne("persistence").sum())
        values.update(fallback_count=fallback, fallback_rate=fallback/len(group) if len(group) else None)
        results[name] = values
    return results


def grouped_metrics(predictions, column):
    rows = []
    for cohort, group in (("primary", predictions.loc[predictions.is_primary]), ("operational", predictions)):
        for value, part in group.groupby(column, sort=True, observed=True):
            rows.append({"cohort": cohort, column: value, **regression_metrics(part.y_true, part.y_pred, allow_unavailable=True)})
    return pd.DataFrame(rows)
