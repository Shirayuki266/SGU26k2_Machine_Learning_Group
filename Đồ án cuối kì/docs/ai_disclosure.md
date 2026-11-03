# Công khai hỗ trợ AI từ giai đoạn cuối kỳ

Áp dụng từ T13 theo bổ sung của người dùng; không sửa AI disclosure hoặc hồ sơ
giữa kỳ đã có. Nội dung giữa kỳ giữ ở `configs/midterm.json` và
[tài liệu MK01](midterm_deliverables.md). Bảng này không gán công việc của AI
thành đóng góp của một sinh viên chưa được nhóm xác nhận.

## Quy tắc

Mỗi PR từ T13 có mục **Hỗ trợ AI**: công cụ, phần được hỗ trợ, file/Issue/PR,
cách kiểm tra, giới hạn và người phụ trách đã đọc/hiểu. Nếu không dùng AI thì
ghi rõ không dùng. Thiếu xác nhận review để [CẦN BỔ SUNG], không tự ghi pass.
AI không được tạo metric, run, nguồn trích dẫn, tên/MSSV hoặc tỷ lệ đóng góp giả.
Thành viên nhận việc chịu trách nhiệm đọc và hiểu trước khi merge.

## Ghi nhận hiện có

| Phạm vi | Hỗ trợ AI được ghi nhận | Kiểm tra có thể đối chiếu | Người đọc/hiểu và xác nhận |
| --- | --- | --- | --- |
| Issue #30: chuẩn bị quy trình từ T13 | Codex hỗ trợ đọc workflow và soạn mapping chủ đề, checklist sản phẩm, quy tắc Git/đánh giá; chỉ tài liệu | Diff/link và checksum log/sản phẩm giữa kỳ; kết quả thực trong PR của Issue #30 | [CẦN BỔ SUNG] thành viên review; chưa xác nhận đã hiểu |
| Công việc từ T13 trở đi | [CẦN BỔ SUNG] theo từng PR thực tế | [CẦN BỔ SUNG] lệnh/artifact/kết quả đã chạy | [CẦN BỔ SUNG] |

Issue #30 không fit/tune/refit mô hình, không mở test, không tạo kết quả cuối kỳ.
Ghi nhận trước T13 theo minh chứng đã có và xác nhận nhóm; không suy rằng mọi
thành viên đã dùng AI, tự làm hay hiểu toàn bộ source chỉ từ lịch sử Git.

## T13 / Issue #32

Codex hỗ trợ dựng runner theo frozen recipe, tests fixture TEST_ONLY, kiểm
provenance/IDs/metrics và soạn báo cáo từ artifact thực. Người nhận được người
dùng xác nhận: hoanglecodingmachine; review/đọc/hiểu trước merge [CẦN BỔ SUNG].
Trước full: tests/prefight được ghi trong PR; test chỉ mở sau kế hoạch và code
đã commit. Kết quả thực và giới hạn cập nhật bằng artifact mới, không sửa run
cũ hoặc quy đóng góp cho sinh viên chưa xác nhận.

T13 đã chạy xong theo yêu cầu: một parent/ba child, hai pipeline fit dataset,
permutation chẩn đoán, không retry/tuning thêm. Codex hỗ trợ soạn thảo luận từ
metrics/predictions/figures thật; verifier/CRC/restore fixture pass. Run IDs và
các giới hạn ở docs/results_discussion.md; review của thành viên vẫn chưa được
xác nhận, không tự đánh dấu đã hiểu hoặc tự điền tỷ lệ đóng góp.

## T14 / Issue #34

Codex hỗ trợ service inference/Streamlit, kiểm model/schema/version, resource
replay sau fit, tests TEST_ONLY, đối chiếu36 mẫu với predictions T13, chụp5ảnh
browser thật và soạn hướng dẫn/storyboard. Không train/tune, không thêm run hoặc
metric thực nghiệm. Đọc phần test đã đánh giá T13 để chuẩn bị replay, không gọi
là test chưa xem. Lỗi T08 cũ báo riêng Issue #35, không thay source/weights/run cũ.

Người nhận do người dùng xác nhận: hoanglecodingmachine. Thành viên review,
đọc/hiểu và video thật [CẦN BỔ SUNG]. Chưa deploy hoặc quay video; không quy phần
AI hỗ trợ thành tỷ lệ đóng góp học thuật đã xác nhận. Lệnh/kết quả ở docs/demo.md
và reports/demo/; artifact UI không giả làm một run model mới.
