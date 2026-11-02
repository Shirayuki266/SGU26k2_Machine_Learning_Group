# Quy trình GitHub sau mỗi task

Áp dụng cho đồ án dự báo PM2.5 trước một giờ tại các trạm Bắc Kinh, trong thư
mục `Đồ án cuối kì/`. Người dùng cấp quyền ngày 02/11/2026: được tự tạo Issue
khi cần, tạo branch, commit, push và mở PR cho task được giao. Quy trình này
thay thế quy định trước đây yêu cầu chờ cho phép commit/push/tạo PR từng lần.
**Chỉ người dùng merge. Không merge, bật auto-merge hoặc tự đóng Issue.**

## 1. Chia công việc

- Mỗi task nhỏ: một Issue, một branch, một PR; hướng tới một commit hoàn chỉnh
  trước khi mở PR. Code, kiểm tra và tài liệu trực tiếp liên quan thuộc cùng task.
- Chia task lớn thành các task con có đầu ra độc lập; không gộp thay đổi không
  liên quan vào một PR.
- Một task có thể có nhiều lần thực nghiệm ghi đầy đủ trong Experiment Log;
  không bắt buộc mỗi run là một commit.

## 2. Trước khi thực hiện

- Đọc AGENTS.md, CONTRIBUTING.md nếu có, quy trình dự án và `git status`.
- Xác minh remote, nhánh đích và quy ước branch thực tế; không mặc định main
  hoặc develop. Cập nhật nhánh đích an toàn trước khi tạo branch.
- Tìm và tái sử dụng Issue đúng task, kể cả kiểm tra lịch sử để tránh tạo trùng.
  Nếu chưa có, tạo Issue với mục tiêu, phạm vi, checklist, phụ thuộc và điều kiện
  hoàn thành. Số Issue phải do GitHub cấp; T05/T06 là mã task, không phải số Issue.
- Không ghi đè, stage hoặc commit thay đổi chưa commit của người khác. Không
  đổi Git author hoặc tạo lịch sử đóng góp giả.
- Nếu phụ thuộc PR chưa merge, nêu rõ phụ thuộc; chỉ tạo stacked PR khi người
  dùng yêu cầu, không âm thầm gộp thay đổi của PR đó.

## 3. Branch

Format: `<prefix>/<task-id>-<short-description>`.

| Prefix | Phạm vi |
| --- | --- |
| `feature/` | Chức năng, pipeline, logger, mô hình |
| `fix/` | Sửa lỗi |
| `test/` | Bổ sung kiểm tra |
| `docs/` | Tài liệu |
| `chore/` | Cấu hình, hỗ trợ |

Ví dụ tên: `feature/t04-experiment-logger`, `feature/t05-hour-ahead-target`,
`feature/t09-persistence-baseline`, `docs/mk01-midterm-report`. Đây là quy ước
tên, không phải quyền tự thực hiện các task chưa được giao.

## 4. Kiểm tra trước commit

- Rà diff và phạm vi file; chỉ stage danh sách file thuộc task.
- Chạy kiểm tra phù hợp. Thực nghiệm phải xác minh config, run_id, log, metric,
  predictions; tài liệu phải đối chiếu bảng/hình với artifact thật.
- Không đưa secrets, môi trường ảo, cache, dataset hoặc model lớn vào Git.
  Artifact không commit phải có hướng dẫn tạo lại hoặc truy cập.
- Không coi smoke là full; không tuyên bố kiểm tra pass khi chưa chạy.

## 5. Commit và push

Tiêu đề tiếng Anh, ngắn gọn, mô tả kết quả cụ thể:

```text
<type>: <action and outcome> (#<issue-number>)
```

