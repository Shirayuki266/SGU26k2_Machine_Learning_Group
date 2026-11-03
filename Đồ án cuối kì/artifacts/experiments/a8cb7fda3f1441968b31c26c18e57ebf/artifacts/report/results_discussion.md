# T13 — Kết quả và thảo luận RQ1–RQ3

Issue #32; parent run `a8cb7fda3f1441968b31c26c18e57ebf`. **Test đã được mở và đánh giá**; không coi test là chưa từng xem. Không tuning/chọn lại theo test.

## Protocol và khả năng truy vết

RF A đã chọn bằng validation MAE trong T12, reference `780ecb7fb59d48bea58d5e4a076f1f26`. Giữ RF A làm phương án triển khai bất kể thứ tự test. Ridge A alpha0.1 là comparator đã chọn CV T11, không thử B/C hoặc alpha mới trên test. Persistence dùng PM2.5(t).
Refit hai pipeline trên 307,344 mẫu primary train+validation (204,865+102,479); test primary 101,836, cùng IDs/order cho cả ba. Giữ target t+1, station, T08 train-only và hậu xử lý identity. Không đánh giá cohort operational/fallback; primary có PM2.5(t), baseline fallback=0.
Nhãn fit cuối 2016-02-29 23:00:00, origin test đầu 2016-02-29 23:00:00: label<=origin theo giả định số đo giờ t đã sẵn sàng. Pipeline/imputer/encoder/scaler chỉ fit train+validation, không fit test.
Config trước test: configs/final_evaluation.json và artifact parent/config. Mỗi model có config/metrics/predictions refit+test; ML có pipeline.joblib và summary. is_test=False trong logger là run thật, không phải fixture; partition đánh giá là test.

## RQ1 — Có cải thiện so với persistence?

| Model | Run ID | N | MAE (µg/m³) | RMSE (µg/m³) | R² | % MAE giảm persistence |
| --- | --- | --- | --- | --- | --- | --- |
| persistence | `0960fac6455f4380bd5b6d1407633cf8` | 101836 | 10.161809 | 19.436188 | 0.944975 | 0.0000% |
| ridge | `51975d2c66ff4263b83ace6962f3d3f7` | 101836 | 10.384443 | 18.939487 | 0.947752 | -2.1909% |
| random_forest | `24cd6d765f214d52aa26e5988380e2cd` | 101836 | 9.877150 | 18.569634 | 0.949772 | 2.8013% |

RF có mức giảm MAE 2.8013%; Ridge -2.1909%. Dấu âm nghĩa là kém persistence, không ép kết luận cải thiện. Đây là metric theo mẫu primary; chưa chứng minh hiệu quả với origin PM2.5 thiếu hoặc trạm chưa quan sát.

## Generalization gap và độ ổn định

generalization_gap.csv giữ train/validation lịch sử (model fit train-only), CV trong train và test final sau refit nhiều dữ liệu hơn. Refit_train_validation là **in-sample**, không gọi validation sau refit là held-out. Chênh lệch còn do phạm vi fit/thời gian/phân phối, không đủ để quy toàn bộ cho overfit/underfit.
| Model | Historical train MAE | Historical validation MAE | Final refit train+validation MAE (in-sample) | Final test MAE | Test − refit MAE |
| --- | --- | --- | --- | --- | --- |
| persistence | không ghi nhận | 9.736617 | 10.666052 | 10.161809 | -0.504243 |
| ridge | 11.286262 | 10.200529 | 10.777080 | 10.384443 | -0.392637 |
| random_forest | 9.837287 | 9.561488 | 9.549074 | 9.877150 | 0.328076 |

development_fold_metrics.csv và cv_summary.csv tính lại từ predictions fold Ridge alpha0.1 và PM2.5(t) của cùng train IDs; đây là phân tích mới có reference fold run IDs, không sửa log T11. Bảng gồm MAE/RMSE/R²/%giảm từng fold, pooled và mean/std (ddof0). RF chưa có CV trong ngân sách T11: không tạo fold/std giả.
| Model | CV pooled MAE | Fold mean MAE ± std | CV pooled RMSE |
| --- | --- | --- | --- |
| ridge | 10.405534 | 10.425491 ± 1.268015 | 18.080608 |
| persistence | 10.159566 | 10.180941 ± 1.357574 | 18.683536 |

Train chỉ khoảng2năm, ít chu kỳ mùa. Evaluation fold1 là06–08/2014, thiếu các mùa khác; train fold1 không mặc nhiên thiếu mọi mùa đó. Ba fold có mùa khác nhau, std không chứng minh ổn định mọi năm hoặc là khoảng tin cậy độc lập.

## RQ2 — Feature và diễn giải

