# Đối chiếu bài giảng và rubric từ T13

Issue #30; áp dụng bổ sung của người dùng sau MK02. Đây là kế hoạch áp dụng,
không phải bằng chứng đã thực hiện T13–T16. Không sửa kết quả/lịch sử giữa kỳ.

## Nguồn hiện có và phần thiếu

Chưa có tài liệu giảng dạy trong `docs/course_materials/` tại lần cập nhật này.
Tên chủ đề dưới đây do người dùng cung cấp; chưa xác minh tên file, slide,
trang, công thức hoặc ví dụ của thầy. Không dùng kiến thức tổng quát để giả
làm trích dẫn bài giảng. Rubric chi tiết/điểm và đường dẫn tài liệu chính thức:
**[CẦN BỔ SUNG]**. Khi nhóm cung cấp, ghi đúng file/trang và điều chỉnh mapping
trong PR mới; không đổi báo cáo cũ để tạo cảm giác đã dùng tài liệu từ trước.

| Chủ đề người dùng cung cấp | Áp dụng dự kiến từ T13 | Bằng chứng phải có trong PR | Tài liệu thầy |
| --- | --- | --- | --- |
| Chủ đề 05: đánh giá, overfitting/underfitting | MAE/RMSE/R², % MAE giảm persistence, generalization gap, fold/std và giới hạn dữ liệu thời gian | Bảng cùng cohort/IDs, run tham chiếu, predictions, N, fold và độ lệch chuẩn | [CẦN BỔ SUNG] file/trang |
| Chủ đề 06: Ridge/hồi quy | Giải thích điều chuẩn và kết quả Ridge đã chạy khi so sánh; không tự fit/tune lại | Config/alpha, pipeline train-only và run thật; nếu chỉ viện dẫn thì ghi reuse | [CẦN BỔ SUNG] file/trang |
| Ensemble: Random Forest | Diễn giải phương án RF được khóa bằng validation, chi phí và sai số; refit chỉ khi được giao T13 | Frozen config, seed/params, model/pipeline thật sau refit, run mới | [CẦN BỔ SUNG] file/trang |
| Chủ đề 04: feature selection khi diễn giải | Phân biệt A/B/C; giải thích selector/nhóm one-hot và giới hạn diễn giải | Registry, feature giữ/bỏ, cách selector fit; không suy importance thành nhân quả | [CẦN BỔ SUNG] file/trang |

## Điều chỉnh cho chuỗi thời gian

Những cách ở cột đầu là tình huống cần tránh nếu xuất hiện trong tài liệu;
**chưa có bằng chứng thầy đã chỉ dẫn các cách đó cho bài toán này**.

| Cách không phù hợp nếu áp dụng máy móc | Quyết định của dự án | Lý do và bằng chứng cần kiểm |
| --- | --- | --- |
| Random split hoặc random K-fold | Temporal split theo target timestamp, expanding-window trong train, ranh giới chung mọi trạm và purge nhãn khi cần | Dự báo dùng quá khứ; nhãn fit phải sẵn có trước origin đánh giá. Lưu fold ranges/IDs/audit |
| Fit imputer/encoder/scaler/selector trên toàn dữ liệu | Fit trong training partition mỗi run/fold; T13 chỉ refit train+validation sau khóa, không fit test | Thống kê tương lai sẽ làm rò rỉ. Lưu config và pipeline fit thực tế |
| Loại nồng độ cao bằng IQR mặc định | Giữ đợt ô nhiễm cao hợp lệ; chỉ xử lý lỗi theo quy tắc có bằng chứng và log | Nồng độ cao là trường hợp phải đánh giá, không tự xóa để cải thiện metric |
| Chọn lại model/threshold/features sau khi xem test | Khóa bằng dữ liệu phát triển, đánh giá test theo kế hoạch T13 được giao | Test dùng đánh giá cuối, không làm tập chọn phương án; ghi sai sót bằng Issue/PR riêng |

