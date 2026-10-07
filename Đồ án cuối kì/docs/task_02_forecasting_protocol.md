# Task 02 — Đặc tả bài toán và kế hoạch thực nghiệm

**Đề tài:** Dự báo nồng độ PM2.5 trước 1 giờ tại các trạm quan trắc ở Bắc Kinh.

**Trạng thái:** Đây là đặc tả và kế hoạch trước thực nghiệm. Chưa tải/kiểm tra dữ liệu trong Task 02, chưa huấn luyện và chưa có kết quả, metric hay biểu đồ thực nghiệm. Các cấu hình dưới đây là đề xuất để triển khai ở task tiếp theo.

## 1. Bài toán và dữ liệu

Nguồn do nhóm lựa chọn: [Beijing Multi-Site Air Quality, UCI dataset 501](https://archive.ics.uci.edu/dataset/501/beijing+multi-site+air+quality+data). Khi tải dữ liệu, cần lưu thông tin nguồn, ngày tải, phiên bản/checksum và trích dẫn theo metadata chính thức; kiểm tra schema, đơn vị, phạm vi thời gian, trạm và dữ liệu thiếu trước khi chạy. Không coi các thông tin chưa kiểm tra là kết quả EDA.

Với trạm `s` và thời điểm quan trắc theo giờ `t`:

- Input `X(s,t)` chỉ chứa thông tin đã quan sát tại cùng trạm đến và bao gồm giờ `t`, cùng thông tin lịch và mã trạm.
- Target `y(s,t) = PM2.5(s,t + 1 giờ)`, đơn vị dự kiến µg/m³, cần xác nhận từ nguồn dữ liệu.
- Dự báo được phát hành **sau khi có số đo giờ t**. Vì vậy `PM2.5(s,t)` được phép làm feature.
- `PM2.5(s,t+1)` và mọi số đo có timestamp sau `t` bị cấm làm feature, kể cả khi đã có sẵn trong file dữ liệu ngoại tuyến.

Đây là bài toán hồi quy có horizon đúng 1 giờ, không phải dự báo dòng tiếp theo bất kể khoảng cách thời gian. Mỗi mẫu có khóa `(station, input_timestamp)` và lưu riêng `target_timestamp = input_timestamp + 1 giờ`. Target được ghép bằng `(station, target_timestamp)`; không dùng `shift(-1)` trên các dòng chưa kiểm tra tính liên tục theo giờ. Không lấy target từ trạm khác. Nếu thiếu bản ghi hoặc giá trị target tại đúng giờ cần dự báo, loại mẫu khỏi đánh giá và ghi số lượng bị loại; không nội suy target.

### Hợp đồng feature và xử lý thiếu

| Nhóm | Đề xuất input | Ràng buộc |
| --- | --- | --- |
| Quan trắc hiện tại | PM2.5, các chất ô nhiễm và khí tượng có trong schema, tại giờ t | Chỉ dùng trường đã quan sát khi phát hành dự báo; xác nhận danh sách cột khi đọc dữ liệu |
| Lịch và trạm | Giờ, tháng, ngày trong tuần tại t; mã trạm | Mã trạm là biến phân loại, không gán thứ tự số có ý nghĩa |
| Lịch sử PM2.5 | Lag tại t−1, t−2, t−3, t−6, t−12, t−24 giờ | Tra cứu đúng timestamp, cùng trạm; không coi dòng trước là giờ trước nếu có khoảng trống |
| Rolling PM2.5 | Trung bình và độ lệch chuẩn trong 3, 6, 12, 24 giờ | Cửa sổ w gồm t−(w−1) giờ đến t, được phép chứa PM2.5(t); tuyệt đối không centered rolling |

Reindex theo lưới giờ riêng từng trạm trước khi tạo lag/rolling hoặc dùng phép ghép timestamp tương đương. Rolling yêu cầu đủ số giờ quan trắc trong cửa sổ; nếu không đủ, để missing rồi xử lý bằng pipeline. Không nối lịch sử giữa các trạm.

Các mẫu đánh giá chính phải có PM2.5 tại t và target tại t+1 quan sát được để persistence có dự báo hợp lệ. Các mô hình và ablation được so sánh trên **cùng tập mẫu**; không loại thêm mẫu chỉ vì lag/rolling thiếu. Báo cáo số mẫu và tỷ lệ bao phủ theo tập/trạm, cùng ảnh hưởng của việc loại mẫu thiếu PM2.5(t) hoặc target. Demo cần báo thiếu đầu vào nếu không có PM2.5(t).

Đề xuất: impute biến số bằng median train, biến phân loại bằng giá trị phổ biến train hoặc mã thiếu được định nghĩa trước; xử lý category chưa thấy bằng encoder phù hợp. Ridge chuẩn hóa biến số và one-hot biến phân loại; Random Forest dùng imputation và mã hóa phân loại, không bắt buộc chuẩn hóa. Mọi imputer, scaler, encoder và thống kê phụ thuộc dữ liệu phải **fit trên train của từng lần thực nghiệm**, rồi chỉ transform validation/test. Không backward-fill, không nội suy sử dụng điểm tương lai, không fit tiền xử lý trên toàn bộ dữ liệu.

## 2. Ba câu hỏi nghiên cứu

1. **So với persistence:** Ridge và Random Forest có giảm MAE dự báo trước 1 giờ so với việc giữ nguyên PM2.5(t) không? So sánh trên cùng mẫu; ghi MAE, chênh lệch MAE và tỷ lệ cải thiện so với persistence khi MAE persistence khác 0.
2. **Giá trị của lịch sử PM2.5:** Thêm lag/rolling có cải thiện so với chỉ dùng quan trắc hiện tại, lịch và trạm không? Giữ PM2.5(t) trong cả hai bộ feature để đo giá trị tăng thêm của lịch sử trước t.
3. **Sai số theo trạm/mùa/nồng độ:** Mô hình sai nhiều ở trạm, mùa hoặc mức PM2.5 nào? Phân tích phân nhóm của cấu hình đã khóa, báo số mẫu từng nhóm và không dùng phân tích test để đổi mô hình.

Đây là các câu hỏi cần trả lời bằng thực nghiệm; chưa kết luận mô hình nào tốt hơn hoặc lịch sử có ích.

## 3. Chia dữ liệu và dự báo cuốn chiếu

Chia theo **target timestamp**, với các mốc dùng chung cho tất cả trạm; không random split:

| Tập | Điều kiện target timestamp |
| --- | --- |
| Train | Trước `2015-03-01 00:00:00` |
| Validation | Từ `2015-03-01 00:00:00` đến trước `2016-03-01 00:00:00` |
| Test | Từ `2016-03-01 00:00:00` đến hết dữ liệu hợp lệ |

Dùng một quy ước timestamp nhất quán với giờ quan trắc gốc; không tự chuyển mốc sang UTC. Xác nhận cách biểu diễn thời gian khi nhập dữ liệu. Kiểm tra từng trạm có mẫu trong các tập, khóa duy nhất và khoảng thời gian hợp lệ. Không tự đổi mốc sau khi nhìn kết quả test.

Ví dụ: input `2015-02-28 23:00` có target `2015-03-01 00:00`, nên thuộc validation dù input nằm trước mốc chia. Input `2016-02-29 23:00` có target `2016-03-01 00:00`, nên thuộc test.

Đây là **đánh giá dự báo cuốn chiếu trước 1 giờ**: tại mỗi lần dự báo, được dùng tất cả số đo đã quan sát tới t, kể cả các giờ trước trong giai đoạn validation/test. Sau khi thực tế tại t+1 đã được quan sát, số đo đó được phép làm input cho lần dự báo tiếp theo. Lịch sử có thể đi qua ranh giới train/validation/test; không cắt mất lịch sử hợp lệ ở đầu mỗi tập.

Mô hình và bộ tiền xử lý vẫn được giữ cố định trong mỗi lần đánh giá. Việc dùng số đo mới đã quan sát để tạo input không phải fit lại mô hình, tuning bằng test hay sử dụng tương lai. Không dự báo toàn bộ test tại một thời điểm đầu kỳ, không thay số đo thực tế bằng dự báo trước đó, và không tự động retrain trên validation/test trong protocol này.

## 4. Mô hình và ma trận thực nghiệm

Huấn luyện một mô hình chung cho các trạm, với mã trạm là feature. Giữ cùng split, tiêu chí mẫu hợp lệ và target cho mọi mô hình.

| Mô hình | Định nghĩa/cấu hình đề xuất |
| --- | --- |
| Persistence | `prediction(s,t+1) = PM2.5(s,t)`; không huấn luyện, không tuning |
| Ridge | Linear regression có L2; `alpha ∈ {0.1, 1, 10, 100}` |
| Random Forest | `n_estimators=300`; `max_depth ∈ {None, 15}`; `min_samples_leaf ∈ {1, 5}`; `max_features ∈ {1.0, 0.7}`; `random_state=42` |

Hai bộ feature cho từng mô hình học máy:

- **F0 — Hiện tại:** quan trắc tại t (gồm PM2.5(t)), lịch và trạm.
- **F1 — Có lịch sử:** F0 cộng lag và rolling PM2.5 đã định nghĩa ở mục 1.

Tổng dự kiến: 4 cấu hình Ridge và 8 cấu hình Random Forest cho mỗi bộ feature, cộng persistence. Tuning riêng F0/F1 với cùng ngân sách trong từng họ mô hình để so sánh giá trị lịch sử công bằng. Các thay đổi danh sách feature hoặc ngân sách chỉ được quyết định trên train/validation, phải được ghi lại trước khi mở đánh giá test.

## 5. Metric và quy trình chọn mô hình

Với `e_i = prediction_i − y_i` và N mẫu hợp lệ:

- **MAE chính:** `sum(abs(e_i))/N`, đơn vị của PM2.5; dùng để chọn cấu hình.
- **RMSE bổ sung:** `sqrt(sum(e_i²)/N)`, cùng đơn vị; phản ánh sai số lớn.
- **R² bổ sung:** `1 − sum(e_i²)/sum((y_i − mean(y))²)`; có thể âm. Nếu nhóm có dưới 2 mẫu hoặc target không có phương sai, ghi R² là không xác định và nêu lý do, không thay bằng 0/1.

MAE tổng hợp trên tất cả mẫu là tiêu chí chính. Báo thêm MAE từng trạm và trung bình MAE giữa các trạm để thấy ảnh hưởng của số mẫu không đều; không thay tiêu chí chọn mô hình sau khi xem test.

Quy trình:

1. Kiểm tra dữ liệu và các điều kiện chống rò rỉ; tạo mẫu, feature và split theo đặc tả.
2. Với mỗi cấu hình F0/F1, fit pipeline và mô hình **chỉ trên train**, dự báo validation theo cơ chế cuốn chiếu. Persistence dùng cùng mẫu.
3. Chọn cấu hình MAE validation thấp nhất trong mỗi cặp mô hình/bộ feature; chọn mô hình học máy chính theo MAE validation thấp nhất trong các cấu hình đó. Nếu MAE bằng nhau, ưu tiên F0 rồi Ridge; trong cùng họ chọn cấu hình ít phức tạp hơn (Ridge alpha lớn hơn; forest độ sâu hữu hạn nhỏ hơn, leaf lớn hơn, max_features nhỏ hơn).
4. Trước đánh giá test, khóa danh sách feature, split, tiêu chí lọc mẫu, tiền xử lý, hyperparameter, seed, metric, nhóm phân tích và quy tắc xử lý output. Lưu cấu hình, phiên bản mã và log validation. Protocol này giữ mô hình fit trên train, **không refit trên train+validation**.
5. Chạy một đợt đánh giá test cho persistence và các cấu hình F0/F1 đã chọn trên validation; mô hình chính vẫn là mô hình đã chọn trước bước này. Báo cả kết quả bất lợi, không chọn lại theo test.
6. Phân tích lỗi và viết kết luận sau khi có output thật. Nếu phát hiện lỗi triển khai phải sửa và chạy lại, ghi rõ lỗi, phạm vi ảnh hưởng và lần chạy; không âm thầm tuning dựa trên test.

Đề xuất không clip dự báo âm trong thực nghiệm chính; nếu nghiên cứu clipping sau này, phải quy định và lựa chọn bằng validation trước khi đánh giá test.

## 6. Kế hoạch phân tích sai số

Phân nhóm theo trạm và **thời điểm target**:

- Mùa khí tượng theo tháng: xuân 3–5, hè 6–8, thu 9–11, đông 12–2.
- Nồng độ PM2.5 thực tế của target: `[0, 35)`, `[35, 75)`, `[75, 150)`, `[150, +∞)` µg/m³. Đây là các khoảng phân tích được đề xuất trước thực nghiệm, không phải tuyên bố về ngưỡng sức khỏe hay tiêu chuẩn pháp lý. Giá trị âm cần được kiểm tra theo quy tắc chất lượng dữ liệu trước khi đánh giá.

Target chỉ dùng để chấm điểm và phân nhóm phân tích sau dự báo, không làm feature. Báo N, MAE, RMSE, R² hợp lệ cho từng nhóm; nhóm rỗng ghi không có mẫu. Các bảng/biểu đồ dự kiến gồm so sánh mô hình, ablation F0/F1, sai số theo trạm/mùa/nồng độ và chuỗi thực tế–dự báo ở khoảng thời gian được quy định trước khi xem test. Không tạo bảng số hoặc biểu đồ kết quả ở Task 02.

## 7. Tái lập và kiểm tra dự kiến

- Logic nhập dữ liệu, tạo mẫu/feature, fit và đánh giá nằm trong `src/beijing_air/`; notebook gọi lại logic, không chứa toàn bộ pipeline.
- Cấu hình hóa horizon, mốc chia, feature, hyperparameter, đường dẫn, `seed=42` và mode. Lưu cấu hình thực dùng, phiên bản dependency, checksum dữ liệu, model, dự báo với station/input_timestamp/target_timestamp và log loại mẫu.
- **Smoke:** chạy nhanh trên tập con theo thời gian còn đủ các ranh giới cần kiểm tra, với ngân sách nhỏ; chỉ xác nhận pipeline. Không coi metric smoke là kết quả chính thức hoặc dùng để chọn mô hình.
- **Full:** dùng toàn bộ mẫu hợp lệ, split và ngân sách đã khóa; output phân biệt rõ với smoke.
- Kiểm thử cần xác nhận target đúng cùng trạm và đúng +1 giờ, khoảng trống không biến thành lag sai, rolling không dùng tương lai, mốc chia dựa trên target, cùng mẫu đánh giá giữa mô hình, và bộ tiền xử lý không fit trên validation/test. Kiểm tra bất biến: sửa số đo sau t không được làm thay đổi feature tại t.

Task 02 chỉ tạo tài liệu, chưa triển khai các kiểm thử hay lệnh thực nghiệm này.

## 8. Sản phẩm nộp và mapping yêu cầu môn học

Mapping dưới đây dựa trên phạm vi môn học do nhóm cung cấp trong phiên làm việc. Chưa có rubric chính thức trong repo; cần đối chiếu rubric khi có, không khẳng định đã đáp ứng tiêu chí chấm điểm chưa được cung cấp.

| Sản phẩm dự kiến | Nội dung cần có | Yêu cầu được thể hiện |
| --- | --- | --- |
| Đặc tả và kế hoạch (`docs/`) | Target, input hợp lệ, câu hỏi nghiên cứu, split, lựa chọn mô hình và chống rò rỉ | Xác định bài toán hồi quy và thiết kế thực nghiệm |
| Mã nguồn, cấu hình, kiểm thử | Persistence, Ridge, Random Forest; pipeline train-only; seed; smoke/full | Cài đặt phương pháp học máy, tính đúng đắn và tái lập |
| Notebook tái lập (`notebooks/`) | EDA thật, gọi pipeline, so sánh và phân tích lỗi từ output thật | Khám phá dữ liệu, thực nghiệm và giải thích kết quả |
| Demo Streamlit (`app/`) | Chọn trạm/thời điểm hoặc nhập thông tin quan sát; dự báo +1 giờ; hiển thị persistence, mô hình và thiếu đầu vào | Ứng dụng mô hình vào bài toán; không giả lập dữ liệu thành số đo thật |
| README | Nguồn dữ liệu, cài đặt, lệnh smoke/full, chạy notebook/demo, tái lập và giới hạn | Hướng dẫn sử dụng và bàn giao |
| Báo cáo 5 chương | Cấu trúc bên dưới; số liệu/biểu đồ chỉ sau thực nghiệm | Trình bày bài toán, cơ sở, phương pháp, thực nghiệm và kết luận |
| Slide | Bài toán, dữ liệu, protocol, mô hình, kết quả thật, demo và giới hạn | Thuyết trình và bảo vệ lựa chọn kỹ thuật |
| Artifacts/log thực nghiệm | Cấu hình đã khóa, model, dự báo, metric, log và hình từ full run | Bằng chứng kiểm chứng và tái lập; không bắt buộc commit file nhị phân |

Đề xuất báo cáo 5 chương:

1. **Giới thiệu:** động cơ, phạm vi dự báo trước 1 giờ, ba câu hỏi nghiên cứu và sản phẩm.
2. **Cơ sở lý thuyết và dữ liệu:** hồi quy, persistence/Ridge/Random Forest, metric, nguồn UCI và EDA đã kiểm chứng.
3. **Phương pháp:** target, feature, xử lý thiếu, chống rò rỉ, split, ablation và lựa chọn bằng validation.
4. **Thực nghiệm và thảo luận:** môi trường/cấu hình, kết quả full thật, so sánh persistence, giá trị lịch sử và lỗi phân nhóm.
5. **Kết luận và hướng phát triển:** trả lời câu hỏi dựa trên kết quả đã chạy, giới hạn và đề xuất tiếp theo.

README, báo cáo và slide phải ghi nguồn dữ liệu, tài liệu thực sự sử dụng và sự hỗ trợ của AI. Không thêm tài liệu tham khảo, số liệu hoặc kết luận thực nghiệm giả.

## 9. Ghi nhận Task 02

Codex hỗ trợ soạn đặc tả và kế hoạch thực nghiệm dựa trên yêu cầu của nhóm. Nhóm cần rà soát, đối chiếu schema dữ liệu và rubric môn học trước triển khai. Task này không xác nhận hiệu quả dự báo của bất kỳ mô hình nào.

Commit đề xuất: `docs: define forecasting task and evaluation protocol`.
