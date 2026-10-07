# Beijing Air Quality

Dự án học máy dự báo chất lượng không khí tại Bắc Kinh, với chân trời dự báo ban đầu là 1 giờ. Task 01 chỉ khởi tạo cấu trúc, môi trường và cấu hình; chưa tải dữ liệu, chưa huấn luyện mô hình.

## Cấu trúc

```text
src/beijing_air/   Package Python chính
scripts/           Script kiểm tra và chạy các bước xử lý
notebooks/         Notebook khám phá dữ liệu
configs/           Cấu hình dự án
tests/             Kiểm thử
data/raw/          Dữ liệu gốc (không commit)
data/processed/    Dữ liệu đã xử lý (không commit)
artifacts/         Model và kết quả sinh ra (không commit)
reports/figures/   Biểu đồ cho báo cáo
docs/              Tài liệu dự án
app/               Ứng dụng Streamlit
```

Dependencies được khai báo duy nhất trong `pyproject.toml`: pandas, numpy, scikit-learn, matplotlib, seaborn, joblib, streamlit, pytest và Jupyter. Package dùng cấu trúc `src`; cài editable để import `beijing_air` từ môi trường dự án.

## Tạo môi trường trên Windows PowerShell

Cài Python 3.10 trở lên và Python Launcher (`py`), sau đó mở PowerShell tại thư mục chứa README này:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python scripts/check_imports.py
```

Nếu PowerShell chặn kích hoạt môi trường, có thể chạy trực tiếp interpreter trong môi trường:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts/check_imports.py
```

Mở notebook bằng `python -m jupyter notebook`. Thư mục `tests/` dành cho các kiểm thử khi bổ sung chức năng; Task 01 chưa có logic xử lý dữ liệu cần kiểm thử.

## Cấu hình

`configs/default.json` dùng JSON chuẩn, không cần thêm dependency đọc YAML. Giá trị mặc định: `seed=42`, `horizon_hours=1`, `mode="smoke"`. Hai chế độ dự kiến là `smoke` (chạy nhanh trên dữ liệu nhỏ) và `full` (chạy đầy đủ); pipeline sẽ được triển khai trong các task sau. Các đường dẫn dữ liệu và đầu ra được tính từ thư mục gốc dự án này.

Các thư mục dữ liệu và artifacts giữ `.gitkeep` để bảo toàn cấu trúc trong Git, còn nội dung sinh ra và model nhị phân được bỏ qua.

Commit đề xuất: `chore: 07/10/2026/initialize air quality project structure`