Các quyết định này giữ protocol đã có; không thay split, run hay kết quả T01–MK02.
Tham chiếu [kế hoạch thực nghiệm](experiment_plan.md) và
[bổ sung đánh giá cuối kỳ](final_stage_requirements.md#đánh-giá-từ-t13).

## Ghi trong từng PR từ T13

- **Bài giảng áp dụng:** tên chủ đề, file/trang nếu có, cách áp dụng/khác biệt
  và artifact kiểm chứng. Thiếu nguồn ghi [CẦN BỔ SUNG]; không bịa nội dung.
- **Tiêu chí rubric đáp ứng:** yêu cầu người dùng truyền đạt hoặc mục rubric
  có nguồn, bằng chứng/đường dẫn và trạng thái đã làm/chưa làm. Chưa có rubric
  chính thức thì ghi rõ, không suy điểm hoặc tuyên bố đạt toàn bộ rubric.
- **Hỗ trợ AI:** phần AI hỗ trợ, người đọc/kiểm tra/hiểu phần nhận và liên kết
  [AI disclosure](ai_disclosure.md). Review của thành viên chưa có phải ghi thiếu.

Checklist sản phẩm nằm ở [yêu cầu cuối kỳ](final_stage_requirements.md).

## Minh chứng T13 / Issue #32

Chưa có file/trang bài giảng hoặc rubric chính thức, tiếp tục [CẦN BỔ SUNG].
Các áp dụng kỹ thuật sau truy vết từ artifact thực, không giả làm trích giảng:

- Chủ đề05: comparison.csv, generalization_gap.csv, development_fold_metrics.csv,
  cv_summary.csv và grouped_metrics.csv trong reports/final_evaluation; metric
  được tính lại từ6file predictions. Không fit test hoặc chọn lại theo test.
- Chủ đề06: Ridge A alpha0.1 từ CV T11, refit train+validation;65hệ số tại
  ridge_coefficients.csv. MAE kém baseline nhưng RMSE tốt hơn; báo2067dự báo âm
  theo policy identity đã khóa, không clipping sau test.
- Ensemble: RF A80cây/depth12 chọn bằng validation, weights có checksum trong
  final_model.json; permutation nhóm raw16nguồn,3repeat,2400IDs/1luồng,
  chỉ chẩn đoán sau scoring, không chọn model từ importance.
- Chủ đề04 khi diễn giải: T13 chỉ A, dùng kết quả A/B/C T12 trên development
  để nói về selection; không khẳng định đã chấm B/C trên test hoặc fit selector
  mới trong T13. Hệ số/importance không chứng minh nhân quả.

Bảng/hình và nhận xét: [results_discussion.md](results_discussion.md).
Người nhận hoanglecodingmachine cần đọc/hiểu/review; chưa tự tick xác nhận.

## Minh chứng T14 / Issue #34

Chủ đề Ensemble: inference từ RF A đã chọn bằng validation, load đầy đủ pipeline
và schema/version, không fit lại khi rerun. Chủ đề05: phân biệt demo vài ví dụ
với đánh giá tổng hợp T13; không chọn lại bằng test hoặc tuyên bố cảnh báo thực tế.
Chủ đề04/06: giữ quyết định A và so sánh phát triển trước đó, không thêm selector,
không tuyên bố demo Ridge hay suy importance thành nhân quả. Feature dùng input
đến t và lịch t+1; thời điểm replay sau fit cuối, actual chỉ query sau predict.

Minh chứng: [hướng dẫn/QA](demo.md),19 tests,36 parity/12trạm,5 PNG browser thật.
Yêu cầu demo/model/README đã có; video chỉ [storyboard chưa quay](demo_video_storyboard.md).
File/trang bài giảng và rubric chính thức [CẦN BỔ SUNG]; chưa xác nhận điểm cộng
hoặc đáp ứng toàn bộ rubric. Người nhận phải đọc/hiểu trước merge.

## Minh chứng T17a / Issue #40

Chủ đề05: cùng primary validation IDs/coverage, pooled theo n_i khác mean/std
fold, tách test refit T13 và giữ lock từ development. Chủ đề06/Ensemble và04:
bảng Ridge/RF/A/B/C dùng artifact thật, không fit selector/model mới. Dòng
tốt nhất chỉ tô theo validation, không chọn lại model sau test.

Bằng chứng: reports/tables/experiment_summary.*, các checks/provenance và
tests/test_experiment_summary.py. Chỉ tổng hợp, không T17b/training. File/trang
bài giảng/rubric gốc [CẦN BỔ SUNG]; không tự gán điểm hoặc bịa bảng leaderboard.

## NB01 / Issue #42

Notebook chỉ tổng hợp minh chứng: chủ đề02/quy trình CRISP-DM;03/Lab03 cho
audit/EDA/preprocessing;04 cho selector A/B/C;05 cho temporal split/CV,
metric, adverse outcomes và RQ;06/Ridge;Ensemble/RF. File/trang bài giảng
và rubric chính thức [CẦN BỔ SUNG], không bịa nội dung/điểm. Giữ temporal
split thay random split, fit trong train/fold và không xóa đỉnh bằng IQR.
Nguồn nằm ngay dưới bảng/hình, T13 chỉ đọc artifact đã có; NB01 không chọn
lại phương án bằng test. Chi tiết ở project_journey.md/notebook/code map.
