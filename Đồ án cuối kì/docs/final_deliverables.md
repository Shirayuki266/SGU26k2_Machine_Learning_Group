# T15 — Hướng dẫn hồ sơ cuối kỳ

## Trạng thái

Các file trong `reports/final/` là **bản nháp**, không phải bản nộp đã được
nhóm/giảng viên duyệt. Tên nhóm, thành viên, MSSV, vai trò, phần việc thật,
phần trăm đóng góp, rubric, tham chiếu trang bài giảng và kích thước poster
cần được nhóm xác nhận trước khi nộp. Không suy tỷ lệ đóng góp từ số commit.

## Sinh và kiểm chứng

Chạy tại thư mục `Đồ án cuối kì` trên Windows, với môi trường phụ thuộc của dự án:

```powershell
.\.venv\Scripts\python.exe scripts/build_final_deliverables.py
.\.venv\Scripts\python.exe scripts/verify_final_deliverables.py
.\.venv\Scripts\python.exe -m pytest tests/test_final_deliverables.py tests/test_experiment_summary.py -q
```

Builder tạo DOCX 5 chương, PPTX 18 slide, poster PPTX/PNG, `figure_table_index.csv`,
`traceability.json`, `NEEDS_GROUP_INPUT.md` và `verification.json` trong
`reports/final/`. Khi sửa config nhóm ở `configs/final_deliverables.json`, hãy
sinh lại và kiểm toàn bộ Office output; không chỉ sửa file đã sinh vì lần chạy
kế tiếp sẽ ghi đè.

`traceability.json` ghi commit nguồn, SHA-256/kích thước các nguồn tương đối,
thống kê commit theo author, và checksum lịch sử được bảo vệ. Verifier kiểm
Office archive/CRC, nội dung, số slide, poster PNG, dấu vết đường dẫn cá nhân,
source hashes, ledger và cây `reports/midterm/`.

## Phạm vi dữ liệu và bất biến

Builder chỉ đọc artifact tổng hợp, hình, tài liệu và ledger để tính checksum/
thống kê lịch sử. Không gọi huấn luyện, tuning, refit, inference hoặc mở mẫu
test thô. T13 đã đánh giá Test trước T15; báo cáo dùng các metric đã lưu và
công khai điều này. `experiments/experiment_log.csv` và `reports/midterm/` là
nguồn chỉ đọc; nếu thay đổi, verifier phải báo lỗi.

Số liệu trong báo cáo lấy từ artifact đã lưu khi khác với nội dung yêu cầu:
RF Dingling MAE là 8,5951 (không phải 8,6287), RF JJA MAE là 7,6437 (không phải
6,6666). Run ID lần T17b full lỗi `3cc5790dd34d4ca29435f4da86b68ae7` không tìm
thấy trong ledger hiện tại; tài liệu supplementary mô tả lỗi Stack metadata.
Các khác biệt được ghi trong `reports/final/verification.json` và
`reports/final/NEEDS_GROUP_INPUT.md`; không sửa ngược artifact lịch sử để khớp
yêu cầu.

## Tài liệu nền

- [Tham khảo đã kiểm chứng](references.md)
- [Ghi chú nghiên cứu liên quan](related_work_notes.md)
- [Công bố hỗ trợ AI](ai_disclosure.md)
- [Đóng góp nhóm](team_contributions.md)
- [Checklist bàn giao](submission_checklist.md)

Tài liệu tham khảo giảng viên vẫn có nhãn `[CẦN BỔ SUNG]` ở tên file/chủ đề/
trang slide, và không được thay bằng trích dẫn suy đoán. Poster mặc định
36 × 48 inch chỉ là thiết lập tạm, cần xác nhận với giảng viên.
