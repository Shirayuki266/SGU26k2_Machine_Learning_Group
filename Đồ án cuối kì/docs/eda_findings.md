# T06 — EDA train và quyết định cho T07/T08

Ghi chú sau T07: đây là kết quả/thiết kế tại thời điểm T06, giữ nguyên bảng,
hình và manifest. Người dùng đã chốt T07 bỏ lag 2h, dùng lịch giờ dự báo t+1
và cho phép sin/cos giờ/tháng có cơ sở; cấu hình thực thi hiện hành ở
[feature dictionary](feature_dictionary.md). Verifier dùng config T06 từ
Git để kiểm provenance lịch sử khi chỉ phần features được cập nhật.

## Phạm vi và nguồn bằng chứng

Issue #12; T05/PR #11 đã merge. Phân tích ngày 02/11/2026 bằng
[notebook đã thực thi](../notebooks/01_train_eda.ipynb), gọi
[`beijing_air.eda`](../src/beijing_air/eda.py). Kế thừa năm nhóm nội dung của
`Tuan03/Lab03/eda_analysis.ipynb`: cấu trúc, đơn biến, đa biến, missing/bất
thường và ngoại lệ; bổ sung chuỗi thời gian/trạm. Lab03 là Ames Housing,
không áp dụng suy luận về missing cấu trúc hoặc xóa outlier nhà ở sang PM2.5.

Nguồn duy nhất cho số liệu EDA là `data/processed/samples_full/train.csv`
và `sample_ids/train.csv`; kiểm tra checksum, khóa, target đúng +1 giờ,
cohort và membership với manifest T05. Không đọc CSV validation/test hoặc
raw toàn thời kỳ. Đọc split manifest chỉ để xác minh provenance/protocol.

| Thuộc tính train | Giá trị xác minh |
| --- | --- |
| Cohort operational | 205.977 dòng, 25 cột, 12 trạm |
| Cohort primary | 204.865 dòng, có PM2.5 tại origin |
| Origin thiếu PM2.5 | 1.112 dòng, vẫn giữ trong operational |
| Origin | 2013-03-01 00:00 → 2015-02-28 22:00 |
| Target | 2013-03-01 01:00 → 2015-02-28 23:00; không thiếu |
| Split | Theo target timestamp, trước 2015-03-01; chung ranh giới trạm |
| Snapshot T05 | `2129d08dbac2b6ebe6a6c7bf12cf8188d9ea7b0069939d690e27ad5c47cf0ddc` |
| SHA-256 train CSV | `ebc89c94b576f009705446da7c4bec079f750755e5755e5041b6a93f09226d46` |

[Manifest EDA](../reports/eda_train/eda_manifest.json) lưu checksum đầu vào,
module/config, Git tại lúc thực thi, phiên bản, số mẫu và checksum đầu ra.
Git dirty được ghi đúng vì chạy notebook trước commit. Đây là audit Data
Understanding, **không phải model run**; Experiment Log vẫn chỉ có header.

## 1. Loại biến, đơn vị, khóa và chuỗi thời gian

Khóa tự nhiên `(station,input_timestamp)` duy nhất, sắp tăng theo trạm/giờ;
`sample_id` SHA-256 ổn định. Dữ liệu là panel giờ có phụ thuộc thời gian,
không phải mẫu IID. Timestamp nguồn local-naive; không tự gán timezone.

11 số đo tại t là định lượng: pollutant (PM2.5, PM10, SO2, NO2, CO, O3) đều
µg/m³; TEMP/DEWP °C; PRES hPa; RAIN mm; WSPM m/s. `station` và `wd` định tính;
year/month/day/hour rời rạc và có cấu trúc lịch. `target_pm25` là nhãn liên
tục đúng t+1 cùng trạm, **không phải feature**. `No` đã bị loại; ID, nguồn
file/dòng, split và target timestamp chỉ phục vụ quản lý/truy vết.

[schema.csv](../reports/eda_train/schema.csv) có dtype, vai trò, đơn vị,
missing và số giá trị phân biệt từng cột. Ý nghĩa theo
[dictionary hiện có](data_dictionary.md), không suy đơn vị từ thang giá trị.
T07 chọn feature tường minh theo bộ A/B trong config, không lấy mọi cột số.

## 2. Đơn biến, missing, bất thường và ngoại lệ

