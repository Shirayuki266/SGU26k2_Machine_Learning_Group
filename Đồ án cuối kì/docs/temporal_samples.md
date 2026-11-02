# T05 — Mẫu dự báo một giờ và temporal split

T05 dùng lại dữ liệu hợp nhất chưa impute đã được T04 chấp nhận. Không tải,
merge/audit lại raw, không fit preprocessing/selector/model. Tạo nhãn test là
bước chuẩn bị dữ liệu; chưa được dùng để khám phá, chọn mô hình hoặc tính metric.

## Hợp đồng mẫu

`beijing_air.samples.build_samples` ghép bằng khóa **station + timestamp đúng
t+1 giờ**. Chỉ lấy PM2.5 tương lai làm `target_pm25`; các cột quan trắc còn lại
là snapshot tại origin. Không dùng dòng kế tiếp thay giờ kế tiếp, không impute
target hoặc nối qua trạm. Input phải có timestamp hourly, timezone-naive,
khóa duy nhất và PM2.5 số hữu hạn không âm (hoặc missing hợp lệ). Input được
sắp xếp canonical trên bản sao, không sửa dữ liệu T04.

| Cột thêm/đổi | Ý nghĩa |
| --- | --- |
| `input_timestamp` | Origin t, đổi tên từ timestamp T04; không thêm cột origin trùng nghĩa |
| `target_timestamp` | input_timestamp + đúng 1 giờ |
| `target_pm25` | PM2.5 quan sát tại target_timestamp, cùng station |
| `sample_id` | SHA-256 JSON compact UTF-8 của `["pm25-h1-v1", station, input ISO seconds, target ISO seconds]` |
| `is_primary` | Có PM2.5(t), sau khi đã loại mọi target không quan sát được |
| `split` | train/validation/test theo **target timestamp** |

ID không phụ thuộc thứ tự input, file nguồn, index, seed hoặc giá trị PM2.5.
Thay giá trị dữ liệu giữ ID của khóa quan trắc, nhưng checksum input/snapshot
sẽ đổi. Có kiểm tra ID duy nhất; không coi ID là feature. `No` không được đưa
lại vào input. `target_pm25`, ID/cohort/split, timestamps khóa và provenance
không tự trở thành feature; T07/T08 sẽ chọn cột tường minh.

Hai cohort được lưu cùng snapshot:

- **operational**: mọi mẫu có target quan sát được; giữ PM2.5(t) thiếu để T09
  triển khai fallback theo đặc tả. T05 chưa thực hiện fallback.
- **primary**: operational với `is_primary=True`; dùng cùng IDs khi so sánh
  baseline và model. Không loại mẫu vì các feature khác hoặc lag/rolling thiếu.

Mẫu bị loại có lý do loại trừ lẫn nhau: `end_of_series` (t+1 vượt giờ cuối
trạm trong input), `missing_target_timestamp` (thiếu hàng t+1 bên trong chuỗi),
`missing_target_value` (có hàng t+1 nhưng PM2.5 thiếu). CSV exclusions chỉ lưu
ID/trạm/ngày/lý do/cờ origin có quan sát, không chứa target giả. CSV theo trạm
và totals đối chiếu `input = retained_operational + excluded`.

## Split và khả dụng nhãn

Giữ mốc T02 trong `configs/default.json`: train target trước 2015-03-01;
validation từ đó tới trước 2016-03-01; test từ 2016-03-01. Ranh giới giống
nhau cho mọi trạm, không shuffle. Input 2015-02-28 23:00 thuộc validation nếu
target là 2015-03-01 00:00; tương tự ranh giới test. Lịch sử được đi qua biên
khi đã quan sát tới t; không fit lại mỗi khi nhận số đo mới.

`check_label_availability(fit, evaluation, fit_cutoff=None)` kiểm tra nhãn
fit lớn nhất **<= cutoff <= origin đánh giá đầu tiên**, trên toàn bộ trạm của
mô hình chung. Mặc định cutoff là origin đầu. Cho phép bằng nhau ở holdout vì
dự báo phát hành sau khi có số đo t. Đây là kiểm tra cutoff dự kiến, không
khẳng định đã fit hoặc đã đo thời gian fit/độ trễ phát hành dự báo.

