"""T08 unfitted sklearn factories for T07 features; no dataset reads or fits.

Training code must fit each returned pipeline only on its permitted train
partition. Validation/inference use transform/predict, never fit_transform.
Numeric/categorical statistics and vocabularies live inside each fitted clone.
Prediction policy is identity for every model; no hidden clipping is applied.
"""

from copy import deepcopy

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from beijing_air.features import feature_registry


MODELS = ("ridge", "random_forest")


class FeatureSchema(TransformerMixin, BaseEstimator):
    """Check the T07 allowlist and normalize missing representations.

    No learned numeric/category statistics. Input column order may differ;
    missing/duplicate/extra columns (including labels/IDs) are rejected.
    Output retains the original row index and registry order. This top-level
    estimator supports sklearn clone, set_output, get_feature_names_out/joblib.
    """

    def __init__(self, feature_names, numeric_features, categorical_features, missing_token="__MISSING__"):
        self.feature_names = feature_names
        self.numeric_features = numeric_features
        self.categorical_features = categorical_features
        self.missing_token = missing_token

    def _validated(self, X):
        if not isinstance(X, pd.DataFrame) or not X.columns.is_unique:
            raise ValueError("Expected a DataFrame with unique T07 feature columns")
        expected, actual = set(self.feature_names), set(X.columns)
        if actual != expected:
            raise ValueError(f"T07 schema mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
        result = X.loc[:, list(self.feature_names)].copy()
        for column in self.numeric_features:
            if pd.api.types.is_bool_dtype(result[column]):
                raise ValueError(f"Boolean is not a numeric T07 measurement/calendar: {column}")
            result[column] = pd.to_numeric(result[column], errors="raise").astype("float64")
            if not np.isfinite(result[column].dropna()).all():
                raise ValueError(f"Nonfinite numeric feature: {column}")
        for column in self.categorical_features:
            observed = result[column].dropna()
            # Python all also accepts an empty observed sequence, independent
            # of pandas StringDtype/Arrow reduction support (Issue #35).
            if not all(isinstance(value, str) for value in observed):
                raise ValueError(f"Categorical values must be strings or missing: {column}")
            if observed.eq(self.missing_token).any():
                raise ValueError(f"Reserved missing category in source values: {column}")
            # sklearn's missing_values=np.nan must see None/pd.NA as np.nan too.
            result[column] = result[column].astype(object).where(result[column].notna(), np.nan)
        return result

    def fit(self, X, y=None):
        self._validated(X)
        self.n_features_in_ = len(self.feature_names)
        self.feature_names_in_ = np.asarray(self.feature_names, dtype=object)
        return self

    def transform(self, X):
        check_is_fitted(self, "feature_names_in_")
        return self._validated(X)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "feature_names_in_")
        if input_features is not None and list(input_features) != list(self.feature_names):
            raise ValueError("input_features must follow the T07 registry")
        return self.feature_names_in_.copy()


def _validate_options(model_name, feature_set, preprocessing_config):
    if model_name not in MODELS or feature_set not in ("A", "B"):
        raise ValueError("Supported model_name: ridge/random_forest; feature_set: A/B (C not selected)")
    cfg = preprocessing_config
    if cfg["schema_version"] != "t08-preprocessing-v1":
        raise ValueError("Unsupported preprocessing schema")
    numeric, categorical = cfg["numeric"], cfg["categorical"]
    if (numeric["imputation_strategy"] != "median" or numeric["keep_empty_features"] is not True
            or numeric["missing_indicators"] not in ("all", "none")
            or numeric["scale"] != {"ridge": True, "random_forest": False}):
        raise ValueError("Expected median/keep-empty numeric preprocessing and Ridge-only scaling")
    if (categorical["imputation_strategy"] != "constant" or not isinstance(categorical["fill_value"], str)
            or not categorical["fill_value"] or categorical["handle_unknown"] != "ignore"
            or categorical["sparse_output"] is not False):
        raise ValueError("Expected a reserved constant category and dense one-hot with unknown=ignore")
    if cfg["output"] != {"format": "pandas", "verbose_feature_names": True}:
        raise ValueError("Expected pandas output with verbose feature names")
    if cfg["prediction_postprocessing"] != {
        "negative_predictions": "identity", "applies_to": ["persistence", "ridge", "random_forest"]
    }:
        raise ValueError("Prediction policy must be shared identity; clipping requires a new explicit protocol")


def make_preprocessor(model_name, *, feature_set, config, preprocessing_config):
    """Return an UNFITTED schema + ColumnTransformer pipeline for A or B.

    Medians/scaler/vocabulary use only data passed to fit. A column empty in
    that train partition remains present (SimpleImputer fallback 0), flagged
    by the independent all-feature MissingIndicator branch. Binary indicators
    and one-hot columns stay 0/1 for both models. Categories seen only at
    inference map to all-zero one-hot for that categorical input.
    """
    _validate_options(model_name, feature_set, preprocessing_config)
    registry = feature_registry(config)
    chosen = registry.loc[registry.feature_sets.str.split(";").map(lambda sets: feature_set in sets)]
    names = tuple(chosen.feature_name)
    categorical = tuple(chosen.loc[chosen.dtype.eq("string"), "feature_name"])
    numeric = tuple(name for name in names if name not in categorical)
    cfg = preprocessing_config
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy=cfg["numeric"]["imputation_strategy"], keep_empty_features=True)),
        ("scale", StandardScaler() if cfg["numeric"]["scale"][model_name] else "passthrough"),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value=cfg["categorical"]["fill_value"], keep_empty_features=True)),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False, drop=None, dtype=np.float64)),
    ])
    branches = [("numeric", numeric_pipeline, list(numeric))]
    if cfg["numeric"]["missing_indicators"] == "all":
        branches.append(("missing", MissingIndicator(features="all", sparse=False, error_on_new=False), list(numeric)))
    branches.append(("categorical", categorical_pipeline, list(categorical)))
    columns = ColumnTransformer(branches, remainder="drop", sparse_threshold=0., n_jobs=1,
                                verbose_feature_names_out=True)
    pipeline = Pipeline([
        ("schema", FeatureSchema(names, numeric, categorical, cfg["categorical"]["fill_value"])),
        ("columns", columns),
    ])
    return pipeline.set_output(transform="pandas")


def make_regression_pipeline(model_name, *, feature_set, config, preprocessing_config):
    """Return an UNFITTED preprocessing+regressor Pipeline, usable by clone/CV.

    Hyperparameters come from the existing project initial_parameters. No
    data, fit, predictions, logger writes or serialization happen in factories.
    Callers record both configs and actual feature names in future model runs.
    """
    preprocessing = make_preprocessor(model_name, feature_set=feature_set, config=config,
                                     preprocessing_config=preprocessing_config)
    parameters = deepcopy(config["evaluation"]["initial_parameters"][model_name])
    estimator = Ridge(**parameters) if model_name == "ridge" else RandomForestRegressor(**parameters)
    return Pipeline([("preprocess", preprocessing), ("model", estimator)])
