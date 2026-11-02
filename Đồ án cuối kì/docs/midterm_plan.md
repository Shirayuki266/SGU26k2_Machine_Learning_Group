# Kế hoạch và checklist giữa kỳ — MK01/MK02

Tên/phạm vi do người dùng chốt ngày 02/11/2026. **MK01 tạo cả DOCX và PPTX;
MK02 kiểm tra và đóng gói**, không tách nhầm hai mã thành báo cáo và slide.
T02 chỉ chuẩn bị checklist, chưa tạo các sản phẩm đó.

Hiện có T01 xác minh môi trường, đặc tả T02, manifest/audit T03–T04 và logger
T04-LOG, target/split và count/date audit T05, EDA train T06 có bảng/PNG gốc,
T07 có feature A/B nhân quả, registry và missing train; T08 có factories
preprocessing và kiểm tra fixture. T09 có [baseline full validation thật](baseline_results.md),
predictions/log/metric/hình/bundle; T10 có [Ridge/RF A full](initial_findings.md),
so persistence cùng IDs, chi phí và nhận xét. Chưa đánh giá test.
Ưu tiên tiến độ thực tế đến T10; có T11/T12 thì bổ sung. Không bắt buộc tuning,
test cuối hoặc demo và **không mở test để lấy số liệu giữa kỳ**. Phải nêu thiếu,
không điền bảng giả.

## 1. MK01 — Nội dung DOCX/PPTX

| Yêu cầu | CRISP-DM/task | Checklist bằng chứng | Hiện có |
| --- | --- | --- | --- |
| Đề tài/thành viên/phân công | Business Understanding/quản lý | [ ] Tên/MSSV/số nhóm/phân công và đóng góp xác nhận | Chưa đủ thông tin nhóm |
| Bối cảnh/mục tiêu/Input–Output/hồi quy | T02 | [ ] Đúng t+1/cùng trạm, µg/m³, input tới t, giả định số đo t, RQ1/2/3 | Có đặc tả, chưa có DOCX/PPTX |
| Dữ liệu/nguồn/số mẫu/thuộc tính/target | Data Understanding, T03–T05 | [ ] Trích nguồn/manifest/audit; phân biệt số công bố/audit/supervised thật | Có audit raw/T04 và manifest/số mẫu supervised T05; chưa có DOCX/PPTX |
| EDA train | T06 | [ ] Đơn/đa biến, missing/bất thường/ngoại lệ, thời gian/trạm, hình/bảng gốc và quyết định | Có notebook full kernel sạch, 14 bảng/9 PNG và [nhận xét T07/T08](eda_findings.md); chưa đưa vào DOCX/PPTX |
| Feature/pipeline | Data Preparation, T07–T08 | [ ] A/B/dictionary/causal tests; train-only/schema/save-load; tách thiết kế/đã chạy | Có A/B T07 và [factories T08](preprocessing.md), kiểm fixture clone/train-only/save-load; T10 đã fit pipeline A trên train dự án, chưa lưu model triển khai hoặc đưa vào DOCX/PPTX |
| Baseline/model/protocol | Modeling/Evaluation, T09–T10 | [ ] Persistence/fallback, Ridge/RF A, MAE/RMSE/R², cùng IDs, split/CV/test gate | Có persistence/Ridge/RF full, cùng primary N=102.479; MAE 9,736617/10,200433/9,561488; chưa đưa vào DOCX/PPTX |
| Kết quả/nhận xét bước đầu | T09–T10; T11/T12 nếu có | [ ] Validation/CV có run_id/config/mode/N/thời gian; smoke khác full | Có [T09](baseline_results.md) và [T10](initial_findings.md) với bảng/hình/chi phí/gap; chưa đưa vào DOCX/PPTX |
| Vòng thử–nhận xét–sửa | Mọi giai đoạn/T04-LOG | [ ] Giả thuyết/thay đổi, tham chiếu/số liệu/quyết định; giữ kém/thất bại | T10 giữ cả Ridge MAE kém và RF cải thiện nhỏ so baseline, đề xuất T11/T12 chưa chạy; smoke chỉ kiểm thực thi, không coi khác mẫu là cải tiến |
| Tiến độ/khó khăn/kế hoạch | Project plan | [ ] Artifact task hoàn thành, phần còn lại/phụ thuộc/tài nguyên/giới hạn | Có mapping; Issue đóng không đủ bằng chứng |
| Đóng góp/nguồn/AI disclosure | Tất cả sản phẩm | [ ] Đóng góp thực tế và nguồn/hỗ trợ AI được ghi đúng | Chưa xác minh từng thành viên |

