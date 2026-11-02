# Experiment Log — T04-BỔ SUNG

Logger nằm trong `beijing_air.experiment_logging`, chỉ dùng thư viện chuẩn Python
3.10+. Module không đọc dataset, tạo split, tính metric hay huấn luyện mô hình.
Script baseline/training sau này gọi logger quanh phần thực thi của mình.

## Vị trí và quy ước

Chạy từ thư mục `Đồ án cuối kì`, sau khi cài editable như README. Mặc định đường
dẫn được xác định theo package trong repo, không phụ thuộc working directory:

```text
experiments/experiment_log.csv             CSV tổng hợp, một dòng/run
experiments/.experiment_log.lock           Khóa hệ điều hành, bỏ qua trong Git
artifacts/experiments/<run_id>/
    config.json                           Cấu hình bất biến từng run
    metrics.json                          Metric thực do script cung cấp
    metadata.json                         Trạng thái, môi trường, Git, lỗi, artifact
    notes.md                              Nhận xét gần nhất
    artifacts/predictions/...              File do log_artifact sao chép
    artifacts/figures/...
    artifacts/model/...
```

Tái sử dụng `artifacts/` hiện có trong `configs/default.json`, không thay đổi đầu
ra/audit T03–T04. CSV được theo dõi trong Git; toàn bộ hồ sơ run nằm trong
`artifacts/` đang được ignore. Khi bàn giao, **phải đóng gói cả CSV và cây
`artifacts/experiments/`**, hoặc lưu chúng cùng nhau ở kho artifact. Chỉ CSV trong
Git sẽ không chứa các file được liên kết. Không import báo cáo audit thành run mô hình.

Tại T04-LOG, CSV chính thức chỉ có header. Đến T09 đã có hai run persistence
smoke/full thật; [kết quả và bundle](baseline_results.md) có predictions,
config/metrics/metadata/notes và restore sau clone. Smoke không là số liệu
chính thức.
Fixture kiểm thử nằm hoàn toàn trong thư mục tạm, ghi `is_test=True` và
`task_id=TEST_ONLY_...`; không đưa các run đó vào CSV chính thức.

## API và schema

```python
from beijing_air.experiment_logging import ExperimentLogger

logger = ExperimentLogger()  # Hoặc project_root=Path(...) khi cần chỉ rõ project.
run = logger.start_run(task_id="mã task được giao", objective="câu hỏi thực nghiệm")
# Chạy công việc thực tế ở script gọi; logger không tự chạy.
run.log_metrics(metrics_thuc_te, split="validation")
run.log_artifact(duong_dan_file_da_tao, name="predictions/validation.csv")
run.finish_run(notes="Nhận xét dựa trên output thật", decision="Quyết định tiếp theo")
```

Đây là mẫu tích hợp, các biến metric/file phải do script thực tế cung cấp.
Có thể gọi trực tiếp `logger.log_metrics(run.run_id, ...)`,
`logger.log_artifact(run.run_id, ...)`, `logger.finish_run(run.run_id, ...)`.
Không dùng ví dụ gọi trực tiếp này nếu chưa có xử lý exception; ưu tiên context
manager bên dưới để tự ghi lỗi và kết thúc.

`start_run` cấp `run_id` UUID4 mới, không cho người gọi tái sử dụng ID. Những
trường chưa cung cấp được ghi JSON `null`, CSV là ô rỗng; `metrics.json` ban đầu
là `{}`. Không có seed, model, mode, metric hoặc người đóng góp tự suy diễn.
Mọi cấu hình phải là giá trị JSON chuẩn; chuyển scalar NumPy sang `float/int`
và `Path` sang `str` trước khi truyền. NaN/Inf bị từ chối; dùng `None` cho metric
không xác định và ghi lý do trong notes.

| Nhóm | Trường trong config.json |
| --- | --- |
| Truy vết | `task_id`, `reference_run_id`, `parent_run_id`, `fold_id`, `source` |
| Thiết kế | `objective`, `hypothesis`, `change`, `mode`, `kind`, `budget`, `is_test` |
| Mô hình | `model`, `parameters`, `feature_set`, `preprocessing`, `seed` |
| Dữ liệu | `data`, `split`, `time_ranges`, `sample_counts` |

`mode`: `smoke`, `full` hoặc `None`. `kind`: `baseline`, `train`, `tuning`,
`ablation`, `feature_selection` hoặc `None`. Các trường data/split/preprocessing
nhận dict/list JSON; lưu **cấu hình thực dùng**, không chỉ đường dẫn đến cấu hình
có thể thay đổi. `data` nên có đường dẫn manifest và checksum thật đã xác minh,
checksum dữ liệu xử lý và quy tắc chọn mẫu. `split` lưu basis `target_timestamp`,
các mốc, fold; `time_ranges` và `sample_counts` lưu phạm vi/số mẫu thực đọc.
Logger không tự mở manifest hoặc dữ liệu để điền các trường này.

