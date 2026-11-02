# T01 — Xác minh cấu trúc và môi trường hiện có

Ngày kiểm tra: 02/11/2026, Windows, CPython portable 3.12.10 tại
`.venv/python.exe`; không phải venv chuẩn. Issue T01 gốc: #2 (đã đóng).
Đây là kiểm tra môi trường hiện tại, không dựng lại lịch sử cài đặt trước đây.
Không tải lại dataset, chạy merge/audit, huấn luyện hoặc mở test set.

## Bảng xác minh

| Hạng mục | Kết quả thực tế |
| --- | --- |
| Cấu trúc | Đủ `src/beijing_air`, `scripts`, `notebooks`, `configs`, `tests`, `data/raw`, `data/processed`, `artifacts`, `reports/figures`, `docs`, `app`; không tạo thư mục tương đương |
| Python/package | Khai báo `>=3.10`; thực chạy 3.12.10; package `beijing-air-quality`, layout `src` |
| Dependencies | 9 dependency trong `pyproject.toml` khớp danh sách kiểm tra import; không thêm khai báo trùng |
| Cấu hình | `seed=42`, `horizon_hours=1`, mặc định smoke, hỗ trợ smoke/full; mọi path tương đối đều trỏ tới thư mục hiện có |
| Git ignore | Xác minh raw/processed data, model `.joblib`/`.pkl`/`.onnx`, `.venv`, `__pycache__`, `.pytest_cache`, `.env`, `.env.production` bị ignore; data/artifacts chỉ theo dõi `.gitkeep` |
| PowerShell | Phân biệt venv chuẩn và portable; không tạo venv chồng lên portable; hướng dẫn gọi đúng interpreter và cài build backend |
| Cài/import | PASS: editable install exit 0, pip check không lỗi; package dự án và 9 dependencies đều import được |
| Notebook/Streamlit CLI | PASS: `python -m notebook --version` trả 7.6.4; `python -m streamlit --version` trả 1.66.1; không khởi chạy server |
| Regression T04/logger | PASS: 47 passed, 1 deselected, chỉ fixture tổng hợp; không chạy kiểm tra tích hợp đọc dữ liệu full |

## Phát hiện và cách xử lý

Lúc bắt đầu, môi trường chỉ có pandas/numpy/pytest cùng dependencies phụ của
T04; `check_imports.py` báo thiếu sklearn, matplotlib, seaborn, joblib, streamlit,
jupyter. `beijing_air` import được nhờ `../src` trong `.venv/python312._pth`,
nhưng `pip show beijing-air-quality` chưa có metadata package đã cài.

`py -0p` báo `No installed Pythons found!`; lệnh tạo venv bằng Python Launcher
chưa chạy được trên máy này. Dùng lại Python portable sẵn có, không cài Python
hệ thống, tạo môi trường trùng hoặc thay đổi source cấu trúc dự án.

Lệnh `pip install -e .` mặc định đã thử và thất bại ở build isolation:
`Cannot import 'setuptools.build_meta'`. Đã cài build backend vào portable và
dùng `--no-build-isolation`. `scripts/check_imports.py` được bổ sung kiểm tra
metadata và in phiên bản/interpreter/source path. Cài đặt cuối cùng được xác
minh bằng exit code 0 và `pip show beijing-air-quality`: Location nằm trong
`.venv/Lib/site-packages`, Editable project location trỏ đúng đồ án. Không chỉ
dựa vào import thông qua source path để kết luận cài thành công.

## Phiên bản đã kiểm tra

| Package | Phiên bản |
| --- | --- |
| beijing-air-quality | 0.1.0 (editable) |
| pandas | 3.0.6 |
| numpy | 2.5.4 |
| scikit-learn | 1.9.1 |
| matplotlib | 3.11.2 |
| seaborn | 0.13.2 |
| joblib | 1.6.0 |
| streamlit | 1.66.1 |
| pytest | 9.1.1 |
| jupyter | 1.1.1 |

Công cụ cài: pip 26.2.1, setuptools 84.2.1, wheel 0.48.0. Giữ nguyên khai báo
dependencies trong `pyproject.toml` vì đã đầy đủ; không tạo requirements song song.

## Lệnh thực tế

Từ thư mục `Đồ án cuối kì/`:

```powershell
.\.venv\python.exe --version
.\.venv\python.exe -m pip --version
.\.venv\python.exe -m pip install -e . # Lần thử mặc định thất bại như trên
.\.venv\python.exe -m pip install "setuptools>=68" wheel
.\.venv\python.exe -m pip install --no-build-isolation -e .
.\.venv\python.exe -m pip check
.\.venv\python.exe scripts/check_imports.py
.\.venv\python.exe -m pip show beijing-air-quality
.\.venv\python.exe -m notebook --version
.\.venv\python.exe -m streamlit --version
.\.venv\python.exe -m pytest tests -q -k "not test_saved_full_output_matches_audit_and_raw_checksums" --basetemp=.pytest_cache/t01-verification
git diff --check
```

Các kiểm tra không mở dữ liệu: `Test-Path` cho các thư mục, đối chiếu cấu hình
JSON và pyproject, `git check-ignore --no-index --verbose` với tên giả
`T01_TEST_ONLY`, `git ls-files` để kiểm tra dữ liệu/artifacts được theo dõi.
Tên giả chỉ dùng làm đối số kiểm tra ignore; không sinh dataset hoặc run.

`check_imports.py` báo OK cho 10 module, `pip check` trả
`No broken requirements found.`. Pip cảnh báo `.venv/Scripts` không nằm trong
PATH; các lệnh dùng trực tiếp interpreter nên không phụ thuộc PATH. Kiểm tra
cú pháp script bằng `compile()` không ghi bytecode pass; `py_compile` từng gặp
quyền ghi cache trong sandbox, không phải lỗi cú pháp của mã.

## Giới hạn

Chưa xác minh cài mới trên máy sạch, Python 3.10/3.11 hoặc Linux/macOS.
`pyproject.toml` không pin dependency; bảng phiên bản kiểm tra là snapshot của
môi trường hiện tại, chưa phải lockfile. Không đánh đồng import thành công với
pipeline/model hoạt động đúng. Không phát sinh thực nghiệm mô hình.

Codex hỗ trợ kiểm tra, hoàn thiện hướng dẫn và script kiểm tra môi trường.
