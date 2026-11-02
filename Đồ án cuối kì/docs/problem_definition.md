# T02 — Đặc tả bài toán

Đề tài: **Dự báo nồng độ PM2.5 trước 1 giờ tại các trạm quan trắc ở Bắc Kinh bằng
học máy**. Đây là đặc tả đã cập nhật theo phạm vi người dùng chốt ngày
02/11/2026, không phải báo cáo kết quả mô hình.

## 1. Mục tiêu, input và output

Với trạm `s` đã xuất hiện trong dữ liệu và giờ quan trắc `t`, sau khi nhận số đo
giờ t, dự báo một giá trị liên tục `y(s,t) = PM2.5(s,t+1 giờ)`, đơn vị **µg/m³**.
Loại bài toán là **hồi quy có giám sát**, horizon đúng một giờ. Chưa nghiên cứu
khả năng tổng quát hóa tới trạm mới, nhiều bước dự báo hoặc nhân quả ô nhiễm.

Input chỉ gồm thông tin đã sẵn sàng đến t: số đo hiện tại, lịch sử của cùng
trạm, mã trạm và lịch biết trước. `PM2.5(t)` được phép dùng. Giả định các trường
giờ t đã được nhận khi phát hành dự báo; nếu triển khai có độ trễ truyền số
liệu phải kiểm tra lại giả định, không mặc định mọi số đo luôn có sẵn.

Khóa mẫu là `(station, input_timestamp)`; giữ thêm
`target_timestamp = input_timestamp + 1 giờ`. Target ghép đúng station và đúng
timestamp, không coi dòng kế tiếp là giờ tiếp theo khi có khoảng trống. Không
impute target; ghi số mẫu bị loại khi thiếu hàng/giá trị t+1. Dự báo cuốn chiếu
từng giờ trên các trạm đã quan sát: sau khi thực tế tại t+1 được quan sát, có
thể dùng nó làm input của lần dự báo sau, không dùng trước khi nó sẵn sàng.

## 2. Dữ liệu và biến

Nguồn: UCI 501 Beijing Multi-Site Air Quality. Đơn vị PM2.5 lấy từ
[từ điển dữ liệu T03](data_dictionary.md); provenance/checksum hiện có tại
`reports/data_manifest.json`. T04 đã ghép dữ liệu chưa impute, giữ raw và các
giá trị cực đoan đã audit. Xem [chính sách chất lượng](data_quality_policy.md).
Không tải/audit lại hoặc dùng số thống kê toàn dataset để fit tiền xử lý.

| Thành phần | Nội dung và ràng buộc |
| --- | --- |
| Quan trắc tại t | PM2.5, PM10, SO2, NO2, CO, O3, TEMP, PRES, DEWP, RAIN, WSPM; wd là categorical |
| Trạm/lịch | station là categorical; hour, month, day_of_week từ input timestamp |
| Lịch sử | Lag/rolling PM2.5 theo timestamp, cùng trạm, chỉ tới t; bộ B trong kế hoạch |
| Output | PM2.5 tại đúng t+1 cùng trạm, µg/m³; không phân lớp nồng độ làm mục tiêu chính |
| Loại khỏi feature | No, source_file, source_row, target/giá trị tương lai và target_timestamp dùng làm khóa/split |

`FEATURE_COLUMNS` của loader T04 là danh sách cột được phép xem xét, không phải
ma trận feature được chọn tự động. T07 chọn tường minh theo config và ghi feature
dictionary; không đưa tất cả cột hoặc provenance vào mô hình. Encoding lịch chu
kỳ nếu thử phải được ghi là thay đổi có chủ đích, không âm thầm thêm vào bộ A.

## 3. Câu hỏi nghiên cứu đã chốt

| RQ | Câu hỏi | Minh chứng dự kiến |
| --- | --- | --- |
| RQ1 | Ridge/Random Forest cải thiện MAE so với persistence không? | T09–T11: cùng validation sample IDs, chênh lệch MAE, thời gian và độ bao phủ |
| RQ2 | Thêm lag/rolling A→B và chọn đặc trưng B→C ảnh hưởng thế nào? | T12: ablation có kiểm soát, selector fit trong fold, metric/chi phí và nhận xét kể cả không cải thiện |
| RQ3 | Sai số thay đổi theo trạm, mùa, khoảng nồng độ như thế nào? | Validation trong phát triển; T13 trên test sau khóa/refit, có N từng nhóm và giới hạn |

Chưa có câu trả lời thực nghiệm cho các RQ. Không khẳng định model hoặc feature
selection tốt hơn khi chưa có số liệu thật. Chênh lệch quan sát từ một run
không tự chứng minh ý nghĩa thống kê hoặc quan hệ nhân quả.

## 4. Phương pháp và tiêu chí thành công

Persistence: `prediction(s,t+1) = PM2.5(s,t)` khi có số đo; T09 phải có fallback
nhân quả và thống kê tỷ lệ fallback theo [kế hoạch](experiment_plan.md).
Hai mô hình học máy là Ridge và Random Forest, mô hình chung cho các trạm.
MAE là metric chính; RMSE và R² bổ sung. MAE/RMSE có đơn vị µg/m³, R² không
có đơn vị, có thể âm hoặc không xác định. Mục tiêu là kiểm tra RQ bằng thực
nghiệm tái lập, không đặt sẵn ngưỡng metric hoặc cam kết ML thắng baseline.

Phải giữ timestamp/source convention, split, sample IDs và thời điểm thông tin
sẵn sàng nhất quán. Mọi model, tiền xử lý và selector chỉ học trên partition
được phép của run/fold. Test bị khóa trong phát triển và giữa kỳ. Sau khi khóa
phương án, **T13 refit pipeline trên train+validation rồi đánh giá test**, theo
quyết định mới nhất của người dùng; không dùng test để chọn lại mô hình.

## 5. Tài liệu triển khai và giới hạn

[experiment_plan.md](experiment_plan.md) chốt A/B/C, split/CV, tuning, test gate,
metrics và log; [project_plan.md](project_plan.md) mapping task vào CRISP-DM;
[midterm_plan.md](midterm_plan.md) là checklist MK01/MK02. Giá trị cấu hình máy
đọc ở `configs/default.json`. T05 đã triển khai target/split theo
[temporal_samples.md](temporal_samples.md); feature engineering và training
vẫn là phần việc sau, chưa được triển khai trong T05.

Chưa có rubric chính thức hoặc thông tin thành viên/đóng góp được xác minh.
Nguồn và AI disclosure phải được ghi đúng tài liệu/artifact thật. Codex hỗ trợ
cập nhật đặc tả, không tạo dữ liệu, metric hoặc lịch sử mô hình giả.