`metadata.json` tự lưu Git commit/branch/trạng thái dirty của toàn repo lúc bắt
đầu, Python/OS và phiên bản các package cài trong interpreter thực chạy. Git
không dùng được thì `available=False`, các giá trị còn lại `null`. Không tự lưu
biến môi trường, token, remote URL, tên người chạy hoặc tác giả học thuật. Người
gọi phải loại secrets khỏi config, notes, file và thông báo exception trước khi
ghi. Traceback lưu stack/thông báo lỗi, không dump locals.

Thời gian dùng ISO 8601 UTC (`+00:00`), kèm `timezone=UTC`; không đổi timezone
của dữ liệu/split. `duration_seconds` đo khoảng bắt đầu–kết thúc, gồm I/O logger;
muốn đo fit/predict riêng, script cần đo và ghi metric thời gian riêng.
Git dirty không lưu bản sao diff; muốn tái lập chính xác cần giữ cả mã chưa commit.

`log_metrics` cập nhật các key, giữ key khác. Với `split="validation"` metric
được nhóm dưới `validation`; có thể dùng `train` hoặc tên fold. Không truyền
split thì merge ở cấp gốc; dict lồng được thay theo key, không deep merge.
Metric test chỉ được cung cấp sau khi được giao đánh giá test và đã khóa mô hình.
`log_artifact` nhận **một file**, sao chép vào run, lưu đường dẫn, SHA-256 và kích
thước. Cùng tên ở run khác độc lập; cùng tên trong một run bị từ chối, không ghi
đè. Dùng tên mới nếu cần snapshot khác. Logger không tự serialize mô hình và
không sao chép cả thư mục; script dùng joblib/CSV/PNG rồi gọi từng file.

CSV có config, metric, metadata và các đường dẫn `config_path`, `metrics_path`,
`metadata_path`, `notes_path`. Mọi đường dẫn trong CSV/registry artifact được tính
**từ thư mục chứa CSV**; dict/list/bool được mã hóa JSON, tiếng Việt UTF-8.
Đọc bằng `csv.DictReader(..., encoding="utf-8")`, hoặc
`pandas.read_csv(..., encoding="utf-8", keep_default_na=False)` rồi `json.loads`
các cột JSON. CSV ô rỗng biểu diễn missing; JSON là nguồn để phân biệt chính xác
`null` với chuỗi rỗng. Với Excel chọn nhập UTF-8, không tách dòng thủ công vì
notes/JSON có thể chứa dấu phẩy hoặc xuống dòng.

## Ví dụ tích hợp baseline/training sau này

Mẫu hàm dưới đây **chưa được chạy** và không triển khai baseline/T05. Truyền
config và callable từ script sau này; callable chịu trách nhiệm trả kết quả thật.

```python
from beijing_air.experiment_logging import ExperimentLogger

def execute_logged(config, execute):
    logger = ExperimentLogger()
    with logger.start_run(**config) as run:
        # execute là hàm baseline/training sẽ được triển khai ở task được giao.
        # Trả về metrics theo split, danh sách (tên lưu, file thật), nhận xét.
        metrics_by_split, files, notes, decision = execute()
        for split_name, metrics in metrics_by_split.items():
            run.log_metrics(metrics, split=split_name)
        for artifact_name, file_path in files:
            run.log_artifact(file_path, name=artifact_name)
        run.finish_run(notes=notes, decision=decision)
    return run.run_id
```

Config phải ghi task thực, mục tiêu/giả thuyết, run tham chiếu, model/tham số,
feature set, preprocessing, data/split, seed và ngân sách trước khi chạy. Lưu
tham số của persistence bằng `None` nếu không có; không giả định baseline là
một mô hình đã fit. Giữ cùng sample IDs khi so sánh baseline và model; logger
chỉ lưu thông tin, không thay thế kiểm tra chống leakage.

Context tự chuyển `running → completed` nếu khối lệnh kết thúc bình thường,
`running → failed` khi exception, `running → interrupted` với
`KeyboardInterrupt`/`SystemExit`. Exception được truyền lại caller; metadata
giữ loại lỗi, thông báo, traceback và các file/metric đã ghi. Gọi
`finish_run` lặp với cùng trạng thái chỉ cập nhật nhận xét/lỗi, giữ thời điểm
kết thúc và một dòng CSV; không đổi trạng thái cuối sang trạng thái khác.
Chỉ ghi metrics/artifact khi run còn `running`.

