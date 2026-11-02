# T08 — Preprocessing train-only cho Ridge và Random Forest

Issue #16; T07/PR #15 đã merge. Source:
[`beijing_air.preprocessing`](../src/beijing_air/preprocessing.py), config
[preprocessing.json](../configs/preprocessing.json), tests
[test_preprocessing.py](../tests/test_preprocessing.py).

T08 xây factory **chưa fit** cho preprocessing và pipeline hồi quy hoàn chỉnh.
Chỉ fit fixture TEST_ONLY nhỏ để kiểm tra giao diện/state/save-load; chưa fit
trên dataset dự án hoặc train mô hình full, chưa chạy baseline/tuning/metric.
Không đọc raw, ma trận feature thật, validation/test hoặc ghi Experiment Log.

## 1. Quyết định và cơ sở

| Thành phần | Quy tắc đã chốt | Cơ sở và giới hạn |
| --- | --- | --- |
| Numeric imputation | SimpleImputer median; học từ train của run/fold | T06 có CO thiếu 6,74%, phân phối pollutant lệch phải; không coi missing là 0 mặc định |
| Cột numeric toàn NA ở train | keep_empty_features=True, fallback 0 cố định của SimpleImputer | Không có median để học; giữ tên/chiều và cờ missing, không xem 0 là số đo thật |
| Numeric missing indicators | MissingIndicator(features="all") riêng trên dữ liệu trước impute | T07 rolling 24h thiếu 9,643%; nhận diện missing mới ở inference, không chỉ missing đã gặp ở train |
| Categorical missing | SimpleImputer constant `__MISSING__`; giữ cột toàn NA | Token định trước, không học mode trên holdout; None/pd.NA/np.nan được chuẩn hóa |
| station/wd | OneHotEncoder(categories="auto", handle_unknown="ignore", drop=None, sparse_output=False) | Vocabulary chỉ học từ train; không lấy danh sách category validation/test |
| Ridge | StandardScaler sau numeric imputation | Số đo có thang/đơn vị rất khác nhau theo EDA T06; scaler fit đúng train/fold |
| Random Forest | Numeric scale="passthrough" | Không cần scale numeric; vẫn dùng cùng imputation/indicators/OHE |
| Indicator/OHE | Giữ binary 0/1 (indicator dtype bool), không scale | Quy tắc giống nhau giữa Ridge/RF |
| Outlier | Không loại/clip số đo, không học threshold | Kế thừa T04/T06 giữ đợt ô nhiễm cao; không dùng test chọn ngưỡng |
| Dự báo âm | Identity cho persistence/Ridge/Random Forest | Giữ output gốc; chưa áp clipping hoặc chọn quy tắc từ test |

`missing_indicators="none"` là tùy chọn cấu hình tắt cờ rõ ràng cho ablation
sau này, chưa thử hiệu quả ở T08. Các quy tắc hiện hành khác được kiểm tra
tại factory; cấu hình clipping hoặc scale RF không được âm thầm bỏ qua.
Thiếu feature hoặc thêm target/ID/provenance vào X bị từ chối.

Một giới hạn cần hiểu đúng của categories="auto": nếu train chưa từng thiếu
categorical, token thiếu chưa có cột one-hot. Missing xuất hiện lúc inference
sẽ thành vector toàn 0 cho input categorical đó, giống category chưa thấy.
Nếu train đã thấy missing, nó có cột `__MISSING__` riêng; nếu cả cột train
đều thiếu, cột token vẫn được giữ. Cả ba tình huống đã được kiểm thử. Không
thêm category vào vocabulary từ holdout để thay đổi hành vi này.

Token `__MISSING__` được dành riêng: dữ liệu đầu vào chứa chuỗi này như một
category quan sát sẽ báo lỗi để tránh lẫn với missing. Các chuỗi category
khác, kể cả trạm mới/tiếng Việt, được giữ nguyên trước OHE.

## 2. Cấu trúc pipeline và schema

```text
Pipeline hồi quy
  preprocess: Pipeline
    schema: FeatureSchema (registry T07, normalize missing, giữ index)
    columns: ColumnTransformer
      numeric: SimpleImputer(median, keep_empty_features=True)
               -> StandardScaler [Ridge] / passthrough [RF]
      missing: MissingIndicator(features="all", sparse=False)
      categorical: SimpleImputer(constant="__MISSING__", keep_empty_features=True)
                   -> OneHotEncoder(handle_unknown="ignore", dense)
  model: Ridge / RandomForestRegressor (tham số từ config dự án)
```

