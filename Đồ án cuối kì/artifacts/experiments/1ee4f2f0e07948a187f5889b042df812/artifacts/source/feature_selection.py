"""Train-fitted grouped coefficient selection after the unchanged T08 encoder."""

from copy import deepcopy

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from beijing_air.features import feature_registry
from beijing_air.preprocessing import make_regression_pipeline


def encoded_groups(names, raw_features):
    groups = []
    for name in names:
        matches = [raw for raw in raw_features if name in (f"numeric__{raw}", f"missing__missingindicator_{raw}")
                   or (raw in ("station", "wd") and name.startswith(f"categorical__{raw}_"))]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous/unmapped encoded feature: {name}")
        groups.append(matches[0])
    return np.asarray(groups, dtype=object)


class GroupRidgeSelector(TransformerMixin, BaseEstimator):
    """Select k raw groups, retaining all indicator/one-hot columns per group.

    Pilot and final model are separate Ridge fits. RMS coefficient scores are
    predictive rankings under this encoding, not causal or scale-free effects.
    """

    def __init__(self, k_groups=20, alpha=0.1, raw_features=()):
        self.k_groups = k_groups
        self.alpha = alpha
        self.raw_features = raw_features

    def fit(self, X, y):
        if (not isinstance(X, pd.DataFrame) or not X.columns.is_unique
                or type(self.k_groups) is not int or not 1 <= self.k_groups <= len(self.raw_features)):
            raise ValueError("Expected encoded DataFrame and valid raw-group count")
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = X.shape[1]
        self.column_groups_ = encoded_groups(X.columns, self.raw_features)
        self.estimator_ = Ridge(alpha=self.alpha).fit(X, y)
        self.group_scores_ = {raw: float(np.sqrt(np.mean(self.estimator_.coef_[self.column_groups_ == raw]**2)))
                              for raw in self.raw_features}
        ranked = sorted(self.raw_features, key=lambda raw: (-self.group_scores_[raw], self.raw_features.index(raw)))
        chosen = set(ranked[:self.k_groups])
        self.selected_groups_ = [raw for raw in self.raw_features if raw in chosen]
        self.dropped_groups_ = [raw for raw in self.raw_features if raw not in chosen]
        self.support_ = np.isin(self.column_groups_, self.selected_groups_)
        return self

    def transform(self, X):
        check_is_fitted(self, "support_")
        if not isinstance(X, pd.DataFrame) or list(X.columns) != self.feature_names_in_.tolist():
            raise ValueError("Encoded feature names/order changed")
        return X.loc[:, self.feature_names_in_[self.support_]].copy()

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "support_")
        if input_features is not None and list(input_features) != self.feature_names_in_.tolist():
            raise ValueError("Unexpected input names")
        return self.feature_names_in_[self.support_].copy()


def make_ablation_pipeline(feature_set, config, prep, *, alpha=0.1, k_groups=None):
    if feature_set not in ("A", "B", "C"):
        raise ValueError("Expected A/B/C")
    effective = deepcopy(config)
    effective["evaluation"]["initial_parameters"]["ridge"] = {"alpha": alpha}
    pipe = make_regression_pipeline("ridge", feature_set="A" if feature_set == "A" else "B", config=effective, preprocessing_config=prep)
    if feature_set == "C":
        raw = tuple(feature_registry(config).feature_name)
        pipe = Pipeline([("preprocess", pipe.named_steps["preprocess"]),
                         ("select", GroupRidgeSelector(k_groups, alpha, raw)), ("model", pipe.named_steps["model"])])
    return pipe


def selection_state(pipe):
    pre, model = pipe.named_steps["preprocess"], pipe.named_steps["model"]
    columns = pre.named_steps["columns"]
    numeric = columns.named_transformers_["numeric"]
    categorical = columns.named_transformers_["categorical"]
    encoded = pre.get_feature_names_out().tolist()
    raw = pre.named_steps["schema"].get_feature_names_out().tolist()
    selector = pipe.named_steps.get("select")
    kept = selector.get_feature_names_out().tolist() if selector else encoded
    return {"artifact_type": "fitted_state_summary_not_serialized_model", "pipeline_class": "sklearn.pipeline.Pipeline",
            "parameters": model.get_params(), "raw_feature_names": raw, "encoded_feature_names": encoded,
            "model_feature_names": kept, "model_dimensions": int(model.n_features_in_), "preprocessing_dimensions": len(encoded),
            "kept_groups": selector.selected_groups_ if selector else raw, "dropped_groups": selector.dropped_groups_ if selector else [],
            "group_scores": selector.group_scores_ if selector else None,
            "column_groups": encoded_groups(encoded, raw).tolist(),
            "pilot_coef": selector.estimator_.coef_.tolist() if selector else None,
            "pilot_parameters": selector.estimator_.get_params() if selector else None,
            "numeric_features": list(columns.transformers_[0][2]),
            "imputer_statistics": numeric.named_steps["impute"].statistics_.tolist(),
            "scaler_mean": numeric.named_steps["scale"].mean_.tolist(),
            "scaler_scale": numeric.named_steps["scale"].scale_.tolist(),
            "categories": [c.tolist() for c in categorical.named_steps["one_hot"].categories_],
            "coef": model.coef_.tolist(), "intercept": float(model.intercept_),
            "fitted_object_hash": joblib.hash(pipe), "weights_saved": False}
