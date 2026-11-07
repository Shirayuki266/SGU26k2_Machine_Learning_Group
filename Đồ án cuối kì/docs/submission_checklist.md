# MK02 — BẢN NHÁP giữa kỳ, chưa sẵn sàng nộp

Nhóm tự bổ sung số nhóm, họ tên–MSSV, phân công/đóng góp thật, trường/lớp,
giảng viên và yêu cầu/hạn nộp. Xem `source/reports/midterm/NEEDS_GROUP_INPUT.md`.
Không suy tên thành viên hoặc tỷ lệ đóng góp từ lịch sử Git. Chưa đối chiếu được
rubric riêng của thầy vì chưa được cung cấp. Không tự nộp Classroom.

## Nội dung gói ZIP

| Thư mục | Nội dung và trạng thái |
| --- | --- |
| `report/` | DOCX 17 trang, PDF đã render; còn [CẦN BỔ SUNG] |
| `slides/` | PPTX 15 slide, PDF đã render; thống nhất số liệu với báo cáo |
| `source/` | Source PY, notebook IPYNB, tests, config, dependencies, docs, artifacts và báo cáo gốc |
| `experiment_logs/` | Excel chỉ mục 49 hồ sơ thật; CSV chuẩn ở `source/experiments/experiment_log.csv` |
| `figures/` | PNG gốc và hình giữa kỳ; chỉ mục/truy vết ở `source/reports/midterm/` |
| `resources/` | Manifest từng file/SHA-256, nguồn tải/license/checksum raw, constraints và QA |

49 hồ sơ gồm smoke, search parent, candidate, fold và final run; không phải 49
mô hình độc lập. Tất cả config/metadata/metrics/notes và 200 artifact đăng ký
được giữ nguyên, gồm predictions train/validation/CV. CSV giữ liên kết tương
đối tới `../artifacts/`; đừng tách riêng CSV khỏi cây `source/`.

Các đường dẫn trong tài liệu này tính từ root ZIP, không từ thư mục docs của repo.
Gói có train samples và train/validation sample IDs để kiểm lại EDA. Không có
raw lớn, validation/test sample measurements hoặc test predictions. Audit số
mẫu/khoảng ngày test đã có từ T05 vẫn được giữ. Test chưa được mở để chấm điểm.
`resources/reproduction_scope.json` liệt kê file T05 cố ý không kèm và phạm vi
tái lập. Các manifest lịch sử vẫn giữ checksum của file không kèm; đây không
phải yêu cầu mở test hoặc tải lại dữ liệu trong MK02. Cache feature T07 có thể
tạo lại bằng recipe khi task tương lai cần; chưa kiểm tái huấn luyện full.

Chưa có model weights đã serialize trong các run cũ: đây là mục **không áp
dụng**, không giả tạo file model. Recipe đã khóa ở
`source/reports/ablation/frozen_model.json`; T13 refit và test chưa thực hiện.

## Cài và kiểm tra từ ZIP bằng PowerShell

Giải nén ZIP trước. Từ thư mục `NhomXX_DuBaoPM25_BacKinh_GiuaKy`:

```powershell
Set-Location source
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -c ..\resources\constraints.txt ".[midterm]"
.\.venv\Scripts\python.exe scripts/verify_midterm.py --office-only --output artifacts/mk02_office_check.json
.\.venv\Scripts\python.exe scripts/run_eda_notebook.py --mode full --output-tag mk02_replay_01
```

Mỗi lần EDA dùng `--output-tag` **mới**; notebook nguồn và lịch sử run không
bị ghi đè. Lệnh chỉ đọc train, không huấn luyện mô hình hoặc ghi Experiment Log.
Không cần tải raw để thực hiện hai lệnh kiểm trên. Nếu máy thiếu Python/venv
chuẩn, dùng Python 3.12 phù hợp; đường dẫn portable của máy tác giả khác venv.

Kiểm đầy đủ ZIP từ source (đích giải nén phải chưa tồn tại):

```powershell
.\.venv\Scripts\python.exe scripts/verify_submission.py <duong-dan-ZIP> --extract-to artifacts/mk02_check_01 --output artifacts/mk02_check_01.json
```

Validator kiểm CRC/path/SHA, 49 run, 200 artifact, tính lại 43 file predictions,
CV pooled/mean/std, cùng validation IDs, link CSV/Excel, metric và nguồn bảng/hình
trong Office. Đây là kiểm lại kết quả đã chạy; không gọi fit hoặc tạo run mới.
SHA-256 toàn ZIP nằm ở file `.zip.sha256` bên cạnh ZIP; file manifest không
tự băm chính nó. Giữ tên thư mục và đường dẫn tương đối khi giải nén.

## Dữ liệu, tái lập và kiểm soát lịch sử