| Số đo tại t | Missing | Mean | Median | Q99 | Max | Đơn vị |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| PM2.5 | 1.112 (0,54%) | 83,88 | 61 | 350 | 844 | µg/m³ |
| PM10 | 909 (0,44%) | 110,53 | 92 | 403 | 999 | µg/m³ |
| CO | 13.884 (6,74%) | 1.272,65 | 1.000 | 5.400 | 10.000 | µg/m³ |
| O3 | 6.033 (2,93%) | 55,52 | 42 | 240 | 1.071 | µg/m³ |
| WSPM | 174 (0,08%) | 1,63 | 1,3 | 6,1 | 13,2 | m/s |

Hình 01–03 và [numeric_summary](../reports/eda_train/numeric_summary.csv)
bao phủ toàn bộ 11 số đo và nhãn; [station_missing_pct](../reports/eda_train/station_missing_pct.csv)
phân rã missing theo trạm. PM2.5 lệch phải (skew 1,64), mean lớn hơn median;
target mean 84,00, không có nhãn được impute. Độ lệch chuẩn CO 1.079,72
µg/m³ so với WSPM 1,25 m/s cho thấy cần xét scaling ở Ridge.

PM2.5(t) có 7.678 cờ IQR (ngưỡng trên 263), 203 giá trị vượt ngưỡng rà soát
500 µg/m³; target tương ứng có 7.803/211 cờ. O3 có 18 giá trị vượt ngưỡng
rà soát 500. Không có vi phạm điều kiện vật lý theo chính sách T04.
Ngưỡng rà soát không phải chuẩn sức khỏe hoặc giới hạn hợp lệ UCI. Chưa có
bằng chứng cảm biến để kết luận các giá trị O3 cao là sai, nên giữ và nêu
rõ cần kiểm chứng nguồn nếu dùng để diễn giải chuyên sâu.

RAIN có 199.014 giá trị 0 trong 205.808 quan sát; Q25=Q75=0 khiến mọi giá
trị mưa dương bị gắn cờ IQR (6.794). Đây là ví dụ cụ thể cho việc không
dùng IQR làm quy tắc tự xóa. WSPM=0 cũng không phải missing; missing `wd`
không được suy thành lặng gió. Không áp quy tắc “missing nghĩa là không có
tiện ích” từ dataset nhà ở của Lab03.

Quyết định T08: thử median/cờ missing cho số đo, category missing riêng và
encoder có xử lý unknown cho station/wd; scaler cho Ridge, RF không bắt
buộc scaling. Mọi thống kê/encoder chỉ fit trong train của từng run/fold.
Không backfill, không mặc định missing là 0; không impute nhãn. Giữ đợt ô
nhiễm cao, chưa clip/xóa hoặc biến đổi target. Không cần predictor có phân
phối chuẩn để chạy hồi quy; chưa phân tích residual vì chưa fit model.

## 3. Đa biến và khác biệt trạm

Hình 04 cung cấp cả Pearson và Spearman; mẫu là từng cặp không thiếu,
[correlation_pairs](../reports/eda_train/correlation_pairs.csv) ghi đúng N.
Hình 05 hexbin dùng toàn bộ cặp quan sát, màu là mật độ theo thang log,
không vẽ đường hồi quy hoặc biến đổi nồng độ trên trục.

Pearson của nhãn t+1 với PM2.5(t) = 0,965, PM10(t) = 0,842,
TEMP(t) = −0,094, WSPM(t) = −0,274. PM2.5(t)/nhãn có 204.865 cặp,
khác tổng 205.977 nhãn. TEMP/PRES tương quan khoảng −0,80 và TEMP/DEWP
khoảng 0,83, cho thấy một số predictor liên hệ mạnh. Pearson nhỏ của một
biến không chứng minh biến đó vô ích hoặc không có quan hệ phi tuyến.

Hình 06 và [station_summary](../reports/eda_train/station_summary.csv):
median PM2.5 tại Dingling thấp nhất 45, Wanliu cao nhất 68 µg/m³.
Số mẫu trạm từ 16.881 (Huairou) đến 17.398 (Wanliu); không coi các trạm
có coverage/missing giống nhau. Tần suất station/wd lưu ở
[categorical_counts](../reports/eda_train/categorical_counts.csv).

Quyết định T07/T08: giữ A gồm khí tượng/pollutant và station/wd theo
protocol; encoder không áp thứ bậc lên hướng gió/mã trạm. Ridge dùng
regularization; chưa loại biến theo correlation. T12 mới thử selection
trong từng fold. Tương quan và khác biệt trạm có thể bị nhiễu bởi mùa,
khí hậu, thiếu và phụ thuộc thời gian; không suy nguyên nhân hay mức cải
thiện dự báo từ biểu đồ. EDA này phục vụ trạm đã quan sát, chưa kiểm chứng
khả năng chuyển sang trạm mới.

## 4. Giờ/tháng/mùa, timeline, khoảng trống và tự tương quan

