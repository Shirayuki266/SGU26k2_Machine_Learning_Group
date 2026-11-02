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
| T03 | Tải UCI 501, nguồn/license, manifest/checksum | T01–T02 | Issue #4; xác minh lại 02/11/2026: 12 trạm/420.768 dòng, manifest/raw không đổi; sửa fallback ZIP, xem reports/data_audit.md; không tải lại |
| T04 | Ghép trạm, audit chất lượng, giữ raw/chưa impute | T03 | Issue #5; có src/beijing_air/data.py, tests/test_data.py, reports/data_quality.md; không audit lại |
| T04-LOG | Logger, CSV, hồ sơ run và kiểm thử | T01–T04; trước model | Tên hiện hành của T04-BỔ SUNG, cùng Issue #6/PR #7 đã merge; không tạo hệ thống song song |
| T05 | Target đúng +1 giờ cùng trạm, temporal split và kiểm tra ranh giới | T04, T02 | Issue #1; PR #11 đã merge; samples.py/build_samples.py, tests và [audit split](../reports/sample_split.md) |
| T06 | EDA train: tính chất biến, đơn/đa biến, missing/bất thường/ngoại lệ, chu kỳ thời gian/trạm; notebook, bảng, hình gốc và nhận xét | T05 xác định train | Issue #12; PR #13 đã merge; notebook full kernel sạch, 14 bảng/9 PNG và [quyết định T07/T08](eda_findings.md) |
| T07 | Feature engineering A/B, lag/rolling đúng trạm/timestamp, dictionary và causal tests | T05–T06 | Issue #14; PR #15 đã merge; A 20/B 33 cột, giữ 205.977 train IDs, [dictionary và missing](feature_dictionary.md), API forecast không cần nhãn |
| T08 | Pipelines impute/encode/scale Ridge/RF, fit train/fold, save/load/inference | T05, T07 | Issue #16; PR #17 đã merge; [factories/config](preprocessing.md), fixture kiểm train-only/missing/unknown/clone/save-load; chưa fit ML trên dữ liệu dự án |
| T09 | Persistence + fallback/tỷ lệ fallback, validation MAE/RMSE/R², log/predictions | T05, T04-LOG, T08 | Issue #18, PR #19 đã merge; [smoke/full thật](baseline_results.md), primary MAE 9,736617/RMSE 19,240919/R² 0,944804, khóa validation IDs |
| T10 | Ridge và RF ban đầu A, so baseline cùng validation IDs; config/metric/thời gian/nhận xét/đề xuất | T07(A), T08–T09, T04-LOG | Issue #20, PR #21 đã merge; [hai smoke/hai full và nhận xét](initial_findings.md); validation MAE Ridge 10,200433, RF 9,561488 |
| T11 | Tune ít nhất một model bằng expanding-window CV train chung ranh giới trạm; giả thuyết/budget/log từng cấu hình/fold và so trước–sau | T10, T04-LOG | Issue #22, PR #23 đã merge; [Ridge A 4alpha×3fold +1refit](tuning_findings.md), chọn alpha0.1, validation MAE 10,200529 chưa cải thiện T10 |
| T12 | A/B ablation, chọn C từ B trong fold, phân tích và khóa bằng train/CV/validation | T07(B), T08, T10–T11 | Issue #24, PR #25 đã merge; [ablation/RQ2](ablation_findings.md), Ridge A/B/C MAE 10,200529/9,968755/9,903377, C12 nhóm; [frozen](../reports/ablation/frozen_model.json) chọn RF A T10 theo validation, chưa T13 |
| T13 | Sau khóa refit train+validation rồi test, sai số theo trạm/mùa/nồng độ, diễn giải và trả lời RQ; không tuning test | T12 khóa, T04-LOG | Chưa xác minh hoàn thành/Issue/artifact; test khóa |
| T14 | Streamlit dùng pipeline/model chọn bằng validation, dự báo t+1, lịch sử/thực tế nếu có, feature causal | T12 khóa lựa chọn, T13 artifact cuối | Chưa xác minh hoàn thành/Issue/artifact |
| T15 | Báo cáo 5 chương, slide, notebook/README; truy vết artifact, nguồn/AI disclosure | T06–T14/artifact thật | Chưa xác minh hoàn thành/Issue/artifact |
| T16 | Tái lập, đối chiếu source–log–metric–hình–báo cáo, tài nguyên và gói cuối kỳ; lệnh đã chạy/giới hạn | T15 và artifact liên quan | Chưa xác minh hoàn thành/Issue/artifact |
| MK01 | DOCX/PPTX giữa kỳ: bài toán/dữ liệu/EDA/pipeline/baseline/model, kết quả/vòng thử–nhận xét–sửa, khó khăn/kế hoạch/đóng góp | Ưu tiên tới T10; T11/T12 nếu có | Issue #26; [DOCX17trang/PPTX15slide đã render/kiểm](midterm_deliverables.md), bản nháp chờ nhóm bổ sung; PR #28 đã merge theo quyền người dùng |
| MK02 | Đối chiếu source/log/hình/DOCX/PPTX/README; ZIP NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip, tài nguyên hoặc hướng dẫn tải/chạy | MK01 và artifact hiện có | Issue #27; [gói ZIP nháp/checklist/QA](submission_checklist.md) đã có: kiểm 49 run/200 artifact/43 predictions, Python cách ly và EDA train full; chờ người dùng review/merge MK02, tự bổ sung XX/thành viên |

