# MK01 — Bộ tài liệu giữa kỳ từ minh chứng

Issue #26; T12/PR #25 đã merge. Người dùng xác nhận tự bổ sung nhóm và cho phép
merge riêng MK01; MK02 chỉ mở PR để người dùng merge sau. Không mở test hoặc
huấn luyện model mới trong hai task tài liệu.

## File và trạng thái

- [DOCX 17 trang](../reports/midterm/NhomXX_DuBaoPM25_BacKinh_GiuaKy.docx).
- [PPTX 15 slide](../reports/midterm/NhomXX_DuBaoPM25_BacKinh_GiuaKy.pptx).
- [PDF báo cáo](../reports/midterm/previews/report.pdf),
  [PDF slide](../reports/midterm/previews/slides.pdf) và contact sheets cùng thư mục.
- [Chỉ mục bảng/hình](../reports/midterm/figure_table_index.csv),
  [nguồn/hash/run IDs](../reports/midterm/traceability.json),
  [snapshot dữ liệu báo cáo](../reports/midterm/evidence.json).
- [Mục nhóm cần tự bổ sung](../reports/midterm/NEEDS_GROUP_INPUT.md).

**BẢN NHÁP — CHƯA SẴN SÀNG NỘP.** Không có danh sách thành viên, MSSV,
phân công/đóng góp và rubric riêng được xác nhận. Các ô giữ [CẦN BỔ SUNG],
không suy từ Git. Sửa `configs/midterm.json` và filename_stem khi nhóm đã chốt,
hoặc điền trực tiếp rồi kiểm/render lại. Không coi tên NhomXX là số nhóm thật.

Nội dung theo CRISP-DM: Input/Output, dữ liệu/thuộc tính/target, EDA train,
preprocessing, baseline/model, kết quả validation/CV, vòng thử–nhận xét–sửa,
khó khăn/phần còn lại, đóng góp cần xác nhận, nguồn và AI disclosure. Trọng tâm
T09/T10; T11 tuning không cải thiện validation và T12 A/B/C được bổ sung trung
thực. RF A được khóa bằng validation, chưa có weights triển khai/test metric.

## Tạo và kiểm lại

Từ root đồ án, dùng Python môi trường đang có; venv chuẩn thay đường dẫn
portable bằng `.\.venv\Scripts\python.exe`:

```powershell
.\.venv\python.exe -m pip install -e ".[midterm]"
.\.venv\python.exe scripts/build_midterm.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/render_midterm.ps1 -LibreOfficePath 'C:\Program Files\LibreOffice\program\soffice.com'
.\.venv\python.exe scripts/verify_midterm.py
```

Máy tạo tài liệu: DOCX render bằng LibreOffice 26.8.2.2, PPTX bằng Microsoft
PowerPoint 16.0. Word mở được DOCX nhưng tự động export bị treo, nên không báo
đã render thành công bằng Word. LibreOffice lấy từ máy chủ chính thức và kiểm
SHA-256; chỉ giải nén administrative image trong thư mục tools ignored, không
đưa binary Office/LibreOffice vào Git/gói. Renderer dùng profile tạm riêng,
không sửa file gốc hoặc đóng tài liệu người dùng khác.

Kiểm thực tế: 49 hồ sơ completed thật, 200 artifact checksum/size, 43 file
predictions tính lại và các CV pooled/mean/std; cùng validation primary IDs.
DOCX/PPTX CRC mở được, 19 bảng DOCX, 15 slide; các MAE chính khớp giữa hai
tài liệu. PDF17/15 trang, text slide đầy đủ, dấu tiếng Việt/placeholder/bounds
pass. Đã xem toàn bộ contact sheets và các trang5/16, slide10 ở độ phân giải
đầy đủ; không thấy tràn/cắt nội dung. Ledger giữ SHA như trước task.

Chi tiết: `build_manifest.json`, `verification.json`, `previews/render_manifest.json`
và `visual_review.json`. Hình giữa kỳ vẽ lại từ bảng artifact với font lớn;
hình gốc T06/T10/T11/T12 vẫn giữ nguyên. Chưa cấu hình CI. Không chạy lại bộ
model tests trong MK01 chỉ để tạo số kiểm thử; con số243 trong nội dung là lịch
sử T12, được ghi rõ. Chưa kiểm môi trường Python sạch tại MK01; thuộc kiểm MK02.