Factory lấy allowlist từ `feature_registry(config)` T07, không tạo registry
song song. A có 20 input (18 numeric + station/wd), B có 33 (31 numeric +
station/wd). Lịch vẫn là t+1 biết trước và lịch sử vẫn có tính nhân quả theo
T07; preprocessing không tạo lại feature hoặc nhãn.

FeatureSchema yêu cầu DataFrame với đúng tập cột A/B, không trùng cột;
cho phép thứ tự cột input khác và đưa về registry order. ID ở index được
giữ nguyên. Numeric được chuyển float64, giữ NA, từ chối nonnumeric/inf/bool;
categorical chỉ nhận chuỗi hoặc missing. Không thay đổi dataframe đầu vào.
Đây là chuẩn hóa biểu diễn/schema, không học thống kê/categorical vocabulary.

Output preprocessing là DataFrame dense với index cũ và tên đầy đủ:
`numeric__CO`, `missing__missingindicator_CO`,
`categorical__station_<category>`… Truy xuất tên **sau fit**:

```python
names = fitted_pipeline.named_steps["preprocess"].get_feature_names_out()
```

Mặc định số cột output là `2*n_numeric + tổng số categories học từ train`.
Các fold có thể học vocabulary khác nhau nên chiều/tên OHE giữa fold không
bắt buộc giống nhau; trong cùng pipeline đã fit, tên/thứ tự/chiều phải giữ
nguyên khi transform/inference và sau load. Numeric all-empty không bị mất
cột, indicator có một cột cho mọi numeric dù train chưa thấy missing.

DataFrame output có cả float và bool; khi cần mảng NumPy đồng nhất dùng
`transformed.to_numpy(dtype="float64")`. Pipeline sklearn hoàn chỉnh nhận
output này trực tiếp. Chưa benchmark RAM/full; dense được chọn do station/wd
có vocabulary nhỏ, cần đánh giá lại nếu thêm categorical nhiều giá trị.

## 3. Factory và hai nguồn cấu hình

```python
from beijing_air.eda import read_json
from beijing_air.preprocessing import make_preprocessor, make_regression_pipeline

project_config = read_json("configs/default.json")
preprocessing_config = read_json("configs/preprocessing.json")

# Chỉ khởi tạo: không đọc dataset hoặc fit bất kỳ bước nào.
preprocessor = make_preprocessor(
    "ridge", feature_set="B", config=project_config,
    preprocessing_config=preprocessing_config,
)
pipeline = make_regression_pipeline(
    "random_forest", feature_set="A", config=project_config,
    preprocessing_config=preprocessing_config,
)
```

Config dự án tiếp tục là nguồn cho A/B, seed và initial_parameters của model.
Config mới chỉ định preprocessing/prediction policy, không sao chép schema,
split hay hyperparameter vào hệ thống song song. C chỉ được hỗ trợ khi task
selection đã chọn xong; hiện factory chỉ nhận A/B và ridge/random_forest.

Ridge/RF được khởi tạo từ `evaluation.initial_parameters` đã có. RF mặc định
300 trees/seed=42/n_jobs=1 theo config hiện hành, **chưa fit**. Tests chỉ dùng
bản config deepcopy TEST_ONLY có 3 trees/max_depth=2 trên 6 dòng tổng hợp,
không phải kết quả của cấu hình full hoặc dữ liệu dự án.

## 4. Training/CV/inference trong task sau

Ví dụ tích hợp dưới đây là giao diện cho task training sau, T08 không gọi
fit trên dữ liệu dự án:

```python
from sklearn.base import clone

def fit_future_training_partition(X_train, y_train, base_pipeline):
    # Caller chọn partition T05 hợp lệ, align y theo cùng sample IDs trước.
    assert X_train.index.equals(y_train.index)
    fitted = clone(base_pipeline)
    fitted.fit(X_train, y_train)
    return fitted

# Khi task tương ứng được giao:
# fitted = fit_future_training_partition(X_train, y_train, base_pipeline)
# validation_predictions = fitted.predict(X_validation)  # không fit lại
# one_prediction = fitted.predict(one_forecast.select("A"))
```

Pipeline không tự biết một DataFrame thuộc train/validation/test. Caller
phải chọn đúng partition/membership T05, kiểm nhãn đã sẵn sàng và CV purge
theo [temporal_samples.md](temporal_samples.md). Cột split/nhãn không nằm
trong X; schema guard ngăn chúng bị đưa vào như feature, không thay thế
kiểm tra thời gian và quyền mở test tại driver training.