Hình 07 dùng lịch tại **origin**, gộp các năm/trạm và báo count/mean/median/
IQR trong bảng. Mean theo giờ thấp nhất 07h (77,1), cao nhất 22h (94,6)
µg/m³; theo mùa JJA 73,0, MAM 82,8, SON 85,7, DJF 94,4 µg/m³.
Mùa khí tượng quy ước DJF=12/1/2, MAM=3/4/5, JJA=6/7/8, SON=9/10/11.
Đây là nhóm tháng theo lịch, không phải nhãn khí hậu được học từ dữ liệu.
T07 giữ lịch biết trước; biểu diễn chu kỳ là giả thuyết có thể kiểm tra
sau bằng CV, không tự đổi bộ feature đã chốt.

Hình 08 là daily mean/max của PM2.5 theo trạm, giữ NaN cho ngày không có
quan sát; không nội suy. [daily_station](../reports/eda_train/daily_station.csv)
ghi số dòng và số đo thực sự quan sát mỗi ngày. Có những đợt tăng đồng
thời ở nhiều trạm nhưng hình không đủ để xác định cơ chế phát thải.
Daily mean dựa trên số giờ hiện có, không mặc định đủ 24 giờ.

[sample_gaps](../reports/eda_train/sample_gaps.csv) ghi 4.251 origin vắng
trong span đầu–cuối từng trạm, 1.112 đoạn; dài nhất 343 giờ tại Aotizhongxin.
T05 đã bỏ origin có target thiếu nên đây là **khoảng trống cohort supervised**,
không phải phép đo lại giờ thiếu raw. Không đọc raw toàn thời kỳ để truy
nguyên trong T06. T07 cần tính lag/rolling trên timeline quan sát T04, chỉ
dùng thời điểm ≤t, rồi chọn sample IDs T05; tính trên các dòng supervised
đã nén sẽ có nguy cơ nhầm độ trễ. Không làm bước tạo feature trong T06.

Hình 09 và [autocorrelation](../reports/eda_train/autocorrelation.csv)
ghép PM2.5(t) với PM2.5(t−h) đúng timestamp **cùng trạm**, chỉ lấy cặp có
số đo; không `.dropna().autocorr()` hoặc shift theo dòng qua gap. Báo số
cặp theo trạm/lag; thiếu <3 cặp hoặc hằng số thì để NA. Trung bình đều
theo trạm: 1 giờ 0,965; 24 giờ 0,363; 168 giờ 0,004. Đây là Pearson trên
chuỗi chưa khử trend/mùa, không phải ACF trên timeline hoàn chỉnh và không
có kiểm định p-value theo giả định IID.

Quyết định T07: thử B với lag 1/2/3/6/12/24h và rolling 3/6/12/24h đã
chốt; kiểm tra exact-hour và tính nhân quả. T09 phải có persistence và
fallback cho origin thiếu. Chưa khẳng định B tốt hơn A, chưa dùng lag
168h làm feature hoặc thêm feature ngoài protocol từ EDA này.

## 5. Artifact và tái lập

| Nhóm | Đường dẫn |
| --- | --- |
| Notebook thực thi đủ 13 code cell | [01_train_eda.ipynb](../notebooks/01_train_eda.ipynb) |
| Module / runner / verifier | [eda.py](../src/beijing_air/eda.py), [run_eda_notebook.py](../scripts/run_eda_notebook.py), [verify_eda.py](../scripts/verify_eda.py) |
| Config EDA / protocol / chất lượng | [eda.json](../configs/eda.json), [default.json](../configs/default.json), [data_quality.json](../configs/data_quality.json) |
| 14 bảng thống kê, chỉ mục CSV và manifest | [reports/eda_train](../reports/eda_train) |
| 9 PNG gốc, 150 dpi | [reports/figures/eda_train](../reports/figures/eda_train) |
| Chỉ mục từng hình, bảng nguồn và nhận xét | [figure_index.md](../reports/eda_train/figure_index.md), [figure_index.csv](../reports/eda_train/figure_index.csv) |
| Tests tổng hợp TEST_ONLY | [test_eda.py](../tests/test_eda.py) |

Từ thư mục `Đồ án cuối kì`, dùng môi trường T01 đã cài package editable:

```powershell
# Đã chạy: smoke, sau đó full từ kernel mới bằng đúng interpreter hiện có.
.\.venv\python.exe scripts/run_eda_notebook.py --mode smoke --output-tag execution_check
.\.venv\python.exe scripts/run_eda_notebook.py --mode full

# Chạy lại để đối chiếu, giữ báo cáo/notebook full chính thức hiện có.
.\.venv\python.exe scripts/run_eda_notebook.py --mode full --output-tag reproduce
.\.venv\python.exe scripts/verify_eda.py
.\.venv\python.exe -m pytest tests/test_eda.py -q --basetemp=.pytest_cache/t06-eda
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t06-regression
```

