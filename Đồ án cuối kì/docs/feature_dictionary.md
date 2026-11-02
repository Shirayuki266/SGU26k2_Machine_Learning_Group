# T07 — Bộ feature A/B nhân quả và registry

Issue #14; phụ thuộc T05 và T06/PR #13 đã merge. Source thực thi:
[`beijing_air.features`](../src/beijing_air/features.py), cấu hình duy nhất
ở mục `features` của [default.json](../configs/default.json).

T07 được người dùng chốt **lịch của giờ dự báo t+1**, không phải lịch origin
t như thiết kế T02 cũ; lag là **1/3/6/12/24 giờ**, bỏ lag 2h. Có thêm sin/cos
giờ/tháng trong cả A/B: EDA train T06 cho thấy mean thay đổi theo giờ và tháng,
đồng thời mã số giờ/tháng có điểm nối 23→0, 12→1. Công thức cố định này không
fit và không cần tương lai. Đây là cơ sở thiết kế, chưa chứng minh tăng độ
chính xác; T10/T12 mới kiểm tra hiệu quả theo protocol. Bảng/hình/manifest
T06 vẫn giữ nguyên như bằng chứng lịch sử, không sửa ngược kết quả EDA.

## 1. Hợp đồng input/output và thời điểm khả dụng

- `observations`: dataframe timeline T04 có station, timestamp, 11 số đo và
  wd, chưa impute. Timestamp local-naive, đúng giờ; khóa station–timestamp
  duy nhất. Nồng độ cao hợp lệ vẫn giữ. Source/provenance/No và cột lạ không
  được chọn vào feature.
- `requests`: sample_id, station, input_timestamp=t, target_timestamp=t+1;
  tùy có is_primary/split. ID phải khớp scheme `pm25-h1-v1` T05. Nhãn,
  giá trị feature trong requests hoặc source_row không tham gia tính toán.
- Mỗi request phải có **quan trắc thực tế tại origin** trong observations,
  dù giá trị PM2.5(t) có thể NA. Giờ không có hàng quan trắc không được tạo
  thành mẫu giả. Thứ tự và IDs request được giữ nguyên.
- `FeatureResult.features`: X của B, index là sample_id; `.select("A")` hoặc
  `.select("B")` chỉ lấy allowlist registry theo thứ tự. sample_id không là
  cột feature. `sample_metadata` giữ khóa, thời gian và cohort/split; không
  chứa nhãn. `missing_reasons` là audit int8 cùng shape với X, không là X.
- Chỉ số đo thời gian ≤t, cùng trạm, được dùng. Lịch target là phép tính từ
  t+1 biết trước, không phải phép đọc PM2.5(t+1). Target timestamp/nhãn không
  được dùng như predictor số. Giả định số đo giờ t đã sẵn sàng theo T02.

## 2. Dictionary bộ A — 20 cột

Registry máy đọc có **một dòng cho từng feature** tại
[feature_registry.csv](../reports/features_full/feature_registry.csv): tên,
nguồn, offset giờ nguồn, thời điểm khả dụng, ý nghĩa, kiểu, đơn vị, bộ A/B,
missing policy và công thức. Bảng dưới nhóm các cột có cùng quy tắc.

