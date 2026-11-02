"""T07 deterministic A/B features from observations available at origin t.

No target values, fit, imputation or encoding learned from data. Requests are
observed origins, not an hourly grid. History may cross split boundaries when
already observed. Calendar values describe the known forecast hour t+1.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from beijing_air.data import MEASUREMENTS, validate_temporal_integrity
from beijing_air.samples import _sample_id


KEYS = ["sample_id", "station", "input_timestamp", "target_timestamp"]
CALENDAR = ["target_hour", "target_month", "target_day_of_week"]
REASONS = {
    0: "observed", 1: "current_value_missing", 2: "lag_before_history",
    3: "lag_hour_absent", 4: "lag_value_missing", 5: "rolling_warmup",
    6: "rolling_incomplete",
}
UNITS = {name: "µg/m³" for name in MEASUREMENTS[:6]}
UNITS.update(TEMP="°C", PRES="hPa", DEWP="°C", RAIN="mm", WSPM="m/s")


def _spec(config):
    a, b = config["features"]["A"], config["features"]["B"]
    if config["horizon_hours"] != 1 or isinstance(config["horizon_hours"], bool):
        raise ValueError("Feature protocol requires horizon=1")
    if (a["measurements"] != MEASUREMENTS or a["categorical"] != ["station", "wd"]
            or a["calendar"] != CALENDAR or a.get("calendar_reference") != "target_timestamp"):
        raise ValueError("Expected explicit A inputs and forecast-hour calendar")
    if a.get("cyclic_calendar", {}) not in ({}, {"target_hour": 24, "target_month": 12}):
        raise ValueError("Supported cycles are forecast hour/24 and month/12")
    for key in ("pm25_lag_hours", "pm25_rolling_windows_hours"):
        values = b[key]
        if not values or any(type(n) is not int or n < 1 for n in values) or values != sorted(set(values)):
            raise ValueError("History hours must be sorted unique positive integers")
    if (b["extends"] != "A" or b["rolling_stats"] != ["mean", "std"]
            or b["rolling_std_ddof"] != 1 or b["rolling_include_current"] is not True
            or b["rolling_min_periods"] != "window" or min(b["pm25_rolling_windows_hours"]) < 2):
        raise ValueError("Expected trailing full windows including current, mean/std(ddof=1)")
    return a, b


def feature_registry(config):
    """Ordered allowlist and availability dictionary; no fitted information."""
    a, b = _spec(config)
    rows = []

    def add(name, source, offsets, meaning, dtype, unit, sets="A;B", missing="preserve_NA", formula="identity"):
        rows.append({"feature_name": name, "source": source, "source_time_offsets_hours": offsets,
                     "available_by": "origin_t", "meaning_vi": meaning, "dtype": dtype, "unit": unit,
                     "feature_sets": sets, "missing_policy": missing, "formula": formula})

    for name in a["measurements"]:
        add(name, name, "[0]", f"Số đo {name} tại giờ phát hành t", "float64", UNITS[name])
    for name in a["categorical"]:
        add(name, name, "[0]", "Mã trạm" if name == "station" else "Hướng gió tại t", "string", "category")
    for name, meaning in zip(CALENDAR, ("Giờ dự báo 0–23", "Tháng dự báo 1–12", "Thứ giờ dự báo, Monday=0")):
        add(name, "input_timestamp+1h (known calendar only)", "no_measurement", meaning, "int64", "calendar",
            missing="not_missing", formula=f"(t+1h).{name.removeprefix('target_')}")
    for name, period in a.get("cyclic_calendar", {}).items():
        offset = 1 if name == "target_month" else 0
        for function in ("sin", "cos"):
            add(f"{name}_{function}", name, "no_measurement", f"Chu kỳ {name}, {function}", "float64", "dimensionless",
                missing="not_missing", formula=f"{function}(2*pi*({name}-{offset})/{period})")
    for lag in b["pm25_lag_hours"]:
        add(f"pm25_lag_{lag}h", "PM2.5 same station", f"[-{lag}]", f"PM2.5 đúng t−{lag} giờ", "float64", "µg/m³", "B",
            formula=f"PM2.5(station,t-{lag}h); exact timestamp")
    for window in b["pm25_rolling_windows_hours"]:
        for stat in b["rolling_stats"]:
            add(f"pm25_roll_{stat}_{window}h", "PM2.5 same station", f"[-{window-1},0]",
                f"Rolling {stat} {window} giờ, kết thúc tại t", "float64", "µg/m³", "B",
                missing=f"NA unless {window}/{window} observations present", formula=f"{stat}(PM2.5[t-{window-1}h:t]); ddof=1 for std")
    result = pd.DataFrame(rows)
    if result.feature_name.duplicated().any():
        raise ValueError("Duplicate feature name")
    return result


@dataclass
class FeatureResult:
    features: pd.DataFrame
    sample_metadata: pd.DataFrame
    missing_reasons: pd.DataFrame
    registry: pd.DataFrame

    def select(self, feature_set="B"):
        """Return only feature columns (ID stays in index, labels stay outside X)."""
        if feature_set not in ("A", "B"):
            raise ValueError("feature_set must be A or B")
        names = self.registry.loc[self.registry.feature_sets.str.split(";").map(lambda sets: feature_set in sets), "feature_name"]
        return self.features.loc[:, names].copy()


def _requests(requests):
    if not set(KEYS).issubset(requests) or requests.empty or not requests.columns.is_unique:
        raise ValueError("Nonempty request keys required")
    result = requests[KEYS + [c for c in ("is_primary", "split") if c in requests]].copy().reset_index(drop=True)
    for name in ("input_timestamp", "target_timestamp"):
        s = result[name]
        if (not pd.api.types.is_datetime64_any_dtype(s) or isinstance(s.dtype, pd.DatetimeTZDtype)
                or s.isna().any() or not s.eq(s.dt.floor("h")).all()):
            raise ValueError("Requests require naive hourly timestamps")
    if not result.target_timestamp.sub(result.input_timestamp).eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Request target timestamp must equal t+1 hour")
    if not result.station.map(lambda x: isinstance(x, str) and bool(x.strip()) and x == x.strip()).all():
        raise ValueError("Invalid request station")
    expected = [_sample_id(s, t, u) for s, t, u in result[["station", "input_timestamp", "target_timestamp"]].itertuples(index=False, name=None)]
    if result.sample_id.isna().any() or result.sample_id.duplicated().any() or result.sample_id.tolist() != expected:
        raise ValueError("Requests must retain valid unique T05 sample IDs")
    if result.duplicated(["station", "input_timestamp"]).any():
        raise ValueError("Duplicate requested origin")
    return result


def build_features(observations, requests, *, config):
    """Build both sets, retaining exactly request IDs/order and missing values.

    History is station/timestamp plus raw measurements and wd. Only the
    allowlist is read; request labels/provenance never enter calculations.
    Future observations beyond each station's last requested origin are cut
    before value validation/aggregation. Reindex is lookup only: no new sample.
    """
    a, b = _spec(config)
    metadata = _requests(requests)
    required = ["station", "timestamp", *a["measurements"], "wd"]
    if not set(required).issubset(observations) or not observations.columns.is_unique:
        raise ValueError("Expected T04 observation schema")
    if (not pd.api.types.is_datetime64_any_dtype(observations.timestamp)
            or isinstance(observations.timestamp.dtype, pd.DatetimeTZDtype)
            or observations.timestamp.isna().any()):
        raise ValueError("History requires naive timestamps")
    cutoffs = metadata.groupby("station").input_timestamp.max()
    relevant = observations.station.isin(cutoffs.index) & observations.timestamp.le(observations.station.map(cutoffs))
    history = observations.loc[relevant, required].sort_values(["station", "timestamp"], kind="stable").copy()
    validate_temporal_integrity(history)
    for name in a["measurements"]:
        if not pd.api.types.is_numeric_dtype(history[name]) or pd.api.types.is_bool_dtype(history[name]):
            raise ValueError("History measurements must be numeric")
        history[name] = history[name].astype("float64")
        if not np.isfinite(history[name].dropna()).all():
            raise ValueError("Nonfinite history value")
    if history["PM2.5"].lt(0).any():
        raise ValueError("Negative observed PM2.5")
    current = history.rename(columns={"timestamp": "input_timestamp"})
    joined = metadata.merge(current, on=["station", "input_timestamp"], how="left", validate="one_to_one", indicator=True, sort=False)
    if not joined["_merge"].eq("both").all():
        raise ValueError("Requested origin has no actual observation; cannot synthesize a sample")
    if "is_primary" in joined and not joined.is_primary.equals(joined["PM2.5"].notna()):
        raise ValueError("Current observations differ from T05 primary flag")
    x = joined[a["measurements"] + a["categorical"]].copy()
    for name in a["categorical"]:
        x[name] = x[name].astype("string")
    target = metadata.target_timestamp
    x["target_hour"] = target.dt.hour.astype("int64")
    x["target_month"] = target.dt.month.astype("int64")
    x["target_day_of_week"] = target.dt.dayofweek.astype("int64")
    for name, period in a.get("cyclic_calendar", {}).items():
        angle = 2*np.pi*(x[name]-(1 if name == "target_month" else 0))/period
        x[f"{name}_sin"], x[f"{name}_cos"] = np.sin(angle), np.cos(angle)
    reasons = pd.DataFrame(0, index=x.index, columns=x.columns, dtype="int8")
    reasons[x.isna()] = 1
    for station, group in metadata.groupby("station", sort=False):
        positions = group.index
        series = history.loc[history.station.eq(station)].set_index("timestamp")["PM2.5"]
        origins = pd.DatetimeIndex(group.input_timestamp)
        first = series.index.min()
        for lag in b["pm25_lag_hours"]:
            name = f"pm25_lag_{lag}h"
            times = origins-pd.Timedelta(hours=lag)
            values = series.reindex(times).to_numpy()
            x.loc[positions, name] = values
            code = np.select([times < first, ~times.isin(series.index), pd.isna(values)], [2, 3, 4], default=0)
            reasons.loc[positions, name] = code
        for window in b["pm25_rolling_windows_hours"]:
            # On unique hourly keys, (t-window,t] contains at most window slots.
            # min_periods=window therefore also rejects any absent hour or NA.
            rolling = series.rolling(f"{window}h", min_periods=window, closed="right")
            for stat in b["rolling_stats"]:
                name = f"pm25_roll_{stat}_{window}h"
                values = (rolling.mean() if stat == "mean" else rolling.std(ddof=b["rolling_std_ddof"])).reindex(origins).to_numpy()
                x.loc[positions, name] = values
                code = np.where(pd.isna(values), np.where(origins-pd.Timedelta(hours=window-1) < first, 5, 6), 0)
                reasons.loc[positions, name] = code
    registry = feature_registry(config)
    x = x.loc[:, registry.feature_name]
    reasons = reasons.loc[:, registry.feature_name].astype("int8")
    x.index = pd.Index(metadata.sample_id, name="sample_id")
    reasons.index = x.index
    metadata = metadata.set_index("sample_id")
    if not x.isna().equals(reasons.ne(0)):
        raise ValueError("Feature missing reasons do not reconcile")
    if not x.index.equals(metadata.index) or len(x) != len(requests):
        raise ValueError("Feature membership/order changed")
    return FeatureResult(x, metadata, reasons, registry)


def features_for_prediction(observations, *, station, origin, config):
    """One forecast without needing a target observation, label or split."""
    origin = pd.Timestamp(origin)
    target = origin+pd.Timedelta(hours=1)
    request = pd.DataFrame({"sample_id": [_sample_id(station, origin, target)], "station": [station],
                            "input_timestamp": [origin], "target_timestamp": [target]})
    return build_features(observations, request, config=config)


def missing_summary(result, *, by_station=False):
    """Counts only; causes describe missing inputs, never replace their values."""
    rows = []
    meta = result.sample_metadata
    groups = meta.groupby("station", sort=True).groups.items() if by_station else [(None, meta.index)]
    for station, ids in groups:
        for cohort in (["operational", "primary"] if "is_primary" in meta else ["operational"]):
            ids = pd.Index(ids)
            chosen = ids if cohort == "operational" else ids[meta.loc[ids, "is_primary"].to_numpy()]
            for column in result.features:
                codes = result.missing_reasons.loc[chosen, column]
                row = {"feature": column, "cohort": cohort, "rows": len(chosen), "observed": int(codes.eq(0).sum()),
                       "missing": int(codes.ne(0).sum()), "missing_pct": 100*codes.ne(0).mean() if len(chosen) else None}
                if by_station:
                    row["station"] = station
                row.update({reason: int(codes.eq(code).sum()) for code, reason in REASONS.items() if code})
                rows.append(row)
    return pd.DataFrame(rows)
