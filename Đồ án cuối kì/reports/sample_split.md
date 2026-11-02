# T05 — Kết quả tạo mẫu và temporal split

Nguồn: `data/processed/merged_unimputed_full.csv` đã được T04 chấp nhận, SHA-256
`45def94e4f4262360d1be95e3844f53db33b0a0dd9e65b3acd081ace2a11de6a`.
Không thay raw hoặc artifact T04, không huấn luyện/fit preprocessing/model.
Số liệu dưới đây là count/date audit, không phải metric thực nghiệm.

## Full

Manifest: [splits_full/split_manifest.json](splits_full/split_manifest.json).
Snapshot `2129d08dbac2b6ebe6a6c7bf12cf8188d9ea7b0069939d690e27ad5c47cf0ddc`,
tạo thực tế `2026-11-02T11:32:37.664380+00:00`, Python 3.12.10/pandas 3.0.6.

| Split | Operational | Primary | Target min | Target max |
| --- | ---: | ---: | --- | --- |
| Train | 205.977 | 204.865 | 2013-03-01 01:00 | 2015-02-28 23:00 |
| Validation | 103.287 | 102.479 | 2015-03-01 00:00 | 2016-02-29 23:00 |
| Test (count/date audit) | 102.753 | 101.836 | 2016-03-01 00:00 | 2017-02-28 23:00 |
| Tổng | 412.017 | 409.180 | — | — |

Cả 12 trạm có mẫu trong mỗi split/cohort. Operational gồm mọi target quan sát
được, primary còn yêu cầu PM2.5(t) quan sát được. 2.837 mẫu thiếu PM2.5(t) vẫn
được giữ trong operational để task fallback sau này; T05 không impute chúng.

Từ 420.768 origin, loại 8.751: 8.739 thiếu giá trị target, 12 cuối chuỗi (mỗi
trạm một), 0 thiếu timestamp target nội bộ. Lý do loại trừ nhau; tổng đối
chiếu đúng. [exclusion_summary.csv](splits_full/exclusion_summary.csv) ghi từng
trạm; [split_summary.csv](splits_full/split_summary.csv) và
[station_split_summary.csv](splits_full/station_split_summary.csv) ghi cohort,
số mẫu và khoảng thời gian. IDs/loại mẫu chi tiết nằm trong data/processed,
được manifest liên kết checksum; không commit các CSV lớn.

Holdout label-cutoff audit pass cho cả hai cohort: train có nhãn cuối
2015-02-28 23:00 đúng origin validation đầu; train+validation có nhãn cuối
2016-02-29 23:00 đúng origin test đầu. Cho phép bằng nhau vì đã nhận số đo t
trước dự báo. Tất cả bản ghi kiểm tra ghi `fitted=False`, không có refit thực.
Guard CV nghiêm ngặt đã kiểm thử bằng fixture, chưa chạy CV trên dữ liệu thật.

## Smoke và kiểm tra

Smoke dùng 1.200 origin prefix T04: 1.179 operational/primary, loại 21 (9
target thiếu, 12 cuối prefix), chỉ có train; validation/test count 0 và ngày
null. Không dùng kết quả này làm kết quả full. Manifest:
[splits_smoke/split_manifest.json](splits_smoke/split_manifest.json), snapshot
`32b77db6bb3f97f4eeca3cebd15f7cf6950a3d47718d8d1218aba2dacd48d9e1`.

Lệnh thực tế và kiểm thử:

```powershell
.\.venv\python.exe scripts/build_samples.py --mode smoke
.\.venv\python.exe scripts/build_samples.py --mode full
.\.venv\python.exe -m pytest tests/test_samples.py -q --basetemp=.pytest_cache/t05-samples-release
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t05-final-regression
git diff --check
```

31 kiểm thử T05 pass: hai trạm, join đúng giờ, giờ khuyết, target thiếu,
origin thiếu, cuối chuỗi, boundary leap-day, ID ổn định/không giao nhau, cutoff
nhãn holdout/CV, cấu hình sai, smoke null, manifest và checksum/reuse CLI;
clone chỉ có báo cáo có thể tái tạo bằng output-tag mà không ghi đè.
Lần đầu phát hiện NaN ở khoảng ngày split rỗng, đã sửa thành JSON null.

Regression tổng hợp: **93 passed, 1 deselected**; loại kiểm tra tích hợp T04
đọc toàn bộ dữ liệu vì đã xác minh ở T04 và không cần cho task này. Đối chiếu
artifact thực chỉ dùng checksum và IDs/trạm/ngày/cờ cohort: ID duy nhất, các
split không giao nhau, origin/target đúng một giờ và đúng trạm, exclusions đối
chiếu đủ input, mốc split và label cutoff đúng. Smoke IDs là tập con full.
Chạy lại cả smoke/full trả `Verified existing T05 snapshot`, không ghi đè.
Raw/T04 và Experiment Log chính thức không đổi; không tính thống kê giá trị
target hoặc metric test trong bước xác minh này.

Lần chạy đầu bị sandbox chặn tạo thư mục tạm; đã dừng và bổ sung fail-fast.
Sau đó phát hiện thư mục private của tempfile giữ ACL khi rename; thay bằng
staging kế thừa quyền cha, bảo toàn bốn output T05 cũ trong
`artifacts/t05_superseded/permissions_v1` rồi tạo snapshot hiện hành ở trên.
Đây là sửa quá trình xuất bản dữ liệu, không tạo run/lịch sử mô hình giả.
Khi bổ sung output-tag để tái lập trên clone mới, bảo toàn output trung gian
ở `artifacts/t05_superseded/output_tag_v1` và tạo bản cuối. Đã đối chiếu:
membership IDs và checksum mọi CSV giữa hai bản giữ nguyên; chỉ metadata
code/signature/thời điểm trong manifest thay đổi đúng lần tạo thực tế.

Giới hạn: chưa fit, EDA, CV/tuning hoặc tính metric train/validation/test; chưa
kiểm tra độ trễ fit/phát hành trong vận hành. Timestamps giữ giờ nguồn naive,
không tự gắn UTC. Cần giữ dataset/IDs cùng manifest hoặc tái tạo bằng đúng
input/config/code. Các output thiếu hoặc khác checksum không tự ghi đè.