Nguồn chính thức: [UCI 501](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data),
DOI 10.24432/C5RK5G, CC BY 4.0. `resources/data_provenance.json` có URL tải,
ngày tải đã ghi nhận và SHA-256 ZIP/từng CSV PRSA2017; không dùng liên kết local.
Hướng dẫn tải thủ công/CLI trong `source/README.md` và `source/scripts/download_uci.ps1`.
Không tải dataset một trạm thay thế. Các lệnh huấn luyện trong README nguồn là
hướng dẫn task tương lai; MK02 không chạy chúng.

Muốn tạo lại tài liệu sau khi bổ sung nhóm, sửa `source/configs/midterm.json`,
đọc `source/docs/midterm_deliverables.md`, tạo lại DOCX/PPTX và render/kiểm hình.
Muốn đóng gói lại dùng `scripts/package_midterm.py` từ source; cần constraints
ở `reports/submission/constraints.txt` (chép từ `../resources/constraints.txt`).
Generator giữ nguyên run history, không sửa timestamp/metric cũ. Sau khi sửa
nhóm phải kiểm lại và tạo ZIP/checksum mới; bản ZIP hiện tại vẫn là bản nháp.

## Checklist và hạn chế

- [x] DOCX/PPTX, PDF render, PNG, nguồn/run IDs và bảng hình có trong gói.
- [x] Source/config/dependencies, log CSV/Excel và dữ liệu train để chạy EDA.
- [x] Dataset có URL/license/checksum; model weights ghi rõ chưa có.
- [x] Không `.git`, venv, cache, token/mật khẩu hoặc raw lớn trong gói.
- [ ] Điền và xác nhận nhóm/phân công/đóng góp thật, yêu cầu riêng của thầy.
- [ ] Nhóm review bản Office sau khi tự bổ sung; xác nhận đủ điều kiện nộp.

Kết quả kiểm tự động thực tế nằm ở `resources/qa.json` và bản kiểm ZIP bên
ngoài. Phân biệt PASS với chưa chạy trong JSON. Kiểm môi trường sạch chỉ có thể
xác nhận gói Python cách ly trên cùng Windows; chưa phải máy/OS hoàn toàn mới.
Đã kiểm cài/import bằng Python 3.12.10 có site-packages mới; `pip check` pass.
Do Python embedded không nhận build isolation chuẩn, lệnh thực dùng cài thêm
setuptools/wheel/pip trong runtime tạm rồi `pip install --no-build-isolation`.
Venv chuẩn trong ví dụ trên chưa được chạy trực tiếp; chưa khẳng định đã kiểm.
Constraints ghi phiên bản trong runtime đã kiểm trên Windows/Python 3.12,
không phải lockfile chung mọi nền tảng. Không thay venv hiện có hoặc Python hệ thống.
EDA full train chạy đủ 13 cell, kiểm lại 14 bảng/9 PNG và 14 bảng khớp lịch sử.
Minh chứng mới có tag `mk02_clean_20261103_01`; QA tách khỏi Experiment Log.
Sáu kiểm tra ZIP tổng hợp pass; lệnh thực và giới hạn lưu trong QA JSON.
Renderer DOCX là LibreOffice 26.8.2.2, PPTX là PowerPoint 16.0; Word export tự
động từng bị treo, không báo đã render bằng Word. Chi tiết kiểm bố cục trực
quan giữ ở `source/reports/midterm/visual_review.json`.

ZIP chứa predictions thực nên lớn và không commit vào Git. PR giữ generator,
manifest/checksum/checklist và QA; ZIP bàn giao trong `reports/submission/` trên
máy làm việc. Không có link upload công khai cho ZIP; người dùng tự nộp sau review.

## T15 — hồ sơ cuối kỳ (bản nháp)

T15 đã tạo report DOCX 5 chương, presentation 18 slide, poster PPTX/PNG, chỉ
mục bảng/hình, traceability, verification, tham khảo và related-work notes.
Hướng dẫn sinh/kiểm ở [final_deliverables.md](final_deliverables.md); đầu ra
ở `reports/final/`.

- [x] Có tài liệu tham khảo học thuật/kỹ thuật và ghi chú nghiên cứu liên quan.
- [x] Số liệu T13/T17b gắn nguồn/run; không train, tune, refit hoặc đọc test thô.
- [x] Ghi nhận QA protected: ledger và `reports/midterm/` không được ghi bởi generator.
- [ ] Thành viên, MSSV, vai trò, phần việc và tổng đóng góp 100% do nhóm xác nhận.
- [ ] Rubric, file/trang bài giảng và kích thước poster theo giảng viên.
- [ ] Rà soát trực quan toàn bộ Office output; quay video thật và hoàn thiện T16/package.

**Trạng thái hiện tại: BẢN NHÁP, CHƯA SẴN SÀNG NỘP.** Artifact có sai khác so
với hai số nhóm theo trạm/mùa được nêu trong yêu cầu; xem
`reports/final/verification.json` và `reports/final/NEEDS_GROUP_INPUT.md`.
