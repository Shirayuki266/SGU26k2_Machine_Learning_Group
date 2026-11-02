# Quy tắc làm việc với Codex

Ngoại lệ theo yêu cầu MK01/MK02 mới nhất của người dùng: **Codex được merge
riêng PR MK01 (Issue #26) sau khi hoàn tất kiểm tra DOCX/PPTX**. Đây là quyền
cho một task, không mở rộng sang task khác hoặc tự đóng Issue. MK02 (Issue #27)
chỉ commit/push/mở PR để người dùng merge sau; không nộp Classroom. Người dùng
tự bổ sung thông tin nhóm, nên sản phẩm giữ NhomXX/[CẦN BỔ SUNG] và trạng thái
nháp. Yêu cầu trực tiếp này có ưu tiên hơn quy tắc không merge chung bên dưới.

Áp dụng trong `Đồ án cuối kì/`; không sửa bài lab. Theo quyền người dùng bổ sung
ngày 02/11/2026, được tạo Issue khi cần, tạo branch, commit, push branch và mở PR
cho task được giao; quy trình này thay thế yêu cầu chờ cho phép từng lần trước
đó. **Người dùng review và merge; không merge, bật auto-merge hoặc tự đóng Issue.**
Chi tiết bắt buộc và mẫu bàn giao nằm trong [quy trình GitHub](github_workflow.md).
Trước mỗi task đọc AGENTS.md, CONTRIBUTING.md nếu có, tài liệu này, kế hoạch,
cấu hình, cấu trúc repo và `git status`; bảo toàn thay đổi của thành viên khác.
Chỉ triển khai task được giao cùng phụ thuộc tối thiểu, không tự chuyển sang T05
trở đi. Không đổi Git author hoặc tạo bằng chứng đóng góp giả.

## Phạm vi nghiên cứu và dữ liệu

Đề tài: dự báo PM2.5 đúng một giờ tiếp theo, cùng trạm, UCI 501. Theo CRISP-DM,
mỗi vòng thực nghiệm bắt đầu từ câu hỏi/giả thuyết, thiết kế, chạy, ghi nhận xét
và quyết định. Không giả định pipeline đầu tiên là phương án cuối; không làm
sai có chủ ý để dựng lịch sử cải tiến hoặc tạo metric/kết quả giả.

Đọc [chỉ mục T02](task_02_forecasting_protocol.md), [bài toán](problem_definition.md),
[kế hoạch thực nghiệm](experiment_plan.md) và config trước khi triển khai.
Target ghép đúng `(station, timestamp+1h)`; không dùng dòng kế tiếp khi có
giờ khuyết; không impute target. Không dùng IQR để tự xóa nồng độ cao. Raw giữ
nguyên; audit dữ liệu tách khỏi thực nghiệm mô hình. Dùng lại đầu ra T03–T04
đã có nếu phù hợp, chỉ chạy lại khi có lý do cụ thể.

Feature chỉ dùng thông tin tới t, tính lag/rolling riêng từng trạm; không
backfill, centered rolling hoặc dùng tương lai. Imputer, encoder, scaler và
selector chỉ fit trên training partition của từng run/fold: trong phát triển
là train; riêng T13 sau khóa mới refit train+validation trước khi chấm test.
Không fit bất kỳ bước nào trên test. Split theo **target timestamp**:
train trước 2015-03-01, validation từ 2015-03-01 đến trước 2016-03-01, test từ
2016-03-01; không tự đổi mốc. Đánh giá cuốn chiếu cho phép dùng quan sát đã có
tới t. Baseline và model dùng cùng sample IDs khi so sánh.

Baseline persistence, Ridge, Random Forest; MAE chính, RMSE/R² bổ sung; seed
dự kiến 42 nhưng log ghi đúng seed thực dùng. Feature engineering khác feature
selection; selector được fit trong từng fold, không mặc định sẽ cải thiện.
Feature hiện tại F0 tương ứng bộ A, F1 có lag/rolling tương ứng bộ B; bộ C là
tập con của B, sẽ được thiết kế khi có task feature selection. Không âm thầm
đổi protocol T02. Tuning khi được giao dùng expanding-window trong train,
unique timestamps và target fit đã quan sát trước origin đánh giá. Validation
dùng chọn cấu hình; test chỉ được đánh giá sau khi khóa lựa chọn và có task
cho phép, không dùng test để cải tiến. Theo phạm vi người dùng chốt mới nhất,
T13 refit toàn pipeline trên train+validation sau khóa; quyết định này thay
quy định không refit của protocol T02 cũ. MK01 tạo DOCX/PPTX, MK02 đóng gói;
mapping tên/phạm vi task trong project_plan.md đã được người dùng xác nhận.

## Thực nghiệm và bàn giao

T04-LOG là tên hiện hành của T04-BỔ SUNG (Issue #6), không tạo logger song song.
Tích hợp [Experiment Log](experiment_logging.md) trước baseline/training tiếp
theo. Trước run: đọc kết quả cũ, ghi giả thuyết, lý do, thay đổi, run tham chiếu,
cấu hình và ngân sách. Sau run: lưu metric/predictions/artifact, so sánh dựa
trên số liệu, ghi cả kết quả bất lợi/thất bại và giới hạn. Không nhập kết quả
cũ khi thiếu artifact xác minh; nếu nhập có bằng chứng, ghi
`source="imported_existing_artifact"`, trường chưa biết để null. Không dựng lại
lịch sử mất. Không lưu secrets hoặc suy tên người chạy thành đóng góp học thuật.

Có smoke/full và giới hạn tài nguyên, n_jobs; smoke không phải kết quả full.
Không chạy vòng lặp không giới hạn. Khi task thực nghiệm chưa quy định ngân
sách: smoke rồi tối đa một cấu hình full ban đầu nếu tài nguyên cho phép;
quy tắc này không tự cấp phép chạy mô hình trong task logger/tài liệu.

Mã dùng chung ở `src/beijing_air/`, notebook gọi module. Kiểm tra có ý nghĩa
với fixture tổng hợp; không mở test set để kiểm tra hạ tầng. Cuối task báo file
thay đổi, lệnh/kết quả, run ID thật nếu có, hạn chế/chưa xác minh, task/Issue,
branch/commit, link PR và local/CI trên HEAD mới nhất. Trạng thái bàn giao:
“PR đang chờ bạn review và merge.” Nếu bị chặn, nêu bước chưa thực hiện và cung
cấp commit/PR title cùng body, không báo đã push/mở PR khi chưa thành công.

Báo cáo giữa kỳ dùng validation thật, ghi nguồn/run_id cho bảng hình; thiếu kết
quả phải ghi thiếu. Không tự điền tên/MSSV/phân công/đóng góp chưa xác minh.
Giữ nguồn dữ liệu, tài liệu tham khảo thực dùng và AI disclosure. Báo cáo giữa
kỳ không thay báo cáo cuối kỳ 5 chương; chi tiết ở [kế hoạch giữa kỳ](midterm_plan.md).

File này được bổ sung trong T04-BỔ SUNG từ yêu cầu người dùng; trước đó repo
chưa có workflow và kế hoạch tổng hợp. Không xem sự hiện diện tài liệu là bằng
chứng các bước mô hình hóa đã hoàn thành.
