"""TEST_ONLY categorical fixtures against saved T13 weights; no dataset or fit."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from beijing_air.demo import load_demo_model

ROOT = Path(__file__).resolve().parents[1]
DTYPES = ["object", "string[python]", "string[pyarrow]"]


def fixed_features(model, dtype="object"):
    """Synthetic values/IDs, unrelated to any train/validation/test sample."""
    x = pd.DataFrame({name: [10., 20., 30., 40.] for name in model.feature_names},
                     index=pd.Index([f"TEST_ONLY_ISSUE35_{i}" for i in range(4)], name="sample_id"))
    x["station"] = pd.Series(["Aotizhongxin", "Changping", "Aotizhongxin", "Changping"], index=x.index, dtype=dtype)
    x["wd"] = pd.Series(["N", "S", "E", "W"], index=x.index, dtype=dtype)
    x["PM2.5"] = [12., 48., 125., np.nan]
    x["PRES"] = [1010., 1005., 1020., 1015.]
    x["RAIN"] = 0.
    x["target_hour"] = [0., 6., 12., 18.]
    x["target_month"] = [1., 4., 7., 10.]
    x["target_day_of_week"] = [0., 2., 4., 6.]
    for name, period in model.config["features"]["A"]["cyclic_calendar"].items():
        offset = 1 if name == "target_month" else 0
        for trig, function in (("sin", np.sin), ("cos", np.cos)):
            x[f"{name}_{trig}"] = function(2*np.pi*(x[name]-offset)/period)
    assert tuple(x.columns) == model.feature_names
    return x


@pytest.fixture(scope="module")
def saved_model():
    # Integration requirement: absent weights are a failure, not a silent skip.
    return load_demo_model(ROOT)


@pytest.fixture(autouse=True)
def forbid_fit(monkeypatch):
    from sklearn.pipeline import Pipeline
    from sklearn.ensemble import RandomForestRegressor
    from beijing_air.preprocessing import FeatureSchema
    def forbidden(*a, **k):
        raise AssertionError("Issue35 only loads/predicts saved weights; no fit")
    for cls in (Pipeline, RandomForestRegressor, FeatureSchema):
        monkeypatch.setattr(cls, "fit", forbidden)


@pytest.mark.parametrize("dtype", DTYPES)
@pytest.mark.parametrize("missing", [None, np.nan, pd.NA], ids=["None", "nan", "NA"])
@pytest.mark.parametrize("rows", [1, 4], ids=["single", "all_missing_batch"])
def test_missing_wind_preserved_for_saved_imputer(saved_model, dtype, missing, rows):
    pipeline = saved_model.pipeline
    x = fixed_features(saved_model, dtype).iloc[:rows].copy()
    x["wd"] = pd.Series([missing]*rows, index=x.index, dtype=dtype)
    original = x.copy(deep=True)
    state = joblib.hash(pipeline)
    pre = pipeline.named_steps["preprocess"]
    normalized = pre.named_steps["schema"].transform(x)
    assert normalized["wd"].dtype == object and normalized["wd"].isna().all()
    categorical = pre.named_steps["columns"].named_transformers_["categorical"]
    imputed = categorical.named_steps["impute"].transform(normalized[["station", "wd"]])
    assert imputed["wd"].eq("__MISSING__").all()
    expected = x.copy()
    expected["wd"] = pd.Series([np.nan]*rows, index=x.index, dtype=object)
    np.testing.assert_allclose(pipeline.predict(x), pipeline.predict(expected), rtol=0, atol=0)
    pd.testing.assert_frame_equal(x, original)
    assert joblib.hash(pipeline) == state


@pytest.mark.parametrize("dtype", DTYPES)
def test_unknown_valid_and_roundtrip_without_refit(saved_model, dtype, tmp_path):
    pipeline = saved_model.pipeline
    x = fixed_features(saved_model, dtype)
    reference = fixed_features(saved_model, "object")
    np.testing.assert_allclose(pipeline.predict(x), pipeline.predict(reference), rtol=0, atol=0)
    x.loc[x.index[0], "wd"] = "TEST_ONLY_UNSEEN_WIND"
    x.loc[x.index[1], "wd"] = pd.NA
    z = pipeline.named_steps["preprocess"].transform(x)
    assert z.filter(like="categorical__wd_").iloc[0].eq(0).all()
    state = joblib.hash(pipeline)
    path = tmp_path/"TEST_ONLY_saved_T13_roundtrip.joblib"
    joblib.dump(pipeline, path)  # Only a temporary copy; never replace T13 weights.
    loaded = joblib.load(path)
    loaded_state = joblib.hash(loaded)
    np.testing.assert_allclose(loaded.predict(x), pipeline.predict(x), rtol=0, atol=0)
    np.testing.assert_array_equal(loaded.named_steps["preprocess"].get_feature_names_out(), z.columns)
    pd.testing.assert_frame_equal(loaded.named_steps["preprocess"].transform(x), z)
    # RF node buffers contain padding: joblib.hash is useful for mutation of
    # one instance, but not guaranteed equal across separate deserializations.
    assert joblib.hash(pipeline) == state
    assert joblib.hash(loaded) == loaded_state


@pytest.mark.parametrize("bad", [123, True, ["N"]])
def test_nonstring_observed_category_still_rejected(saved_model, bad):
    x = fixed_features(saved_model)
    x.at[x.index[0], "wd"] = bad
    with pytest.raises(ValueError, match="Categorical values must be strings"):
        saved_model.pipeline.predict(x)


@pytest.mark.parametrize("dtype", DTYPES)
def test_reserved_category_still_rejected(saved_model, dtype):
    x = fixed_features(saved_model, dtype)
    x.loc[x.index[0], "wd"] = "__MISSING__"
    with pytest.raises(ValueError, match="Reserved missing category"):
        saved_model.pipeline.predict(x)
