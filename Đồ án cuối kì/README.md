# Beijing Air Quality

Dự án học máy dự báo nồng độ PM2.5 tại giờ t+1 của cùng trạm quan trắc ở Bắc Kinh. Dự báo được thực hiện sau khi có số đo giờ t và chỉ sử dụng thông tin có sẵn đến giờ t. Task 01 chỉ khởi tạo cấu trúc, môi trường và cấu hình; chưa tải dữ liệu, chưa huấn luyện mô hình.

Nguồn dữ liệu dự kiến do nhóm lựa chọn: [Beijing Multi-Site Air Quality, UCI dataset 501](https://archive.ics.uci.edu/dataset/501/beijing+multi-site+air+quality+data).

Dự án dùng baseline persistence, Ridge và Random Forest; đánh giá bằng MAE (chính), RMSE và R². Train/validation/test được chia theo thời gian; tiền xử lý fit trên train, không dùng test để tuning hay chọn đặc trưng. Target, lag và rolling phải đúng trạm, đúng thời gian và không dùng tương lai. Kết quả T09/T10 và phạm vi đã thực thi nằm trong các phần tương ứng bên dưới.

## Cấu trúc

```text
src/beijing_air/   Package Python chính
scripts/           Script kiểm tra và chạy các bước xử lý
notebooks/         Notebook khám phá dữ liệu
configs/           Cấu hình dự án
tests/             Kiểm thử
data/raw/          Dữ liệu gốc (không commit)
data/processed/    Dữ liệu đã xử lý (không commit)
artifacts/         Kết quả sinh ra; chỉ allowlist hồ sơ T10–T12 thật, không model lớn/cache
experiments/       CSV tổng hợp thực nghiệm (hồ sơ run trong artifacts/experiments/)
reports/figures/   Biểu đồ cho báo cáo
docs/              Tài liệu dự án
app/               Ứng dụng Streamlit
```

Dependencies được khai báo duy nhất trong `pyproject.toml`: pandas, numpy, scikit-learn, matplotlib, seaborn, joblib, streamlit, pytest và Jupyter. Package dùng cấu trúc `src`; cài editable để import `beijing_air` từ môi trường dự án.

Issue #35 ghim **pandas==3.0.6** (môi trường tái hiện lỗi guard categorical), yêu
cầu Python>=3.11 theo metadata pandas. Khi nạp model T13, dùng Python3.12 và
các phiên bản đã lưu theo [hướng dẫn demo](docs/demo.md). Bản sửa guard dùng
kiểm tra kiểu Python độc lập dtype, vẫn giữ missing cho imputer đã fit.
Xem [changelog và ảnh hưởng fingerprint](docs/changelog_issue35.md); không sửa
SHA/config/weights hoặc kết quả lịch sử. Khởi động lại app sau cập nhật source.

## Tạo môi trường trên Windows PowerShell

Cài Python 3.11 trở lên và Python Launcher (`py`), sau đó mở PowerShell tại thư mục chứa README này:

Các lệnh tạo venv bên dưới dành cho máy có Python cài chuẩn và chưa có `.venv`.
Nếu đã có `.venv\python.exe` portable như workspace hiện tại, dùng phần portable
bên dưới; không tạo venv chồng lên thư mục đó. `py -0p` giúp kiểm tra các Python
đã cài; launcher không tìm thấy Python thì cần cài Python chuẩn trước khi tạo
venv mới. Dùng đúng interpreter của môi trường khi cài dependencies cho project.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python scripts/check_imports.py
```

Nếu PowerShell chặn kích hoạt môi trường, có thể chạy trực tiếp interpreter trong môi trường:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts/check_imports.py
```

Với Python portable **đã có** tại `.\.venv\python.exe` của workspace này:

```powershell
.\.venv\python.exe --version
.\.venv\python.exe -m pip install "setuptools>=68" wheel
.\.venv\python.exe -m pip install --no-build-isolation -e .
.\.venv\python.exe -m pip check
.\.venv\python.exe scripts/check_imports.py
```

`--no-build-isolation` là cách cài đã kiểm chứng cho portable khi lệnh `pip install -e .` lỗi
`Cannot import 'setuptools.build_meta'`. Venv chuẩn dùng lệnh cài mặc định ở trên.
Không cần tải lại dữ liệu để kiểm tra môi trường. Script `check_imports.py` in
interpreter, phiên bản package và source path; kiểm tra cả metadata cài đặt để
không nhầm import từ `src` với cài package thành công. Phiên bản và lệnh kiểm tra
thực tế nằm trong [bảng xác minh T01](docs/t01_environment_verification.md).

Mở notebook bằng `python -m notebook` với đúng interpreter của môi trường;
portable dùng `.\.venv\python.exe -m notebook`. Các lệnh kiểm tra T01 không
khởi chạy notebook/server. Kiểm thử xử lý dữ liệu được bổ sung từ T04.

## Cấu hình

`configs/default.json` dùng JSON chuẩn, không cần thêm dependency đọc YAML. Giá trị mặc định: `seed=42`, `horizon_hours=1`, `mode="smoke"`. Hai chế độ dự kiến là `smoke` (chạy nhanh trên dữ liệu nhỏ) và `full` (chạy đầy đủ); pipeline sẽ được triển khai trong các task sau. Kết quả smoke không dùng làm kết quả chính thức. Các đường dẫn dữ liệu và đầu ra được tính từ thư mục gốc dự án này.

Các thư mục dữ liệu và artifacts giữ `.gitkeep` để bảo toàn cấu trúc trong Git, còn nội dung sinh ra và model nhị phân được bỏ qua.

## T02: đặc tả, CRISP-DM và giữa kỳ

[Problem definition](docs/problem_definition.md) và
[experiment plan](docs/experiment_plan.md) là đặc tả hiện hành; file T02 cũ
giữ vai trò chỉ mục truy vết quyết định. `configs/default.json` bổ sung hợp
đồng dưới đây cho các task sẽ triển khai, chưa tự chạy pipeline/model:

| Hợp đồng | Giá trị đã chốt |
| --- | --- |
| Mục tiêu | Hồi quy PM2.5, µg/m³; input tới t khi số đo t sẵn sàng, output đúng t+1 cùng trạm đã quan sát; dự báo cuốn chiếu |
| Split | Theo target_timestamp: train trước 2015-03-01; validation tới trước 2016-03-01; test từ 2016-03-01, vẫn khóa |
| Temporal CV | Expanding-window chỉ trong train, unique target timestamps, chung ranh giới trạm; fold fit target phải trước origin đánh giá đầu |
| Features | A=F0 số đo t, station/wd, lịch t+1 và sin/cos giờ/tháng; B=F1 thêm lag 1/3/6/12/24 giờ và rolling 3/6/12/24 giờ; C chọn từ B trong từng fold |
| Phương pháp/metric | Persistence có fallback/coverage riêng; Ridge/Random Forest ban đầu A; MAE chính, RMSE/R² bổ sung, cùng sample IDs |
| Test gate | Khóa phương án bằng train/CV/validation; chỉ T13 mới refit pipeline trên train+validation rồi test, không chọn lại bằng test |

[Project plan](docs/project_plan.md) mapping CRISP-DM với T01–T16 và T04-LOG
(cùng task logger T04-BỔ SUNG/Issue #6). [Midterm plan](docs/midterm_plan.md)
chốt MK01 tạo DOCX/PPTX từ tiến độ thật, MK02 đối chiếu và đóng gói; ưu tiên
kết quả tới T10, T11/T12 nếu có, không mở test lấy số liệu giữa kỳ.
Chưa có metric mô hình, DOCX/PPTX hoặc gói giữa kỳ được xác minh trong repo.
Codex hỗ trợ cập nhật tài liệu, chưa triển khai các task tiếp theo.

## Sự hỗ trợ của AI

Codex hỗ trợ khởi tạo cấu trúc, cấu hình, script kiểm tra import và hướng dẫn môi trường trong Task 01. Nhóm cần rà soát mã và tự xác nhận kết quả chạy; hiện chưa có kết quả thực nghiệm.

Commit đề xuất: `chore: initialize air quality project structure`

## Task 03: tải và audit dữ liệu gốc

Script PowerShell chạy độc lập với Python, dùng thư viện có sẵn trên Windows. Chạy từ thư mục dự án:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_raw.ps1 -Mode smoke
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_raw.ps1 -Mode full
```

Script tải ZIP chính thức UCI 501, tìm ZIP con `PRSA2017_Data_20130301-20170228.zip` rồi giải nén các CSV trạm trực tiếp vào `data/raw/`. Không dùng các CSV phụ trong ZIP ngoài và không thay bằng bộ Beijing PM2.5 một trạm. Các file đã tồn tại được kiểm tra SHA-256; nếu khác, script dừng và không ghi đè.

ZIP phải có đủ số file trạm theo metadata UCI (hiện là 12); ZIP thiếu trạm bị
từ chối trước khi xuất CSV. Khi raw/manifest đã có và còn khớp, script chỉ xác
minh, không tải lại hoặc ghi lại manifest. ZIP ngoài hoặc ZIP PRSA2017 bên
trong đều được chấp nhận nếu checksum đã được ghi trong manifest; giữ nguyên
descriptor ZIP gốc, nguồn và ngày tải ban đầu. Nếu metadata/checksum khác,
script dừng để rà soát, không tự thay provenance.

Nếu mạng bị chặn, mở [trang UCI 501](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data), chọn **Download**, lưu ZIP vào `data/raw/uci_501_download.zip`. Hoặc đặt ZIP PRSA2017 lấy từ gói tải chính thức vào `data/raw/PRSA2017_Data_20130301-20170228.zip`. Không cần tự giải nén. Chạy một trong hai lệnh tương ứng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/uci_501_download.zip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/PRSA2017_Data_20130301-20170228.zip
```

Với ZIP thủ công, thêm `-DownloadedAt "2026-10-12T10:00:00+07:00"` **chỉ khi đó là thời điểm tải thực tế của bạn**; ví dụ này không phải ngày tải mặc định. Nếu không biết, manifest ghi `null`, không suy ra từ ngày sửa file. Nếu lần tải lỗi để lại `.part`, kiểm tra và xóa riêng file tải dở đó trước khi thử lại; không xóa dữ liệu đã giải nén.

`-DownloadedAt` phải có offset timezone hoặc `Z`, được chuẩn hóa về UTC khi tạo
manifest mới. Manifest hiện có luôn giữ ngày tải đã ghi, không lấy ngày xác
minh lại thay ngày tải hoặc điền ngày cũ bằng phỏng đoán.

`reports/data_manifest.json` lưu nguồn, license, ngày tải UTC, thời điểm ghi manifest và SHA-256 của ZIP/CSV. Checksum là dấu vết của file tải thực tế, không phải checksum do UCI công bố. `configs/uci_501.json` ghi metadata tham chiếu chính thức. `docs/data_dictionary.md` ghi ý nghĩa và đơn vị các trường.

Audit đọc raw mà không sửa, impute hay huấn luyện; kiểm tra schema, tên trạm, kiểu giá trị, missing từng cột, số dòng, thời gian, timestamp trùng và khoảng trống giờ. Kết quả ghi `reports/raw_audit_smoke.json` hoặc `reports/raw_audit_full.json`; chỉ full được dùng cho báo cáo dữ liệu chính thức. Số dòng được đếm từ CSV rồi đối chiếu metadata, không gán bằng số công bố. Nếu lệch hoặc lỗi dữ liệu, script ghi báo cáo và trả lỗi.

Lần audit full Task 03 đã đếm 420.768 dòng từ 12 file/trạm, khớp số công bố. Báo cáo thực tế và giới hạn kiểm tra: [reports/data_audit.md](reports/data_audit.md). Raw vẫn giữ nguyên; chưa impute hoặc huấn luyện.

Kiểm thử cơ chế tải dùng fixture `TEST_ONLY` trong thư mục tạm, mock mạng và
không đọc/sửa raw dự án:

```powershell
.\.venv\python.exe -m pytest tests/test_acquisition.py -q --basetemp=.pytest_cache/t03-acquisition
```

Các ca PowerShell được skip rõ ràng nếu máy chưa có PowerShell; kết quả local
Windows của lần xác minh được ghi trong báo cáo audit. T03 chỉ kiểm tra nguồn
và chất lượng raw, không tạo split/mẫu dự báo hoặc đánh giá test mô hình.

## Sự hỗ trợ của AI (Task 03)

Codex hỗ trợ script tải/audit, từ điển dữ liệu và hướng dẫn sử dụng. Chưa thực hiện imputation hoặc huấn luyện. Commit đề xuất Task 03: `feat: add reproducible UCI dataset download and audit`.

## Task 04: hợp nhất và kiểm tra chất lượng

Sau khi đã tải raw và cài môi trường Python theo hướng dẫn phía trên:

```powershell
python -m pytest -q
python scripts/merge_data.py --mode smoke
python scripts/merge_data.py --mode full
```

Nếu dùng Python trong venv mà không kích hoạt, thay `python` bằng `.\.venv\Scripts\python.exe`. Lần chạy Task 04 trong workspace này dùng Python portable tại `.\.venv\python.exe` (được tải để kiểm tra, không phải venv chuẩn và không commit); có thể dùng interpreter đó để chạy các lệnh trên. Ở thời điểm T04, portable chỉ cài pandas, numpy, pytest và dependencies phụ. Trạng thái môi trường mới nhất xem [bảng xác minh T01](docs/t01_environment_verification.md).

Loader trong `src/beijing_air/data.py` đọc các file PRSA2017, kiểm tra inventory/checksum theo manifest, tạo timestamp từ năm/tháng/ngày/giờ, sắp xếp theo `station,timestamp` và xác nhận khóa duy nhất. `No` bị loại khỏi bảng hợp nhất; `source_file` và `source_row` chỉ dùng truy vết, không làm feature. Danh sách đầu vào mô hình phải chọn tường minh từ `FEATURE_COLUMNS`, không lấy tất cả cột trong bảng.

Quy tắc chất lượng chi tiết: [docs/data_quality_policy.md](docs/data_quality_policy.md). Không dùng IQR để xóa outlier, không impute, không thêm các hàng giờ bị thiếu và không tạo target/lag trong task này. Timestamp lỗi, số không hợp lệ, giá trị vi phạm điều kiện vật lý hoặc **bất kỳ trùng khóa nào** đều chặn xuất bảng hợp nhất. Audit phân biệt bản ghi trùng giống nhau và trùng mâu thuẫn; không dùng `No` hay thứ tự dòng để giữ một bản ghi. Ngưỡng rà soát trong `configs/data_quality.json` chỉ sinh cảnh báo, không kết luận số đo cao là sai và không đổi giá trị.

Đầu ra theo mode:

- `data/processed/merged_unimputed_<mode>.csv`: bảng hợp nhất chưa impute; missing ghi `NA`, raw giữ nguyên.
- `reports/quality_<mode>/issues.csv`: chi tiết lỗi/cảnh báo cùng nguồn dòng/cột.
- `reports/quality_<mode>/stations.csv`: khóa, khoảng thời gian và giờ thiếu mỗi trạm.
- `reports/quality_<mode>/summary.json`: số dòng, missing, dtype, cấu hình, phiên bản và checksum.

Mặc định không ghi đè đầu ra đã có. Chỉ thêm `--overwrite` khi chủ động chạy lại và chấp nhận thay đầu ra được sinh cho mode đó. Khi audit lỗi, không xuất bảng hợp nhất; nếu đã cho phép overwrite, bảng hợp nhất cũ của mode đó được xóa để tránh dùng nhầm kết quả đã hết hiệu lực, còn audit lỗi được lưu.

Smoke chỉ đọc 100 dòng đầu mỗi file, không dùng để kết luận chất lượng toàn bộ dữ liệu. Báo cáo full Task 04: [reports/data_quality.md](reports/data_quality.md). Codex hỗ trợ loader, kiểm thử và tài liệu; chưa impute hay huấn luyện.

Commit đề xuất: `feat: merge station data and validate temporal integrity`.

## T04-BỔ SUNG: Experiment Log

`beijing_air.experiment_logging.ExperimentLogger` cung cấp `start_run`,
`log_metrics`, `log_artifact`, `finish_run` và context manager tự ghi trạng thái
thành công/thất bại/ngắt, giữ lỗi và traceback. Mỗi run có UUID, config/metrics/
metadata/notes riêng trong `artifacts/experiments/`; CSV tổng hợp tại
`experiments/experiment_log.csv` được cập nhật bằng khóa hệ điều hành và thay
file an toàn. T04-LOG chỉ tạo header; T09 có smoke/full persistence thật,
xem [kết quả T09](docs/baseline_results.md). T10 bổ sung Ridge/RF và các run
trees được track trực tiếp; clone mới dùng [restore T09 cho ledger T10](docs/initial_findings.md)
trước khi ghi run mới để giữ liên kết/lịch sử.

Hướng dẫn API, ví dụ tích hợp baseline/training, null/UTF-8, artifact và phục hồi:
[docs/experiment_logging.md](docs/experiment_logging.md). Đọc
[workflow](docs/codex_workflow.md), [kế hoạch dự án](docs/project_plan.md) và
[kế hoạch giữa kỳ](docs/midterm_plan.md) trước task tiếp theo. Khi bàn giao run,
đóng gói cả CSV và `artifacts/experiments/` vì hồ sơ run đang được ignore trong Git.

[Quy trình GitHub](docs/github_workflow.md): mỗi task nhỏ dùng một Issue, branch
và PR; được commit/push branch và mở PR. Người dùng review và merge; không
merge, bật auto-merge hoặc tự đóng Issue.

Kiểm tra logger và hồi quy T04 bằng dữ liệu tổng hợp, không đọc dữ liệu full:

```powershell
.\.venv\python.exe -m pytest tests/test_experiment_logging.py -q --basetemp=.pytest_cache/t04-logging
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t04-logging-regression
```

Codex hỗ trợ logger, kiểm thử và tài liệu T04-BỔ SUNG. Chưa huấn luyện, tuning,
feature selection hoặc mở test set. Commit đề xuất:
`feat: add reproducible experiment logging infrastructure`.

## T05: target đúng một giờ và temporal split

Từ input T04 đã được audit, tạo target bằng join `(station,t+1 giờ)`, không
dùng dòng kế tiếp khi có giờ khuyết và không impute target:

```powershell
.\.venv\python.exe scripts/build_samples.py --mode smoke
.\.venv\python.exe scripts/build_samples.py --mode full
.\.venv\python.exe -m pytest tests/test_samples.py -q --basetemp=.pytest_cache/t05-samples
```

`src/beijing_air/samples.py` giữ origin/target timestamps, ID ổn định, lý do
loại mẫu và split theo target timestamp. Đầu ra tại `data/processed/samples_<mode>/`
gồm train/validation/test, IDs và exclusions; audit nhỏ tại `reports/splits_<mode>/`.
Sample CSV chứa cohort operational; lọc `is_primary` cho cohort so sánh chính.
Full có 412.017 operational/409.180 primary, loại 8.751 vì target thiếu/cuối
chuỗi. [Báo cáo](reports/sample_split.md) có bảng số mẫu/khoảng ngày theo split;
[hướng dẫn](docs/temporal_samples.md) giải thích ranh giới, nhãn fit và tái lập.

Chạy lại cùng input/config/code chỉ xác minh checksum và giữ nguyên output;
khác signature hoặc checksum thì dừng, không tự ghi đè. Giữ dataset/IDs cùng
manifest khi bàn giao hoặc tái tạo từ T04. Test chỉ được audit count/date trong
T05, chưa EDA/fit/tính metric; audit này không ghi thành model Experiment Log.
Trên clone mới hoặc cần snapshot khác, dùng `--output-tag reproduce` để tạo
`samples_full_reproduce`/`splits_full_reproduce`, giữ nguyên báo cáo đã commit.

## T06: EDA chỉ trên train

[Notebook đã chạy](notebooks/01_train_eda.ipynb) gọi `beijing_air.eda` để mô tả
205.977 mẫu operational train (204.865 primary), 12 trạm. Có 14 bảng thống kê,
9 PNG gốc có nhãn/đơn vị và nhận xét về missing, phân phối/ngoại lệ, quan hệ
đa biến, trạm, giờ/tháng/mùa, timeline và tự tương quan đúng timestamp.
[Kết luận và quyết định T07/T08](docs/eda_findings.md),
[chỉ mục hình](reports/eda_train/figure_index.md),
[manifest/checksum](reports/eda_train/eda_manifest.json).

```powershell
.\.venv\python.exe scripts/verify_eda.py
.\.venv\python.exe scripts/run_eda_notebook.py --mode smoke --output-tag local_check
.\.venv\python.exe scripts/run_eda_notebook.py --mode full --output-tag reproduce
.\.venv\python.exe -m pytest tests/test_eda.py -q --basetemp=.pytest_cache/t06-eda
```

Notebook chạy từ kernel mới bằng đúng interpreter hiện có; không phụ thuộc
outputs của phiên cũ. Đầu ra có sẵn không ghi đè, lần chạy lại dùng tag mới.
Smoke/reproduce và cache kernel giữ local. Trên clone mới, tái tạo train T05
rồi truyền split manifest tương ứng; xem hướng dẫn trong `docs/eda_findings.md`.
Không mở CSV validation/test cho EDA, không impute, tạo feature hoặc fit model.
Các đợt ô nhiễm cao được giữ; audit này không thêm run/metric vào Experiment Log.

## T07: feature A/B có tính nhân quả

`beijing_air.features` tạo A (20 cột) và B (33 cột) từ quan sát thực tế,
giữ ID/order T05, để missing nguyên trạng. Lịch là giờ dự báo t+1 biết tại t;
B thêm lag đúng t−1/3/6/12/24h cùng trạm và rolling mean/std 3/6/12/24h
kết thúc tại t, `min_periods=window`, `ddof=1`. T07 cập nhật có chủ đích
thiết kế cũ: bỏ lag 2h, chuyển lịch origin sang lịch forecast, thêm sin/cos
giờ/tháng dựa trên chu kỳ EDA train; chưa chứng minh cải thiện dự báo.

```powershell
.\.venv\python.exe scripts/build_features.py --mode smoke
.\.venv\python.exe scripts/build_features.py --mode full
.\.venv\python.exe scripts/verify_features.py
.\.venv\python.exe -m pytest tests/test_features.py -q --basetemp=.pytest_cache/t07-features
```

Ma trận train và metadata nằm trong `data/processed/features_full/` (ignore);
registry, bảng missing và manifest nhỏ ở `reports/features_full/`.
Chạy lại cùng input/config/code kiểm checksum và giữ output; thay đổi phải
dùng `--output-tag reproduce`. Chỉ parse prefix raw đến origin train cuối
bằng loader T04 để không mất lịch sử những origin bị T05 loại do thiếu nhãn;
không ghi lại raw/dữ liệu hợp nhất/audit T04 và không mở CSV validation/test.

[Dictionary/API một lần dự báo](docs/feature_dictionary.md) giải thích
schema, missing history, quy ước ranh giới và lệnh tái lập. API một lần dự
báo chỉ cần buffer quan sát cùng trạm đến t, không cần target tại t+1.
Chưa fit preprocessing/model hoặc chọn C. T06 giữ nguyên artifact lịch sử;
verifier EDA kiểm config cũ từ Git khi chỉ phần features được cập nhật.

## T08: preprocessing cho Ridge và Random Forest

`beijing_air.preprocessing` có `make_preprocessor` và
`make_regression_pipeline`, trả pipeline **chưa fit** từ registry A/B T07.
Numeric dùng median train, giữ cột toàn NA và có missing indicator cho mọi
cột; categorical dùng token thiếu, one-hot station/wd và unknown=ignore.
Ridge scale numeric đã impute; RF không scale. Output có feature names và
giữ sample index; pipeline clone/joblib được cho CV/inference.

[Quyết định, API và giới hạn](docs/preprocessing.md),
[config preprocessing/prediction policy](configs/preprocessing.json).
Config A/B/model vẫn ở `configs/default.json`; không đổi artifact T05–T07.
Policy chung: giữ dự báo âm, không clipping riêng model. Numeric missing
flags/OHE giữ binary 0/1; missing categorical chưa từng gặp ở train có thể
thành vector toàn 0 giống category mới, được mô tả và kiểm tra trong tài liệu.

```powershell
.\.venv\python.exe -m pytest tests/test_preprocessing.py -q --basetemp=.pytest_cache/t08-preprocessing
.\.venv\python.exe -m pip check
```

T08 chỉ fit fixture TEST_ONLY nhỏ để kiểm tra, không fit trên dữ liệu dự án,
không mở validation/test, train full hoặc ghi run/metric vào Experiment Log.
Task training sau phải fit/clone toàn pipeline trong train từng run/fold;
inference chỉ load/predict với cùng schema/config.

## T09: persistence baseline thực tế trên validation

Đã chạy smoke, sau đó **một full baseline** với logger và validation IDs T05.
Primary N=102.479: **MAE=9,736617 µg/m³, RMSE=19,240919 µg/m³,
R²=0,944804**. Operational N=103.287: MAE=9,903556, RMSE=20,060564,
R²=0,939982; fallback 808 (0,782286%), coverage 100%. Smoke không dùng làm
số liệu chính thức.

Full run `24cef47874a94d9faa7bfcbae29b5c58`; smoke tham chiếu
`5a6c965f64754a2ea9508e554fd92092`. Fallback chốt trước metric: số đo gần
nhất cùng trạm tuổi ≤24h, sau đó median trạm/global từ train. Không tương
lai/clipping/impute target. Seed thực=null vì không dùng RNG; config giữ 42.

[Kết quả, nhận xét, T10 và restore](docs/baseline_results.md),
[validation anchor](reports/evaluation/validation_manifest.json),
[bundle run đầy đủ](reports/baseline/t09_runs.zip),
[checksum](reports/baseline/t09_runs.json). Raw/dataset giữ nguyên; chưa chạy
Ridge/RF, tuning hoặc test. Sau clone restore run trees rồi kiểm lại:

```powershell
.\.venv\python.exe scripts/verify_baseline.py --run-id 5a6c965f64754a2ea9508e554fd92092 24cef47874a94d9faa7bfcbae29b5c58
.\.venv\python.exe -m pytest tests/test_baseline.py -q --basetemp=.pytest_cache/t09-baseline
```

Verifier không tạo run mới; không chạy full lại vì budget T09 đã dùng.
T10 so model trên cùng primary IDs/policy, không buộc thắng persistence.

## T10: Ridge và Random Forest ban đầu, bộ A

Thiết kế cố định ở [initial_models.json](configs/initial_models.json), factory
pipeline T08, primary train/validation T05. Chạy riêng từng model để giải phóng
RAM giữa các tiến trình. Lệnh dưới mô tả lượt chạy; runner tái sử dụng run
completed cùng signature/artifact thay vì fit lại, từ chối full thứ hai khi
đổi cấu hình. Không xóa log để vượt ngân sách.

```powershell
.\.venv\python.exe scripts/run_initial_models.py --mode smoke --model ridge
.\.venv\python.exe scripts/run_initial_models.py --mode smoke --model random_forest
.\.venv\python.exe scripts/run_initial_models.py --mode full --model ridge
.\.venv\python.exe scripts/run_initial_models.py --mode full --model random_forest
.\.venv\python.exe scripts/report_initial_models.py --write-comparison
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t10-check
```

[Kết quả, run IDs, nhận xét và giới hạn](docs/initial_findings.md),
[bảng so sánh từ artifact](reports/initial_models/comparison.csv),
[hình gốc](reports/figures/initial_models/comparison.png).
Hồ sơ T10 thật được lưu trực tiếp dưới `artifacts/experiments/<run_id>/` gồm
config/metadata/metrics, source snapshots và predictions CSV.GZ có checksum;
không tạo thêm ZIP. Không lưu trọng số ở vòng đầu: fitted pipeline summary
không dùng để inference. Phạm vi T10 chưa tuning/test; kết quả T11 ở phần sau.

## T11: tuning Ridge A bằng temporal CV trong train

[Config](configs/tuning.json) cố định bốn alpha `{0.1,1,10,100}` và ba cửa sổ
CV T02. Mỗi fold fit lại toàn Pipeline T08, purge nhãn fit để target có trước
origin eval đầu. Chọn pooled CV MAE trong train, khóa selection trước khi đọc
validation, rồi một selected refit trên toàn primary train; không test/RF tuning/T12.

Đã chạy smoke rồi full với 12 fit CV +1 refit. Alpha0.1 được chọn nhưng validation
MAE 10,200529 hơi kém Ridge T10 10,200433: chưa cải thiện validation. Chi tiết
run IDs, mean/std, chi phí và giới hạn ở [tuning_findings](docs/tuning_findings.md),
[bảng candidates](reports/tuning/candidates.csv), [trước-sau](reports/tuning/before_after.csv)
và [hình](reports/figures/tuning/comparison.png).

```powershell
.\.venv\python.exe scripts/run_tuning.py --mode smoke
.\.venv\python.exe scripts/run_tuning.py --mode full
.\.venv\python.exe scripts/report_tuning.py --write-report
.\.venv\python.exe -m pytest tests/test_tuning.py -q --basetemp=.pytest_cache/t11-check
```

Runner tái sử dụng completed cùng signature/artifact; full khác cấu hình hoặc
sau full lỗi bị chặn, không xóa lịch sử để chạy vượt budget. Hồ sơ search,
candidate/fold/refit được track trực tiếp, không ZIP mới. Khi clone, restore
riêng hai tree T09 như hướng dẫn T10 và giữ index hiện tại. Chưa lưu model để
inference hoặc kiểm máy sạch; smoke/fixture không phải kết quả chính.

## T12: A/B/C, grouped feature selection và frozen config

Đã so sánh Ridge alpha0.1 cố định trên cùng primary IDs: A reuse T11,
B33 feature, C chọn 12 nhóm qua train-only CV từ ba k={12,20,28}.
Validation MAE A/B/C: 10,200529 / 9,968755 / 9,903377; chiều model65/91/24.
RF A T10 vẫn tốt nhất MAE9,561488 trong pool đã chốt nên được khóa cho
lần refit tương lai, không fit lại RF hoặc mở test/T13.

Xem [RQ2, run IDs, feature giữ/bỏ và giới hạn](docs/ablation_findings.md),
[bảng so sánh](reports/ablation/comparison.csv),
[frozen config](reports/ablation/frozen_model.json).
C dùng wrapper Pipeline T08 với grouped pilot Ridge selector; một nhóm giữ
mọi numeric/indicator hoặc dummy OHE cùng nguồn. Factory/helper ở
[src/beijing_air/feature_selection.py](src/beijing_air/feature_selection.py).

```powershell
.\.venv\python.exe scripts/run_ablation.py --mode smoke
.\.venv\python.exe scripts/run_ablation.py --mode full
.\.venv\python.exe scripts/report_ablation.py --write-report
.\.venv\python.exe -m pytest tests/test_ablation.py -q --basetemp=.pytest_cache/t12-check
```

Ngân sách full đã dùng9 pipeline CV (9pilot+9final Ridge) và2 final B/C
(3 estimator fits), tổng21 estimator fits; A/RF/persistence reuse artifact.
Runner không fit lại completed cùng signature, chặn full khác config hoặc
sau lỗi; không xóa lịch sử vượt budget. Hồ sơ T12 track trực tiếp, không ZIP mới.
Frozen config khóa data/split provenance/features/preprocessing/model/params/
postprocessing/criteria, **chưa có weights triển khai**; T13 chỉ khi được giao.

## MK01: tài liệu giữa kỳ bản nháp

Đã tạo [DOCX17trang](reports/midterm/NhomXX_DuBaoPM25_BacKinh_GiuaKy.docx) và
[PPTX15slide](reports/midterm/NhomXX_DuBaoPM25_BacKinh_GiuaKy.pptx), có
[PDF preview](reports/midterm/previews/report.pdf), [slide PDF](reports/midterm/previews/slides.pdf)
và [hướng dẫn/kiểm tra](docs/midterm_deliverables.md). Cùng snapshot49run thật,
không huấn luyện hoặc mở test. Nhóm tự bổ sung thông tin trong configs/midterm.json;
NhomXX/[CẦN BỔ SUNG] nghĩa là **bản nháp, chưa sẵn sàng nộp**.

Cài optional dependencies với pip install -e ".[midterm]", chạy scripts/build_midterm.py,
render bằng scripts/render_midterm.ps1 (LibreOffice +PowerPoint), kiểm scripts/verify_midterm.py.
MK01 đã merge PR #28. MK02 đóng gói riêng và người dùng merge PR MK02; không nộp Classroom.

## MK02: gói giữa kỳ đã kiểm, còn thông tin nhóm

[Checklist và cách chạy từ ZIP](docs/submission_checklist.md),
[QA thực tế](reports/submission/qa.json), [manifest/SHA từng file](reports/submission/submission_manifest.json)
và [kiểm ZIP](reports/submission/verification.json).
ZIP cục bộ: reports/submission/NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip; vì chứa predictions
thật nên lớn, không commit binary ZIP vào Git. Không có link upload công khai;
người dùng lấy file trên máy làm việc và tự nộp sau review.

Từ root đồ án đã có artifact đầy đủ, chạy .venv/python.exe scripts/package_midterm.py,
rồi scripts/verify_submission.py với ZIP, --extract-to thư mục mới và --output file QA riêng.
Gói có 49 hồ sơ thật/200 artifact, 43 predictions tính lại; Excel liên kết JSON và CSV
chuẩn giữ nguyên. Python cách ly cài/import/pip check/Office pass; EDA train chạy13cell,
14bảng/9PNG kiểm lại, 14bảng khớp lịch sử. Minh chứng EDA mới mang tag mk02_clean_20261103_01,
không thêm dòng model log. Chưa kiểm venv chuẩn/OS mới hoặc tái huấn luyện full;
chưa có serialized model weights. **BẢN NHÁP: nhóm/rubric còn [CẦN BỔ SUNG]**.

## Quy định cuối kỳ từ T13

Đọc [checklist cuối kỳ](docs/final_stage_requirements.md),
[bài giảng/rubric](docs/course_alignment.md),
[bảng nhóm chờ xác nhận](docs/team_contributions.md) và
[AI disclosure](docs/ai_disclosure.md).
Mỗi PR từ T13 có mục bài giảng/rubric/AI; Issue gán thành viên thật, kiểm danh
tính Git trước commit. Bổ sung % MAE giảm persistence, fold/std và phân tích lỗi
đợt ô nhiễm cao. Cuối kỳ có 5chương/slide/poster/video/model/source/README,
ZIP tên nhóm trưởng và yêu cầu in/chia sẻ repo. Các mục thiếu giữ [CẦN BỔ SUNG].
Lần cập nhật này chỉ tài liệu, chưa thực hiện T13 hoặc thay đổi gói giữa kỳ.

## T13: test đã đánh giá theo recipe khóa

[Thảo luận RQ1–RQ3](docs/results_discussion.md),
[protocol/lệnh/bàn giao](docs/final_evaluation.md),
[bảng test](reports/final_evaluation/comparison.csv) và
[model RF final](reports/final_evaluation/final_model.json).
Hai pipeline refit307344primary train+validation;3model cùng101836test IDs.

| Model A/primary | Test MAE (µg/m³) | Test RMSE (µg/m³) | Test R² | % MAE giảm persistence |
| --- | --- | --- | --- | --- |
| Persistence | 10,161809 | 19,436188 | 0,944975 | 0% |
| Ridge alpha0.1 | 10,384443 | 18,939487 | 0,947752 | −2,1909% |
| RF80cây/depth12 | 9,877150 | 18,569634 | 0,949772 | 2,8013% |

RF vẫn là phương án chọn bằng validation, không chọn lại theo test. Identity
chung, không clipping; Ridge có2067dự báo âm được giữ/báo rõ. Train/CV/validation
lịch sử khác final refit, không gọi validation đã refit là held-out. RF chưa
có CV, không tạo fold/std giả. Ngưỡng/mùa/episode/permutation đã chốt trước test.

Verifier pass41artifact/6predictions/2weights/2946metric nhóm;49row và196file
run cũ giữ nguyên. Bundle cục bộ reports/final_evaluation/t13_runs.zip kèm
weights và hai dependency T09, có checksum/restore helper; binary ignored,
chưa upload công khai. Cần chuyển bundle cùng source khi sang máy khác.
Báo cáo/ZIP giữa kỳ giữ nguyên; không chạy lại MK01/MK02 để thêm số liệu test.
T13 đã được người dùng xác nhận merge PR #33; T14 bàn giao riêng bên dưới.

## T14: demo Streamlit cục bộ

[Hướng dẫn chạy/khôi phục model](docs/demo.md), [storyboard video chưa quay](docs/demo_video_storyboard.md)
và [ảnh app thật](reports/demo/screenshots/02_forecast.png). Tại root đồ án:

```powershell
.\.venv\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1
```

Dùng RF A chọn bằng validation, pipeline final T13; cần bundle T13 trên máy,
chưa có URL tải công khai. Resource SQLite nhỏ đã kèm source. Chọn trạm/giờ,
dự báo đúng t+1 rồi mới đọc số đo đối chiếu; không fit khi UI rerun.
Ví dụ lịch sử sau fit: một tuần test đã đánh giá T13, không chọn model hoặc
tạo metric tổng hợp mới. 19 tests và 36 kiểm tra khớp predictions T13 pass;
[QA](reports/demo/qa.json), [browser/5 ảnh](reports/demo/browser_verification.json).
Issue #34 giao hoanglecodingmachine; chưa merge/deploy, video thật còn thiếu.
T15/T16 chưa triển khai. Lỗi T08 được báo riêng ở Issue #35, không sửa lịch sử cũ.

## T17a: bảng tổng hợp thí nghiệm chỉ đọc

[Cách đọc/nguồn/giới hạn](docs/experiment_summary_readme.md),
[bảng tổng hợp](reports/tables/experiment_summary.md),
[CSV](reports/tables/experiment_summary.csv), [PNG](reports/tables/experiment_summary.png)
và [Excel](reports/tables/experiment_summary.xlsx).

```powershell
.\.venv\python.exe scripts/build_experiment_summary.py
```

Gộp53hồ sơ thành10cấu hình đã chạy và2dòng nhóm chưa chạy. CV pooled từ
saved OOF (fallback có trọng số n_i), validation/CV/test có run nguồn riêng;
highlight theo validation chỉ mô tả, marker khóa T12/T13 không đổi. Đọc saved
test artifact T13, không mở raw test samples, không training/tuning hoặc thêm
run. Có checks OK/KHÁC, provenance/SHA và audit đủ mọi run trong reports/tables/.
Issue #40 giao hoanglecodingmachine; người dùng review/merge, không tự làm T17b.

## NB01: hành trình T01–T14 có minh chứng

[Notebook có output](notebooks/PM25_Project_Journey_T01_T14.ipynb),
[HTML đọc ngay](reports/notebook/PM25_Project_Journey_T01_T14.html),
[bản đồ code/dòng/test](docs/notebook_code_map.md) và
[hướng dẫn kiểm/chạy lại](docs/project_journey.md).
Mỗi task giải thích code nào triển khai, file kết quả ở đâu và ý nghĩa;
đọc artifact cũ, không huấn luyện hoặc mở test samples.

```powershell
.\.venv\python.exe scripts/build_project_journey.py --execute
```

Kernel mới có guard chỉ đọc; xuất notebook/HTML/code map/QA NB01, không sửa
ledger hay run lịch sử. T13/T14 test chỉ đọc lại artifact đã lưu. Issue #42
giao hoanglecodingmachine, PR chờ người dùng review/merge. Tại snapshot NB01,
PR T14 #36, bug-fix #37 và T17a #41 đã merge; các dòng “chưa merge” ở mốc
trước là ghi nhận lịch sử, không hồi tố chỉnh sửa báo cáo/run cũ.

## T17b: thí nghiệm bổ sung và gộp mô hình

[Thiết kế T17b](docs/t17b_design.md) và [kết quả/giới hạn](docs/supplementary_experiments.md)
ghi lại các thí nghiệm RF bộ B, tuning RF, HistGradientBoosting, Lasso/ElasticNet,
Decision Tree, baseline, Fusion-3 và Stack. Chạy thí nghiệm bằng:

```powershell
.\.venv\python.exe scripts/run_supplementary_experiments.py
```

Bảng tổng hợp tái tạo từ ledger và run artifacts bằng
`.\.venv\python.exe scripts/build_experiment_summary.py` được lưu tại
[experiment_summary.md](reports/tables/experiment_summary.md): 27 dòng mô hình/ứng viên/gộp,
264 hồ sơ và 412 kiểm tra nhất quán đều OK. Validation MAE nổi bật là RF B
9.3798, Fusion-3 9.2746 và Stack 9.2321 µg/m³. Đây là kết quả phát triển bổ sung;
không thay mô hình RF A đã khóa ở T12/T13 và không sử dụng hay chạm tập test.
