# Yêu cầu giai đoạn cuối kỳ — áp dụng từ T13

Nguồn: bổ sung trực tiếp của người dùng sau MK02, Issue #30. Quy định sản phẩm
được người dùng truyền đạt từ giảng viên; bản rubric chi tiết: [CẦN BỔ SUNG].
Đây là kế hoạch/checklist, **chưa thực hiện T13–T16 và chưa có gói cuối kỳ**.
Không thay đổi task, commit, run, log hoặc báo cáo/ZIP đã làm tới MK02. Phát
hiện sai sót cũ thì báo và đề xuất Issue/PR sửa riêng, không sửa âm thầm.

Đọc cùng [workflow](codex_workflow.md), [GitHub](github_workflow.md),
[bài giảng/rubric](course_alignment.md), [thành viên](team_contributions.md)
và [AI disclosure](ai_disclosure.md).

## Đánh giá từ T13

Giữ target đúng t+1 cùng trạm, horizon1, seed/config thực tế, temporal split,
feature nhân quả, test gate và recipe đã khóa. Chỉ refit train+validation và
đánh giá test khi được giao T13; bổ sung tài liệu này **không cấp quyền mở test**.
Không chọn lại model/params/selector/hậu xử lý bằng test. Validation đã tham
gia refit không còn là held-out validation của model final.

### RQ1: mức giảm MAE so với persistence

Bên cạnh MAE/RMSE/R², luôn báo:

```text
mae_reduction_vs_persistence_pct = 100 * (MAE_persistence - MAE_model) / MAE_persistence
```

Chỉ tính trên **cùng split, ordered sample IDs, cohort và chính sách coverage**;
lưu run_id persistence/model, N và nguồn predictions. Cohort primary và
operational/fallback báo riêng. Số dương là MAE giảm, số âm là kém hơn baseline;
giữ kết quả âm, không ép model thắng. Với persistence tự so chính nó, kết quả
là 0% khi mẫu số hợp lệ. MAE persistence bằng0/không xác định, nhóm rỗng hoặc
khác mẫu thì ghi null/lý do, không chia0 hoặc đổi mẫu để lấy phần trăm đẹp.

Áp dụng cho bảng/biểu đồ/báo cáo mới từ T13, gồm từng nhóm khi có đủ baseline
cùng mẫu. Nếu baseline theo nhóm/fold chưa có, ghi thiếu, không bịa số. Metric
bổ sung suy từ artifact cũ phải nằm ở phân tích mới có reference_run_id và
provenance; không sửa metrics.json/CSV/báo cáo giữa kỳ của run lịch sử.

### Độ ổn định và phạm vi mùa

Khi nói về độ ổn định phải kèm bảng từng fold: khoảng fit/evaluation, N/trạm,
metric và persistence tương ứng nếu có; báo mean/std và cách tổng hợp. Giữ
quy ước đã dùng: std giữa các fold với ddof=0; phân biệt mean không trọng số
với pooled metric theo mẫu. R² pooled tính từ predictions gộp, không suy từ
trung bình R². Chưa có fold/baseline phù hợp phải ghi thiếu, không tạo số mới.

Train chỉ khoảng hai năm, số chu kỳ mùa hạn chế. Theo config hiện có,
evaluation fold đầu là `[2014-06-01,2014-09-01)`, chỉ mùa hè, thiếu đại diện
các mùa khác; các cửa sổ fold khác cũng không tương đương mùa. Phải nêu rõ
đó là thiếu phủ mùa trong **cửa sổ đánh giá**, không mặc nhiên kết luận phần
fit của fold1 không từng quan sát các mùa đó. Std qua3fold không phải bằng
chứng đủ về ổn định mọi mùa/năm hoặc khoảng tin cậy độc lập. Không chạy CV mới
hoặc tăng ngân sách chỉ để bổ sung mục này khi chưa được giao.

### Phân tích sai số và diễn giải

Lưu bảng/PNG/predictions truy vết được theo trạm; mùa tại target timestamp
(xuân3–5, hè6–8, thu9–11, đông12–2); nhóm nồng độ target `[0,35)`, `[35,75)`,
`[75,150)`, `[150,+∞)` đã chốt. Các khoảng là nhóm phân tích, không phải chuẩn
sức khỏe. Báo N, coverage/fallback, MAE/RMSE/R² hợp lệ và % MAE giảm persistence;
nhóm ít mẫu/R² không xác định phải ghi rõ.

Thêm phân tích **đợt ô nhiễm cao**: chốt ngưỡng, số giờ liên tiếp tối thiểu,
cách xử lý giờ khuyết/ranh giới và quy tắc tách sự kiện theo trạm từ tài liệu
hoặc dữ liệu phát triển trước khi mở test. Các giá trị chưa chốt: [CẦN BỔ SUNG]
trong kế hoạch thực thi T13. Không dùng giờ kế tiếp thay cho đúng1giờ khi có
khoảng trống. Lưu event IDs/thời gian/N, lỗi khi bắt đầu/đỉnh/kết thúc nếu đủ
quan sát, cùng baseline trên mẫu tương ứng; giữ đợt cao hợp lệ.

