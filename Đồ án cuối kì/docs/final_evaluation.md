# T13 — Kế hoạch đánh giá cuối đã khóa

Issue #32, người nhận hoanglecodingmachine theo câu trả lời “cho tôi” của
người dùng và tài khoản GitHub đang đăng nhập đã xác minh. Git author hiện
hoanglecodingmachine <thanhtanicluod@gmail.com>; không đổi global/local config
hoặc co-author. Nhóm tự bổ sung họ tên/MSSV/tỷ lệ, review/đọc/hiểu trước merge.

## Chốt trước mở test

`configs/final_evaluation.json` ghi đủ params thực tế, SHA các đầu vào,
reference run, seed42, cohort, schema và ngân sách. Frozen T12 gốc
`reports/ablation/frozen_model.json` **giữ nguyên**. Preflight xác minh:

- RF A80cây/depth12/leaf2/n_jobs1, reference
  `780ecb7fb59d48bea58d5e4a076f1f26`, được chọn triển khai theo validation MAE.
- Ridge **A alpha0.1** reference `32e65c5a4cbc489c905cf146b743867f`, chọn alpha
  bằng temporal CV T11, comparator cùng features A; không mở thêm B/C trên test.
- Persistence reference `24cef47874a94d9faa7bfcbae29b5c58`, dự báo PM2.5(t).
  Cả ba đánh giá cùng **primary IDs**. Primary có số đo tại t nên fallback=0;
  T13 không chấm cohort operational thiếu PM2.5(t), không suy hiệu quả fallback.
- Hai pipeline T08 refit trên307344primary train+validation (204865+102479),
  mọi thống kê chỉ học ở đó. Hậu xử lý identity chung, không clipping.
- latest fit target <= first test origin, giả định số đo tại origin đã sẵn có;
  cuốn chiếu một bước, không batch forecast cả năm tại origin đầu.

Khi thiếu frozen hoặc fingerprint/params/IDs khác, dừng **trước test**.
Lựa chọn triển khai vẫn RF A bất kể model nào có metric test tốt nhất.

## Ngân sách và quy tắc phân tích

Một full parent attempt, hai ML fits (một/model), một test configuration/model;
baseline không fit estimator. BLAS1luồng, RF n_jobs1, chạy tuần tự, kiểm RAM
khả dụng tối thiểu768MiB; không giảm sample/tree/params ngầm nếu thiếu RAM.

Không auto retry. Nếu lỗi kỹ thuật, giữ run lỗi và audit test exposure, chỉ
retry với lý do rõ và config không đổi; tạo parent/child IDs mới. Nếu đã có
parent completed thì runner chặn chạy full lần nữa. Rerun vì phương pháp sau
test phải công khai tác động, không coi test là chưa xem hoặc tuning bằng test.

Ngưỡng concentration35/75/150 là nhóm mô tả đã chốt trong protocol phát triển,
không phải chuẩn sức khỏe; preflight ghi phân bố train. Episode: target>=150,
ít nhất3giờ liên tiếp cùng trạm, giờ khuyết tách; primary selection có thể cắt
ngắn sự kiện. Biến đổi đột ngột dùng q95 |target−PM2.5(t)| từ train (**38µg/m³**
theo preflight trước test). Mùa lấy target timestamp; R² nhóm N<30 hoặc target
constant là null/lý do. %MAE giảm so persistence dùng cùngIDs/cohort, mẫu số0
ghi null; giữ phần trăm âm khi model kém baseline.

Permutation RF: tối đa200IDs/trạm,12trạm, chọn cách đều thời gian; seed42,
3repeat/nhóm nguồn,1luồng. OHE categorical giữ cùng nguồn raw; hour/month và
sin/cos xáo chung nhóm. Giới hạn16nhóm/49predict kể baseline, không fit thêm;
chỉ chẩn đoán, không chọn model/feature từ test. Hệ số Ridge lưu encoded space
và raw-unit cho numeric, không diễn giải độ lớn/importance thành nhân quả.

Hình timeline: Aotizhongxin,7ngày test đầu đã định trước. Hình episode chọn
đỉnh quan sát cao nhất sau scoring, tie theo start/station để mô tả sai số,
không thay cấu hình. Scatter/hist giữ mọi test primary, không loại đỉnh lớn.
Giờ khuyết trong timeline để NaN, không nối giả hoặc impute label.

## Lệnh và artifact

Từ root đồ án trong PowerShell, dùng môi trường portable hiện có:

```powershell
.\.venv\python.exe -m pytest tests/test_final_evaluation.py tests/test_preprocessing.py -q -p no:cacheprovider --basetemp=artifacts/T13_TEST_CHECK_NEW
.\.venv\python.exe scripts/run_final_evaluation.py --preflight
# Chỉ sau khi code/config đã commit và preflight pass:
.\.venv\python.exe scripts/run_final_evaluation.py --execute
.\.venv\python.exe scripts/verify_final_evaluation.py
```

`--preflight` chỉ đọc train/validation; không mở test hoặc log run thật.
Fixture tests có nhãn TEST_ONLY, không thêm metric giả vào ledger chính.
`--execute` ghi execution audit **trước lần đọc test đầu tiên**, log parent và
ba child bằng ExperimentLogger cũ; `is_test=False` nghĩa là run thật, không
phải partition train. Split chấm trong run là held-out test, không được che giấu.
Technical retry chỉ với `--execute --technical-retry-reason 'lý do kỹ thuật'`
sau parent failed; không chạy lệnh đó khi full đã completed.