| Feature | Nguồn và ý nghĩa | Kiểu / đơn vị | Khả dụng / bộ |
| --- | --- | --- | --- |
| PM2.5, PM10, SO2, NO2, CO, O3 | Nồng độ đúng giờ t cùng trạm; CO cũng µg/m³ | float64 / µg/m³ | Tại t / A;B |
| TEMP, DEWP | Nhiệt độ/điểm sương tại t | float64 / °C | Tại t / A;B |
| PRES | Áp suất tại t | float64 / hPa | Tại t / A;B |
| RAIN | Lượng mưa tại t | float64 / mm | Tại t / A;B |
| WSPM | Tốc độ gió tại t | float64 / m/s | Tại t / A;B |
| station | Mã trạm; vừa là khóa nhóm vừa là categorical feature | string / category | Biết tại t / A;B |
| wd | Hướng gió tại t; không suy thứ bậc từ mã | string / category | Tại t / A;B |
| target_hour | `(t+1h).hour`, 0–23 | int64 / calendar | Biết trước tại t / A;B |
| target_month | `(t+1h).month`, 1–12 | int64 / calendar | Biết trước tại t / A;B |
| target_day_of_week | `(t+1h).dayofweek`, Monday=0 tới Sunday=6 | int64 / calendar | Biết trước tại t / A;B |
| target_hour_sin, target_hour_cos | sin/cos của `2π*target_hour/24` | float64 / không đơn vị | Biết trước tại t / A;B |
| target_month_sin, target_month_cos | sin/cos của `2π*(target_month−1)/12` | float64 / không đơn vị | Biết trước tại t / A;B |

Giữ cả mã lịch số và sin/cos theo config; chưa học encoder/scaler hoặc tự
loại cột vì dư thừa. Ví dụ origin 2020-12-31 23:00 có lịch forecast
2021-01-01 00:00: hour=0, month=1, day_of_week=4. Không lấy cột hour/month
raw tại origin để thay các cột này.

## 3. Dictionary bộ B — 33 cột

B gồm đủ 20 cột A cộng 13 cột lịch sử dưới đây, tất cả float64 và µg/m³.
Mọi nguồn đều cùng trạm, đã quan sát trước hoặc tại origin, không dùng
nhãn để lấp lịch sử. `C` chưa chọn, selection_method/selected_features vẫn null.

| Feature | Công thức / nguồn |
| --- | --- |
| pm25_lag_1h | PM2.5(station,t−1h) |
| pm25_lag_3h | PM2.5(station,t−3h) |
| pm25_lag_6h | PM2.5(station,t−6h) |
| pm25_lag_12h | PM2.5(station,t−12h) |
| pm25_lag_24h | PM2.5(station,t−24h) |
| pm25_roll_mean_3h, pm25_roll_std_3h | Mean/std trên [t−2h,t], đủ 3 quan sát |
| pm25_roll_mean_6h, pm25_roll_std_6h | Mean/std trên [t−5h,t], đủ 6 quan sát |
| pm25_roll_mean_12h, pm25_roll_std_12h | Mean/std trên [t−11h,t], đủ 12 quan sát |
| pm25_roll_mean_24h, pm25_roll_std_24h | Mean/std trên [t−23h,t], đủ 24 quan sát |

Lag dùng lookup station/timestamp tuyệt đối, không shift theo dòng. Rolling
là time window `(t−wh,t]`, include current, min_periods=w, std mẫu ddof=1.
Vì khóa duy nhất và giờ được căn chỉnh, cửa sổ này có nhiều nhất w vị trí;
thiếu một giờ hoặc một giá trị PM2.5 làm cả mean/std NA. Không centered
rolling, không backfill, không nội suy. Một chuỗi hằng có std=0 khi đủ cửa
sổ, không phải missing. Reindex chỉ tra cứu timestamp cần thiết, không tạo
lưới output hoặc thêm mẫu/nhãn mới.

API cắt observations sau origin lớn nhất được yêu cầu của **từng trạm**
trước khi kiểm giá trị/tính rolling. Trong batch có origin muộn hơn, rolling
vẫn là trailing cho từng origin. Không group qua trạm; đổi future không làm
đổi feature quá khứ. Không lấy lịch sử chỉ từ sample train T05: các origin
bị loại vì target thiếu vẫn có thể cung cấp quan trắc hợp lệ cho lag sau đó.

## 4. Missing history và bảng missing thật

Missing không làm mất request hoặc đổi cohort. Primary vẫn chỉ là PM2.5(t)
có quan sát, **không** có nghĩa mọi feature B đều đủ lịch sử. T08 mới được
fit imputation trong training partition của từng run/fold; không impute target.