Ô chưa tick là checklist bàn giao **tài liệu MK01**, không phủ nhận source/audit
đã có. Khi thiếu kết quả nêu rõ thiếu và kế hoạch; không coi đó là đã đủ mọi
rubric chấm điểm. Chưa có rubric chính thức trong repo, đối chiếu khi được cấp.

DOCX/PPTX theo logic CRISP-DM và bao phủ bảng trên. Giữa kỳ không thay báo cáo
cuối kỳ 5 chương. Không suy đóng góp từ Git author/người chạy script. Mỗi
bảng/hình có nguồn audit hoặc run_id; hình gốc có trục/đơn vị/chú thích, không
gọi hình minh họa là kết quả thực nghiệm.

## 2. MK02 — Đối chiếu và đóng gói

- [ ] DOCX/PPTX MK01 mở được, nhất quán nội dung/phiên bản; bảng/hình đối chiếu
  artifact/run_id/mode và split train/validation/CV.
- [ ] Source .py, notebook .ipynb nếu có, config/dependencies và README có lệnh
  thật; notebook gọi module và tái lập được phần đã triển khai.
- [ ] Kèm experiments/experiment_log.csv và hồ sơ run thật trong
  artifacts/experiments/ khi có; link config/metrics/predictions/hình hợp lệ.
  Chưa có run thì CSV header và báo thiếu, không tạo run mẫu.
- [ ] Kèm hình/bảng gốc EDA/kết quả và sơ đồ pipeline thực nếu đã có; chỉ mục
  truy vết tài liệu → audit/run → artifact.
- [ ] Dataset hoặc nguồn/hướng dẫn tải và kiểm checksum; không tải lại chỉ để
  đóng gói, không đưa data lớn vào Git.
- [ ] Model/pipeline đã huấn luyện nếu có và cần bàn giao, kèm load/inference;
  chưa có model phải ghi rõ, không tạo model giả.
- [ ] Đối chiếu source–config–log–metric–predictions–hình–DOCX/PPTX–README;
  ghi kiểm tra thực chạy/kết quả/giới hạn, không báo lệnh chưa chạy pass.
- [ ] Loại secrets, .venv/cache khỏi gói; artifact không commit có đường dẫn
  truy cập/cách tạo lại, nguồn và license phù hợp.
- [ ] Xác nhận nhóm XX, tạo NhomXX_DuBaoPM25_BacKinh_GiuaKy.zip và kiểm tra
  giải nén/đường dẫn/hướng dẫn sử dụng. Đây là tên mẫu, chưa có ZIP thực tế.

Tuning/test/demo không phải điều kiện hoàn thành MK01/MK02. Nếu nêu T13, ghi
đó là kế hoạch refit train+validation sau khóa rồi test, chưa phải kết quả.
Không mở test mới để bổ sung bảng giữa kỳ.

## 3. Hoàn thành và bàn giao

MK01 hoàn thành khi DOCX/PPTX phản ánh đúng tiến độ, nguồn/truy vết và mục thiếu
rõ ràng. MK02 hoàn thành khi có gói và bằng chứng kiểm tra đối chiếu/tái lập
cho phần thực có. Trong T02 chưa tạo DOCX/PPTX/model/ZIP, không tick checklist
thay cho thực hiện MK01/MK02.

Phân công, deadline và Issue MK01/MK02 chưa xác minh, chỉ ghi mã task.
Theo [quy trình GitHub](github_workflow.md); người dùng merge.
Codex hỗ trợ cập nhật mapping và checklist.