Với tuning, dùng một run cha `kind="tuning"`, mỗi cấu hình/fold mở run con
`parent_run_id=parent.run_id`, `fold_id=...`, ghi parameters/split/metrics riêng.
`reference_run_id` chỉ run dùng để so sánh, có thể khác run cha. Đây là hướng
dẫn tích hợp; task này không thực thi tuning hay feature selection.

## Ghi đồng thời, phục hồi và giới hạn

Tất cả writer dùng chung **một cặp** `experiment_dir`/`artifact_dir`. Khóa hệ
điều hành (`msvcrt` trên Windows, `flock` trên POSIX) bao quanh cập nhật run và
toàn bộ CSV. Mặc định chờ tối đa 10 giây, có thể đổi `lock_timeout`. File được
ghi tạm cùng thư mục, flush/fsync và `os.replace`; CSV được dựng lại theo run ID
từ hồ sơ từng run, không append mù nên cập nhật lại không sinh dòng trùng.
Không sửa/xóa file lock khi đang có writer; khóa tự giải phóng khi process chết.
Không dùng hai CSV với cùng artifact_dir hoặc nhiều artifact_dir cho cùng CSV.

Không có transaction nguyên khối cho nhiều file: nếu crash sau khi lưu JSON
nhưng trước khi thay CSV, CSV có thể cũ, JSON vẫn là nguồn chính. Khôi phục bằng:

```python
logger.rebuild_index()
# Khi đã xác nhận một run running thực sự đã dừng:
logger.finish_run(run_id, status="interrupted", notes="Lý do dừng đã xác minh")
```

Không tự đánh dấu run lâu là thất bại. Kill cưỡng bức/mất điện không đảm bảo ghi
được exception; crash lúc khởi tạo có thể để thư mục chưa đủ metadata, không
được tính là run hoàn chỉnh trong CSV. Đóng Excel nếu nó chặn thay CSV rồi
`rebuild_index()`; lỗi I/O được báo về caller. Nếu logger gặp lỗi trong lúc xử lý
exception gốc, giữ exception gốc (Python 3.11+ có thêm note về lỗi logger);
run có thể còn `running` và cần rà soát. File artifact sao chép xong nhưng chưa
ghi registry khi crash có thể cần đối chiếu thủ công. Cơ chế này dành cho ổ đĩa
cục bộ, chưa xác minh trên network filesystem hoặc nhiều máy. Nhánh POSIX chưa
được thực thi trong phiên Windows này. Không suy ra khả năng tái lập chỉ từ
việc có log: cần giữ mã, dữ liệu/checksum và môi trường phù hợp.

T09 bổ sung guard tại start_run: CSV có run nhưng thiếu config/metrics/
metadata/notes thì dừng trước khi tạo run mới hoặc dựng lại CSV. Clone chỉ
có tracked CSV cần restore bundle trước, không rebuild_index để bỏ các dòng
chưa có tree. Guard không đổi metric cũ hoặc schema logger.

## Kiểm tra task

```powershell
.\.venv\python.exe -m pytest tests/test_experiment_logging.py -q --basetemp=.pytest_cache/t04-logging
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t04-logging-regression
git diff --check
```

Interpreter trên là Python portable sẵn có của T04; venv chuẩn dùng
`.\.venv\Scripts\python.exe`. Các kiểm thử logger và unit T04 chỉ dùng fixture
tổng hợp. Loại riêng kiểm tra tích hợp đọc dữ liệu full đã lưu vì nó bao gồm cả
giai đoạn test; task này không mở lại dữ liệu đó và không chạy lại merge/audit.
Không chạy nguyên bộ pytest không có bộ lọc trong task này.

Kết quả kiểm tra ngày 02/11/2026 trên Python portable 3.12.10/Windows:
**20 kiểm thử logger pass**, **47 kiểm thử pass, 1 deselected** khi gộp unit T04.
Bao gồm thành công/thất bại/ngắt, metadata/error, null/tiếng Việt, cập nhật không
trùng, artifact/checksum/link, thread/process đồng thời, timeout khóa và phục hồi
CSV sau lỗi thay file. Kiểm tra tích hợp T04 trên dữ liệu thật không chạy.
Lần đầu có một assertion sai vì thư mục tạm nằm trong repo và Git vẫn tìm được
repo cha; assertion đã được sửa để chấp nhận trạng thái Git thực, kèm test riêng
cho trường hợp Git không khả dụng. Không có metric/run thử trong log chính thức.