| Mã audit | Tên | Ý nghĩa, áp dụng theo thứ tự |
| ---: | --- | --- |
| 0 | observed | Feature có giá trị |
| 1 | current_value_missing | Số đo hoặc wd tại t thiếu |
| 2 | lag_before_history | Timestamp lag trước đầu history được cung cấp |
| 3 | lag_hour_absent | Timestamp lag trong span nhưng không có hàng quan trắc |
| 4 | lag_value_missing | Có hàng đúng giờ nhưng PM2.5 ở giờ đó NA |
| 5 | rolling_warmup | Thiếu và cửa sổ bắt đầu trước đầu history được cung cấp |
| 6 | rolling_incomplete | Cửa sổ trong span nhưng thiếu giờ/giá trị PM2.5 |

Các nguyên nhân loại trừ nhau, cộng bằng tổng missing; observed+missing=rows.
Thiếu buffer đầu inference không được đoán thành raw mất giờ. Raw UCI
snapshot hiện có không thiếu khóa giờ theo audit T04, nhưng có số đo NA.

Full train thực tế: **205.977 operational / 204.865 primary**. Lịch sử T04
được đọc tới 2015-02-28 22:00, từ 2013-03-01 00:00: 17.519 quan trắc/trạm,
210.228 quan trắc của 12 trạm. 4.251 origin trong timeline này không nằm
trong train T05; giữ chúng làm nguồn history, không thêm vào tập mẫu.

| Feature, operational train | Missing | Tỷ lệ |
| --- | ---: | ---: |
| PM2.5(t) | 1.112 | 0,540% |
| pm25_lag_1h | 1.511 | 0,734% |
| pm25_lag_3h | 1.869 | 0,907% |
| pm25_lag_6h | 2.201 | 1,069% |
| pm25_lag_12h | 2.655 | 1,289% |
| pm25_lag_24h | 3.272 | 1,589% |
| rolling mean/std 3h, mỗi cột | 3.117 | 1,513% |
| rolling mean/std 6h, mỗi cột | 5.766 | 2,799% |
| rolling mean/std 12h, mỗi cột | 10.724 | 5,206% |
| rolling mean/std 24h, mỗi cột | 19.862 | 9,643% |
| 7 cột lịch/sin/cos | 0 | 0% |

[missing_summary.csv](../reports/features_full/missing_summary.csv) có đủ
33 feature × 2 cohort, phân rã nguyên nhân. Bảng
[station_missing_summary.csv](../reports/features_full/station_missing_summary.csv)
có cùng thống kê cho từng trạm (792 dòng). Rolling 24h có 276 warmup và
19.586 incomplete; lag 24h có 288 trước history, 0 thiếu timestamp và 2.984
thiếu số đo. Số liệu này là chất lượng feature train, không phải metric model.

## 5. Quy ước ranh giới cuốn chiếu và fit

Không reset lịch sử tại train/validation/test hoặc ranh giới CV. Ví dụ
origin 2015-02-28 23:00 dự báo 2015-03-01 00:00 thuộc validation; khi số đo
23:00 đã có, có thể dùng nó và các quan trắc trước đó cho feature của mẫu.
Tương tự origin trong validation/test về sau có thể dùng quan trắc thật đã
nhận tới chính origin, đúng bài toán rolling một bước. Không dùng một buffer
ở origin đầu để giả vờ đã có số đo của cả holdout; không dùng forecast thay
quan trắc thật hoặc học lại estimator ở mỗi giờ.

Feature không fit gì nên không có bước học trên toàn dataset. Điều kiện nhãn
đã sẵn sàng lúc fit, CV purge, imputation/encoding/scaling và selector vẫn
theo T02/T05, do task huấn luyện kiểm soát. API cho phép buffer lịch sử hợp
lệ qua boundary; task này chỉ materialize train, các boundary thật của holdout
được kiểm bằng fixture TEST_ONLY, không mở test CSV.