CV T11 dùng `strict_before_origin=True`: nhãn fit phải **< origin đầu**; bên
gọi purge nhãn ở origin nếu cần rồi kiểm tra. T05 cung cấp guard, chưa tạo/chạy
fold CV/tuning. Manifest kiểm tra train→validation và kiểm tra **dự kiến**
train+validation→test cho T13, ghi `fitted=False`; không thực hiện refit.
Split rỗng được báo `not_evaluated_empty_partition`, không pass giả. Full yêu
cầu đủ mọi trạm trong mọi split/cohort; smoke có thể rỗng validation/test.

## Chạy và artifact

Từ thư mục đồ án với Python portable hiện có:

```powershell
.\.venv\python.exe scripts/build_samples.py --mode smoke
.\.venv\python.exe scripts/build_samples.py --mode full
.\.venv\python.exe -m pytest tests/test_samples.py -q --basetemp=.pytest_cache/t05-samples
```

Trên clone mới, báo cáo chuẩn đã có trong Git nhưng dataset được ignore.
Sau khi tạo input T04, dùng tên output mới để giữ nguyên báo cáo đã commit:

```powershell
.\.venv\python.exe scripts/build_samples.py --mode full --output-tag reproduce
```

Lệnh tạo `samples_full_reproduce` và `splits_full_reproduce`; tên tag chỉ gồm
chữ/số/gạch dưới/gạch nối, bắt đầu bằng chữ/số. Có thể dùng tag mới cho lần
tái lập hoặc phiên bản code/config mới. Các báo cáo có tag được ignore mặc
định; muốn chia sẻ hãy đóng gói hoặc chủ động chọn audit nhỏ sau rà soát.

Venv chuẩn dùng `.\.venv\Scripts\python.exe`. Smoke dùng chính input prefix
T04 đã lưu, không đại diện ranh giới/coverage toàn bộ dữ liệu. End-of-series
trong smoke là cuối prefix. Các ca ranh giới được kiểm tra bằng fixture riêng.

```text
data/processed/samples_<mode>/
  train.csv, validation.csv, test.csv    Operational, có cờ primary
  sample_ids/<split>.csv                 IDs/trạm/ngày/cờ primary, không có nhãn
  excluded_samples.csv                  Mẫu loại theo lý do
reports/splits_<mode>/
  split_manifest.json                   Signature, membership/hash, fit-cutoff audit
  exclusion_summary.csv                 Số mẫu/lý do theo trạm
  split_summary.csv                     Số mẫu/khoảng ngày theo split/cohort
  station_split_summary.csv             Số mẫu/khoảng ngày từng trạm/split/cohort
```

Sample/ID CSV lớn được ignore trong Git; commit manifest và các bảng audit nhỏ.
Đường dẫn manifest tính từ gốc đồ án. Signature gồm checksum input T04, manifest
raw, phần config T05, code module/script; metadata ghi Python/pandas và UTC lúc
tạo. Snapshot ID là hash signature, **không phải run ID mô hình**. Logical sample
IDs ổn định; byte hash/snapshot có thể đổi theo code, line endings hoặc input.

Script kiểm checksum và trạng thái T04 trước khi đọc, không xuất nếu input
không khớp. Staging kế thừa quyền thư mục cha và publish bằng rename; manifest
chỉ xuất cuối cùng. Chạy lại cùng signature xác minh mọi artifact rồi giữ
nguyên bytes/created_at. Khác input/config/code hoặc checksum thì dừng, không
ghi đè. Nếu bị gián đoạn giữa hai rename, trạng thái thiếu manifest bị từ chối;
cần rà soát/bảo toàn snapshot cũ hoặc dùng output-tag mới, không xóa raw/T04.
Thư mục cha phải cho tài khoản chạy script quyền tạo thư mục/ghi file.

Đọc train trong task sau, chưa fit ở T05:

```python
import pandas as pd
train = pd.read_csv("data/processed/samples_full/train.csv",
                    parse_dates=["input_timestamp", "target_timestamp"])
primary_train = train.loc[train["is_primary"]].copy()
# Chọn feature tường minh trong T07/T08; không lấy toàn bộ cột làm X.
```

Không mở `test.csv` để EDA/tuning. Có thể dùng sample_ids/test.csv và các bảng
count/date để audit sự tách biệt. Khi bàn giao kèm cả dataset/IDs được liên kết,
hoặc chạy lại từ T04 bằng config/code tương ứng; không commit dataset lớn.
T05 không gọi ExperimentLogger để biến audit dữ liệu thành lịch sử mô hình.
Kết quả thực và giới hạn: [reports/sample_split.md](../reports/sample_split.md).
Codex hỗ trợ module, script, kiểm thử và tài liệu; chưa triển khai T06 trở đi.
