# Kế hoạch dự án theo CRISP-DM

Cập nhật T02 ngày 02/11/2026 theo danh sách người dùng chốt. **Tên và phạm vi
T01–T16, T04-LOG, MK01/MK02 đã thống nhất**. Chỉ trạng thái hoàn thành, số
Issue, người phụ trách và artifact chưa có bằng chứng mới cần xác minh.
Mã task không phải số Issue; không tạo Issue cho task chưa được giao.

Đặc tả hiện hành: [bài toán](problem_definition.md), [thực nghiệm](experiment_plan.md),
[giữa kỳ](midterm_plan.md). Một task quản lý Issue/branch/PR có thể có nhiều
run và vòng thử–nhận xét–sửa; không mặc định một run tương ứng một commit.

## 1. Mapping CRISP-DM

| Giai đoạn | Task chính | Bằng chứng/sản phẩm |
| --- | --- | --- |
| Business Understanding | T02; quay lại khi RQ/phạm vi đổi | Input/output, giả định, RQ và tiêu chí |
| Data Understanding | T03, T04, T06 | Manifest/audit, EDA train và nhận xét |
| Data Preparation | T04, T05, T07, T08; selector T12 | Merge, target/split, dictionary, causal tests, pipeline |
| Modeling | T09, T10, T11, T12 | Baseline, A, tuning train-CV, A/B/C; config/log/predictions |
| Evaluation | T10–T13 | Validation/CV phát triển; test sau khóa/refit, sai số/diễn giải |
| Deployment và bàn giao | T14, T15, T16; MK01/MK02 giữa kỳ | Demo, hồ sơ, tái lập và gói nộp |

T01 và T04-LOG là hạ tầng xuyên suốt. CRISP-DM có vòng lặp: EDA/đánh giá có
thể tạo giả thuyết đổi feature/pipeline; mỗi thay đổi có log/budget, giữ test
khóa và không tự chạy task kế tiếp hoặc vòng chạy vô hạn.

## 2. Danh sách task đã chốt

Phụ thuộc là trình tự kỹ thuật, không cấp quyền chạy. Chưa có người phụ trách
được xác minh; không tự phân công. Các task chưa có Issue chỉ ghi mã task.

