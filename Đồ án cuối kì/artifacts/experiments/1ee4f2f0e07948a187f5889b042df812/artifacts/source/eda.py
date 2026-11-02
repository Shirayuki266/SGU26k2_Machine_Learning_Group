"""T06 descriptive EDA on verified T05 training samples; never open holdouts.

Operational rows retain missing origin PM2.5. Descriptions are conditional on
T05's observed-target selection, not an unbiased inventory of raw observations.
No estimator, transformation fit, feature matrix, or model metric is produced.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess

import numpy as np
import pandas as pd

from beijing_air.data import MEASUREMENTS, sha256, validate_temporal_integrity
from beijing_air.samples import ID_COLUMNS


NUMERIC = [*MEASUREMENTS, "target_pm25"]
UNITS = {name: "µg/m³" for name in ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "target_pm25"]}
UNITS.update(TEMP="°C", DEWP="°C", PRES="hPa", RAIN="mm", WSPM="m/s")
SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
LAGS = (1, 2, 3, 6, 12, 24, 48, 72, 168)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def project_path(root, relative):
    """Resolve a manifest path inside the project, including symlink checks."""
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes project")
    return path


def ids_digest(ids):
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def load_training_data(root, manifest_path="reports/splits_full/split_manifest.json"):
    """Verify only train CSV/IDs. Deliberately never iterate all manifest files."""
    root = Path(root).resolve()
    manifest_path = project_path(root, manifest_path)
    manifest = read_json(manifest_path)
    config = read_json(root / "configs/default.json")
    if manifest.get("status") != "complete" or manifest.get("task_id") != "T05":
        raise ValueError("Expected complete T05 snapshot")
    if manifest["signature"]["split"] != config["split"] or config["horizon_hours"] != 1:
        raise ValueError("Split/horizon differs from current protocol")
    frames, accessed = {}, []
    for key in ("train_samples", "train_ids"):
        info = manifest["files"][key]
        path = project_path(root, info["path"])
        if path.name != "train.csv":
            raise ValueError("EDA only accepts train.csv")
        if path.stat().st_size != info["bytes"] or sha256(path) != info["sha256"]:
            raise ValueError(f"Train checksum differs: {key}")
        frames[key] = pd.read_csv(path, na_values=["NA"], keep_default_na=True,
                                  parse_dates=["input_timestamp", "target_timestamp"])
        accessed.append(info)
    data, ids = frames["train_samples"], frames["train_ids"]
    validate_training_frame(data, validation_start=config["split"]["validation_start"])
    if not data[ID_COLUMNS].equals(ids[ID_COLUMNS]):
        raise ValueError("Train CSV and sample ID membership differ")
    for cohort, subset in (("operational", data), ("primary", data.loc[data["is_primary"]])):
        expected = manifest["membership"]["train"][cohort]
        if len(subset) != expected["samples"] or ids_digest(subset["sample_id"]) != expected["ordered_sample_ids_sha256"]:
            raise ValueError("Train membership differs from T05 manifest")
    return data, {"split_manifest": manifest_path.relative_to(root).as_posix(),
                  "split_manifest_sha256": sha256(manifest_path),
                  "t05_snapshot_id": manifest["snapshot_id"], "input_files_read": accessed,
                  "source_mode": manifest["mode"], "validation_start": config["split"]["validation_start"]}


def validate_training_frame(data, *, validation_start):
    required = set(NUMERIC + ID_COLUMNS + ["split", "wd"])
    if not required.issubset(data) or data.empty or "No" in data:
        raise ValueError("Missing train schema, empty train, or forbidden No column")
    if (data["sample_id"].isna().any() or data["sample_id"].duplicated().any()
            or not data["sample_id"].str.fullmatch(r"[a-f0-9]{64}").all()):
        raise ValueError("Invalid/duplicate sample IDs")
    if not data["split"].eq("train").all():
        raise ValueError("Non-train row in EDA input")
    validate_temporal_integrity(data.rename(columns={"input_timestamp": "timestamp"}))
    origin, target = data["input_timestamp"], data["target_timestamp"]
    if target.isna().any() or not target.sub(origin).eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Target must be exactly one hour after origin")
    if not target.lt(pd.Timestamp(validation_start)).all():
        raise ValueError("Train crosses validation boundary")
    if not data["is_primary"].equals(data["PM2.5"].notna()):
        raise ValueError("Invalid primary cohort flag")
    for name in NUMERIC:
        values = pd.to_numeric(data[name], errors="raise")
        if not np.isfinite(values.dropna()).all():
            raise ValueError("Non-finite measurement")
    if data["target_pm25"].isna().any() or data["target_pm25"].lt(0).any():
        raise ValueError("Target must remain observed and nonnegative")


def exact_hour_autocorrelation(data, lags=LAGS):
    """Pair PM2.5(t) with PM2.5(t-lag) at the same station, never row-shift."""
    rows = []
    for station, group in data.groupby("station", sort=True):
        series = group.set_index("input_timestamp")["PM2.5"].sort_index()
        if not series.index.is_unique:
            raise ValueError("Duplicate station-hour in autocorrelation input")
        for lag in lags:
            if not isinstance(lag, int) or isinstance(lag, bool) or lag < 1:
                raise ValueError("Lag must be a positive integer hour")
            previous = series.reindex(series.index - pd.Timedelta(hours=lag)).to_numpy()
            pairs = pd.DataFrame({"current": series.to_numpy(), "previous": previous}).dropna()
            r = pairs["current"].corr(pairs["previous"]) if len(pairs) >= 3 and pairs.nunique().min() > 1 else np.nan
            rows.append({"station": station, "lag_hours": lag, "pairs": len(pairs), "pearson_r": r})
    return pd.DataFrame(rows)


def group_summary(data, by):
    return data.groupby(by, observed=True)["PM2.5"].agg(
        rows="size", observed="count", mean="mean", median="median",
        q25=lambda x: x.quantile(.25), q75=lambda x: x.quantile(.75),
        q95=lambda x: x.quantile(.95), maximum="max").reset_index()


def build_tables(data, review_ranges, lags=LAGS):
    """Pure descriptive tables; original data/values/order are unchanged."""
    inventory = []
    for name in data:
        role = ("future_label_not_feature" if name == "target_pm25" else
                "measurement_at_t" if name in MEASUREMENTS else
                "categorical_at_t" if name in ("station", "wd") else
                "calendar_at_t" if name in ("year", "month", "day", "hour") else "key_or_provenance_not_feature")
        inventory.append({"column": name, "dtype": str(data[name].dtype), "role": role,
                          "unit": UNITS.get(name, ""), "missing": int(data[name].isna().sum()),
                          "unique_observed": data[name].nunique()})
    numeric = []
    for name in NUMERIC:
        s = data[name]
        q = s.quantile([.01, .05, .25, .5, .75, .95, .99])
        iqr = q.loc[.75] - q.loc[.25]
        low, high = review_ranges["PM2.5" if name == "target_pm25" else name]
        base = "PM2.5" if name == "target_pm25" else name
        impossible = (s.le(0) if base == "PRES" else s.lt(-273.15) if base in ("TEMP", "DEWP") else s.lt(0))
        numeric.append({"column": name, "unit": UNITS[name], "rows": len(s), "observed": s.count(),
                        "missing": s.isna().sum(), "missing_pct": 100 * s.isna().mean(),
                        "mean": s.mean(), "std": s.std(), "min": s.min(), "max": s.max(),
                        "skew": s.skew(), "zero_count": s.eq(0).sum(),
                        **{f"q{int(p*100):02d}": v for p, v in q.items()},
                        "iqr_lower": q.loc[.25]-1.5*iqr, "iqr_upper": q.loc[.75]+1.5*iqr,
                        "iqr_flags": (s.lt(q.loc[.25]-1.5*iqr) | s.gt(q.loc[.75]+1.5*iqr)).sum(),
                        "review_flags": (s.lt(low) | s.gt(high)).sum(), "physical_invalid": impossible.sum()})
    missing_station = data.groupby("station")[MEASUREMENTS + ["wd"]].agg(lambda s: 100*s.isna().mean())
    observed = data[NUMERIC].notna().astype("int64")
    station = group_summary(data, "station")
    station = station.merge(data.groupby("station").agg(primary=("is_primary", "sum"),
                             target_mean=("target_pm25", "mean")), on="station", validate="one_to_one")
    gaps = []
    for name, group in data.groupby("station", sort=True):
        times = group["input_timestamp"].sort_values()
        delta = times.diff().dt.total_seconds().div(3600)
        expected = int((times.max()-times.min()) / pd.Timedelta(hours=1)) + 1
        gaps.append({"station": name, "first_origin": times.min(), "last_origin": times.max(),
                     "samples": len(times), "expected_hours_within_span": expected,
                     "absent_supervised_origins": expected-len(times), "gap_runs": int(delta.gt(1).sum()),
                     "longest_absent_run_hours": int(max(0, delta.max()-1)) if len(times)>1 else 0})
    categorical = pd.concat([data[c].fillna("<MISSING>").value_counts(dropna=False).rename_axis("value")
                             .reset_index(name="count").assign(column=c) for c in ("station", "wd")], ignore_index=True)
    calendar = data.assign(eda_hour=data["input_timestamp"].dt.hour,
                           eda_month=data["input_timestamp"].dt.month,
                           eda_season=data["input_timestamp"].dt.month.map(SEASONS),
                           eda_day=data["input_timestamp"].dt.floor("D"))
    tables = {"schema": pd.DataFrame(inventory), "numeric_summary": pd.DataFrame(numeric),
              "categorical_counts": categorical, "station_summary": station,
              "station_missing_pct": missing_station.reset_index(),
              "pearson": data[NUMERIC].corr(method="pearson").rename_axis("column").reset_index(),
              "spearman": data[NUMERIC].corr(method="spearman").rename_axis("column").reset_index(),
              "correlation_pairs": (observed.T @ observed).rename_axis("column").reset_index(),
              "hourly": group_summary(calendar, "eda_hour"), "monthly": group_summary(calendar, "eda_month"),
              "seasonal": group_summary(calendar, "eda_season"),
              "daily_station": group_summary(calendar, ["station", "eda_day"]),
              "sample_gaps": pd.DataFrame(gaps), "autocorrelation": exact_hour_autocorrelation(data, lags)}
    return tables


def findings(tables, provenance):
    """Quantitative captions used by notebook, figure index and final report."""
    s = tables["numeric_summary"].set_index("column")
    pm, target = s.loc["PM2.5"], s.loc["target_pm25"]
    missing = s.drop(index="target_pm25")["missing_pct"].sort_values(ascending=False)
    r = tables["pearson"].set_index("column")["target_pm25"]
    station = tables["station_summary"].set_index("station")["median"]
    hours = tables["hourly"].set_index("eda_hour")["mean"]
    seasons = tables["seasonal"].set_index("eda_season")["mean"]
    acf = tables["autocorrelation"].groupby("lag_hours")["pearson_r"].mean()
    gap = tables["sample_gaps"]
    return {
        "01_missing": f"Thiếu nhiều nhất: {missing.index[0]} {missing.iloc[0]:.2f}%; PM2.5(t) thiếu {int(pm['missing']):,} mẫu. T08 thử median và cờ missing fit riêng train/fold; không coi NA là 0, không backfill.",
        "02_distributions": f"PM2.5(t) median {pm['q50']:.1f}, mean {pm['mean']:.1f}, skew {pm['skew']:.2f}; CO std {s.loc['CO','std']:.1f} µg/m³ so với WSPM {s.loc['WSPM','std']:.2f} m/s. T08 scale biến số cho Ridge; RF không bắt buộc scaling. Không yêu cầu predictor phân phối chuẩn.",
        "03_tails": f"PM2.5(t) q99={pm['q99']:.1f}, max={pm['max']:.1f} µg/m³; {int(pm['iqr_flags']):,} cờ IQR, {int(pm['review_flags']):,} cờ ngưỡng rà soát, {int(pm['physical_invalid'])} sai vật lý. Target max={target['max']:.1f}. Giữ đợt cao; cờ thống kê không chứng minh lỗi, không clip/xóa/log-transform target trong T06.",
        "04_correlations": f"Pearson với nhãn t+1: PM2.5(t)={r['PM2.5']:.3f}, PM10={r['PM10']:.3f}, TEMP={r['TEMP']:.3f}, WSPM={r['WSPM']:.3f}. Ma trận dùng pairwise observed; xem bảng số cặp. T07 giữ A, T08 dùng regularization; tương quan không phải nhân quả hoặc bằng chứng loại feature.",
        "05_relationships": f"Hexbin dùng cặp quan sát train, gồm {int(target['observed']):,} nhãn nhưng chỉ {int(pm['observed']):,} cặp PM2.5(t)/nhãn. Các đám mây có thể phản ánh trạm/mùa và phụ thuộc thời gian; chưa thể kết luận lợi ích dự báo. T10 mới so sánh model cùng IDs.",
        "06_stations": f"Median PM2.5(t) theo trạm thấp nhất {station.idxmin()}={station.min():.1f}, cao nhất {station.idxmax()}={station.max():.1f} µg/m³. T07 giữ station/wd categorical, T08 encode với xử lý unknown; không suy thứ bậc từ mã trạm/hướng gió. Xem categorical_counts cho tần suất wd.",
        "07_calendar": f"Mean theo giờ origin thấp nhất {int(hours.idxmin()):02d}h={hours.min():.1f}, cao nhất {int(hours.idxmax()):02d}h={hours.max():.1f}; theo mùa {seasons.idxmin()}={seasons.min():.1f} tới {seasons.idxmax()}={seasons.max():.1f} µg/m³. T07 giữ lịch biết trước; cân nhắc biểu diễn chu kỳ, kiểm tra hiệu quả sau bằng CV, không suy tác động nhân quả.",
        "08_timeline": f"Có {int(gap['absent_supervised_origins'].sum()):,} origin không hiện diện trong khoảng đầu–cuối train mỗi trạm, {int(gap['gap_runs'].sum()):,} đoạn gián đoạn; dài nhất {int(gap['longest_absent_run_hours'].max())} giờ. Đây là khoảng trống trong cohort có target quan sát, không xác nhận raw mất giờ. T07 tạo lag/rolling trên timeline quan sát T04 rồi chọn IDs T05; không nén thời gian hoặc nội suy nhãn.",
        "09_autocorrelation": f"Tự tương quan Pearson trung bình đều theo trạm: lag 1h={acf.get(1, np.nan):.3f}, 24h={acf.get(24, np.nan):.3f}, 168h={acf.get(168, np.nan):.3f}. Ghép đúng station/timestamp, báo n từng lag; chưa khử trend/mùa nên đây là mô tả, không kiểm định độc lập. T07 thử B lag/rolling đã chốt; T09 cần persistence. Chưa có metric mô hình.",
    }


def plot_figures(data, tables, directory, *, dpi=150):
    """Save original PNG figures from the exact tables or stated train pairs."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", font_scale=.85)
    saved = []

    def save(fig, key, title, sources):
        fig.suptitle(title, fontsize=14)
        fig.tight_layout(rect=(0, 0, 1, .95))
        path = directory / f"{key}.png"
        fig.savefig(path, dpi=dpi, metadata={"Description": "T06 train-only descriptive EDA"})
        plt.close(fig)
        saved.append({"figure_id": key, "filename": path.name, "title": title, "tables": sources})

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    summary = tables["numeric_summary"].set_index("column")
    summary["missing_pct"].plot.bar(ax=axes[0], ylabel="Missing (%)", xlabel="Measurement")
    sns.heatmap(tables["station_missing_pct"].set_index("station"), ax=axes[1], cmap="YlOrRd", cbar_kws={"label": "Missing (%)"})
    save(fig, "01_missing", "Observed-target training cohort: missing values", "numeric_summary;station_missing_pct")

    fig, axes = plt.subplots(3, 4, figsize=(15, 10))
    for ax, name in zip(axes.flat, NUMERIC):
        ax.hist(data[name].dropna(), bins=60, color="#24788e", log=True)
        ax.set(xlabel=f"{name} ({UNITS[name]})", ylabel="Count (log scale)")
    save(fig, "02_distributions", "Train distributions: all observed values, no clipping", "numeric_summary")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for name in ("PM2.5", "target_pm25"):
        values = np.sort(data[name].dropna().to_numpy())
        axes[0].plot(values, np.arange(1, len(values)+1)/len(values), label=name)
    axes[0].set(xlabel="PM2.5 (µg/m³)", ylabel="Empirical cumulative probability")
    axes[0].legend()
    axes[1].boxplot([data[n].dropna() for n in ("PM2.5", "target_pm25")], tick_labels=["PM2.5(t)", "PM2.5(t+1)"], flierprops={"markersize": 2})
    axes[1].set(ylabel="PM2.5 (µg/m³)")
    save(fig, "03_tails", "PM2.5 tails: IQR fliers retained, not labelled errors", "numeric_summary")

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    for ax, method in zip(axes, ("pearson", "spearman")):
        sns.heatmap(tables[method].set_index("column"), ax=ax, vmin=-1, vmax=1, cmap="vlag", annot=True, fmt=".2f", annot_kws={"size": 7}, cbar_kws={"label": "Correlation (dimensionless)"})
        ax.set_title(f"{method.title()} — pairwise observed")
    save(fig, "04_correlations", "Train correlations; target_pm25 is a label, never an input", "pearson;spearman;correlation_pairs")

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    for ax, name in zip(axes.flat, ["PM2.5", "PM10", "NO2", "CO", "O3", "TEMP", "PRES", "WSPM"]):
        pairs = data[[name, "target_pm25"]].dropna()
        if not pairs.empty:
            h = ax.hexbin(pairs[name], pairs["target_pm25"], gridsize=35, mincnt=1, bins="log", cmap="viridis")
            fig.colorbar(h, ax=ax, label="Pair count (log scale)")
        ax.set(xlabel=f"{name}(t) ({UNITS[name]})", ylabel="PM2.5(t+1) (µg/m³)")
    save(fig, "05_relationships", "Train feature/label pairs: descriptive association only", "correlation_pairs;pearson;spearman")

    fig, axes = plt.subplots(2, 1, figsize=(13, 8))
    groups = list(data.groupby("station", sort=True))
    axes[0].boxplot([g["PM2.5"].dropna() for _, g in groups], tick_labels=[s for s, _ in groups], flierprops={"markersize": 1})
    axes[0].set(ylabel="PM2.5(t) (µg/m³)", xlabel="Station (categorical)")
    axes[0].tick_params(axis="x", rotation=25)
    wd = tables["categorical_counts"].query("column == 'wd'")
    axes[1].bar(wd["value"], wd["count"])
    axes[1].set(xlabel="Wind direction (categorical; <MISSING> is not calm)", ylabel="Training rows")
    save(fig, "06_stations", "Station distributions and observed wind direction", "station_summary;categorical_counts")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, name, key in zip(axes, ["hourly", "monthly", "seasonal"], ["eda_hour", "eda_month", "eda_season"]):
        t = tables[name].copy()
        if name == "seasonal":
            t = t.set_index(key).reindex(["DJF", "MAM", "JJA", "SON"]).reset_index()
        x = np.arange(len(t))
        ax.plot(x, t["mean"], "o-", label="Mean")
        ax.plot(x, t["median"], "--", label="Median")
        ax.fill_between(x, t["q25"], t["q75"], alpha=.2, label="IQR")
        ax.set(xticks=x, xticklabels=t[key], xlabel=f"Origin {key.removeprefix('eda_')}", ylabel="PM2.5(t) (µg/m³)")
        ax.legend(fontsize=7)
    save(fig, "07_calendar", "Train calendar profiles pooled across stations/years", "hourly;monthly;seasonal")

    n = len(groups)
    fig, axes = plt.subplots(n, 1, figsize=(14, max(4, 1.55*n)), squeeze=False)
    daily = tables["daily_station"]
    for ax, (station, _) in zip(axes.flat, groups):
        t = daily.loc[daily["station"].eq(station)].set_index("eda_day")
        # Reindex for plotting only: missing days remain NaN, never interpolated.
        t = t.reindex(pd.date_range(t.index.min(), t.index.max(), freq="D"))
        ax.plot(t.index, t["mean"], linewidth=.65, label="Daily mean")
        ax.plot(t.index, t["maximum"], linewidth=.45, alpha=.5, label="Daily max")
        ax.set(ylabel="µg/m³", title=station)
        ax.legend(loc="upper right", fontsize=6)
    axes[-1, 0].set_xlabel("Origin date (source local, timezone unspecified)")
    save(fig, "08_timeline", "Train PM2.5 daily summaries; days use available observations", "daily_station;sample_gaps")

    fig, ax = plt.subplots(figsize=(11, 5))
    ac = tables["autocorrelation"]
    for station, t in ac.groupby("station", sort=True):
        ax.plot(t["lag_hours"], t["pearson_r"], ".-", alpha=.55, linewidth=.8, label=station)
    mean = ac.groupby("lag_hours")["pearson_r"].mean()
    ax.plot(mean.index, mean, "k.-", linewidth=2, label="Equal-station mean")
    ax.set(xscale="log", xlabel="Exact lag (hours, log scale)", ylabel="PM2.5 Pearson autocorrelation", ylim=(-1, 1))
    ax.legend(ncol=3, fontsize=7)
    save(fig, "09_autocorrelation", "Same-station, exact-hour observed pairs; not compressed row lags", "autocorrelation")
    return saved


