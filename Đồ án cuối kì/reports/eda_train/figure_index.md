# Chỉ mục hình T06

## 01_missing — Observed-target training cohort: missing values

[PNG gốc](../../reports/figures/eda_train/01_missing.png) · Bảng: numeric_summary;station_missing_pct

Thiếu nhiều nhất: CO 6.74%; PM2.5(t) thiếu 1,112 mẫu. T08 thử median và cờ missing fit riêng train/fold; không coi NA là 0, không backfill.

## 02_distributions — Train distributions: all observed values, no clipping

[PNG gốc](../../reports/figures/eda_train/02_distributions.png) · Bảng: numeric_summary

PM2.5(t) median 61.0, mean 83.9, skew 1.64; CO std 1079.7 µg/m³ so với WSPM 1.25 m/s. T08 scale biến số cho Ridge; RF không bắt buộc scaling. Không yêu cầu predictor phân phối chuẩn.

## 03_tails — PM2.5 tails: IQR fliers retained, not labelled errors

[PNG gốc](../../reports/figures/eda_train/03_tails.png) · Bảng: numeric_summary

PM2.5(t) q99=350.0, max=844.0 µg/m³; 7,678 cờ IQR, 203 cờ ngưỡng rà soát, 0 sai vật lý. Target max=844.0. Giữ đợt cao; cờ thống kê không chứng minh lỗi, không clip/xóa/log-transform target trong T06.

## 04_correlations — Train correlations; target_pm25 is a label, never an input

[PNG gốc](../../reports/figures/eda_train/04_correlations.png) · Bảng: pearson;spearman;correlation_pairs

Pearson với nhãn t+1: PM2.5(t)=0.965, PM10=0.842, TEMP=-0.094, WSPM=-0.274. Ma trận dùng pairwise observed; xem bảng số cặp. T07 giữ A, T08 dùng regularization; tương quan không phải nhân quả hoặc bằng chứng loại feature.

## 05_relationships — Train feature/label pairs: descriptive association only

[PNG gốc](../../reports/figures/eda_train/05_relationships.png) · Bảng: correlation_pairs;pearson;spearman

Hexbin dùng cặp quan sát train, gồm 205,977 nhãn nhưng chỉ 204,865 cặp PM2.5(t)/nhãn. Các đám mây có thể phản ánh trạm/mùa và phụ thuộc thời gian; chưa thể kết luận lợi ích dự báo. T10 mới so sánh model cùng IDs.

## 06_stations — Station distributions and observed wind direction

[PNG gốc](../../reports/figures/eda_train/06_stations.png) · Bảng: station_summary;categorical_counts

Median PM2.5(t) theo trạm thấp nhất Dingling=45.0, cao nhất Wanliu=68.0 µg/m³. T07 giữ station/wd categorical, T08 encode với xử lý unknown; không suy thứ bậc từ mã trạm/hướng gió. Xem categorical_counts cho tần suất wd.

## 07_calendar — Train calendar profiles pooled across stations/years

[PNG gốc](../../reports/figures/eda_train/07_calendar.png) · Bảng: hourly;monthly;seasonal

Mean theo giờ origin thấp nhất 07h=77.1, cao nhất 22h=94.6; theo mùa JJA=73.0 tới DJF=94.4 µg/m³. T07 giữ lịch biết trước; cân nhắc biểu diễn chu kỳ, kiểm tra hiệu quả sau bằng CV, không suy tác động nhân quả.

## 08_timeline — Train PM2.5 daily summaries; days use available observations

[PNG gốc](../../reports/figures/eda_train/08_timeline.png) · Bảng: daily_station;sample_gaps

Có 4,251 origin không hiện diện trong khoảng đầu–cuối train mỗi trạm, 1,112 đoạn gián đoạn; dài nhất 343 giờ. Đây là khoảng trống trong cohort có target quan sát, không xác nhận raw mất giờ. T07 tạo lag/rolling trên timeline quan sát T04 rồi chọn IDs T05; không nén thời gian hoặc nội suy nhãn.

## 09_autocorrelation — Same-station, exact-hour observed pairs; not compressed row lags

[PNG gốc](../../reports/figures/eda_train/09_autocorrelation.png) · Bảng: autocorrelation

Tự tương quan Pearson trung bình đều theo trạm: lag 1h=0.965, 24h=0.363, 168h=0.004. Ghép đúng station/timestamp, báo n từng lag; chưa khử trend/mùa nên đây là mô tả, không kiểm định độc lập. T07 thử B lag/rolling đã chốt; T09 cần persistence. Chưa có metric mô hình.