| Task | Phạm vi/đầu ra | Phụ thuộc chính | Trạng thái và Issue có bằng chứng |
| --- | --- | --- | --- |
| T01 | Cấu trúc/môi trường, README/config/dependencies, cài/import | — | Issue #2; PR #8 đã merge; [xác minh](t01_environment_verification.md) portable 3.12.10/import đủ; chưa kiểm máy sạch |
| T02 | Problem definition, experiment plan, CRISP-DM/project plan, checklist giữa kỳ | T01 | Issue #3 gốc đã đóng; lần này cập nhật tài liệu, bàn giao PR riêng |
| T03 | Tải UCI 501, nguồn/license, manifest/checksum | T01–T02 | Issue #4; có configs/uci_501.json, reports/data_manifest.json, reports/data_audit.md; không tải lại |
| T04 | Ghép trạm, audit chất lượng, giữ raw/chưa impute | T03 | Issue #5; có src/beijing_air/data.py, tests/test_data.py, reports/data_quality.md; không audit lại |
| T04-LOG | Logger, CSV, hồ sơ run và kiểm thử | T01–T04; trước model | Tên hiện hành của T04-BỔ SUNG, cùng Issue #6/PR #7 đã merge; không tạo hệ thống song song |
| T05 | Target đúng +1 giờ cùng trạm, temporal split và kiểm tra ranh giới | T04, T02 | Issue #1 có tên tương ứng và đã đóng, **chưa có mã/artifact đủ xác minh trong repo**; không suy hoàn thành từ Issue |
| T06 | EDA train: tính chất biến, đơn/đa biến, missing/bất thường/ngoại lệ, chu kỳ thời gian/trạm; notebook, bảng, hình gốc và nhận xét | T05 xác định train | Chưa xác minh hoàn thành/Issue/artifact |
| T07 | Feature engineering A/B, lag/rolling đúng trạm/timestamp, dictionary và causal tests | T05–T06 | Chưa xác minh hoàn thành/Issue/artifact |
| T08 | Pipelines impute/encode/scale Ridge/RF, fit train/fold, save/load/inference | T05, T07 | Chưa xác minh hoàn thành/Issue/artifact |
| T09 | Persistence + fallback/tỷ lệ fallback, validation MAE/RMSE/R², log/predictions | T05, T04-LOG | Chưa xác minh hoàn thành/Issue/artifact |
| T10 | Ridge và RF ban đầu A, so baseline cùng validation IDs; config/metric/thời gian/nhận xét/đề xuất | T07(A), T08–T09, T04-LOG | Chưa xác minh hoàn thành/Issue/artifact |
| T11 | Tune ít nhất một model bằng expanding-window CV train chung ranh giới trạm; giả thuyết/budget/log từng cấu hình/fold và so trước–sau | T10, T04-LOG | Chưa xác minh hoàn thành/Issue/artifact |
| T12 | A/B ablation, chọn C từ B trong fold, phân tích và khóa bằng train/CV/validation | T07(B), T08, T10–T11 | Chưa xác minh hoàn thành/Issue/artifact |
| T13 | Sau khóa refit train+validation rồi test, sai số theo trạm/mùa/nồng độ, diễn giải và trả lời RQ; không tuning test | T12 khóa, T04-LOG | Chưa xác minh hoàn thành/Issue/artifact; test khóa |
| T14 | Streamlit dùng pipeline/model chọn bằng validation, dự báo t+1, lịch sử/thực tế nếu có, feature causal | T12 khóa lựa chọn, T13 artifact cuối | Chưa xác minh hoàn thành/Issue/artifact |
| T15 | Báo cáo 5 chương, slide, notebook/README; truy vết artifact, nguồn/AI disclosure | T06–T14/artifact thật | Chưa xác minh hoàn thành/Issue/artifact |
| T16 | Tái lập, đối chiếu source–log–metric–hình–báo cáo, tài nguyên và gói cuối kỳ; lệnh đã chạy/giới hạn | T15 và artifact liên quan | Chưa xác minh hoàn thành/Issue/artifact |
| MK01 | DOCX/PPTX giữa kỳ: bài toán/dữ liệu/EDA/pipeline/baseline/model, kết quả/vòng thử–nhận xét–sửa, khó khăn/kế hoạch/đóng góp | Ưu tiên tới T10; T11/T12 nếu có | Chưa có DOCX/PPTX xác minh; không mở test |
| MK02 | Đối chiếu source/log/hình/DOCX/PPTX/README; ZIP NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip, tài nguyên hoặc hướng dẫn tải/chạy | MK01 và artifact hiện có | Chưa có gói xác minh; XX/thành viên cần cung cấp |

Trạng thái GitHub được đọc lúc bắt đầu T02. Không thay trạng thái Issue đã
đóng hoặc tự gán số Issue từ mã task. T03/T04 có báo cáo audit sẵn có, không
phải kết quả mô hình. Người dùng merge; theo [quy trình GitHub](github_workflow.md).

## 3. Cổng chất lượng và sản phẩm

- Trước T09/T10: xác minh mã/kiểm thử target/split T05, T07/T08 khi cần, logger
  sẵn sàng và config/budget đã ghi. Issue #1 đóng chưa thay được bằng chứng T05.
- Phát triển: chỉ train/CV/validation, A/B/C cùng mẫu và thay đổi được kiểm soát;
  kiểm tra leakage, save/load và pipeline trong task triển khai.
- Trước T13: khóa lựa chọn/run validation; khi được giao mới refit
  train+validation và mở test, không quay lại chọn phương án theo test.
- Giữa kỳ: MK01 DOCX/PPTX phản ánh tiến độ thật ưu tiên T10, không bắt buộc
  T11/T12/test/demo; MK02 đối chiếu và đóng gói theo [checklist](midterm_plan.md).
- Cuối kỳ: source/notebook/config/dependencies/README, pipeline/model/predictions
  nếu có, hình gốc, CSV/hồ sơ run, demo, T15 báo cáo 5 chương/slide và T16 gói
  tái lập. Artifact không commit phải có đường dẫn/cách tạo lại.

CSV chính thức hiện chỉ header; chưa xác minh EDA train, target/features,
baseline/model/metric trong repo. Không nhập audit vào log mô hình hoặc dựng
lịch sử. T02 chỉ cập nhật tài liệu/config hợp đồng, chưa triển khai task sau.
Codex hỗ trợ mapping; không tự điền tên/MSSV/đóng góp hoặc rubric chưa cung cấp.
