# T17b — Thiết kế trước khi chạy

Issue #44; thực hiện trên nhánh `feat/t17b-supplementary-experiments`. Thiết kế
này được ghi trước khi chạy thí nghiệm. Kết quả thực tế sẽ được ghi riêng trong
[supplementary experiments](supplementary_experiments.md).

## Câu hỏi và giả thuyết

1. Baseline trung bình 3 giờ gần nhất hoặc giá trị cùng giờ mục tiêu hôm trước
   có thể cạnh tranh với persistence mà không fit mô hình.
2. Với RF giữ nguyên tham số đã khóa, đặc trưng B có thể giúp hoặc không giúp
   so với A. Một tìm kiếm RF B nhỏ, chọn bằng pooled CV MAE, có thể giảm sai số.
3. HistGradientBoosting, Lasso/ElasticNet và Decision Tree có thể cung cấp
   phương án sai số/độ phức tạp khác; không giả định sẽ tốt hơn RF đã khóa.
4. Fusion-3 hoặc Stack có thể tận dụng dự báo OOF của các họ mô hình khác nhau;
   validation chỉ dùng để đánh giá sau khi đã chọn cấu hình/gộp bằng CV.

Không có giả thuyết nào cho phép đổi frozen recipe T12/T13 hoặc chọn mô hình
bằng test. Nếu mô hình mới tốt hơn trên validation, chỉ gọi là ứng viên đánh
giá bổ sung; test cuối cùng vẫn là T13.

## Phạm vi và đối chứng

- Dùng primary cohort và cùng T05 train/validation IDs; chỉ đọc T05 `train.csv`,
  `validation.csv`, T07 feature artifact và lịch sử quan sát đến origin. Không
  mở test CSV/IDs hay dự báo test.
- Tham chiếu chính: RF A đã khóa, run `780ecb7fb59d48bea58d5e4a076f1f26`;
  persistence validation, run `24cef47874a94d9faa7bfcbae29b5c58`.
- CV: 3 expanding folds cấu hình sẵn, nhóm timestamp chung mọi trạm, purge
  nhãn theo origin. Chấm pooled MAE/RMSE/R², mean ± population std theo fold
  chỉ mô tả; cùng sample IDs giữa các ứng viên.
- Pipeline: T08, imputer/encoder/scaler chỉ fit trên fold fit. Scale cho
  Lasso/ElasticNet; không scale cây/RF/HistGB. Không clip dự báo.
- Seed 42, thực thi tuần tự, một BLAS thread, không retry tự động.

## Ngân sách đã chốt

| Họ | Cấu hình | CV fit tối đa | Lý do |
| --- | ---: | ---: | --- |
| RF | 4 (A khóa, B khóa, 2 cấu hình B nông) | 12 | Mỗi fit RF trên hàng trăm nghìn mẫu tốn tài nguyên; chỉ khảo sát một biến thể nông và số cây |
| HistGradientBoosting | 4 (A/B × squared/absolute) | 12 | Bao phủ hai loss và hai bộ đặc trưng trong thiết kế nhỏ |
| Lasso/ElasticNet | 3 (2 alpha Lasso, 1 ElasticNet) | 9 | Giới hạn các fit lặp trên ma trận dense |
| Decision Tree | 2 độ sâu | 6 | Hai điểm độ phức tạp diễn giải được |
| **Tổng** | **13 cấu hình** | **39** | Tối đa 3 fold/cấu hình |

Tối đa 6 refit validation: RF A/B đã khóa và ứng viên RF B được chọn bằng CV,
cộng một ứng viên CV tốt nhất của từng họ HistGB, tuyến tính và Decision Tree.
Baselines không fit. Fusion/Stack dùng dự báo sẵn trong run; Stack chỉ fit meta
Ridge trên OOF. MLP không chạy do không thuộc câu hỏi ưu tiên và ngân sách
RAM/thời gian.

Ngân sách thực thi full bị chặn đúng bởi file
[`configs/supplementary_experiments.json`](../configs/supplementary_experiments.json);
không mở rộng grid sau khi xem metric. Nếu tài nguyên không đủ, giữ run failed/
interrupted và ghi cấu hình chưa chạy, không tự giảm dữ liệu hay đổi split.

## Chọn mô hình và ensembles

- Mỗi candidate được xếp hạng bằng pooled MAE của đúng ba fold hoàn tất; hòa
  trong `1e-12` thì giữ thứ tự khai báo trước.
- RF A/B được giữ là đối chứng riêng; tuning RF B chỉ chọn trong 2 cấu hình B
  đã khai báo. Mỗi họ khác chọn ứng viên theo CV, không theo validation.
- Fusion-3 chọn tối đa ba candidate hoàn chỉnh tốt nhất pooled CV MAE từ các
  champion đã định trước (baseline, RF, HistGB, tuyến tính, cây), rồi lấy trung
  bình dự báo trên validation.
- Stack dùng cùng ba base learner: Ridge(alpha=1) fit từ ma trận prediction
  OOF đã căn theo sample ID và labels train tương ứng. Validation không tham gia
  fit meta-learner.

## Đọc kết quả

Mọi run mới dùng ID mới; không chỉnh sửa log/artifact cũ hoặc frozen config.
Validation chỉ là một split, nhiều phương án đã được quan sát và chưa có kiểm
định thống kê; kết quả validation tốt hơn là ứng viên, không phải kết luận
độc lập. Không thêm test score cho mô hình T17b. Bảng T17a được sinh lại từ
ledger/artifact thật và giữ nguyên test_run_id T13 riêng.

Rubric chính thức và file/trang bài giảng chưa được cung cấp; tham chiếu chủ đề
05 (đánh giá), 06 (hồi quy), Ensemble và 04 (feature selection) theo tên chủ đề
người dùng cung cấp, không tự nhận đã trích nội dung bài giảng.
