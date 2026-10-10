# Lab04: Feature Selection

Lớp: dect124c1 — Môn học: Machine Learning

## Nội dung

- `house_price_submission.py`: một file Python độc lập chứa toàn bộ tiền xử lý, Feature Selection, ba mô hình, 5-fold CV và xuất kết quả.
- `house_price_submission.ipynb`: notebook độc lập, sắp theo luồng EDA → từng nhóm tiền xử lý → Feature Selection → CV và kết quả; mỗi nhóm có giải thích trước code tương ứng. Phân tích EDA đầy đủ nằm trong `eda_analysis.ipynb`.
- `BAO_CAO_HOUSE_PRICE.docx`: báo cáo gồm trang bìa, mục lục, bảng thành viên, phương pháp và kết quả thực nghiệm.
- `house-prices-advanced-regression-techniques/`: dữ liệu train, test và mô tả cột.
- `plots/feature_selection/`: bảng metrics, kết quả từng fold, OOF predictions, danh sách biến, biểu đồ và submission baseline XGBoost.

## Chạy code

Tiền xử lý áp dụng đầy đủ đề xuất EDA: lọc hai ngoại lệ **chỉ trên train** của mỗi fold; log target; None/0 cho missing cấu trúc; LotFrontage median theo Neighborhood với fallback median train; sửa GarageYrBlt=2207 bằng YearBuilt; điền median/mode còn lại; loại cột gốc có >=99% giá trị đồng nhất; One-Hot và StandardScaler. Baseline giữ tất cả cột sau các bước tiền xử lý này. Validation không lọc theo SalePrice; có đủ 1.460 dự đoán OOF.

Dùng Python 3.13 (môi trường đã kiểm tra). Mở terminal trong thư mục này:

```text
python -m pip install -r requirements.txt
python house_price_submission.py
```

Để chạy notebook: mở `house_price_submission.ipynb` trong VS Code/Jupyter, chọn kernel của môi trường đã cài dependencies và Run All. Notebook không phụ thuộc file `.py`. Khi upload lên Colab, cần upload/giải nén cả thư mục dữ liệu vào thư mục làm việc.

Hai cách chạy thực hiện cùng thí nghiệm 18 tổ hợp × 5 fold. Thời gian chạy tùy máy; thời gian fit trong bảng sẽ thay đổi khi chạy lại. Số cột baseline phụ thuộc vocabulary One-Hot trong từng fold. Không cần LightGBM, CatBoost hoặc các file dự án bên ngoài.

## Trước khi gửi

Kiểm tra tên trường, lớp, môn học, giảng viên và họ tên/MSSV thành viên trong trang bìa, bảng thành viên. Các vị trí chưa được cung cấp có nhãn `[Điền ...]`, không phải thông tin thật.

Dataset: House Prices - Advanced Regression Techniques / Ames Housing, nguồn Kaggle. `test.csv` không có nhãn SalePrice, chỉ dùng tạo submission. Báo cáo lấy kết quả từ `plots/feature_selection/metrics_summary.csv`; hiệu suất là CV với cấu hình cố định, chưa phải đánh giá sau tối ưu hyperparameter.