## 6. API batch và một lần dự báo

```python
from beijing_air.features import build_features, features_for_prediction
from beijing_air.eda import read_json

config = read_json("configs/default.json")
# history: dataframe quan trắc T04, chưa impute, đủ schema nêu ở mục 1.
# train_requests: T05 train, hoặc chỉ các khóa ID/trạm/origin/target.
batch = build_features(history, train_requests, config=config)
X_A, X_B = batch.select("A"), batch.select("B")
# Nhãn giữ riêng trong T05, join bằng sample_id khi task training được giao.

# Dùng cùng thuật toán cho một forecast chưa có nhãn tại t+1.
one = features_for_prediction(
    history, station="Aotizhongxin", origin="2015-02-28 22:00", config=config,
)
one_X = one.select("B")
assert one_X.shape == (1, 33)
```

Một origin chỉ cần buffer cùng trạm từ t−24h tới t (tối đa 25 hàng nếu đủ
giờ), gồm tất cả số đo/wd tại t và PM2.5 lịch sử. Khóa thiếu hoặc giá trị
thiếu trong history vẫn theo policy NA; origin phải hiện diện. Buffer không
cần t+1 hoặc target_pm25. `scripts/verify_features.py` tái tạo đúng cách này
cho origin train cuối của **cả 12 trạm**, đối chiếu với batch full.

Khi đọc ma trận CSV, dùng `pd.read_csv(path,index_col="sample_id")` và chọn
allowlist registry; không dùng mọi cột số hoặc đưa ID thành predictor. Station
vẫn là categorical feature bên trong X, dù cũng có trong metadata.

## 7. Tạo lại, artifact và kiểm tra

Từ thư mục đồ án, dùng interpreter T01 đã cài package editable; không thêm
dependency. Máy hiện tại Python portable 3.12.10, pandas 3.0.6, numpy 2.5.4.

```powershell
.\.venv\python.exe scripts/build_features.py --mode smoke
.\.venv\python.exe scripts/build_features.py --mode full
.\.venv\python.exe scripts/verify_features.py
.\.venv\python.exe scripts/verify_eda.py
.\.venv\python.exe -m pytest tests/test_features.py -q --basetemp=.pytest_cache/t07-features
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t07-regression
```

Venv chuẩn thay bằng `.\.venv\Scripts\python.exe`; Unix dùng Python môi
trường đã cài `pip install -e .`. Smoke lấy tối đa 336 sample đầu mỗi trạm
từ train full (thực tế 4.032 mẫu), không phải kết luận cho toàn train.

Đầu ra:

| Artifact | Nội dung / trạng thái Git |
| --- | --- |
| data/processed/features_full/train_A.csv, train_B.csv | IDs và 20/33 feature, giữ NA; ignore, tổng hai ma trận khoảng 118 MB |
| data/processed/features_full/sample_metadata.csv | ID, station, timestamps, is_primary, split; ignore |
| reports/features_full/feature_registry.csv | 33 dòng dictionary/allowlist; commit |
| reports/features_full/missing_summary.csv | Missing/causes của 2 cohort; commit |
| reports/features_full/station_missing_summary.csv | Missing/causes theo trạm; commit |
| reports/features_full/feature_manifest.json | Provenance/checksum/config/code, số mẫu và trạng thái; commit |

Snapshot T07 full:
`1b01fe65f7bbff32d1273afd704241687b6f220dd867ee681446978db8139a51`.
Manifest liên kết T05 snapshot, hash train/IDs, raw identity, T04 audit, module,
script, effective A/B config, input scope, phiên bản và sáu artifact. Đây là
Data Preparation, không có model run_id; Experiment Log vẫn chỉ header.