Nêu model sai ở trạm/mùa/dải/đợt nào, bằng chứng và giới hạn. Giải thích chưa
được kiểm chứng phải gọi là giả thuyết; không suy tương quan hoặc feature
importance thành nhân quả. Diễn giải feature nhóm/OHE và sự tương quan phải
liên kết registry/selector/pipeline thực tế. Phân tích sau test phục vụ kết
luận, không trở thành vòng tuning test.

## Checklist sản phẩm cuối kỳ

Tất cả mục dưới đây là yêu cầu cần bàn giao, chưa được tick thay cho thực hiện.

| Sản phẩm/yêu cầu | Task liên quan | Bằng chứng hoàn thành cần có | Trạng thái |
| --- | --- | --- | --- |
| Báo cáo hoàn chỉnh 5 chương | T15 | DOCX/PDF, nguồn/run IDs, cấu trúc theo yêu cầu thầy [CẦN BỔ SUNG] | [ ] |
| Slide cuối kỳ | T15 | PPTX/PDF thống nhất với báo cáo, đã render/kiểm | [ ] |
| Poster giới thiệu đề tài | T15 | File nguồn/xuất, kích thước/định dạng theo thầy [CẦN BỔ SUNG], đã kiểm bố cục | [ ] |
| Mã nguồn và cấu hình/dependencies | T13–T16 | PY/IPYNB/config, cài/import/chạy có lệnh và phiên bản thật | [ ] |
| Dataset hoặc link tải khi lớn | T16 | Nguồn chính thức/license/checksum, hướng dẫn tải, không link local cá nhân | [ ] |
| Mô hình đã huấn luyện | T13, T16 | Pipeline/weights thật, config/run/hash, load/inference đã kiểm; không dùng summary thay weights | [ ] |
| Notebook/hình gốc/tài liệu tham khảo | T15–T16 | Nguồn/đơn vị/caption/index và truy vết số liệu, notebook chạy từ đầu nếu khả thi | [ ] |
| VIDEO DEMO và demo | T14–T16 | Video truy cập được, thao tác/chạy thật, không dùng feature tương lai; thời lượng/format [CẦN BỔ SUNG] | [ ] |
| README/hướng dẫn cài đặt/chạy | T16 | Các bước từ gói nộp, môi trường/checksum/tài nguyên và giới hạn đã kiểm | [ ] |
| Bảng thành viên và tổng đóng góp100% | T15–T16 | Họ tên/MSSV/vai trò/nhiệm vụ/phần việc/tỷ lệ được nhóm xác nhận | [ ] |
| ZIP đúng tên, chỉ nhóm trưởng nộp | T16 | Tên xác nhận, manifest/CRC/giải nén/đường dẫn/file đủ, checksum toàn ZIP | [ ] |
| Bản ngoài điện tử | T15–T16 | 01 cuốn báo cáo in; slide và poster theo yêu cầu giảng viên, định dạng/cách nộp [CẦN BỔ SUNG] | [ ] |
| Chia sẻ repo chính và GitHub cá nhân | T16 | URL/quyền truy cập/xác nhận cho giảng viên, lịch sử commit đúng người thực hiện | [ ] |

Gợi ý cấu trúc gói: `report/`, `slides/`, `poster/`, `demo/`, `source/`,
`models/`, `experiment_logs/`, `figures/`, `resources/` và README. Có thể dùng
cấu trúc tương đương dễ hiểu. Tài nguyên lớn cần URL truy cập được, hướng dẫn
và checksum; không `.git`, venv, cache hoặc secrets. Phân biệt model final thật
với recipe đã khóa, smoke với full và kết quả phát triển với test cuối.

## Tên ZIP và bàn giao

Tên bắt buộc theo người dùng:

```text
Nhom??_TenDeTai_HoTen_MaSV.zip
```

HoTen_MaSV là **nhóm trưởng**. Ví dụ người dùng đưa:
`Nhom03_DuBaoPM25_NguyenVanA_3124123456.zip` là tên minh họa, không phải thông
tin nhóm được xác nhận. Số nhóm/tên nhóm trưởng/MSSV và quy ước tên đề tài:
[CẦN BỔ SUNG]; không tự chọn người hoặc tạo gói mang danh tính giả.

Chỉ nhóm trưởng nộp. Codex không tự nộp Classroom hoặc chia sẻ repo cho người
khác khi chưa có yêu cầu thực thi/quyền và địa chỉ cụ thể. Không đẩy toàn bộ mã
một lần sát hạn hoặc sửa lịch sử để tạo đóng góp cân bằng. Thành viên đọc/hiểu
phần việc trước merge theo [bảng đóng góp](team_contributions.md).

Còn chỗ [CẦN BỔ SUNG] ở yêu cầu bắt buộc thì gói tương lai phải ghi nháp/chưa
sẵn sàng nộp; không tự tick đủ rubric. Không tái đóng gói hoặc sửa ZIP MK02
trong lần cập nhật quy định này.