def run_eda(root, *, mode="full", manifest_path=None, output_tag=None):
    """Execute one bounded EDA. Existing artifacts require a new output tag."""
    root = Path(root).resolve()
    config = read_json(root / "configs/eda.json")
    if mode not in ("smoke", "full") or (output_tag is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", output_tag)):
        raise ValueError("Invalid mode/output tag")
    data, provenance = load_training_data(root, manifest_path or config["split_manifest"])
    if mode == "full" and provenance["source_mode"] != "full":
        raise ValueError("Full EDA requires full T05 train")
    source_rows = len(data)
    if mode == "smoke":
        data = data.groupby("station", sort=True, group_keys=False).head(config["smoke_rows_per_station"]).copy()
    suffix = "eda_train" + ("_smoke" if mode == "smoke" else "") + (f"_{output_tag}" if output_tag else "")
    report = root / "reports" / suffix
    figures = root / "reports/figures" / suffix
    if report.exists() or figures.exists():
        raise FileExistsError("EDA output exists; use a new --output-tag (no automatic overwrite)")
    tables = build_tables(data, read_json(root / "configs/data_quality.json")["review_ranges"], tuple(config["autocorrelation_lags_hours"]))
    captions = findings(tables, provenance)
    report.mkdir(parents=True)
    index = plot_figures(data, tables, figures, dpi=config["figure_dpi"])
    for name, table in tables.items():
        table.to_csv(report / f"{name}.csv", index=False, encoding="utf-8", na_rep="NA", lineterminator="\n")
    for row in index:
        row["path"] = (figures / row["filename"]).relative_to(root).as_posix()
        row["commentary_vi"] = captions[row["figure_id"]]
    pd.DataFrame(index).to_csv(report / "figure_index.csv", index=False, encoding="utf-8", lineterminator="\n")
    (report / "figure_index.md").write_text("# Chỉ mục hình T06\n\n" + "\n\n".join(
        f"## {row['figure_id']} — {row['title']}\n\n[PNG gốc](../../{row['path']}) · Bảng: {row['tables']}\n\n{row['commentary_vi']}" for row in index) + "\n", encoding="utf-8", newline="\n")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
    manifest = {"task_id": "T06", "artifact_type": "train_data_understanding", "status": "complete",
                "model_experiment_run": False, "mode": mode, "test_accessed": False,
                "created_at": datetime.now(timezone.utc).isoformat(), "cohort": "operational",
                "source_train_rows": source_rows, "analyzed_rows": len(data), "primary_rows": int(data["is_primary"].sum()),
                "stations": data["station"].nunique(), "input_timestamp_min": str(data["input_timestamp"].min()),
                "input_timestamp_max": str(data["input_timestamp"].max()),
                "target_timestamp_min": str(data["target_timestamp"].min()), "target_timestamp_max": str(data["target_timestamp"].max()),
                "selection_caveat": "Observed-target T05 cohort; gaps do not imply missing raw hours; pairwise observed statistics, no imputation.",
                "seed": config["seed"], "random_sampling": False, "config": config, "provenance": provenance,
                "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                "git_head_at_execution": git.stdout.strip() or None, "git_dirty_at_execution": bool(status.stdout.strip()),
                "module_sha256": sha256(Path(__file__)), "eda_config_sha256": sha256(root / "configs/eda.json"),
                "default_config_sha256": sha256(root / "configs/default.json"),
                "quality_config_sha256": sha256(root / "configs/data_quality.json")}
    outputs = [*report.glob("*.csv"), report / "figure_index.md", *figures.glob("*.png")]
    manifest["files"] = [{"path": p.relative_to(root).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(outputs)]
    (report / "eda_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return {"data": data, "tables": tables, "findings": captions, "figures": index, "manifest": manifest,
            "report_directory": report, "figure_directory": figures}
