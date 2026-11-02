# Kế hoạch bàn giao giữa kỳ

Trạng thái ngày 02/11/2026: có cấu trúc T01, protocol T02, manifest/audit T03,
loader và báo cáo chất lượng T04; T04-BỔ SUNG cung cấp Experiment Log trước
khi chạy baseline. Chưa có kết quả mô hình được xác minh. Log chỉ có header,
không dựng bảng so sánh hoặc lịch sử chạy để lấp phần thiếu.

## Nội dung cần chuẩn bị

1. Đề tài, thành viên và phân công: nhóm cung cấp thông tin thật; chưa xác minh
   tên, MSSV hoặc đóng góp trong task này.
2. Bối cảnh, mục tiêu, input/output và hồi quy: dùng protocol T02, trình bày
   dự báo đúng t+1 cùng trạm và điều kiện thông tin có tới t.
3. Nguồn UCI 501, schema, số mẫu và chất lượng: trích manifest/audit hiện có,
   ghi rõ audit toàn bộ dữ liệu đã thực hiện ở T03–T04; không gọi đó là EDA train.
4. EDA, preprocessing, đặc trưng: hiện mới có chính sách/thiết kế; chưa có
   notebook EDA train và pipeline được xác minh, cần task riêng.
5. Pipeline, baseline, mô hình và thực nghiệm: phân biệt thiết kế với phần đã
   chạy. Tích hợp logger trước baseline/training; kết quả giữa kỳ dùng validation.
6. Kết quả và nhận xét: hiện có kết quả audit, chưa có metric mô hình. Chỉ thêm
   metric/bảng/hình khi có run và artifact thật; ghi run_id hoặc bảng truy vết.
7. Tiến độ, khó khăn, giới hạn và phần còn lại: dựa trên project_plan.md và
   báo cáo task; không bắt buộc tuning/test cuối/demo trước giữa kỳ.
8. Đóng góp thực tế từng người: nhóm xác nhận; không suy từ người chạy script
   hoặc tác giả hỗ trợ AI thành đóng góp học thuật.

## Sản phẩm và đóng gói

Báo cáo `.docx`, slide `.pptx`, mã `.py`/notebook `.ipynb`, cấu hình/dependencies,
CSV Experiment Log, file hình gốc, dữ liệu hoặc đường dẫn/hướng dẫn tải,
model nếu đã huấn luyện và cần bàn giao, README tái lập. Báo cáo và slide chưa
được tạo trong task logger. Thư mục run đang ignore trong Git: khi có run thật
phải kèm `artifacts/experiments/` để CSV liên kết được config/metrics/artifact.

Tên ZIP dự kiến: `NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip`; `XX` chờ nhóm xác nhận.
Không tạo ZIP, kết quả hoặc model giả trong lần bổ sung này. Báo cáo giữa kỳ
theo CRISP-DM, bao phủ các mục yêu cầu trên và không thay báo cáo cuối kỳ 5 chương.
Logger được Codex hỗ trợ cài đặt/kiểm thử/tài liệu; nhóm rà soát khi tích hợp.
