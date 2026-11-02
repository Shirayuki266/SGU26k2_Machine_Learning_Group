# T02 — Kế hoạch thực nghiệm theo CRISP-DM

Phạm vi đã chốt ngày 02/11/2026. Đây là thiết kế cho T05 trở đi, **chưa chạy**
baseline, training, tuning, feature selection hoặc đánh giá test. Đi cùng
[đặc tả bài toán](problem_definition.md) và `configs/default.json`.

## 1. Vòng thực nghiệm và task quản lý

Task là đơn vị bàn giao Issue/branch/PR; run là một lần thực thi có config,
run_id và artifact riêng. Một task có thể chứa nhiều run, kể cả thất bại;
một run không mặc định là một commit hay một đóng góp học thuật. CRISP-DM có
vòng lặp: hiểu vấn đề/dữ liệu → giả thuyết → chuẩn bị → chạy → đánh giá → nhận
xét → giữ/sửa/bỏ. Không cố làm sai để tạo lịch sử cải tiến và không tự chạy
task tiếp theo chỉ vì đã mở PR.

Trước run ghi RQ/giả thuyết, lý do, thay đổi so với reference_run_id, mẫu/split,
config, budget và seed. Sau run lưu kết quả thật, so sánh với tham chiếu, nhận
xét cả trường hợp kém hơn/chưa đủ bằng chứng, chi phí và quyết định tiếp theo.
Tuning/ablation chỉ chạy khi task tương ứng được giao. Khi task thực nghiệm
không chỉ định ngân sách: smoke rồi tối đa một cấu hình full ban đầu nếu đủ tài
nguyên; ngân sách tuning đầy đủ phải được ghi riêng trước khi chạy.

## 2. Bộ đặc trưng A/B/C và preprocessing

| Bộ | Hợp đồng | So sánh chính |
| --- | --- | --- |
| A, tên cũ F0 | Số đo giờ t gồm PM2.5(t), wd, station; lịch t+1 biết trước và sin/cos giờ/tháng (20 cột, T07) | T10 Ridge/RF ban đầu so persistence |
| B, tên cũ F1 | A + PM2.5 lag 1/3/6/12/24 giờ và rolling mean/std 3/6/12/24 giờ (33 cột, T07) | T12 A→B đo giá trị lịch sử |
| C | Tập con được chọn từ B; lưu phương pháp, số/tên feature thật | T12 B→C đo giá trị feature selection |

Danh sách cột chính xác ở config. Không dùng `No`, provenance hoặc biến tương
lai; chọn tường minh và xuất feature dictionary. Lag tra đúng timestamp từng
trạm, không dùng dòng trước thay giờ trước. Rolling w gồm t−(w−1) giờ tới t,
có thể chứa PM2.5(t), dùng đủ w giờ có quan sát; std theo quy ước mẫu `ddof=1`.
Thiếu giờ/giá trị làm feature thiếu, không backfill, centered rolling hoặc nội
suy từ tương lai. Kiểm tra sửa quan sát sau t không đổi feature tại t.

T07 cập nhật theo yêu cầu người dùng: bỏ lag 2h và chuyển lịch origin sang
forecast timestamp t+1. Sin/cos giờ/tháng dựa trên chu kỳ train T06, tính bằng
công thức cố định không fit. [Registry/dictionary](feature_dictionary.md) là
hợp đồng thực thi; chưa chạy ablation hoặc khẳng định các cột này hiệu quả hơn.
Lịch sử lấy trên timeline quan sát T04 trước khi chọn IDs T05, không nén các
origin bị loại do thiếu target thành các giờ liên tiếp.

T08 dùng Pipeline/ColumnTransformer: median train cho số, most_frequent hoặc
mã thiếu định trước cho categorical, encoder xử lý category chưa thấy;
Ridge scale số và one-hot categorical, RF impute/encode, không bắt buộc scale.
Fit imputer/encoder/scaler **trong train của từng run/fold**; save/load phải
giữ đúng thứ tự/schema feature. Không xóa nồng độ cao bằng IQR hoặc impute target.

C có thể dùng mutual information hoặc SelectFromModel; T12 chốt phương pháp
và ngân sách trên train/CV/validation trước test. Hiện `selection_method` và
`selected_features` là null vì chưa chạy. Selector phải nằm trong pipeline
được clone/fit lại từng fold, không fit B trên toàn dataset rồi chọn C.