Trong CV, clone **toàn bộ pipeline** cho từng fold rồi fit chỉ fold-train.
Không fit preprocessor một lần trên toàn train trước CV, không concat
holdout để học categories, không gọi fit_transform/fit trên validation/test.
Temporal CV thực tế vẫn dùng ranh giới chung theo unique target timestamps
của T02/T11; TimeSeriesSplit trong tests chỉ kiểm clone trên fixture một
chuỗi nhỏ, không phải triển khai CV trên panel dữ liệu dự án.

Preprocessor đơn có thể `.fit_transform(X_train)` rồi `.transform(X_eval)`
khi caller quản lý partition; factory hồi quy hoàn chỉnh là lựa chọn trực
tiếp để giữ thống kê đúng fold. Khi task mô hình được giao, Experiment Log
phải ghi cả project/preprocessing config, actual estimator params, bộ A/B,
names output từng fitted pipeline và policy dự báo âm, theo
[logger hiện có](experiment_logging.md). T08 không thêm run/metric vào log.

## 5. Serialize và chính sách dự báo âm

```python
import joblib

def save_future_fitted_pipeline(fitted, path):
    joblib.dump(fitted, path)  # lưu cả schema, imputer, scaler, OHE và model

# Task inference sau chỉ load/predict, không tái học vocabulary hoặc median:
# fitted = joblib.load(saved_pipeline_path)
# prediction = fitted.predict(one_forecast.select("B"))
```

FeatureSchema là class cấp module trong package, không dùng transformer
lambda/closure nên load được ở tiến trình Python mới có package đã cài.
Tests kiểm chính xác predictions, transformed DataFrame/index và feature
names trước/sau joblib trong tiến trình mới cho cả A/B và Ridge/RF. Các file
TEST_ONLY nằm trong thư mục tạm pytest, không commit thành model artifact.
Chưa cam kết load giữa các phiên bản sklearn khác nhau; bàn giao model thật
cần lưu môi trường/phiên bản cùng config và kiểm inference khi được giao.

Hiện pipeline trả nguyên dự báo từ estimator. Kiểm thử có Ridge dự báo âm
trên fixture và xác nhận không bị cắt. Policy identity được chốt chung cho
persistence/Ridge/RF trong config preprocessing. Nếu sau này cân nhắc clip
0 hoặc quy tắc khác, phải thiết kế/chốt trước hoặc bằng validation, áp dụng
nhất quán khi so sánh, lưu rule/config/predictions/metric tương ứng; không
âm thầm hậu xử lý riêng từng model hoặc chọn bằng test. Thay policy hiện tại
cần cập nhật version/protocol và kiểm tra, không chỉ thêm tham số bị bỏ qua.

## 6. Kiểm tra và giới hạn

Từ thư mục đồ án, dùng môi trường T01 hiện có:

```powershell
.\.venv\python.exe -m pytest tests/test_preprocessing.py -q --basetemp=.pytest_cache/t08-preprocessing-recheck
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t08-regression
.\.venv\python.exe -m pip check
```

Venv chuẩn dùng `.\.venv\Scripts\python.exe`. Không thêm dependency mới;
`pyproject.toml` quy định sklearn>=1.2 để có keep_empty_features,
sparse_output và pandas set_output. Máy đã kiểm: Python 3.12.10,
scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.4, joblib 1.6.0. Chưa chạy ma
trận phiên bản tối thiểu hoặc cài lại trên máy sạch; không coi import local
là kiểm chứng mọi tổ hợp phiên bản.

Tests bao phủ missing/all-empty numeric/categorical, new missing, unknown
category, scaler theo model, schema/feature names/index, không đổi input,
holdout thay giá trị không đổi state đã fit từ train, clone fold độc lập,
serialize/load mới, cấu hình sai và identity khi dự báo âm. Dữ liệu, station,
IDs và artifact test đều đánh dấu TEST_ONLY. Không tính metric dự báo hoặc
ghi fixture thành full run. Regression bỏ đúng ca T04 đọc raw/full thực để
giữ T08 không đọc dữ liệu dự án.

Kết quả đã chạy local: **37 tests T08 passed**, regression **176 passed,
1 deselected**, `pip check` báo **No broken requirements found**. Save/load
tiến trình mới kiểm cả 4 tổ hợp A/B × Ridge/RF; thay holdout không đổi hash
state pipeline đã fit từ fixture train. Đây là kiểm tra hạ tầng, không phải
validation metric hoặc model run full. CI được báo theo HEAD của PR.

Chưa benchmark/train full, đánh giá validation/test, ablation missing flags,
tuning, selection hoặc triển khai T09/T10. Chưa có pipeline/model fitted
trên dữ liệu dự án hoặc kết quả trả lời RQ. Codex hỗ trợ source, config,
kiểm tra và tài liệu; không suy đóng góp học thuật từ người chạy.