Test T13 chỉ dùng A cho Ridge/RF để giữ recipe khóa. Đóng góp lag/rolling/selection được trả lời bằng bằng chứng phát triển T12: Ridge A/B/C validation MAE lần lượt 10.200529 / 9.968755 / 9.903377; không coi là kết quả test A/B/C.
Ridge có 65 hệ số encoded, lưu coefficient_model_space và hệ số trên đơn vị numeric gốc khi thích hợp; scaling, OHE và biến tương quan làm hạn chế so sánh độ lớn. Không xem hệ số là tác động nhân quả.
RF permutation dùng 2400 IDs, chọn tối đa200mẫu/trạm theo thời gian cách đều, seed42,3repeat,1luồng và 16 nhóm nguồn (tối đa 49 lượt predict gồm baseline). Lưu exact IDs. Calendar hour/month cùng sin/cos được xáo trộn theo nhóm, categorical xáo raw input giữ OHE cùng nguồn. Đây là chẩn đoán sau scoring, không chọn feature/model theo importance.
Các nhóm tăng MAE lớn nhất: PM2.5: 52.9972 µg/m³, PM10: 6.7182 µg/m³, WSPM: 1.4520 µg/m³, CO: 0.5619 µg/m³, DEWP: 0.5168 µg/m³. Tương quan/đặc trưng thay thế và mẫu con làm giảm hoặc phân tán importance; permutation cũng có thể tạo tổ hợp ít xuất hiện, không suy thành nhân quả.

## RQ3 — Sai ở đâu và vì sao?

grouped_metrics.csv có station/season/concentration/rapid_change/episode_id, N, MAE/RMSE, %giảm persistence và signed error. R² nhóm N<30 hoặc target constant để null/lý do; ngưỡng30 chỉ là quy tắc hiển thị, không đảm bảo độ tin cậy.
Mùa lấy target timestamp. Nhóm nồng độ [0,35),[35,75),[75,150),[150,+∞) chốt từ protocol phát triển, không học từ test/không phải chuẩn sức khỏe. Phân bố train trước test nằm trong preflight.json.
Thay đổi đột ngột: |y(t+1)−PM2.5(t)|≥38.000000 µg/m³, là q95 từ train. Sự kiện cao: target≥150 ít nhất3giờ liên tiếp cùng trạm; giờ khuyết tách. Primary có thể làm ngắn sự kiện khi origin/target thiếu. Có 960 sự kiện đủ quy tắc; không xóa đỉnh hợp lệ.
- RF khó nhất theo station: Wanshouxigong, N=8469, MAE=10.972908, RMSE=21.360863, mean(pred−actual)=-0.307984 µg/m³.
- RF khó nhất theo season: DJF, N=25374, MAE=13.283234, RMSE=26.471188, mean(pred−actual)=-0.181642 µg/m³.
- RF khó nhất theo concentration: [150.0, inf), N=14784, MAE=20.579533, RMSE=33.310068, mean(pred−actual)=-7.549712 µg/m³.
- RF khó nhất theo rapid_change: True, N=4377, MAE=61.922859, RMSE=73.643273, mean(pred−actual)=6.153911 µg/m³.
Sự kiện vẽ có đỉnh quan sát cao nhất: Nongzhanguan__20170127T21, peak=835.000 µg/m³; tại đỉnh actual=835.000, persistence=640.000, Ridge=555.560, RF=590.613. Chọn hình để mô tả lỗi, không chọn lại cấu hình.

Persistence dùng mức hiện tại nên hợp lý khi nồng độ ổn định, nhưng hụt tăng/giảm đột ngột. Signed error và hình đỉnh cho thấy mức hụt/overshoot thực tế của model. Giả thuyết: A chỉ có số đo hiện tại/lịch, Ridge tuyến tính và RF cây hữu hạn có thể làm trơn đỉnh hoặc thiếu thông tin diễn biến; cần nghiên cứu bằng dữ liệu phát triển ở công việc sau. Đây không phải chứng minh nguyên nhân vật lý, không dùng test để thử sửa tiếp.

## Hình, tài nguyên, giới hạn và bài giảng

Chỉ mục figure_index.csv ghi source/run/scope; PNG gốc tại reports/figures/final_evaluation. actual–predicted và histogram giữ tất cả test primary; timeline station chốt trước test, giờ khuyết để NaN; hình đợt cao là chẩn đoán định trước. Model weights/registered SHA trong run directories; hướng dẫn khôi phục artifact ở docs/final_evaluation.md.
Bài giảng áp dụng: chủ đề05 (đánh giá/overfit/underfit),06 (Ridge),Ensemble (RF),04 khi diễn giải selection. File/trang và rubric chi tiết [CẦN BỔ SUNG]; không bịa nội dung bài giảng. Giữ temporal/train-only/no-IQR theo course_alignment.md.
Codex hỗ trợ code/kiểm/soạn nhận xét từ artifact; người nhận hoanglecodingmachine cần đọc/hiểu/review trước merge. Không khẳng định phần review đã hoàn thành. Không có RF temporal CV mới, không có test B/C, không đánh giá unseen stations/cohort fallback, không suy nhân quả. T14–T16 chưa thực hiện.