CLI tái sử dụng T04 `load_station_data` trên prefix giới hạn bằng số giờ từ
audit, không ghép/audit lại toàn dữ liệu, không ghi lại raw hoặc merged CSV.
Điều kiện prefix UCI là mỗi trạm có timeline đều và thứ tự đúng như T04 đã
audit; script kiểm lại bounds/keys của prefix và dừng nếu lệch. Hash đọc
bytes toàn raw để xác minh danh tính, **chỉ giá trị prefix đến origin train
cuối vào DataFrame**; không mở sample CSV validation/test. API thuần hỗ trợ
giờ khuyết bất kỳ và báo missing theo timestamp, độc lập điều kiện loader UCI.

Sau khi tạo, CLI chạy lại cùng input/config/code chỉ kiểm checksum và giữ
nguyên file/created_at. Nếu khác, không ghi đè: dùng `--output-tag reproduce`
hoặc tag mới. Trên clone mới cần snapshot T04/T05 đã tái tạo theo README;
nếu T05 có tag thì truyền `--split-manifest reports/splits_full_reproduce/split_manifest.json`.
Verifier snapshot có tag dùng `--report reports/features_full_reproduce`.
Giữ cả dataset/metadata cùng manifest khi bàn giao; không commit dataset lớn.

Publish dùng staging kế thừa quyền thư mục cha rồi rename, manifest hoàn
tất ghi cuối trong staging. Nếu bị ngắt giữa rename, đầu ra thiếu manifest
bị từ chối; kiểm tra/bảo toàn trước khi dùng tag mới. Các output phụ, staging
và smoke được ignore. LF cố định cho file T07 phục vụ checksum sau checkout.

T06 artifact/config fingerprint lịch sử không bị sửa. Vì A/B config đã được
cập nhật, verifier EDA kiểm config T06 từ Git tại HEAD đã ghi (có xét LF/CRLF),
cho phép **chỉ** phần features khác; các trường khác phải giữ nguyên. Module
EDA/quality config, bảng/hình/PNG nhúng và input train vẫn kiểm như trước.
Nếu clone shallow thiếu commit T06 gốc, cần fetch lịch sử để kiểm provenance;
không bỏ kiểm checksum hoặc sửa manifest cũ cho pass.

## Giới hạn và chuyển giao

T07 chỉ tạo feature, chưa fit imputer/encoder/scaler, chọn C, baseline/model,
tuning hoặc metric. Hiệu quả của sin/cos và B so A chưa xác minh; thiếu
rolling dài có thể ảnh hưởng coverage, T08/T12 cần kiểm tra trên cùng sample
IDs và ghi log thực nghiệm khi được giao. Chưa kiểm môi trường máy sạch.

Tests dùng fixture TEST_ONLY hai trạm, missing/giờ khuyết, warmup/hằng số,
calendar đổi ngày/tháng/năm, future invariance trong batch có origin muộn hơn,
boundary train/validation/test, tái tạo single/batch, giữ input và checksum/
idempotence CLI. Các file holdout fixture cố ý không tồn tại để lộ truy cập
sai; regression bỏ đúng test T04 đọc raw/full thực. Codex hỗ trợ source,
kiểm tra và tài liệu; không tự điền đóng góp nhóm hoặc tạo lịch sử mô hình.

Kết quả local: **31 tests T07 passed**; regression **139 passed, 1 deselected**.
Smoke xuất 4.032 mẫu; full xuất 205.977 mẫu với A/B cùng membership. Verifier
tính lại hai ma trận và toàn bộ registry/missing, kiểm checksum sáu artifact,
tái tạo 12 forecast từ buffer 25 giờ không có target: PASS. Verifier T06
cũng PASS 14 bảng, 9 PNG/caption và 13 cell notebook, với config gốc từ Git.
Trạng thái CI được báo theo HEAD PR, không coi kiểm tra local là CI.
Kiểm tra cuối repo có 0 GitHub Actions workflow: chưa cấu hình CI. CLI full
chạy lại PASS kiểm checksum/idempotence, không ghi đè hoặc đổi created_at.