Các hàng T08/T09 được xác minh khi bắt đầu T09; mốc cũ giữ bằng chứng đã ghi.
Không thay trạng thái Issue đã
đóng hoặc tự gán số Issue từ mã task. T03/T04 có báo cáo audit sẵn có, không
phải kết quả mô hình. Người dùng merge; theo [quy trình GitHub](github_workflow.md).

## 3. Cổng chất lượng và sản phẩm

- Trước T09/T10: dùng snapshot/IDs T05 đã xác minh; hoàn thiện T07/T08 khi cần,
  logger sẵn sàng và config/budget đã ghi; không suy hoàn thành task từ Issue đóng.
- Phát triển: chỉ train/CV/validation, A/B/C cùng mẫu và thay đổi được kiểm soát;
  kiểm tra leakage, save/load và pipeline trong task triển khai.
- Trước T13: khóa lựa chọn/run validation; khi được giao mới refit
  train+validation và mở test, không quay lại chọn phương án theo test.
- Giữa kỳ: MK01 DOCX/PPTX phản ánh tiến độ thật ưu tiên T10, không bắt buộc
  T11/T12/test/demo; MK02 đối chiếu và đóng gói theo [checklist](midterm_plan.md).
- Cuối kỳ: source/notebook/config/dependencies/README, pipeline/model/predictions
  nếu có, hình gốc, CSV/hồ sơ run, demo, T15 báo cáo 5 chương/slide và T16 gói
  tái lập. Artifact không commit phải có đường dẫn/cách tạo lại.

CSV chính thức có 49 run completed: hai persistence T09, bốn Ridge/RF T10,
23 hồ sơ T11 và 20 hồ sơ T12 (5 smoke, 15 full search/candidate/fold/final).
Không có run minh họa; không gọi toàn bộ 49 dòng là 49 model độc lập;
T05 có target/split và audit count/date,
T06 có EDA train, T07 có A/B và registry/missing train theo cấu hình cập nhật
người dùng chốt (lịch t+1, lag 1/3/6/12/24h). T08 có preprocessing factories
và kiểm tra fixture; T09 có metric/predictions validation và fallback
train-only; T10 có pipeline fit train primary, predictions/metrics train và
validation cùng IDs. T11 đã tuning Ridge A trong train CV và refit/validation;
T12 đã so Ridge A/B/C cố định alpha, selection trong fold và khóa RF A bằng
validation; chưa tuning RF hoặc mở test/T13. Không nhập audit/fixture vào log
hoặc dựng lịch sử; không tự triển khai task sau khi chưa được giao.
Codex hỗ trợ mapping; không tự điền tên/MSSV/đóng góp hoặc rubric chưa cung cấp.
