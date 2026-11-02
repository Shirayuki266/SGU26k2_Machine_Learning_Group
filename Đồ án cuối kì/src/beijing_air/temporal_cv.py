"""Shared station boundaries and strict label availability for train-only CV."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from beijing_air.eda import ids_digest
from beijing_air.samples import check_label_availability


@dataclass
class TemporalFold:
    fold_id: int
    fit: np.ndarray
    evaluation: np.ndarray
    purged: np.ndarray
    audit: dict


def membership(frame):
    return {"samples": len(frame), "ordered_ids_sha256": ids_digest(frame.sample_id),
            "stations": sorted(frame.station.unique().tolist()),
            "first_target": str(frame.target_timestamp.min()) if len(frame) else None,
            "last_target": str(frame.target_timestamp.max()) if len(frame) else None,
            "unique_target_timestamps": int(frame.target_timestamp.nunique())}


def expanding_folds(samples, config):
    """Split whole timestamp groups; purge against the actual earliest origin.

    Positions refer to the supplied frame, never row-order K-fold chunks.
    Fold 2/3 may fit observations evaluated in earlier folds, as they are past.
    """
    cv, cutoff = config["temporal_cv"], pd.Timestamp(config["split"]["validation_start"])
    if (cv["strategy"] != "expanding_window" or cv["partition"] != "train"
            or cv["group_by"] != "unique_target_timestamp" or cv["fit_target_must_precede_first_origin"] is not True
            or len(cv["folds"]) != 3 or config["horizon_hours"] != 1):
        raise ValueError("Expected the agreed three-fold hourly train CV protocol")
    if (samples.empty or not samples.split.eq("train").all() or not samples.is_primary.all()
            or samples.sample_id.isna().any() or not samples.sample_id.is_unique
            or samples.duplicated(["station", "input_timestamp"]).any()
            or samples.target_timestamp.isna().any() or samples.input_timestamp.isna().any()
            or not samples.target_timestamp.lt(cutoff).all()
            or not (samples.target_timestamp-samples.input_timestamp).eq(pd.Timedelta(hours=1)).all()):
        raise ValueError("CV requires unique, primary, exact-hour train samples only")
    times = pd.DatetimeIndex(samples.target_timestamp.unique()).sort_values()
    previous_end, result, evaluation_ids = None, [], set()
    all_stations = set(samples.station)
    for number, spec in enumerate(cv["folds"], 1):
        start, end = pd.Timestamp(spec["evaluation_start"]), pd.Timestamp(spec["evaluation_end"])
        if spec["fold_id"] != number or start >= end or end > cutoff or (previous_end is not None and start < previous_end):
            raise ValueError("Invalid, overlapping or holdout-crossing CV windows")
        eval_times = times[(times >= start) & (times < end)]
        evaluation = np.flatnonzero(samples.target_timestamp.isin(eval_times))
        if not len(evaluation):
            raise ValueError("Empty CV evaluation window; do not move boundaries automatically")
        first_origin = samples.iloc[evaluation].input_timestamp.min()
        past = samples.target_timestamp.lt(start)
        fit = np.flatnonzero(past & samples.target_timestamp.lt(first_origin))
        purged = np.flatnonzero(past & samples.target_timestamp.ge(first_origin))
        if not len(fit):
            raise ValueError("Empty CV fit after purging")
        fit_frame, eval_frame = samples.iloc[fit], samples.iloc[evaluation]
        if set(fit_frame.station) != all_stations or set(eval_frame.station) != all_stations:
            raise ValueError("A station is missing from a CV partition; inspect coverage")
        ids = set(eval_frame.sample_id)
        if evaluation_ids & ids or set(fit_frame.sample_id) & ids:
            raise ValueError("CV sample IDs overlap")
        availability = check_label_availability(fit_frame, eval_frame, strict_before_origin=True)
        audit = {"fold_id": number, "evaluation_start": str(start), "evaluation_end_exclusive": str(end),
                 "fit": membership(fit_frame), "evaluation": membership(eval_frame),
                 "purged": membership(samples.iloc[purged]), "label_availability": availability,
                 "shared_station_boundaries": True, "timestamp_grouping": "unique_target_timestamp"}
        result.append(TemporalFold(number, fit, evaluation, purged, audit))
        evaluation_ids.update(ids)
        previous_end = end
    for earlier, later in zip(result, result[1:]):
        if not set(earlier.fit).issubset(later.fit):
            raise ValueError("Fit windows are not expanding")
    return result
