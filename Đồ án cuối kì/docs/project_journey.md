# NB01 — Notebook minh chứng hành trình T01–T14

Issue #42, người phụ trách hoanglecodingmachine, branch
`docs/nb01-project-journey`. Đây là tài liệu đọc kết quả đã có, không phải
thực nghiệm hay notebook History từng hủy trước đây. Không triển khai T15/T16.

## Đọc kết quả

- [Notebook có output](../notebooks/PM25_Project_Journey_T01_T14.ipynb).
- [HTML có ảnh nhúng](../reports/notebook/PM25_Project_Journey_T01_T14.html).
- [Bản đồ mã tự sinh](notebook_code_map.md): vị trí AST inclusive, commit gần
  nhất của file, test có thật và run/artifact liên quan.
- [Kiểm chứng](../reports/notebook/journey_checks.csv),
  [kiểm kê/SHA](../reports/notebook/journey_inventory.csv),
  [xác minh nội dung](../reports/notebook/journey_verification.json),
  [thực thi](../reports/notebook/journey_execution.json).

Mỗi task có sáu phần: mục tiêu, quyết định, mã nguồn, bằng chứng, nhận xét,
kết luận/giới hạn. Bảng vai trò file giải thích file nào triển khai phương
pháp, file nào cấu hình, file nào ghi kết quả và kết quả ấy chứng minh gì.
Không tự gọi file kế thừa là file tạo mới ở task đó. T01 kiểm import ra
terminal và lưu biên bản; T02 ra đặc tả; T08 ra factories/kiểm fixture, chưa
ra một model full. Audit/EDA không giả làm log mô hình; smoke tách full.

T13 artifact, chỉ đọc: test chỉ từ predictions/metrics/hình T13 đã lưu.
Không đọc raw/processed samples, load weights hoặc inference mới; T14 chỉ
hiển thị QA và ảnh đã chụp. Demo QA hàng đầu và screenshot có origin khác
nhau, được chú thích rõ, không ghép chúng thành một phép đối chiếu cùng mẫu.

Ledger hiện có53hồ sơ, gồm49 trước T13 +4 T13. Hồ sơ cha/candidate/fold/smoke
không phải53model độc lập. Bảng giữ alpha kém, Ridge kém MAE, tuning chưa
cải thiện validation và C RMSE kém B. Lock RF A từ validation vẫn giữ nguyên.
Issue #35 đã sửa qua PR #37; notebook đọc changelog, không sửa artifact cũ
hay chạy lại test để che phát hiện. Một số câu “chưa test/chưa merge” trong
văn bản cũ là snapshot lịch sử, không phải trạng thái hiện tại.

## Chạy lại từ thư mục đồ án

Sau khi cài môi trường theo README (`pip install -e .`, Python>=3.11;
portable hiện có dùng Python3.12.10), chạy:

```powershell
.\.venv\python.exe scripts/build_project_journey.py --execute
```

CLI dựng notebook, gọi `python -m nbconvert --to notebook --execute --inplace`
trong một kernel mới, giữ output và xuất HTML bằng HTMLExporter. Kernelspec
tạm chỉ nằm trong `artifacts/nb01_work/` ignored; notebook lưu kernelspec
`python3` chung, không nhúng đường dẫn interpreter cá nhân. Đường dẫn trong
sản phẩm tính từ thư mục đồ án chứa `pyproject.toml`.

Nếu kernel python3 đã đúng môi trường, có thể chạy trực tiếp:

```powershell
.\.venv\python.exe -m nbconvert --to notebook --execute --inplace notebooks/PM25_Project_Journey_T01_T14.ipynb
```

Nên dùng CLI để có audit hook chặn mở `data/`, model/SQLite và ghi
experiments/config/run. CLI so SHA các file lịch sử trước–sau, quét đường
dẫn cá nhân/chuỗi giống secret và kiểm output lỗi. Chỉ ghi notebook, HTML,
code map và bảng QA NB01. Cờ `RERUN_LIGHT=False`, `RERUN_HEAVY=False`; không
có nhánh gọi training/tuning. Kiểm chứng metric từ predictions đã lưu là
thao tác đọc nhẹ, luôn chạy và ghi rõ không phải artifact/run gốc.

Không cần dataset hoặc model bundle để đọc/chạy NB01. Cần source, ledger,
metrics, predictions và ảnh đã lưu trong repo. Thiếu file thì ghi chính xác
đường dẫn đã tìm; không dựng metric/ảnh thay thế. Đối chiếu dung sai1e-6,
giá trị KHÁC giữ nguyên và đưa vào báo cáo QA. Mean±std fold chỉ mô tả;
pooled dùng OOF hoặc trọng số số mẫu theo hạ tầng T17a đã merge, không gọi
exporter T17a hay ghi đè bảng T17a.

## Kiểm tra và giới hạn

```powershell
.\.venv\python.exe -m pytest tests/test_project_journey.py tests/test_experiment_summary.py -q -p no:cacheprovider --basetemp=artifacts/nb01_TEST_helpers
```

Fixture đều TEST_ONLY; kiểm AST cập nhật dòng khi source đổi, chặn dữ liệu/
weights/path escape, missing/Unicode, giới hạn trích mã và test names có thật.
Không tự nhận các test lịch sử trong code map vừa được chạy lại; đó là mapping
theo symbol/import module, không phải call graph. Đọc kết quả thực thi cụ thể
ở `journey_execution.json`; thời gian mục tiêu<5phút, không bảo đảm mọi máy.

Bài giảng/rubric gốc, thông tin thành viên/MSSV/% và người đọc hiểu/review
[CẦN BỔ SUNG]. Video thật chưa có; model bundle chưa có URL công khai là
hạn chế T14, không cản việc đọc NB01. Chưa kiểm mọi OS/máy sạch, mọi notebook
cũ hoặc chạy lại toàn bộ search; NB01 chỉ kiểm kernel sạch cho notebook này.
