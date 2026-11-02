# Kế hoạch dự án và trạng thái kiểm chứng

Cập nhật xác minh T01 và T04-BỔ SUNG, ngày 02/11/2026. Kế hoạch ban đầu nằm trong
[protocol T02](task_02_forecasting_protocol.md); tài liệu này tổng hợp tiến độ,
không triển khai hoặc đổi mã các task sau T04.

| Task | Bằng chứng hiện có | Trạng thái trong lần bổ sung này |
| --- | --- | --- |
| T01 — Cấu trúc/môi trường | pyproject.toml, src, configs, README, [bảng xác minh](t01_environment_verification.md) | Đã cài editable/import đủ 9 dependencies trên Python portable 3.12.10; pip check pass; chưa kiểm tra máy sạch/venv chuẩn |
| T02 — Đặc tả/kế hoạch | docs/task_02_forecasting_protocol.md | Đã đọc; giữ nguyên protocol và mốc chia |
| T03 — Tải/audit raw | reports/data_manifest.json, data_audit.md, raw_audit_full.json | Đã có bằng chứng; không tải/audit lại |
| T04 — Hợp nhất/chất lượng | src/beijing_air/data.py, tests/test_data.py, reports/data_quality.md, quality_full/summary.json | Giữ nguyên; chỉ chạy regression bằng fixture tổng hợp |
| T04-BỔ SUNG — Experiment Log | module logger, CSV header, docs/experiment_logging.md, tests/test_experiment_logging.py | Hạ tầng bổ sung; kết quả kiểm tra ở báo cáo cuối task |

Báo cáo T04 ghi 420.768 dòng/12 trạm, 0 lỗi, 951 cảnh báo được giữ nguyên.
Đây là số liệu từ báo cáo sẵn có, không phải kết quả audit mới trong task này.
Audit dữ liệu không phải một lần huấn luyện. CSV chính thức chưa có dòng run;
không tạo lại lịch sử từ T01–T04.

Các bước tiếp theo theo CRISP-DM, chờ task cụ thể: EDA trên train; chuẩn bị
target/split và kiểm tra leakage; baseline persistence; pipeline Ridge/Random
Forest; thí nghiệm bộ hiện tại và lag/rolling; tuning ít nhất một model; feature
selection; đánh giá đã khóa và phân tích lỗi; demo/báo cáo/bàn giao. Tuning và
test cuối không thuộc phạm vi T04-BỔ SUNG. Mỗi task thực nghiệm phải tích hợp
logger, ghi cấu hình/ngân sách và lưu artifact trước khi diễn giải kết quả.

Chưa có EDA train, target/split pipeline, baseline, model, tuning, feature
selection hay đánh giá test được xác minh trong repo đã kiểm tra. Không mở
test set trong lần bổ sung này. Quy tắc thực thi ở [workflow](codex_workflow.md).
