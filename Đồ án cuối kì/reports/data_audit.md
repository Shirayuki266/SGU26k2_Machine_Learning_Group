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

Giới hạn của lần tải/audit ban đầu 12/10/2026: khi đó môi trường chưa có Python nên chưa kiểm tra pandas dtype/import; Task 03 dùng PowerShell độc lập, không đổi dependencies. Đây là audit cấu trúc và dữ liệu thiếu, chưa xử lý ngoại lệ, tạo target/lag, impute hay huấn luyện. Không có metric mô hình. Codex hỗ trợ mã và tài liệu; số liệu ở đây lấy từ dữ liệu thật đã audit.

Commit đề xuất: `feat: add reproducible UCI dataset download and audit`.

## Xác minh/hoàn thiện T03 — 02/11/2026

Đã đối chiếu lại [UCI 501 chính thức](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data): đúng Beijing Multi-Site Air Quality, ZIP PRSA2017 nhiều trạm, metadata về số dòng/trạm/thời gian/đơn vị và CC BY 4.0 khớp tài liệu. HTTP HEAD của URL ZIP trong config trả 200; không tải lại ZIP. Không dùng các CSV phụ `data.csv`/`test.csv` trong ZIP ngoài hoặc dataset PM2.5 một trạm.

Lần audit full mới hoàn tất lúc `2026-11-02T09:29:29.9813298+00:00`
(16:29:29 UTC+07), PowerShell 5.1.22621.6133. Đếm trực tiếp raw: **420.768
dòng, 12 file/12 trạm, 18 cột/file, 35.064 dòng/trạm**, thời gian từng trạm
`2013-03-01 00:00:00` đến `2017-02-28 23:00:00`, 0 discrepancy. Schema, kiểu
giá trị suy luận, missing, timestamps và checksum đều bằng báo cáo cũ; JSON
`raw_audit_full.json` chỉ đổi `audited_at`, không ép số quan sát theo metadata.

Đã chạy ba nhánh với file thật hiện có, đều xác minh 12 file và không cần mạng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/uci_501_download.zip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_uci.ps1 -ZipPath data/raw/PRSA2017_Data_20130301-20170228.zip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_raw.ps1 -Mode full
.\.venv\python.exe -m pytest tests/test_acquisition.py -q --basetemp=.pytest_cache/t03-acquisition-final
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t03-acquisition-regression
git diff --check
```

SHA-256 toàn bộ file raw và bytes của manifest được kiểm tra trước/sau, giữ
nguyên. `downloaded_at=2026-10-12T01:49:22.8729593+00:00` là ngày tải đã ghi,
không lấy ngày audit mới hoặc file mtime thay ngày tải. Manifest đã đủ URL,
checksum và license nên không sửa để tạo thay đổi giả.

Các lỗi đã tái hiện bằng fixture `TEST_ONLY` rồi sửa:

- ZIP PRSA2017 bên trong bị từ chối khi manifest ghi ZIP ngoài: nay chấp nhận
  một trong hai checksum đã ghi, giữ descriptor ZIP/nguồn/ngày tải gốc.
- Xác minh lại từng ghi lại `recorded_at`: nay đối chiếu inventory/hash/bytes
  và metadata, giữ nguyên toàn bộ manifest; nếu khác thì dừng để rà soát.
- Ngày thủ công có offset không chuẩn hóa theo ghi chú UTC: nay yêu cầu offset
  hoặc Z và chuẩn hóa UTC khi tạo mới; chưa biết để null, không suy từ mtime.
- ZIP thiếu trạm từng tạo manifest như bộ nhiều trạm: nay so số file thực tế
  với `published_stations` trong config và từ chối trước khi xuất CSV.

Kết quả: **15 ca acquisition pass**, gồm nhánh tải mới mock mạng, ZIP ngoài/
trong, mạng lỗi/fallback, `.part`, null/ngày có offset, không ghi đè raw,
metadata/checksum drift, ZIP sai/thiếu. Gộp kiểm thử unit logger/T04: **62 pass,
1 deselected**. Fixture chỉ nằm trong thư mục tạm, không ghi log mô hình. Parser
PowerShell và whitespace pass. Lần audit đầu đọc xong nhưng không ghi được báo
cáo vì quyền sandbox; đã chạy lại với quyền ghi báo cáo và thành công như trên.

Giới hạn: không tải mới nội dung từ UCI để so byte với bản server hôm nay;
checksum là của file đã lưu, không phải hash do UCI công bố. Nhánh HTTP tải
mới được kiểm tra bằng mock; endpoint thật kiểm tra HEAD. Kiểu audit là kiểu
giá trị CSV, không phải cam kết pandas dtype. Chưa impute, fit, tạo target hoặc
đánh giá test mô hình; raw full chỉ được đọc cho audit nguồn/schema/chất lượng.
Các test acquisition cần PowerShell, được skip rõ nếu môi trường thiếu công cụ.

Codex hỗ trợ sửa cơ chế tải, kiểm thử và tài liệu. Commit đề xuất:
`feat: verify UCI dataset acquisition and provenance`.
