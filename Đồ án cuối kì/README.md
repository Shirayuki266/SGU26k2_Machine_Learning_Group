# Beijing Air Quality

Dự án học máy dự báo nồng độ PM2.5 tại giờ t+1 của cùng trạm quan trắc ở Bắc Kinh. Dự báo được thực hiện sau khi có số đo giờ t và chỉ sử dụng thông tin có sẵn đến giờ t. Task 01 chỉ khởi tạo cấu trúc, môi trường và cấu hình; chưa tải dữ liệu, chưa huấn luyện mô hình.

Nguồn dữ liệu dự kiến do nhóm lựa chọn: [Beijing Multi-Site Air Quality, UCI dataset 501](https://archive.ics.uci.edu/dataset/501/beijing+multi-site+air+quality+data).

Các task sau sẽ triển khai baseline persistence, Ridge và Random Forest; đánh giá bằng MAE (chính), RMSE và R². Train/validation/test được chia theo thời gian; tiền xử lý fit trên train, không dùng test để tuning hay chọn đặc trưng. Target, lag và rolling phải đúng trạm, đúng thời gian và không dùng tương lai.

## Cấu trúc

```text
src/beijing_air/   Package Python chính
scripts/           Script kiểm tra và chạy các bước xử lý
notebooks/         Notebook khám phá dữ liệu
configs/           Cấu hình dự án
tests/             Kiểm thử
data/raw/          Dữ liệu gốc (không commit)
data/processed/    Dữ liệu đã xử lý (không commit)
artifacts/         Model và kết quả sinh ra (không commit)
experiments/       CSV tổng hợp thực nghiệm (hồ sơ run trong artifacts/experiments/)
reports/figures/   Biểu đồ cho báo cáo
docs/              Tài liệu dự án
app/               Ứng dụng Streamlit
```

Dependencies được khai báo duy nhất trong `pyproject.toml`: pandas, numpy, scikit-learn, matplotlib, seaborn, joblib, streamlit, pytest và Jupyter. Package dùng cấu trúc `src`; cài editable để import `beijing_air` từ môi trường dự án.

## Tạo môi trường trên Windows PowerShell

Cài Python 3.10 trở lên và Python Launcher (`py`), sau đó mở PowerShell tại thư mục chứa README này:

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

Nếu mạng bị chặn, mở [trang UCI 501](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data), chọn **Download**, lưu ZIP vào `data/raw/uci_501_download.zip`. Hoặc đặt ZIP PRSA2017 lấy từ gói tải chính thức vào `data/raw/PRSA2017_Data_20130301-20170228.zip`. Không cần tự giải nén. Chạy một trong hai lệnh tương ứng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/uci_501_download.zip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/PRSA2017_Data_20130301-20170228.zip
```

Với ZIP thủ công, thêm `-DownloadedAt "2026-10-12T10:00:00+07:00"` **chỉ khi đó là thời điểm tải thực tế của bạn**; ví dụ này không phải ngày tải mặc định. Nếu không biết, manifest ghi `null`, không suy ra từ ngày sửa file. Nếu lần tải lỗi để lại `.part`, kiểm tra và xóa riêng file tải dở đó trước khi thử lại; không xóa dữ liệu đã giải nén.

`reports/data_manifest.json` lưu nguồn, license, ngày tải UTC, thời điểm ghi manifest và SHA-256 của ZIP/CSV. Checksum là dấu vết của file tải thực tế, không phải checksum do UCI công bố. `configs/uci_501.json` ghi metadata tham chiếu chính thức. `docs/data_dictionary.md` ghi ý nghĩa và đơn vị các trường.

Audit đọc raw mà không sửa, impute hay huấn luyện; kiểm tra schema, tên trạm, kiểu giá trị, missing từng cột, số dòng, thời gian, timestamp trùng và khoảng trống giờ. Kết quả ghi `reports/raw_audit_smoke.json` hoặc `reports/raw_audit_full.json`; chỉ full được dùng cho báo cáo dữ liệu chính thức. Số dòng được đếm từ CSV rồi đối chiếu metadata, không gán bằng số công bố. Nếu lệch hoặc lỗi dữ liệu, script ghi báo cáo và trả lỗi.

Lần audit full Task 03 đã đếm 420.768 dòng từ 12 file/trạm, khớp số công bố. Báo cáo thực tế và giới hạn kiểm tra: [reports/data_audit.md](reports/data_audit.md). Raw vẫn giữ nguyên; chưa impute hoặc huấn luyện.

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
file an toàn. CSV hiện chỉ có header; task này chưa chạy mô hình hoặc thêm metric.

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
