"""Causal persistence with bounded-age station history and train-only medians."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from beijing_air.data import validate_temporal_integrity
from beijing_air.features import _requests


@dataclass(frozen=True)
class PersistenceState:
    station_medians: dict
    global_median: float | None
    train_rows: int
    observed_train_rows: int
    latest_train_origin: str


def fit_persistence(training):
    """Statistics from unimputed PM2.5(t) in supplied training origins only."""
    if training.empty or not {"station", "input_timestamp", "PM2.5"}.issubset(training):
        raise ValueError("Training origins and current PM2.5 required")
    if "split" in training and not training.split.eq("train").all():
        raise ValueError("Fallback statistics may only be fitted on train")
    history = training[["station", "input_timestamp", "PM2.5"]].rename(columns={"input_timestamp": "timestamp"})
    history = _history(history)
    medians = history.groupby("station")["PM2.5"].median()
    global_median = history["PM2.5"].median()
    return PersistenceState({s: None if pd.isna(v) else float(v) for s, v in medians.items()},
                            None if pd.isna(global_median) else float(global_median), len(history),
                            int(history["PM2.5"].notna().sum()), str(history.timestamp.max()))


def _history(observations):
    required = {"station", "timestamp", "PM2.5"}
    if not required.issubset(observations) or not observations.columns.is_unique:
        raise ValueError("Observation history schema required")
    history = observations[["station", "timestamp", "PM2.5"]].sort_values(["station", "timestamp"], kind="stable").copy()
    if (not pd.api.types.is_datetime64_any_dtype(history.timestamp)
            or isinstance(history.timestamp.dtype, pd.DatetimeTZDtype)):
        raise ValueError("History requires naive hourly timestamps")
    validate_temporal_integrity(history)
    if not pd.api.types.is_numeric_dtype(history["PM2.5"]) or pd.api.types.is_bool_dtype(history["PM2.5"]):
        raise ValueError("PM2.5 history must be numeric")
    if not np.isfinite(history["PM2.5"].dropna()).all() or history["PM2.5"].lt(0).any():
        raise ValueError("Observed PM2.5 must be finite and nonnegative")
    return history


def predict_persistence(state, requests, observations, *, max_history_age_hours=24):
    if type(max_history_age_hours) is not int or max_history_age_hours < 1:
        raise ValueError("History age must be a positive integer hour limit")
    result = _requests(requests)
    cutoffs = result.groupby("station").input_timestamp.max()
    relevant = observations.station.isin(cutoffs.index) & observations.timestamp.le(observations.station.map(cutoffs))
    history = _history(observations.loc[relevant])
    result["y_pred"] = np.nan
    result["prediction_source"] = "unavailable"
    result["last_observed_timestamp"] = pd.NaT
    result["history_age_hours"] = np.nan
    for station, group in result.groupby("station", sort=False):
        all_rows = history.loc[history.station.eq(station)].set_index("timestamp")["PM2.5"]
        origins = pd.DatetimeIndex(group.input_timestamp)
        if not origins.isin(all_rows.index).all():
            raise ValueError("Requested origin is not an observed sample")
        current = all_rows.reindex(origins).to_numpy(dtype=float, na_value=np.nan)
        if "is_primary" in group and not np.array_equal(group.is_primary.to_numpy(), ~np.isnan(current)):
            raise ValueError("Origin measurements differ from T05 primary flags")
        observed = all_rows.dropna()
        last = pd.Series(observed.index, index=observed.index).reindex(origins, method="ffill")
        previous = observed.reindex(origins, method="ffill").to_numpy(dtype=float, na_value=np.nan)
        age = np.asarray((origins-pd.DatetimeIndex(last)) / pd.Timedelta(hours=1), dtype=float)
        station_median = state.station_medians.get(station)
        fallback_value = station_median if station_median is not None else state.global_median
        fallback_source = "training_station_median" if station_median is not None else "training_global_median" if state.global_median is not None else "unavailable"
        values = np.full(len(group), np.nan if fallback_value is None else fallback_value)
        source = np.full(len(group), fallback_source, dtype=object)
        fresh = ~np.isnan(previous) & (age >= 0) & (age <= max_history_age_hours)
        values[fresh], source[fresh] = previous[fresh], "last_observed_same_station"
        available = ~np.isnan(current)
        values[available], source[available] = current[available], "persistence"
        result.loc[group.index, "y_pred"] = values
        result.loc[group.index, "prediction_source"] = source
        result.loc[group.index, "last_observed_timestamp"] = last.to_numpy()
        result.loc[group.index, "history_age_hours"] = age
    result["fallback"] = result.prediction_source.ne("persistence")
    return result