Kết quả ở `reports/final_evaluation/`, PNG gốc ở
`reports/figures/final_evaluation/`, thảo luận ở `docs/results_discussion.md`
sau run. CSV bảng chỉ là view của artifact; parent ghi config, preflight,
snapshot ledger cũ, các bảng/hình/báo cáo. Child ghi6file predictions tổng cộng
(refit/test cho3model), metrics, pipeline weights và checksum/summary cho2ML.
Verifier tính lại metrics/group metrics, IDs, frozen params/selection, SHA
artifact và49row/core files cũ mà không fit hoặc mở lại input test CSV.

Weights và bundle artifact lớn giữ local/ignored; khi bàn giao có manifest/SHA
và hướng dẫn khôi phục, không gọi pipeline summary là weights. Không rerun
model để giả tái tạo run lịch sử. Run mới append vào ledger;49dòng trước giữ
nguyên, bộ giữa kỳ là snapshot và không regenerate theo kết quả test mới.

CV/gap reuse predictions T11 thật và train-origin persistence trên cùng fold
IDs. Có pooled/mean/std3fold (ddof0). RF CV chưa chạy trong ngân sách trước:
ghi thiếu, không tạo std giả. Train~2năm, cửa sổ evaluation fold đầu06–08/2014
thiếu mùa khác; không quy mọi chênh lệch final test cho overfitting vì model
final refit thêm validation và test ở giai đoạn thời gian khác.

Bài giảng05/06/Ensemble,04 khi nói selection; file/trang/rubric riêng còn
[CẦN BỔ SUNG], xem course_alignment.md. Codex hỗ trợ triển khai/kiểm/soạn
nhận xét từ artifact; thành viên cần đọc/hiểu/review trước merge. T14–T16 chưa
được thực hiện bởi task này.

## Trạng thái thực tế sau run

Đã hoàn tất một parent attempt,3child trên101836test primary IDs; không lỗi
kỹ thuật, không technical retry, không tuning/chọn lại. Parent:
a8cb7fda3f1441968b31c26c18e57ebf.
Persistence0960fac6455f4380bd5b6d1407633cf8,
Ridge51975d2c66ff4263b83ace6962f3d3f7,
RF24cd6d765f214d52aa26e5988380e2cd.

[Thảo luận RQ1–RQ3](results_discussion.md) và
[kiểm artifact](../reports/final_evaluation/verification.json):
41artifact đăng ký,6file predictions,2weights và2946metric nhóm pass.
49row CSV cũ/196core file cũ không đổi. RF MAE9,877150, giảm2,8013%
so persistence10,161809; Ridge10,384443, kém2,1909% theo MAE.
Model vẫn chọn theo validation; manifest bàn giao ở
[final_model.json](../reports/final_evaluation/final_model.json).
Frozen T12 giữ test_evaluated=false như snapshot cũ; trạng thái test hiện tại
phải đọc execution.json: **test đã được mở**.

Weights ignored được kèm trong bundle cục bộ
reports/final_evaluation/t13_runs.zip (102162012byte), SHA-256:
5362ebf0c51961d96537f5c3a8ffae39b4e1da0b7f6daa6230593445a8e471c1.
Bundle có93file:4tree T13 và2tree T09 dependency giữ nguyên, không phải6run mới.
Không có CSV ledger ở root ZIP và không ghi đè ledger mới. Binary bundle/weights
không commit hoặc upload công khai; người dùng lấy file bàn giao trên workspace.
Git giữ manifest/checksum/code/metadata/predictions/bảng/hình. Khi chuyển máy,
cần mang bundle này cùng source; không gọi clone chỉ có Git là đã đủ weights.

```powershell
# Kiểm checksum/CRC/file manifest, không ghi project:
.\.venv\python.exe scripts/package_final_artifacts.py --verify reports/final_evaluation/t13_runs.zip
# Khôi phục chỉ file còn thiếu, file có sẵn phải đúng SHA; không thay CSV:
.\.venv\python.exe scripts/package_final_artifacts.py --restore reports/final_evaluation/t13_runs.zip
.\.venv\python.exe scripts/verify_final_evaluation.py
```

Đã thử restore93file vào thư mục trống, sau đó restore lần2 ghi0file; ledger
workspace không đổi. delivery_verification.json lưu kết quả. Không chạy
--execute để khôi phục artifact, vì parent completed chặn đánh giá mới.
Không dùng lệnh restore T09 cũ yêu cầu ledger chỉ T09 cho repo đã có53row;
bundle T13 đã kèm hai dependency T09 để không cần thay CSV hiện hành.

Báo cáo tự động nguyên gốc giữ trong parent artifact. docs/results_discussion.md
được rà định dạng và thêm nhận xét từ số liệu đã lưu; không thay bản run gốc.
Bảy PNG đã rà contact sheet: đủ axis/đơn vị/legend, không bị cắt; dữ liệu đỉnh
vẫn được giữ. Không tái sinh hình hoặc chấm model khác để cải thiện kết quả.