## 3. Mẫu so sánh và fallback persistence

Cohort chính giữ quyết định cũ: PM2.5(t) và target t+1 đều quan sát được, khóa
duy nhất, mọi phương án dùng cùng sample IDs. Không loại thêm mẫu chỉ vì
lag/rolling thiếu. Ghi số mẫu đầu vào, mẫu loại và coverage theo split/trạm;
target thiếu luôn loại. Dự báo lưu station, input_timestamp, target_timestamp,
y_true, y_pred, split, run_id và cờ fallback nếu có.

T09 bổ sung cohort vận hành mở rộng gồm mọi mẫu có target quan sát được, kể
cả khi PM2.5(t) thiếu. Khi thiếu PM2.5(t), fallback theo
thứ tự **giá trị PM2.5 đã quan sát gần nhất cùng trạm đến t → median trạm của
training partition → median toàn training partition → không có dự báo**.
Không dùng giá trị tương lai; trong phát triển không tính median từ
validation/test. Trong CV tính median trên fold fit; khi T13 được phép refit,
training partition là train+validation, vẫn không học từ test.
Ghi nguồn fallback, tuổi số đo gần nhất, số/tỷ lệ fallback trên tập có target,
số không dự báo và coverage. Cohort chính và cohort có fallback báo riêng;
không trộn hai mẫu số để tuyên bố cải thiện. Khi so sánh ML trên cohort vận
hành cũng phải dùng cùng IDs và chính sách coverage. T09 khóa cách xử lý thiếu
trước khi chấm, không thay đổi sau khi nhìn metric.

## 4. Temporal split và dự báo cuốn chiếu

Chia theo **target_timestamp**, các trạm dùng chung ranh giới:

| Tập | Điều kiện |
| --- | --- |
| Train | target_timestamp < 2015-03-01T00:00:00 |
| Validation | 2015-03-01T00:00:00 ≤ target_timestamp < 2016-03-01T00:00:00 |
| Test, khóa | target_timestamp ≥ 2016-03-01T00:00:00 tới hết mẫu hợp lệ |

Timestamp theo giờ gốc, timezone-naive (`source_local_naive`), không tự gắn UTC
hoặc đổi mốc; cần kiểm tra nguồn nếu vận hành đòi chuyển timezone. Input
2015-02-28 23:00 có target 2015-03-01 00:00 thuộc validation; input
2016-02-29 23:00 có target 2016-03-01 00:00 thuộc test. Đây là ví dụ mốc thời
gian, không phải mẫu đã lấy từ dataset trong T02.

Lịch sử có thể đi qua ranh giới split khi nó đã quan sát tới origin t. Mô hình
và pipeline giữ cố định trong mỗi đợt đánh giá; nhận quan sát mới để tạo feature
không phải retrain. Không dự báo toàn bộ test tại origin đầu, không thay quan
sát bằng dự báo đệ quy trong bài toán một bước này.

## 5. Temporal CV chỉ trong train

T11 dùng expanding-window, chia theo **unique target timestamps**, áp cùng
ranh giới mọi trạm; không random K-fold hoặc chia theo thứ tự từng dòng trạm.
Ba cửa sổ evaluation `[start,end)` đã chốt trong config:

| Fold | Evaluation start | Evaluation end (exclusive) |
| --- | --- | --- |
| 1 | 2014-06-01T00:00:00 | 2014-09-01T00:00:00 |
| 2 | 2014-09-01T00:00:00 | 2014-12-01T00:00:00 |
| 3 | 2014-12-01T00:00:00 | 2015-03-01T00:00:00 |

Fit dùng toàn bộ quá khứ hợp lệ trước cửa sổ evaluation, mở rộng qua các fold.
Guard nghiêm ngặt: `max(fit.target_timestamp) < min(eval.input_timestamp)` để
label fit đã quan sát trước origin đánh giá đầu tiên. Với horizon 1 giờ,
purge target đúng `evaluation_start−1 giờ` nếu nó trùng origin đầu; ghi số mẫu
bị purge. Đây là điều kiện fit trong CV, không thay đổi mốc train/validation/test.
Tính origin thật từ mẫu hợp lệ, không mặc định hàng đầu mỗi trạm đều có dữ liệu.

