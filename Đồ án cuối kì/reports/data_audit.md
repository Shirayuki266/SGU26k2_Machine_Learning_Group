# Audit dữ liệu gốc UCI 501 — Task 03

Ngày tải: 12/10/2026, 08:49:22 (UTC+07), tương ứng thời điểm UTC trong [manifest](data_manifest.json). Nguồn và license được xác minh tại [UCI 501](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data). Raw lấy từ ZIP PRSA2017 nhiều trạm; không dùng CSV phụ hoặc dataset một trạm.

Kết quả dưới đây lấy từ lần chạy full thành công, không phải smoke. Chi tiết máy đọc được: [raw_audit_full.json](raw_audit_full.json).

| Kiểm tra | Quan sát thực tế |
| --- | --- |
| File trạm / trạm phân biệt | 12 / 12 |
| Tổng dòng, không tính header | 420.768 |
| Dòng mỗi file | 35.064 |
| Đối chiếu 420.768 dòng công bố | Chênh lệch 0 |
| Số cột mỗi file | 18; thứ tự và tên đều khớp schema tham chiếu |
| Thời gian mỗi trạm | 2013-03-01 00:00:00 đến 2017-02-28 23:00:00 |
| Timestamp không hợp lệ / trùng | 0 / 0 |
| Chuyển tiếp cách trên 1 giờ / không tăng | 0 / 0 |
| SHA-256 raw trước và sau audit | Không thay đổi, khớp manifest |

Số dòng được đếm từ từng CSV, không gán bằng số công bố. Không có lỗi trong các kiểm tra đã triển khai; điều này không đồng nghĩa mọi số đo đều chính xác hoặc không có ngoại lệ vật lý. Các giá trị thiếu được giữ nguyên.

| Trạm | Dòng | PM2.5 thiếu |
| --- | ---: | ---: |
| Aotizhongxin | 35.064 | 925 |
| Changping | 35.064 | 774 |
| Dingling | 35.064 | 779 |
| Dongsi | 35.064 | 750 |
| Guanyuan | 35.064 | 616 |
| Gucheng | 35.064 | 646 |
| Huairou | 35.064 | 953 |
| Nongzhanguan | 35.064 | 628 |
| Shunyi | 35.064 | 913 |
| Tiantan | 35.064 | 677 |
| Wanliu | 35.064 | 382 |
| Wanshouxigong | 35.064 | 696 |

| Cột | Kiểu giá trị suy luận trên mọi file | Tổng missing (`NA` hoặc rỗng) |
| --- | --- | ---: |
| No | integer | 0 |
| year | integer | 0 |
| month | integer | 0 |
| day | integer | 0 |
| hour | integer | 0 |
| PM2.5 | real | 8.739 |
| PM10 | real | 6.449 |
| SO2 | real | 9.021 |
| NO2 | real | 12.116 |
| CO | integer | 20.701 |
| O3 | real | 13.277 |
| TEMP | real | 398 |
| PRES | real | 393 |
| DEWP | real | 403 |
| RAIN | real | 390 |
| wd | string | 1.822 |
| WSPM | real | 318 |
| station | string | 0 |

CSV là văn bản; kiểu trên được suy luận từ giá trị không thiếu bằng parser invariant culture, không phải dtype pandas. Xem [từ điển dữ liệu](../docs/data_dictionary.md) để biết ý nghĩa và đơn vị.

SHA-256 ZIP tải từ UCI:

```text
b04da438b2f331ac0ffd45aebdfec0d20d2367feb5f6948c4b1f7ce1191e33c4
```

SHA-256 ZIP PRSA2017 bên trong:

```text
d1b9261c54132f04c374f762f1e5e512af19f95c95fd6bfa1e8ac7e927e3b0b8
```

Các hash tính từ file đã tải, không phải hash do UCI công bố. Manifest còn chứa SHA-256 từng CSV.

Lệnh đã chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/uci_501_download.zip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_raw.ps1 -Mode smoke
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_raw.ps1 -Mode full
git diff --check
```

Tải trong sandbox ban đầu lỗi kết nối; lần chạy ngoài sandbox được phê duyệt đã tải thành công. Smoke ban đầu gặp lỗi cộng số dòng với `Measure-Object` trên ordered dictionary; đã sửa, chạy lại smoke và full thành công. Smoke cuối kiểm tra 100 dòng/file (1.200 dòng), không dùng làm báo cáo chính thức. Chạy lại tải/giải nén và chế độ ZIP thủ công giữ checksum raw và provenance tải ban đầu. Parser PowerShell xác nhận hai script không có lỗi cú pháp.

Giới hạn: môi trường chưa có Python nên chưa kiểm tra pandas dtype/import; Task 03 dùng PowerShell độc lập, không đổi dependencies. Đây là audit cấu trúc và dữ liệu thiếu, chưa xử lý ngoại lệ, tạo target/lag, impute hay huấn luyện. Không có metric mô hình. Codex hỗ trợ mã và tài liệu; số liệu ở đây lấy từ dữ liệu thật đã audit.

Commit đề xuất: `feat: add reproducible UCI dataset download and audit`.
