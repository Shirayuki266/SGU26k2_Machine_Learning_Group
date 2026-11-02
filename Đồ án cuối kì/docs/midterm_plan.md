# Kế hoạch và checklist giữa kỳ — MK01/MK02

Tên/phạm vi do người dùng chốt ngày 02/11/2026. **MK01 tạo cả DOCX và PPTX;
MK02 kiểm tra và đóng gói**, không tách nhầm hai mã thành báo cáo và slide.
T02 chỉ chuẩn bị checklist. MK01/Issue #26: [DOCX17trang và PPTX15slide](midterm_deliverables.md) từ artifact T01–T12 đã render/kiểm và merge PR #28. Bản nháp còn [CẦN BỔ SUNG] do người dùng tự điền nhóm/rubric. MK02/Issue #27 kiểm và đóng gói riêng; người dùng merge MK02.

Hiện có T01 xác minh môi trường, đặc tả T02, manifest/audit T03–T04 và logger
T04-LOG, target/split và count/date audit T05, EDA train T06 có bảng/PNG gốc,
T07 có feature A/B nhân quả, registry và missing train; T08 có factories
preprocessing và kiểm tra fixture. T09 có [baseline full validation thật](baseline_results.md),
predictions/log/metric/hình/bundle; T10 có [Ridge/RF A full](initial_findings.md),
so persistence cùng IDs, chi phí và nhận xét. T11 có [Ridge A temporal tuning](tuning_findings.md),
alpha0.1 từ CV chưa cải thiện validation so T10. T12 có [A/B/C và RQ2](ablation_findings.md),
C12 nhóm cải thiện Ridge nhưng RF A vẫn tốt nhất MAE; khóa công thức chưa refit/test.
Ưu tiên tiến độ thực tế đến T10; có T11/T12 thì bổ sung. Không bắt buộc tuning,
test cuối hoặc demo và **không mở test để lấy số liệu giữa kỳ**. Phải nêu thiếu,
không điền bảng giả.

## 1. MK01 — Nội dung DOCX/PPTX

| Yêu cầu | CRISP-DM/task | Checklist bằng chứng | Hiện có |
| --- | --- | --- | --- |
| Đề tài/thành viên/phân công | Business Understanding/quản lý | [ ] Tên/MSSV/số nhóm/phân công và đóng góp xác nhận | Chưa đủ thông tin nhóm |
| Bối cảnh/mục tiêu/Input–Output/hồi quy | T02 | [x] Đúng t+1/cùng trạm, µg/m³, input tới t, giả định số đo t, RQ1/2/3 | Đã đưa vào DOCX/PPTX MK01 |
| Dữ liệu/nguồn/số mẫu/thuộc tính/target | Data Understanding, T03–T05 | [x] Trích nguồn/manifest/audit; phân biệt raw/supervised | DOCX/PPTX có bảng nguồn/split và truy vết B01/B02 |
| EDA train | T06 | [x] Missing/phân phối/quan hệ/trạm/thời gian, hình và quyết định | DOCX/PPTX có hình chọn từ 14 bảng/9 PNG và [nhận xét T07/T08](eda_findings.md) |
| Feature/pipeline | Data Preparation, T07–T08 | [x] A/B/C, train-only và trạng thái thực chạy | Có sơ đồ pipeline; chưa lưu weights triển khai được ghi rõ |
| Baseline/model/protocol | Modeling/Evaluation, T09–T10 | [x] Persistence/fallback, Ridge/RF A, MAE/RMSE/R², IDs và split | Bảng/hình validation primary N=102.479, có run_id/mode |
| Kết quả/nhận xét bước đầu | T09–T12 | [x] Validation/CV có nguồn, tách smoke/full | Đã đưa vào DOCX/PPTX và kiểm khớp artifact |
| Vòng thử–nhận xét–sửa | Mọi giai đoạn/T04-LOG | [x] Giả thuyết/thay đổi/tham chiếu/quyết định, giữ kết quả kém | T11 chưa cải thiện; T12 B/C giúp Ridge nhưng RF A vẫn MAE tốt hơn |
| Tiến độ/khó khăn/kế hoạch | Project plan | [x] Đã làm/chưa làm, tài nguyên/giới hạn | T13–T16 là kế hoạch, chưa mở test |
| Đóng góp/nguồn/AI disclosure | Tất cả sản phẩm | [ ] Đóng góp thật chờ nhóm điền; nguồn/AI disclosure đã có | Không đoán MSSV/tỷ lệ từ Git |