Mỗi fold fit lại toàn pipeline/selector. Baseline và các ứng viên dùng cùng
evaluation IDs; lưu metric từng fold, N và tổng hợp MAE/RMSE từ tổng lỗi cùng
tổng N, không trung bình R² mù. Kiểm tra fold không rỗng, timestamp không chồng
lấn, đủ thời gian/lịch sử và phạm vi trạm; chưa xác minh các điều kiện này trên
dữ liệu thật trong T02. Thiếu dữ liệu thì fail/report, không tự đổi ranh giới
để lấy kết quả tốt hơn. Validation ngoài và test không tham gia CV.

## 6. Mô hình, ngân sách và lựa chọn

| Giai đoạn | Cấu hình/ngân sách thiết kế |
| --- | --- |
| T09 | Persistence không fit estimator; fallback train-only như mục 3 |
| T10 | Bộ A; Ridge alpha=1.0; RF n_estimators=300, max_depth=null, min_samples_leaf=1, max_features=1.0, random_state=42, n_jobs=1 như config; mỗi họ một cấu hình, không duyệt grid |
| T11 | Tinh chỉnh ít nhất một họ được giao; giữ grid cũ: Ridge alpha {0.1,1,10,100}; RF n_estimators=300, max_depth {null,15}, min_samples_leaf {1,5}, max_features {1.0,0.7} |
| T12 | A/B có kiểm soát; chọn C từ B. Nếu tune riêng A/B/C để so sánh phương án tối ưu, phải giữ cùng ngân sách trong từng họ và ghi rõ khác với ablation chỉ đổi feature |

Seed mặc định 42; RF random_state=42, n_jobs ban đầu 1 để giới hạn tài nguyên;
task thực thi chốt RAM/thời gian/n_jobs. Grid cũ là **không gian ứng viên**, không
phải quyền tự chạy 4+8 cấu hình hoặc kết quả đã có. Nếu chạy cả hai grid trên
3 folds: 12+24 candidate-fold runs cho một bộ feature, chưa kể refit; chạy một
họ hoặc rút ngân sách phải khai báo trước. Không tự nhân lên A/B/C vô hạn.

Tuning chọn ứng viên bằng MAE tổng hợp CV trong train; fit ứng viên đã chọn
trên train rồi chấm validation ngoài. Validation chọn giữa các phương án và
giả thuyết phát triển, ghi số lần xem kết quả để thấy rủi ro overfit validation.
So sánh cùng mẫu: `delta_MAE = MAE_model − MAE_reference`; tỷ lệ giảm sai số
chỉ tính khi MAE tham chiếu khác 0. Không bắt buộc tuyên bố model cải thiện.

Tie-break giữ ưu tiên đơn giản của protocol cũ: feature A trước B trước C,
rồi Ridge; trong cùng họ alpha lớn hơn, hoặc RF độ sâu hữu hạn nhỏ hơn, leaf
lớn hơn, max_features nhỏ hơn. Với cấu hình còn bằng nhau dùng thứ tự ứng viên
đã ghi trước run, không nhìn test. Không clip dự báo âm trong thực nghiệm chính;
muốn thử clipping phải thành thay đổi có log và chọn bằng dữ liệu phát triển.

## 7. Metric, phân tích lỗi và test gate

Với `e = prediction−target` và N mẫu: MAE=`sum(abs(e))/N` (chính),
RMSE=`sqrt(sum(e²)/N)`, R²=`1−SSE/SST`. R² không xác định nếu N<2 hoặc target
không có phương sai: ghi null và lý do, không điền 0/1. Nhóm rỗng không có
metric; báo N. MAE chính tổng hợp trên mẫu; bổ sung MAE từng trạm và trung
bình giữa trạm để thấy ảnh hưởng số mẫu, không đổi tiêu chí sau test.

