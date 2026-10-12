# Task 04 — Kết quả loader và kiểm tra chất lượng

Chạy trên dữ liệu UCI 501 thật đã tải ở Task 03, ngày 12/10/2026. Kết quả chính thức của bước kiểm tra dữ liệu lấy từ [summary full](quality_full/summary.json), [audit từng trạm](quality_full/stations.csv) và [chi tiết cảnh báo](quality_full/issues.csv); không dùng smoke để kết luận về toàn bộ dữ liệu.

| Kiểm tra full | Kết quả quan sát |
| --- | ---: |
| File / trạm | 12 / 12 |
| Dòng đọc / dòng hợp nhất | 420.768 / 420.768 |
| Lỗi chặn xuất | 0 |
| Trùng khóa giống nhau / mâu thuẫn | 0 / 0 |
| Timestamp sai | 0 |
| Giờ thiếu nội bộ / theo khoảng metadata | 0 / 0 |
| Cảnh báo nồng độ PM2.5 > 500 µg/m³ | 933 |
| Cảnh báo nồng độ O3 > 500 µg/m³ | 18 |
| Tổng cảnh báo | 951 |
| PM2.5 còn missing | 8.739 |

Mỗi trạm có 35.064 dòng, từ `2013-03-01 00:00:00` đến `2017-02-28 23:00:00`. Bảng đầu ra đã sắp xếp theo station/timestamp; khóa duy nhất. 951 cảnh báo dùng ngưỡng rà soát của dự án được khai báo trước khi chạy full, không phải kết luận lỗi đo lường hoặc ngưỡng sức khỏe. Tất cả các giá trị đó vẫn có trong bảng hợp nhất, không clipping, IQR, xóa hay impute. Missing các cột khác cũng giữ nguyên; xem summary JSON.

Bảng hợp nhất lưu tại `data/processed/merged_unimputed_full.csv` (bỏ qua trong Git). Schema gồm cột gốc trừ `No`, thêm `timestamp`, `source_file` và `source_row` để truy vết. Hai cột nguồn không làm feature. Summary lưu dtype thực tế, seed, chính sách trùng khóa, ngưỡng rà soát, phiên bản Python/pandas và checksum raw/đầu ra.

Quy tắc: [docs/data_quality_policy.md](../docs/data_quality_policy.md). Loader từ chối xuất khi trùng khóa, kể cả bản sao giống nhau. Test kiểm tra trường hợp có mâu thuẫn và đảm bảo không tự giữ một dòng.

Lệnh kiểm tra cuối đã chạy:

```powershell
.\.venv\python.exe scripts/merge_data.py --mode smoke --overwrite
.\.venv\python.exe scripts/merge_data.py --mode full --overwrite
.\.venv\python.exe -m pytest -q --basetemp=.pytest_cache/task04-verified
git diff --check
```

`--overwrite` dùng để thay đầu ra do chính task này đã sinh khi sửa và chạy lại; không sửa raw hoặc phần việc của thành viên khác. Python portable 3.12.10 được tải vào `.venv` sau khi cho phép truy cập mạng ngoài sandbox; cài pandas/numpy/pytest để thực thi Task 04. `.venv` không commit, không đổi Python hệ thống. Dependencies dự án vẫn khai báo duy nhất trong `pyproject.toml`.

Smoke: 1.200 dòng, không lỗi/cảnh báo trong tập con. Full: 420.768 dòng, 0 lỗi và 951 cảnh báo như trên. Kết quả cuối: **28 tests passed**, gồm 27 trường hợp unit với fixture tổng hợp và một kiểm tra tích hợp trên file full đã lưu. Kiểm tra tích hợp đọc lại CSV, xác nhận timestamp, khóa, thứ tự, số missing, checksum output và checksum toàn bộ raw so với manifest. Khi chưa có dữ liệu/output cục bộ, kiểm tra tích hợp này được skip rõ ràng.

Lần chạy đầu đã phát hiện lỗi tổng trên pandas Index và lỗi console encoding khi in đường dẫn tiếng Việt; đã sửa và chạy lại smoke/full thành công. Lệnh kiểm tra nhanh bằng `python -c` từng lỗi quoting PowerShell; được thay bằng kiểm tra tích hợp trong pytest. Lần pytest đầu thiếu thư mục cha của basetemp; tạo `.pytest_cache` rồi chạy lại thành công. Những lần lỗi không được dùng để tuyên bố hoàn thành kiểm tra.

Giới hạn: audit không chứng minh mọi số đo đều đúng hoặc đã phát hiện mọi lỗi thiết bị. Cảnh báo cần đối chiếu nguồn/thiết bị nếu có thêm bằng chứng; chưa xử lý ngoại lệ, tạo target/lag, impute, fit tiền xử lý hoặc huấn luyện. Đây không phải kết quả đánh giá mô hình. Python portable hiện mới cài dependencies phục vụ task này; chưa kiểm tra toàn bộ dependencies ban đầu.

Codex hỗ trợ mã, kiểm thử và tài liệu. Commit đề xuất: `feat: merge station data and validate temporal integrity`.