Ô chưa tick là checklist bàn giao **tài liệu MK01**, không phủ nhận source/audit
đã có. Khi thiếu kết quả nêu rõ thiếu và kế hoạch; không coi đó là đã đủ mọi
rubric chấm điểm. Chưa có rubric chính thức trong repo, đối chiếu khi được cấp.

DOCX/PPTX theo logic CRISP-DM và bao phủ bảng trên. Giữa kỳ không thay báo cáo
cuối kỳ 5 chương. Không suy đóng góp từ Git author/người chạy script. Mỗi
bảng/hình có nguồn audit hoặc run_id; hình gốc có trục/đơn vị/chú thích, không
gọi hình minh họa là kết quả thực nghiệm.

## 2. MK02 — Đối chiếu và đóng gói

- [x] DOCX/PPTX MK01 mở được, nhất quán nội dung/phiên bản; bảng/hình đối chiếu
  artifact/run_id/mode và split train/validation/CV.
- [x] Source .py, notebook .ipynb nếu có, config/dependencies và README có lệnh
  thật; notebook gọi module và tái lập được phần đã triển khai.
- [x] Kèm experiments/experiment_log.csv và hồ sơ run thật trong
  artifacts/experiments/ khi có; link config/metrics/predictions/hình hợp lệ.
  Chưa có run thì CSV header và báo thiếu, không tạo run mẫu.
- [x] Kèm hình/bảng gốc EDA/kết quả và sơ đồ pipeline thực nếu đã có; chỉ mục
  truy vết tài liệu → audit/run → artifact.
- [x] Dataset hoặc nguồn/hướng dẫn tải và kiểm checksum; không tải lại chỉ để
  đóng gói, không đưa data lớn vào Git.
- [x] Model/pipeline đã huấn luyện nếu có và cần bàn giao, kèm load/inference;
  chưa có model phải ghi rõ, không tạo model giả.
- [x] Đối chiếu source–config–log–metric–predictions–hình–DOCX/PPTX–README;
  ghi kiểm tra thực chạy/kết quả/giới hạn, không báo lệnh chưa chạy pass.
- [x] Loại secrets, .venv/cache khỏi gói; artifact không commit có đường dẫn
  truy cập/cách tạo lại, nguồn và license phù hợp.
- [ ] Xác nhận nhóm XX, tạo NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip và kiểm tra
  giải nén/đường dẫn/hướng dẫn sử dụng. ZIP nháp đã có và kiểm được; số nhóm chưa xác nhận nên mục này còn thiếu.

Tuning/test/demo không phải điều kiện hoàn thành MK01/MK02. Nếu nêu T13, ghi
đó là kế hoạch refit train+validation sau khóa rồi test, chưa phải kết quả.
Không mở test mới để bổ sung bảng giữa kỳ.

## 3. Hoàn thành và bàn giao

MK01 hoàn thành khi DOCX/PPTX phản ánh đúng tiến độ, nguồn/truy vết và mục thiếu
rõ ràng. MK02 hoàn thành khi có gói và bằng chứng kiểm tra đối chiếu/tái lập
cho phần thực có. Checklist ban đầu T02 đã được cập nhật từ kiểm thực tế
MK01/MK02; còn thiếu thông tin nhóm/rubric nên chưa xác nhận sẵn sàng nộp.

Issue MK01 #26/PR #28 đã merge; MK02 #27 chỉ mở PR để người dùng merge.
Phân công, deadline và rubric riêng chưa xác minh; nhóm tự bổ sung.
[Checklist MK02](submission_checklist.md) và reports/submission/qa.json ghi các kiểm đã chạy:
Python 3.12.10/site-packages mới cài được, import/pip check/Office pass; notebook13cell,
14 bảng/9PNG train kiểm lại, 14 bảng khớp lịch sử. Chưa kiểm venv chuẩn hoặc OS/máy mới,
không tái huấn luyện full. Gói nháp chưa sẵn sàng nộp.
Theo [quy trình GitHub](github_workflow.md); người dùng merge.
Codex hỗ trợ cập nhật mapping và checklist.