Type: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`. Ví dụ khung tiêu đề:
`feat: add reproducible experiment logging (#<issue-number>)`; thay placeholder
bằng số Issue thật. Không dùng `update code`, `final`, `done`, `fix all` hoặc tự
thêm số PR vào commit. GitHub có thể thêm số PR khi người dùng squash merge.

Body khi cần:

```text
Task: <task-id>
Issue: #<issue-number>

- <Thay đổi chính và mục đích>
- <Thay đổi liên quan>

Validation:
- <Lệnh kiểm tra và kết quả thực tế>

Experiments:
- <run_id và cấu hình liên quan, nếu có>
```

Sau commit, push branch lên đúng remote, không push trực tiếp nhánh đích.
Không force-push hoặc sửa lịch sử đã public nếu chưa được yêu cầu. Ưu tiên
một commit ban đầu; sau khi PR public, chấp nhận commit sửa lỗi bổ sung trong
cùng branch để giữ lịch sử review, không tự squash/force-push để ép còn một commit.

## 6. Pull Request

Tiêu đề: `<type>: <specific outcome> [<task-id>]`.
Ví dụ: `feat: add reproducible experiment logging [T04-BỔ SUNG]`.

Body viết tiếng Việt theo mẫu sau. Chỉ dùng `Closes` khi giải quyết toàn bộ
Issue; nếu một phần, đổi thành `Refs` và ghi phần còn lại. `Closes` chỉ liên
kết để GitHub đóng sau khi người dùng merge; không tự đóng Issue trước đó.

```markdown
## Issue
Closes #<issue-number>

## Mục tiêu
<Vấn đề và kết quả task giải quyết trong 1–2 câu.>

## Thay đổi chính
- <Thay đổi cụ thể và lý do.>
- <Thay đổi cụ thể và lý do.>

## Kiểm tra
| Kiểm tra | Lệnh hoặc phương pháp | Kết quả |
|---|---|---|
| <Tên> | <Lệnh thực tế> | <PASS/FAIL/Chưa chạy và lý do> |

## Thực nghiệm và nhận xét
<Nếu không có: Không phát sinh thực nghiệm mô hình.>
<Nếu có, điền các trường bên dưới bằng kết quả thật.>
- Run IDs:
- Mục tiêu/giả thuyết:
- Run tham chiếu:
- Dữ liệu và split:
- Bộ đặc trưng:
- Mô hình và tham số hoặc đường dẫn config:
- Kết quả:
- Nhận xét dựa trên số liệu:
- Quyết định/bước thử tiếp theo:

## Minh chứng
- <Đường dẫn tương đối đến log, config, bảng, hình hoặc kiểm tra.>
- <Link artifact CI nếu có.>

## Hạn chế và phần chưa thực hiện
<Vấn đề ảnh hưởng đánh giá PR; nếu không có hạn chế đã biết trong phạm vi,
ghi rõ.>

## Bàn giao
- Task: <task-id>
- Branch: <branch>
- Commit: <commit hash>
- Trạng thái: Chờ người dùng review và merge.
```

Phân biệt kiểm tra tự động, smoke và xác minh thủ công; mục không liên quan
phải ghi rõ, không điền kiểm tra giả. Kết quả thực nghiệm ghi rõ train,
validation, CV hay test; không dùng test trước giai đoạn cuối đã chốt. Không
đưa log dài nguyên văn vào PR hoặc sao chép số kiểm thử từ dự án khác.

## 7. CI và cập nhật PR

- Kiểm tra CI gắn với commit HEAD mới nhất; đang chạy ghi pending. Không có
  CI thì ghi “Chưa cấu hình CI” và báo kiểm tra local.
- CI thất bại do thay đổi trong task: sửa cùng branch, tạo commit bổ sung,
  push và kiểm tra lại. Cập nhật title/body để phản ánh trạng thái cuối.
- Nếu CI lỗi do môi trường/dịch vụ ngoài: báo bằng chứng, không tắt kiểm tra
  để lấy trạng thái xanh. Mọi kết luận kiểm tra phải gắn với commit đã kiểm tra.
- Không tự đóng Issue trước merge; không bật auto-merge hoặc merge PR.

## 8. Kết thúc task

Trả về ngắn gọn: task/Issue; branch/commit hash; link PR; local và CI trên HEAD
mới nhất; run IDs/nhận xét nếu có; hạn chế/phần cần người dùng kiểm tra; câu
“PR đang chờ bạn review và merge.”

Nếu thiếu quyền/công cụ GitHub, hoàn thành phần local có thể làm, cung cấp
commit/PR title và body, nêu chính xác bước bị chặn. Không tuyên bố đã commit,
push hoặc mở PR khi thao tác chưa thành công. Không triển khai task tiếp theo
chỉ vì task hiện tại đã bàn giao PR.
