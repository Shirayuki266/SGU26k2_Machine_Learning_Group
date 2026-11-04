# T17a — Bảng tổng hợp thí nghiệm từ artifact thật

Issue [#40](https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group/issues/40),
branch `feat/t17a-experiment-summary-table`. Người dùng xác nhận giao
hoanglecodingmachine. Đây là tổng hợp chỉ đọc, không phải một lần thực nghiệm.

## Chạy script và file đầu ra

Từ root đồ án, dùng môi trường hiện có:

```powershell
.\.venv\python.exe scripts/build_experiment_summary.py
```

Venv chuẩn dùng `.\.venv\Scripts\python.exe`. Cần artifact T09–T13 đã lưu;
khôi phục bằng hướng dẫn/bundle có checksum của từng task nếu chuyển máy.
Không tự train để bù file thiếu. Có thể dùng `--output artifacts/T17a_TEST_preview`
để tạo bản xem thử, `--no-plans` để bỏ hai dòng kế hoạch. Đầu ra phải nằm trong project.

| File | Vai trò |
| --- | --- |
| [experiment_summary.csv](../reports/tables/experiment_summary.csv) | Bảng có header tiếng Việt, UTF-8 BOM để nhập Google Sheets/Excel; giữ đủ run IDs |
| [experiment_summary.md](../reports/tables/experiment_summary.md) | Bảng đọc trực tiếp, dòng tốt nhất in đậm; có toàn bộ kiểm tra OK/KHÁC |
| [experiment_summary.xlsx](../reports/tables/experiment_summary.xlsx) | Nếu openpyxl có: Summary tô màu, All runs, Checks; thiếu dependency này không cản xuất các định dạng khác |
| [experiment_summary.png](../reports/tables/experiment_summary.png) | Hai phần: bảng metric và bảng provenance/ghi chú; ID trên ảnh rút12ký tự, bản dữ liệu giữ đủ |
| [experiment_summary_checks.csv](../reports/tables/experiment_summary_checks.csv) | Metric tính lại từ saved predictions/OOF so log và14điểm lịch sử, dung sai1e-6 |
| [experiment_summary_runs.csv](../reports/tables/experiment_summary_runs.csv) | Audit đủ mọi hồ sơ, gồm smoke/search/candidate/fold/final/status/has_error |
| [experiment_summary_provenance.json](../reports/tables/experiment_summary_provenance.json) | SHA/size nguồn đã đọc, CV/fold IDs, nguồn validation/test, lock, checks, môi trường và SHA đầu ra |

PNG là ảnh lớn để đọc/phóng to hoặc lấy phần metric/provenance cho báo cáo,
không phải slide đã dàn trang. Approach trên ảnh viết gọn trees/depth/leaf/jobs;
CSV/MD/XLSX giữ tên tham số đầy đủ. CSV có ba cột nguồn lặp mỗi dòng để không
thêm footer phá schema; MD/PNG/XLSX ghi nguồn ở dưới bảng.

## Bảng hiện tại đại diện cho những gì?

Ledger hiện có53hồ sơ thật: T09=2,T10=4,T11=23,T12=20,T13=4. Không có run
failed trong snapshot này; code vẫn giữ cấu hình failed và trạng thái lỗi khi
log có. Không tạo thêm run để minh họa thất bại.

Bảng chính có10cấu hình đã chạy: persistence, Ridge A alpha1, RF A,
Ridge A alpha0.1/10/100, Ridge B, Ridge C k12/20/28. Hai dòng cuối chỉ là nhóm
T17b/gộp chưa chạy: không run ID, không số, không tô. Chúng không được tính
vào10cấu hình hoặc53hồ sơ thực nghiệm.

- Alpha1 có validation T10 và CV T11 của cùng cấu hình. Giữ run validation
  trong `run_id`, candidate CV ở `cv_run_id`; không giả rằng T10 đã chạy CV.
- Alpha0.1 có validation refit T11 và candidate CV riêng.
- C12 có validation T12 và candidate/fold riêng. C20/C28 chỉ có CV, không bịa
  validation. B không có CV B độc lập, nên để thiếu; không lấy CV selector C
  rồi điền cho B.
- Parent, fold và smoke vẫn nằm trong All runs/provenance, không lặp thành
  các dòng “model final”. Smoke không được dùng kết luận chính hoặc highlight.
- Tham số candidate T12 chỉ ghi k, alpha0.1 được kế thừa từ thiết kế search
  parent trong ledger; không suy alpha từ số metric.

## Ánh xạ với bảng mẫu của thầy

| Ý ở bảng mẫu | Cột dùng trong dự án | Lý do |
| --- | --- | --- |
| No/Method/Input/Approach | No/Nhóm/Method/Input/Approach | Tên rõ model, A/B/C và tham số chính |
| Public | CV pooled MAE | Đo trong train CV; không giả dữ liệu có public leaderboard |
| Private | Validation MAE/RMSE/R² | Development holdout để chọn phương án trước T13 |
| Avg. | Bỏ, thay bằng Δ MAE validation so persistence (%) | Không trộn metric/split khác nhau thành một số lựa chọn |
| Kết quả cuối | Test MAE + test_run_id | Chỉ pipeline T13 đã chấm, nguồn refit riêng |
| Tô dòng tốt nhất | Best validation mô tả + marker Đã khóa riêng | Không đổi quyết định T12/T13 bằng bảng mới |

Không có cột Public/Private/Avg thật trong CSV. Đây là diễn giải cách đọc
do người dùng cung cấp, không phải bằng chứng đồ án tham gia leaderboard.

## Pooled và thống kê fold

Ưu tiên ghép predictions out-of-fold đã đăng ký, kiểm IDs không giao nhau,
tính bằng `beijing_air.metrics.regression_metrics`. Nếu thiếu OOF, chỉ dùng
metric từng fold khi đủ n_scored hữu hạn nguyên dương và MAE/RMSE hợp lệ:

```text
pooled MAE  = Σ(n_i × MAE_i) / Σ n_i
pooled RMSE = sqrt(Σ(n_i × RMSE_i²) / Σ n_i)
```

Thiếu cả OOF và n_i thì để chưa có, không lấy trung bình đơn giản thay thế.
Candidate phải có đủ3fold completed, không failed folds mới được tổng hợp.
OOF có sẵn nhưng sai checksum/IDs trùng thì dừng báo lỗi, không lén chuyển
sang số metric khác để che lỗi. Kiểm metric OOF từng fold và pooled với log.

Mean±std là trung bình không trọng số và độ lệch chuẩn quần thể giữa fold
(ddof0), chỉ mô tả biến thiên; không phải CI, không thay pooled. Train chỉ
khoảng2năm và fold đầu thiếu mùa; không khẳng định ổn định chỉ từ pooled.
RF A và B chưa có CV riêng, không ghi std hoặc pooled giả.

## Validation, baseline và highlight

Metric validation trong bảng giữ số gốc từ metrics.json (hoặc metric nhúng
trong ledger khi JSON thiếu, có cảnh báo). Saved predictions dùng để tính
lại kiểm tra và chứng minh cùng sorted sample IDs, y_true, primary cohort,
coverage100% trước khi tính:

```text
Δ MAE (%) = 100 × (MAE_persistence − MAE_model) / MAE_persistence
```

Số dương là giảm MAE; giữ cả số âm. Baseline tự so là0hợp lệ, không phải
placeholder. Thiếu nguồn/khác IDs/target/coverage hoặc baseline MAE≤0 thì Δ
để thiếu, có lý do. Metric log KHÁC predictions giữ số đã ghi và cảnh báo,
không highlight hoặc tính Δ từ số đó. Không sửa input/log khi phát hiện KHÁC.

Tô theo validation MAE nhỏ nhất trong các dòng completed, có bằng chứng
cùng cohort. Nếu hòa trong1e-12, tô các dòng đồng hạng; không dùng test để
phá hòa. Hiện RF A được tô, validation MAE9.561488, giảm1.798669% so baseline.

Marker “Đã khóa (T12/T13)” đọc từ development_selected_run_id của thiết kế
T13 lưu trong ledger parent, kế thừa quyết định T12; hiện run780ecb7f…,
RF A. Marker độc lập highlight. Khi sau T17b có dòng validation tốt hơn,
vẫn giữ marker RF và ghi “ứng viên, chưa đánh giá độc lập”; không thay frozen
config, demo/model hoặc test result. Tests kiểm đúng tình huống này.

## Test là run riêng sau refit

Chỉ ghép T13 completed child, feature A, đúng model/locked params và
reference_run_id trỏ đến run development của dòng đó. Không ghép test dựa
riêng tên “Ridge” hoặc “RF”. Persistence so primary chỉ dùng PM2.5(t), nên
T09 feature_set dạng mô tả được liên kết đến T13 A theo reference rõ ràng.

| Dòng development | run_id validation | test_run_id T13 |
| --- | --- | --- |
| Persistence | 24cef47874a94d9faa7bfcbae29b5c58 | 0960fac6455f4380bd5b6d1407633cf8 |
| Ridge A alpha0.1 | 32e65c5a4cbc489c905cf146b743867f | 51975d2c66ff4263b83ace6962f3d3f7 |
| RF A | 780ecb7fb59d48bea58d5e4a076f1f26 | 24cd6d765f214d52aa26e5988380e2cd |

Ridge alpha1/B/C và mọi ứng viên mới để trống Test. Ridge/RF T13 refit pipeline
train+validation; persistence chỉ áp dụng quy tắc, không fit model. Với ML,
fitted state và giai đoạn fit khác mô hình validation,
không lấy chênh lệch hoặc trung bình hai cột để chọn model. Script chỉ đọc
saved T13 test predictions/metrics, không mở raw test samples, không load
joblib hoặc fit model, không coi test là chưa xem.

## Idempotence và provenance

Input allowlist: official ledger, metrics.json do ledger chỉ tới, predictions
đã đăng ký trong đúng run folder (SHA đối chiếu khi có). Không quét data/,
cache/test folders hoặc tự tìm model khác; không ghi vào Experiment Log.
Nguồn ngoài project hoặc prediction không thuộc run sẽ bị từ chối.

Provenance ghi SHA input/module/CLI và dependency versions. Với cùng input,
code và môi trường, lần sau giữ source_commit/generated_at của lần sinh
đầu cùng signature; không đổi timestamp chỉ vì chạy lại hoặc commit output.
XLSX chuẩn hóa ZIP/core timestamps để byte giống nhau; PNG không nhúng ngày
ngẫu nhiên. File chỉ ghi lại nếu bytes khác.

Nếu input/code/môi trường đổi thì signature mới và ghi nguồn mới. source_commit
là commit source lúc sinh, không phải tự tham chiếu commit chứa chính output;
SHA generator cho phép đối chiếu code cụ thể. Không yêu cầu tái tạo PNG giống
từng byte giữa mọi phiên bản font/Matplotlib hoặc OS khác.

```powershell
.\.venv\python.exe -m pytest tests/test_experiment_summary.py -q -p no:cacheprovider --basetemp=artifacts/t17a_TEST_final
.\.venv\python.exe scripts/build_experiment_summary.py
.\.venv\python.exe scripts/build_experiment_summary.py
```

Fixture TEST_ONLY kiểm unequal fold sizes/weighted RMSE, OOF ưu tiên,
missing counts, trùng OOF IDs, group order, test attribution/params,
lock invariant khi ứng viên mới thắng, Δ%/cohort, failed/missing runs,
empty log, Unicode và byte-idempotence CSV/MD/XLSX/PNG/JSON. Không fit mô
hình hoặc coi fixture là thực nghiệm full. QA thực tế được bàn giao trong PR.

## Dùng cho T15/T16 và giới hạn

T15 #38 có thể lấy bảng/hình này làm nguồn; T16 #39 audit nguồn/ID/format và
đưa gói summary vào nộp cuối kỳ. Chưa chạy T17b, NB01 hoặc R01 trong T17a.
Không sửa DOCX/PPTX/báo cáo giữa kỳ hay kết quả T13 để thêm dòng mới.

Thiếu artifact sẽ hiện cảnh báo/CHƯA CÓ, không gọi đó là OK. KHÁC giữ cả
giá trị quan sát và giá trị tham chiếu trong checks. Hiện các mẫu số liệu
tham chiếu14mục lấy từ prompt người dùng, không phải metric dựng cho run mới.

Codex hỗ trợ module/CLI/tests/render/docs; hoanglecodingmachine được giao,
review/đọc/hiểu trước merge [CẦN BỔ SUNG]. Chủ đề05,06,Ensemble/04 khi nói
features; file/trang bài giảng và rubric gốc [CẦN BỔ SUNG], không tự suy điểm.
