# Thông tin nhóm và đóng góp — chờ nhóm cung cấp

Khung này được tạo trong Issue #30 để áp dụng từ T13; **chưa phải danh sách
thành viên hoặc bảng đóng góp được nhóm xác nhận**. Người dùng sẽ tự bổ sung.
Không suy họ tên/MSSV, vai trò, tỷ lệ hoặc người thực hiện từ Git author,
người chạy script hay tài khoản đang đăng nhập. Không sửa lịch sử trước T13.

## Bảng thành viên cần nhóm xác nhận

| Họ tên | MSSV | GitHub cá nhân | Vai trò/nhiệm vụ | Phần công việc thực tế | Đóng góp % | Issue/PR/artifact minh chứng | Đã đọc và hiểu phần nhận |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [CẦN BỔ SUNG] | [CẦN BỔ SUNG] | [hoanglecodingmachine](https://github.com/hoanglecodingmachine) | Người nhận T13 | T13 được giao; AI hỗ trợ code/kiểm, người nhận review/đọc/hiểu trước merge | [CẦN BỔ SUNG] | Issue #32, artifact/PR T13 sau thực thi | [CẦN BỔ SUNG] |

Nhóm tự thêm đúng số thành viên. Tổng tỷ lệ phải bằng **100%** sau khi nhóm
xác nhận; hiện **chưa có số liệu để kiểm tổng**, không chia đều hoặc điền giả.

| Thông tin bàn giao | Giá trị xác nhận |
| --- | --- |
| Số nhóm | [CẦN BỔ SUNG] |
| Nhóm trưởng: họ tên/MSSV/GitHub | [CẦN BỔ SUNG] |
| Repo chính đã chia sẻ cho giảng viên | [CẦN BỔ SUNG] URL/quyền truy cập/xác nhận |
| GitHub cá nhân từng thành viên đã chia sẻ | [CẦN BỔ SUNG] URL/quyền truy cập/xác nhận |

## Gán Issue và kiểm danh tính từ T13

Mỗi Issue thực thi gán một thành viên cụ thể theo bảng được nhóm xác nhận;
PR liên kết Issue và nêu phần việc. Thiếu mapping GitHub thì ghi [CẦN BỔ SUNG],
không gán ngẫu nhiên hoặc coi tài khoản đang cấu hình Git là người phụ trách.
Hoàn thiện gán người trước công việc/commit của task từ T13.

Trước mỗi commit chạy và thông báo danh tính thực tế cho người dùng:

```powershell
git config --show-origin --get user.name
git config --show-origin --get user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Không đổi global config, không giả tác giả/co-author, không dùng biến môi
trường hay amend/rebase để đổi công lao. Nếu danh tính không đúng người được
giao, báo nhóm xử lý; không tự thay bằng tên người khác. Git identity chỉ là
minh chứng kỹ thuật, không tự chứng minh tỷ lệ đóng góp học thuật.

Commit nhỏ theo phần việc thật đã hoàn tất và kiểm; cập nhật đều theo tiến độ
thực. Không tách commit rỗng hoặc thay đổi vô nghĩa để tăng số lượng, không gom
toàn bộ mã sát hạn. Thành viên nhận việc phải đọc và hiểu trước khi merge;
ghi review trong PR và bảng này. Không đánh dấu đã hiểu khi chưa xác nhận.

## Ghi nhận phần trước T13

| Giai đoạn | Người/phần việc thực tế do nhóm xác nhận | Nguồn đối chiếu | Trạng thái |
| --- | --- | --- | --- |
| T01–T12, MK01/MK02 | [CẦN BỔ SUNG] | Issue/PR/commit/artifact và xác nhận của nhóm | Chưa phân bổ đóng góp theo thành viên |

Chỉ ghi việc thật, có nguồn; không sửa commit, thêm co-author hồi tố hoặc phân
bổ lại lịch sử để cân bằng. Nếu phát hiện sai sót, báo và đề xuất Issue/PR sửa
riêng. Khung bảng không khẳng định nhóm đã review các phần AI hỗ trợ.

Issue #30 là cập nhật quy trình chuẩn bị, chưa có thành viên được xác nhận để
gán; trạng thái đó được công khai, không giả nhận người phụ trách.

## Xác nhận người nhận T13

Người dùng trả lời “cho tôi” cho T13; gh api user xác minh tài khoản đang đăng
nhập hoanglecodingmachine, trùng Git identity hiện có. Issue #32 được gán cho
hoanglecodingmachine trước triển khai. Chỉ mapping này đã xác nhận; họ tên,
MSSV, tỷ lệ và thành viên khác vẫn chờ nhóm cung cấp. Không suy công việc cũ
hoặc ghi đã đọc/hiểu khi chưa được xác nhận.

Minh chứng T13 hiện có: hai commit code/protocol74a739e và7aeea64 trước test,
parent a8cb7fda3f1441968b31c26c18e57ebf cùng3child trong
reports/final_evaluation/execution.json. AI hỗ trợ chạy/kiểm; người nhận cần
review/đọc/hiểu trước merge, chưa gán thêm phần đóng góp hoặc tỷ lệ học thuật.