Venv chuẩn dùng `.\.venv\Scripts\python.exe`; Unix dùng interpreter đã cài
`python -m pip install -e .`. Không thêm dependency mới: Jupyter cung cấp
nbclient/nbformat/ipykernel; matplotlib/seaborn đã có ở T01. Máy này dùng
Python portable 3.12.10, pandas 3.0.6, numpy 2.5.4, matplotlib 3.11.2,
seaborn 0.13.2, nbclient 0.11.0, nbformat 5.11.1.

Runner tạo kernel riêng dùng `sys.executable`, clear toàn bộ outputs trước
chạy, đóng kernel khi xong. Cache/kernel và notebook smoke/reproduce nằm
trong `artifacts/t06_runtime/` (ignore). Smoke lấy tối đa 336 dòng đầu mỗi
trạm từ train full, chỉ kiểm tra thực thi; không dùng để quyết định. Tên
thư mục của smoke luôn có `_smoke`. Không lấy mẫu ngẫu nhiên, seed=42 chỉ
là metadata theo config.

Đầu ra đã có không bị ghi đè. Chạy lại dùng tag mới; notebook ở giao diện
Jupyter cũng cần đổi `OUTPUT_TAG` trước **Restart & Run All**. Lỗi giữa chừng
có thể để thư mục output chưa hoàn tất; không dùng khi thiếu manifest
`status=complete`, kiểm tra rồi dùng tag mới. Không tự xóa để thử lại.

Clone mới cần tái tạo T04/T05 theo README; do provenance/code có thể khác
snapshot đã commit, dùng T05 `--output-tag reproduce`, rồi truyền
`--split-manifest reports/splits_full_reproduce/split_manifest.json`
và tag EDA mới. Không cần mở validation/test cho EDA sau khi có train T05.
Để kiểm tra bộ artifact tái tạo, truyền `--report reports/eda_train_reproduce`
và `--notebook artifacts/t06_runtime/executed_full_reproduce.ipynb` cho verifier.
Các CSV dataset/IDs vẫn ignore; các bảng tổng hợp và PNG nhỏ được commit.
Quy tắc `.gitattributes` giữ LF cho source/artifact T06 để checkout Windows
không tự đổi byte của các file được đối chiếu SHA-256.

Verifier tính lại toàn bộ 14 bảng từ train, đối chiếu số, caption, checksum
và notebook đã thực thi; không chỉ kiểm tra file tồn tại. Fixture kiểm thử
hai trạm, giờ khuyết, nhãn thiếu, hằng số, đợt cao, boundary, membership và
checksum; spy file đọc bảo đảm không chạm holdout. Regression bỏ đúng test
T04 đọc raw/full để giữ phạm vi chỉ train của T06.

Kết quả local đã chạy: smoke và full đều đủ 13 code cell từ kernel mới;
verifier PASS 14 bảng tính lại, 9 PNG/caption và hình nhúng notebook khớp
file gốc; pytest riêng T06 **15 passed**, regression **108 passed,
1 deselected** (ca T04 nêu trên). Repo có 0 GitHub Actions workflow tại lúc
kiểm tra, chưa cấu hình CI; đây là kết quả local.

## Giới hạn và phần chưa xác minh

Hai năm train và cohort có target quan sát không đại diện cho toàn bộ raw
hoặc mọi tình huống thiếu. Chưa biết cơ chế missing, chưa xác minh từng đợt
cao bằng dữ liệu cảm biến bên ngoài; không xem cờ rà soát là lỗi đã xác nhận.
Tương quan gộp có thể khác theo mùa/trạm; không suy nhân quả, chưa phân tích
dịch chuyển validation/test. Số thống kê không phải metric dự báo.

Chưa fit imputer/encoder/scaler/selector, chưa tạo A/B, huấn luyện, tuning,
đánh giá test hoặc triển khai T07 trở đi. Quyết định trên là đề xuất chuyển
giao theo bằng chứng train, cần xác nhận bằng protocol thực nghiệm sau này.
Chưa kiểm môi trường máy sạch; CI tùy cấu hình repo, chỉ báo trạng thái thực
tại PR. Codex hỗ trợ source/notebook, kiểm tra và diễn giải số liệu; chưa
xác minh đóng góp của từng thành viên và chưa tạo hồ sơ giữa kỳ.
