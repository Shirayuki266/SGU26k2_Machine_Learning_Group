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

## T17a / Issue #40

Codex hỗ trợ module/CLI tổng hợp, fixture TEST_ONLY, kiểm weighted pooled
MAE/RMSE/nguồn run, render CSV/MD/XLSX/PNG và soạn hướng dẫn. Chỉ đọc ledger,
metrics/saved predictions, gồm artifact test T13 đã có; không fit/tune, mở
raw test samples, ghi thêm run hoặc sửa frozen/log/báo cáo giữa kỳ.

Người dùng xác nhận giao hoanglecodingmachine; Git identity kiểm trước mỗi
commit. Phần người nhận đã đọc/hiểu/review [CẦN BỔ SUNG], không tự gán tỷ lệ
đóng góp học thuật. Chưa triển khai T17b/T15/T16. Bằng chứng ở reports/tables/,
docs/experiment_summary_readme.md và PR T17a.

## NB01 / Issue #42

Codex hỗ trợ soạn notebook hành trình, helper AST/git/test map, bảng vai trò
file và diễn giải từ artifact, crosscheck saved predictions/OOF và số giữa
kỳ; chạy kernel mới, xuất HTML và kiểm bố cục. Không huấn luyện/tuning,
load weights hoặc đọc mẫu test thô; T13/T14 chỉ artifact đã có. Không sửa
ledger/config/frozen/metrics hay hồ sơ giữa kỳ. Hỗ trợ này không tự quy thành
đóng góp học thuật. Người nhận hoanglecodingmachine cần rà soát/hiểu trước
merge; người review, họ tên/MSSV/% [CẦN BỔ SUNG]. Bằng chứng ở reports/notebook,
notebook có output và docs/notebook_code_map.md.

## T17b / Issue #44

Codex hỗ trợ soạn kế hoạch đã khóa trước khi chạy, candidate runner, CLI và
fixture-only tests. Sau khi khôi phục bundle T13 có checksum được manifest
xác nhận, smoke chạy thành công. Lần full đầu đã fit các candidate/fold và
validation nhưng lỗi khi ghi Stack metadata do biến OOF tham chiếu chưa khai
báo; run lỗi được giữ nguyên trong ledger. Đã sửa, thêm regression test và
chạy lại cùng frozen design thành công. Full thiết kế bị chạy lại do lỗi tích
hợp nên compute thực vượt budget đã khai báo; không thêm/thay candidate hoặc
hyperparameter. T17a summary được tái tạo sau T17b, 412 kiểm tra đều OK; runner
xác nhận không truy cập test CSV. Review/đọc/hiểu của thành viên
[CẦN BỔ SUNG]. Trạng thái và kết quả ở docs/supplementary_experiments.md.

## T15 / Issue #38

Codex hỗ trợ đọc quy chuẩn/nguồn, viết module và script sinh DOCX/PPTX/poster,
kiểm thử cấu trúc và lập chỉ mục/hash từ các artifact có sẵn. Không chạy model
runner, không train/tune/refit, không đọc test thô hoặc ghi Experiment Log.
Test metrics được trình bày từ CSV đã lưu; test T13 đã được mở trước task này.
Các khác biệt giữa thông tin đầu vào và artifact được ghi rõ thay vì tự sửa số.

Người dùng xác nhận người nhận là GitHub account `duyhuynh4869-byte`, trùng Git
identity local. Họ tên/MSSV/% đóng góp và xác nhận đã đọc/hiểu/review vẫn
[CẦN BỔ SUNG]. Báo cáo, slides và poster là bản nháp, chưa được nhóm/giảng viên
review trực quan hoặc phê duyệt nộp.
