# Ghi chú nghiên cứu liên quan

Các ghi chú này là khung tổng hợp cho bài toán PM2.5 giờ kế tiếp; không hàm ý
đã triển khai mọi thuật toán hoặc tái lập các kết quả trong tài liệu tham khảo.
Trích dẫn theo danh mục IEEE tại [references.md](references.md).

## Hồi quy điều chuẩn và chọn đặc trưng

Ridge thêm phạt L2 để co hệ số và kiểm soát nghiệm khi biến giải thích tương
quan [2]. Lasso dùng phạt L1, có thể đưa một số hệ số về 0 [3]. Elastic Net kết
hợp L1/L2, hữu ích khi nhóm biến tương quan [4]. Trong dự án, Ridge A là đối
chứng T13 được đánh giá theo recipe đã khóa; Lasso/ElasticNet B chỉ là thí
nghiệm bổ sung T17b trên train-CV/validation. Không suy hệ số thành quan hệ
nhân quả; A/B/C là các bộ đặc trưng, C được chọn theo nhóm và fit bên trong
fold train.

## Cây, boosting và ensemble

Random Forest trung bình hóa nhiều cây bootstrap để giảm phương sai [5].
Gradient boosting cộng dần các learner theo hàm mất mát [6]; HistGradientBoosting
B là ứng viên T17b chứ không thay recipe RF A đã khóa bằng validation. Stacked
generalization học cách kết hợp dự báo tầng cơ sở [7]; trong T17b meta-Ridge
chỉ fit trên dự báo OOF train, validation chỉ dùng để đánh giá. Fusion-3 lấy
trung bình các dự báo được chọn từ pooled CV. So sánh validation của nhiều ứng
viên chỉ mô tả một cohort phát triển; không phải kết quả test hay bằng chứng
thắng ổn định.

## Đánh giá theo thời gian và quy trình phần mềm

Cross-validation ngẫu nhiên có thể làm sai lệch đánh giá chuỗi thời gian khi
thông tin tương lai lọt vào tập huấn luyện; đánh giá phải tôn trọng thứ tự thời
gian [8]. Dự án dùng expanding-window, nhóm timestamp chung qua các trạm và
purge nhãn theo origin. Imputer, encoder, scaler và selector được fit trong
fold-train; T13 refit sau khóa trên train+validation, không fit test. Scikit-learn
cung cấp các API pipeline và estimator được dùng trong triển khai [9], nhưng
thư viện không thay thế protocol chống rò rỉ của dự án.

## Nguồn dữ liệu

UCI Beijing Multi-Site Air-Quality Data là dữ liệu quan trắc nhiều trạm, không
phải bộ Beijing PM2.5 một trạm [1]. Dự án xác định nhãn bằng phép ghép chính
xác `(station, input_timestamp + 1h)`; giờ khuyết không được biến thành bước
liền kề. Đợt nồng độ cao hợp lệ được giữ lại; không loại ngoại lệ bằng IQR mặc
định.

## Bài giảng và phạm vi

Tên chủ đề 02–06 và Ensemble là mapping theo yêu cầu môn học; tài liệu gốc,
trang/slide, rubric và nội dung giảng viên **[CẦN BỔ SUNG]**. Không có trích
dẫn học thuật được thay thế bằng suy đoán về nội dung bài giảng.
