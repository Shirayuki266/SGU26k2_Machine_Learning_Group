"""TEST_ONLY small fixtures; never open project data or log model experiments."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from sklearn.base import clone
from sklearn.exceptions import NotFittedError
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from beijing_air.eda import read_json
from beijing_air.features import feature_registry
from beijing_air.preprocessing import make_preprocessor, make_regression_pipeline


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def configs():
    config = read_json(ROOT / "configs/default.json")
    # TEST_ONLY tiny model for contract checks; never a full RF run.
    config["evaluation"]["initial_parameters"]["random_forest"].update(n_estimators=3, max_depth=2)
    return config, read_json(ROOT / "configs/preprocessing.json")


def fixture_features(config, feature_set="A"):
    registry = feature_registry(config)
    registry = registry.loc[registry.feature_sets.str.split(";").map(lambda sets: feature_set in sets)]
    frame = pd.DataFrame({name: np.arange(10., 16.) for name in registry.feature_name},
                         index=pd.Index([f"TEST_ONLY_ID_{i}" for i in range(6)], name="sample_id"))
    frame["PM10"] = np.nan  # Entirely missing in this training partition.
    frame["CO"] = [np.nan, 20., 40., 50., np.nan, 100.]  # median = 45.
    frame["station"] = pd.array(["TEST_ONLY_Hà_Nội", "TEST_ONLY_B", None, "TEST_ONLY_B", "TEST_ONLY_Hà_Nội", "TEST_ONLY_B"], dtype="string")
    frame["wd"] = pd.array(["N", "S", pd.NA, "N", None, "S"], dtype="string")
    holdout = frame.iloc[:2].copy()
    holdout.index = pd.Index(["TEST_ONLY_HELDOUT_0", "TEST_ONLY_HELDOUT_1"], name="sample_id")
    holdout["CO"] = [np.nan, 999999.]
    holdout["NO2"] = [np.nan, 999999.]  # New missing, absent from fit train.
    holdout["PM10"] = [123., np.nan]
    holdout["station"] = ["TEST_ONLY_NEW_STATION", None]
    holdout["wd"] = ["TEST_ONLY_NEW_DIRECTION", pd.NA]
    return frame, holdout


def factory(model, feature_set, configs, *, complete=False):
    config, prep_config = configs
    make = make_regression_pipeline if complete else make_preprocessor
    return make(model, feature_set=feature_set, config=config, preprocessing_config=prep_config)


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
@pytest.mark.parametrize("feature_set", ["A", "B"])
def test_missing_empty_columns_unknown_categories_names_and_index(configs, model, feature_set):
    train, heldout = fixture_features(configs[0], feature_set)
    original_train, original_heldout = train.copy(deep=True), heldout.copy(deep=True)
    pipeline = factory(model, feature_set, configs)
    transformed_train = pipeline.fit_transform(train)
    output = pipeline.transform(heldout)
    assert isinstance(output, pd.DataFrame) and output.index.equals(heldout.index)
    # MissingIndicator emits bool; mixed bool/float pandas blocks need an
    # explicit numeric dtype when materialized as a homogeneous NumPy array.
    assert np.isfinite(output.to_numpy(dtype="float64")).all()
    assert output.columns.tolist() == pipeline.get_feature_names_out().tolist()
    assert output.columns.equals(transformed_train.columns)
    assert output.columns.is_unique
    columns = pipeline.named_steps["columns"]
    numeric = columns.named_transformers_["numeric"]
    numeric_names = list(columns.transformers_[0][2])
    assert numeric.named_steps["impute"].statistics_[numeric_names.index("CO")] == 45.
    assert numeric.named_steps["impute"].statistics_[numeric_names.index("PM10")] == 0.
    assert output["numeric__PM10"].tolist() == [123., 0.]
    assert transformed_train["missing__missingindicator_PM10"].eq(1).all()
    assert output["missing__missingindicator_NO2"].tolist() == [1., 0.]
    assert output["missing__missingindicator_CO"].tolist() == [1., 0.]
    station_columns = output.columns.str.startswith("categorical__station_")
    direction_columns = output.columns.str.startswith("categorical__wd_")
    assert output.loc[:, station_columns].iloc[0].sum() == 0.
    assert output.loc[:, direction_columns].iloc[0].sum() == 0.
    assert output.loc[:, station_columns].iloc[1].sum() == 1.  # Missing seen at fit.
    assert output.loc[:, direction_columns].iloc[1].sum() == 1.
    assert "TEST_ONLY_NEW_STATION" not in columns.named_transformers_["categorical"].named_steps["one_hot"].categories_[0]
    assert_frame_equal(train, original_train)
    assert_frame_equal(heldout, original_heldout)


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
def test_numeric_scaling_is_model_specific_indicators_stay_binary(configs, model):
    train, _ = fixture_features(configs[0])
    pipeline = factory(model, "A", configs)
    result = pipeline.fit_transform(train)
    scaler = pipeline.named_steps["columns"].named_transformers_["numeric"].named_steps["scale"]
    if model == "ridge":
        assert isinstance(scaler, StandardScaler)
        assert result["numeric__CO"].mean() == pytest.approx(0., abs=1e-12)
        assert result["numeric__CO"].std(ddof=0) == pytest.approx(1.)
    else:
        assert scaler == "passthrough"
        assert result["numeric__CO"].tolist() == [45., 20., 40., 50., 45., 100.]
    assert set(np.unique(result.loc[:, result.columns.str.startswith("missing__")])) <= {0., 1.}


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
def test_holdout_mutation_never_changes_train_learned_state(configs, model):
    train, heldout = fixture_features(configs[0], "B")
    pipeline = factory(model, "B", configs, complete=True)
    pipeline.fit(train, np.arange(1., 7.))
    original_state = joblib.hash(pipeline)
    original_train_result = pipeline.named_steps["preprocess"].transform(train)
    pipeline.predict(heldout)
    changed = heldout.copy()
    for column in changed.columns.difference(["station", "wd"]):
        changed[column] = [np.nan, 1e12]
    changed["station"] = ["TEST_ONLY_ANOTHER_UNKNOWN", "TEST_ONLY_未见站"]
    changed["wd"] = [None, "TEST_ONLY_UNSEEN_WIND"]
    assert np.isfinite(pipeline.predict(changed)).all()
    assert joblib.hash(pipeline) == original_state
    assert_frame_equal(original_train_result, pipeline.named_steps["preprocess"].transform(train))


def test_missing_category_only_at_inference_is_unknown_zero_vector(configs):
    train, heldout = fixture_features(configs[0])
    train["station"], train["wd"] = "TEST_ONLY_STATION", "N"
    heldout["station"], heldout["wd"] = None, pd.NA
    pipeline = factory("ridge", "A", configs)
    pipeline.fit(train)
    result = pipeline.transform(heldout)
    assert result.loc[:, result.columns.str.startswith("categorical__")].eq(0).all().all()
    assert np.isfinite(result).all().all()


def test_all_missing_categorical_train_keeps_columns(configs):
    train, heldout = fixture_features(configs[0])
    train["station"], train["wd"] = None, pd.NA
    pipeline = factory("ridge", "A", configs)
    z = pipeline.fit_transform(train)
    categories = pipeline.named_steps["columns"].named_transformers_["categorical"].named_steps["one_hot"].categories_
    assert [list(values) for values in categories] == [["__MISSING__"], ["__MISSING__"]]
    assert z.loc[:, z.columns.str.startswith("categorical__")].eq(1).all().all()
    assert np.isfinite(pipeline.transform(heldout)).all().all()


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
def test_clones_fit_each_expanding_fixture_fold_independently(configs, model):
    train, _ = fixture_features(configs[0], "B")
    train.loc[train.index[-1], "station"] = "TEST_ONLY_LATE_STATION"
    pipeline = factory(model, "B", configs, complete=True)
    clones = []
    for fit_ids, evaluate_ids in TimeSeriesSplit(n_splits=2).split(train):
        candidate = clone(pipeline)
        candidate.fit(train.iloc[fit_ids], np.arange(len(fit_ids), dtype=float)+1.)
        preprocessor = candidate.named_steps["preprocess"]
        cols = preprocessor.named_steps["columns"]
        numeric_names = list(cols.transformers_[0][2])
        expected_median = train.iloc[fit_ids]["CO"].median()
        assert cols.named_transformers_["numeric"].named_steps["impute"].statistics_[numeric_names.index("CO")] == expected_median
        assert "TEST_ONLY_LATE_STATION" not in cols.named_transformers_["categorical"].named_steps["one_hot"].categories_[0]
        assert np.isfinite(candidate.predict(train.iloc[evaluate_ids])).all()
        clones.append(candidate)
    assert clones[0].named_steps["preprocess"] is not clones[1].named_steps["preprocess"]
    assert not hasattr(pipeline.named_steps["model"], "n_features_in_")


@pytest.mark.parametrize("model", ["ridge", "random_forest"])
@pytest.mark.parametrize("feature_set", ["A", "B"])
def test_joblib_fresh_process_save_load_names_transform_and_predictions(configs, tmp_path, model, feature_set):
    train, heldout = fixture_features(configs[0], feature_set)
    pipeline = factory(model, feature_set, configs, complete=True)
    pipeline.fit(train, np.arange(1., 7.))
    output = tmp_path / "TEST_ONLY_roundtrip_output.joblib"
    bundle = tmp_path / "TEST_ONLY_pipeline.joblib"
    joblib.dump({"pipeline": pipeline, "features": heldout}, bundle)
    code = (
        "import sys,joblib; b=joblib.load(sys.argv[1]); p=b['pipeline']; x=b['features']; "
        "joblib.dump({'predictions':p.predict(x),'transformed':p.named_steps['preprocess'].transform(x),"
        "'names':p.named_steps['preprocess'].get_feature_names_out()},sys.argv[2])"
    )
    run = subprocess.run([sys.executable, "-c", code, str(bundle), str(output)], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=45)
    assert run.returncode == 0, run.stderr
    reloaded = joblib.load(output)
    np.testing.assert_allclose(reloaded["predictions"], pipeline.predict(heldout), rtol=0, atol=0)
    np.testing.assert_array_equal(reloaded["names"], pipeline.named_steps["preprocess"].get_feature_names_out())
    assert_frame_equal(reloaded["transformed"], pipeline.named_steps["preprocess"].transform(heldout))


def test_factories_are_unfitted_cloneable_and_do_not_mutate_config(configs):
    before = deepcopy(configs)
    train, _ = fixture_features(configs[0])
    pipeline = factory("ridge", "A", configs, complete=True)
    clone(pipeline)
    with pytest.raises(NotFittedError):
        pipeline.predict(train)
    with pytest.raises(NotFittedError):
        pipeline.named_steps["preprocess"].get_feature_names_out()
    assert not hasattr(pipeline.named_steps["model"], "coef_")
    assert configs == before


def test_column_reordering_preserves_output_and_index(configs):
    train, heldout = fixture_features(configs[0])
    pipeline = factory("ridge", "A", configs)
    pipeline.fit(train)
    assert_frame_equal(pipeline.transform(heldout), pipeline.transform(heldout.loc[:, heldout.columns[::-1]]))


@pytest.mark.parametrize("kind", ["extra_target", "missing_column", "duplicate", "array", "nonfinite", "bad_numeric", "bool", "bad_category", "reserved_category"])
def test_schema_rejects_wrong_features_instead_of_silently_dropping(configs, kind):
    train, heldout = fixture_features(configs[0])
    pipeline = factory("ridge", "A", configs)
    pipeline.fit(train)
    if kind == "extra_target": heldout["target_pm25"] = 123.
    elif kind == "missing_column": heldout = heldout.drop(columns="PM2.5")
    elif kind == "duplicate": heldout = pd.concat([heldout, heldout[["PM2.5"]]], axis=1)
    elif kind == "array": heldout = heldout.to_numpy()
    elif kind == "nonfinite": heldout["PM2.5"] = np.inf
    elif kind == "bad_numeric": heldout["PM2.5"] = "TEST_ONLY_NOT_NUMBER"
    elif kind == "bool": heldout["PM2.5"] = True
    elif kind == "bad_category": heldout["wd"] = [123, 456]
    else: heldout["wd"] = "__MISSING__"
    with pytest.raises(ValueError):
        pipeline.transform(heldout)


@pytest.mark.parametrize("kind", ["model", "feature_set", "mean_imputer", "scale_rf", "unknown_error", "empty_token", "missing_mode", "clipping"])
def test_unsupported_config_is_explicit(configs, kind):
    model, feature_set = "ridge", "A"
    if kind == "model": model = "TEST_ONLY_OTHER"
    elif kind == "feature_set": feature_set = "C"
    elif kind == "mean_imputer": configs[1]["numeric"]["imputation_strategy"] = "mean"
    elif kind == "scale_rf": configs[1]["numeric"]["scale"]["random_forest"] = True
    elif kind == "unknown_error": configs[1]["categorical"]["handle_unknown"] = "error"
    elif kind == "empty_token": configs[1]["categorical"]["fill_value"] = ""
    elif kind == "missing_mode": configs[1]["numeric"]["missing_indicators"] = "missing-only"
    else: configs[1]["prediction_postprocessing"]["negative_predictions"] = "clip_zero"
    with pytest.raises(ValueError):
        factory(model, feature_set, configs)


def test_indicator_ablation_can_be_explicitly_disabled(configs):
    configs[1]["numeric"]["missing_indicators"] = "none"
    train, _ = fixture_features(configs[0])
    pipeline = factory("ridge", "A", configs)
    result = pipeline.fit_transform(train)
    assert not result.columns.str.startswith("missing__").any()


def test_negative_predictions_are_returned_without_clipping(configs):
    train, _ = fixture_features(configs[0])
    for name in train.columns.difference(["station", "wd", "PM2.5"]):
        train[name] = 1.
    train["station"], train["wd"] = "TEST_ONLY_STATION", "N"
    pipeline = factory("ridge", "A", configs, complete=True)
    pipeline.fit(train, 2*train["PM2.5"]-10.)  # Positive TEST_ONLY targets.
    heldout = train.iloc[[0]].copy()
    heldout["PM2.5"] = 0.
    prediction = pipeline.predict(heldout)
    raw = pipeline.named_steps["model"].predict(pipeline.named_steps["preprocess"].transform(heldout))
    assert prediction[0] < 0
    np.testing.assert_array_equal(prediction, raw)