Phân tích theo station, mùa tại **target timestamp** (xuân 3–5, hè 6–8, thu
9–11, đông 12–2), nồng độ target `[0,35)`, `[35,75)`, `[75,150)`, `[150,+∞)`.
Các khoảng này là nhóm phân tích, không phải chuẩn sức khỏe. Target chỉ dùng
chấm/phân nhóm sau dự báo, không làm feature. T13 thêm diễn giải mô hình theo
phương pháp phù hợp đã chốt, không suy giải thích mô hình thành quan hệ nhân quả.

Trước T13, khóa và lưu artifact: feature/schema, phương pháp/siêu tham số
selector (không khóa các thống kê fit), imputation/encoding/scaling, tham số
model, seed, cohorts/fallback, split/CV, metrics, nhóm phân tích và run validation
được chọn. **Sau khóa, refit toàn pipeline được chọn trên train+validation**,
gồm preprocessing/selector/estimator; không chọn lại k/threshold/hyperparameter.
Với C khóa input B và phương pháp/k/threshold của selector; tên các feature
được chọn có thể đổi khi refit selector trên train+validation, phải lưu danh
sách final thực tế và không chọn lại bằng test.
Giữ ranh giới test, feature causal và cùng sample IDs; có thể refit các phương
án so sánh đã liệt kê trước (gồm fallback baseline nếu dùng). Log parent/reference
để phân biệt run chọn phương án với run final refit/test.

Chỉ khi được giao T13 mới mở test và đánh giá một đợt kế hoạch đã khóa. Mô
hình final không coi điểm trên validation đã dùng refit là held-out validation.
Không tuning/chọn lại sau test. Nếu phát hiện bug cần sửa, ghi lỗi, phạm vi
ảnh hưởng và run mới; không dùng cớ sửa lỗi để tuning theo test. Demo T14 dùng
pipeline/cấu hình chọn trước test, không lấy model thắng test để chọn lại.

## 8. Experiment Log và artifact

T04-LOG là tên task hiện tại của T04-BỔ SUNG đã làm, cùng Issue #6 và cùng
logger; không tạo hệ thống song song. Xem [API tích hợp](experiment_logging.md).
Mỗi run ghi task_id, reference/parent/fold, mục tiêu/giả thuyết/thay đổi,
model/parameters/features/preprocessing, manifest/checksum, split/ranges/N,
seed/Git/environment/thời gian, metrics, artifact, nhận xét/quyết định hoặc lỗi.
`task_id` của run là task thực thi (T09, T10...), không lấy mã hạ tầng T04-LOG
trong config làm task_id cho mọi run.
Trường chưa biết null; giữ run kém/thất bại. Config ghi giá trị thực dùng,
không chỉ đường dẫn mutable. Smoke khác full; không tạo run thật từ ví dụ.

Tuning: run cha kind=tuning; run con theo cấu hình/fold có parent_run_id và
fold_id. Lưu predictions, config/metrics, model/pipeline khi có, hình gốc với
trục/đơn vị/chú thích, danh sách mẫu bị loại/fallback và feature dictionary.
CSV ở `experiments/experiment_log.csv`, hồ sơ ở `artifacts/experiments/<run_id>`;
khi bàn giao phải kèm cả cây run đang ignore trong Git. Giữa kỳ truy vết mọi
bảng/hình bằng run_id hoặc audit artifact thật; không tạo metric giả khi thiếu.

## 9. Thay đổi so với đặc tả T02 cũ

Giữ nguyên target/đơn vị, trạm đã thấy, mốc chia, grid ứng viên, MAE/RMSE/R²,
nhóm phân tích lỗi và luật nhân quả. F0/F1 đổi cách gọi sang A/B, bổ sung C.
Làm rõ tuning chỉ trong train-CV thay vì duyệt toàn grid trực tiếp trên
validation. **Quyết định cũ không refit train+validation được thay bằng quyết
định người dùng mới chốt: refit ở T13 sau khóa**, không thực hiện trong T02.
Bổ sung fallback T09 và cohort phụ, giữ cohort chính để so sánh tương thích.

Tài liệu giữa kỳ/final và task mapping ở [project_plan.md](project_plan.md),
[midterm_plan.md](midterm_plan.md); không mặc định đã có artifact. Chưa có
metric mô hình trong log chính thức ở lần cập nhật này. Codex hỗ trợ tổng hợp
đặc tả theo yêu cầu người dùng, chưa thực hiện các thí nghiệm thiết kế ở trên.
