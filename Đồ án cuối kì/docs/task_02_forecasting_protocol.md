# Task 02 — Chỉ mục đặc tả và kế hoạch thực nghiệm

Đề tài: dự báo PM2.5 đúng một giờ tiếp theo tại cùng trạm Bắc Kinh bằng thông
tin đã có đến t. Protocol ban đầu được tổ chức lại ngày 02/11/2026; nội dung
hợp lệ được chuyển vào các tài liệu chuyên trách, không tạo hai protocol độc lập.

| Tài liệu hiện hành | Nội dung |
| --- | --- |
| [problem_definition.md](problem_definition.md) | Input/output, hồi quy/đơn vị, số đo t, trạm đã thấy và RQ1/RQ2/RQ3 |
| [experiment_plan.md](experiment_plan.md) | Feature/tiền xử lý, persistence/Ridge/RF, grid, split, metric/tie-break, nhóm sai số, tái lập; A/B/C, CV, fallback, test gate và logger |
| [project_plan.md](project_plan.md) | CRISP-DM → T01–T16, T04-LOG, MK01/MK02; phụ thuộc và trạng thái có bằng chứng |
| [midterm_plan.md](midterm_plan.md) | Checklist DOCX/PPTX và gói giữa kỳ |

`configs/default.json` giữ seed=42, horizon_hours=1, smoke/full và paths hiện
có; bổ sung hợp đồng problem/split/CV/features/evaluation/logger. Những trường
mới chưa được pipeline model thực thi. Task này không huấn luyện hoặc mở test.

Giữ quyết định đúng trạm/+1 giờ, quan sát tới t, không impute target, cohort
chính cùng IDs có PM2.5(t)/target, ba họ phương pháp, grid ứng viên, mốc
2015-03-01/2016-03-01, metric và nhóm sai số. Điều chỉnh có chủ đích:

- F0/F1 tương ứng A/B; bổ sung C được chọn từ B trong từng fold.
- Tuning bằng expanding-window trong train; validation ngoài chọn phương án.
- Theo danh sách người dùng chốt, **T13 refit train+validation sau khóa**;
  thay quyết định không refit trong protocol ban đầu, chưa chạy trong T02.
- Bổ sung fallback persistence và cohort phụ, giữ cohort chính tương thích.

Báo cáo cuối kỳ vẫn 5 chương: (1) giới thiệu, (2) cơ sở/dữ liệu, (3) phương pháp,
(4) thực nghiệm/thảo luận, (5) kết luận/hướng phát triển. Giữa kỳ không thay
báo cáo này. Mọi số liệu/hình/model phải có artifact thật, nguồn/AI disclosure;
không tự điền thành viên/đóng góp. Chưa có rubric chính thức trong repo; mapping
dựa trên yêu cầu người dùng, không cam kết tiêu chí chưa được cung cấp.

Codex hỗ trợ cập nhật đặc tả; chưa phát sinh metric hoặc lịch sử mô hình.
