# Task 04 — Chính sách chất lượng dữ liệu

Loader trả về bảng pandas cùng bảng audit; giữ raw nguyên byte và kiểm tra SHA-256 theo manifest. Schema gồm đúng 18 cột UCI 501 theo thứ tự, filename trạm phải khớp trường `station`. Tất cả file trong manifest phải hiện diện. CSV sai số trường, sai encoding hoặc sai cú pháp được báo lỗi; không âm thầm bỏ dòng để xuất kết quả.

`year/month/day/hour` phải có giá trị số nguyên và tạo được ngày giờ hợp lệ. Giờ phải trong 0–23; không cho pandas tự biến giờ 24 thành ngày tiếp theo. Timestamp không gắn timezone, giữ quy ước giờ gốc như Task 02. `station` không được thiếu, rỗng hoặc có khoảng trắng bao ngoài. Dữ liệu hợp nhất được sắp xếp theo khóa `(station,timestamp)`.

Trùng khóa là lỗi chặn xuất, kể cả các bản sao giống nhau. So sánh payload sau parse trên các cột thời gian, số đo và `wd`; hai giá trị missing được xem giống nhau, missing so với giá trị có quan sát là mâu thuẫn. Không dùng `No`, nguồn file hoặc số thứ tự dòng làm tie-breaker. Audit ghi toàn bộ các dòng liên quan dưới mã `identical_duplicate_key` hoặc `conflicting_duplicate_key`. Không tự chọn một bản ghi trong nhóm mâu thuẫn. Muốn thay chính sách phải có task và quy tắc xử lý được duyệt rõ ràng.

Giờ thiếu là cảnh báo. Loader đếm giờ thiếu giữa các timestamp duy nhất mỗi trạm; chế độ full còn kiểm tra cả hai biên theo khoảng metadata trong `configs/data_quality.json`. Không reindex, điền giá trị hoặc thêm hàng trong Task 04. Việc dùng timestamp duy nhất để **đếm giờ thiếu** không loại bản ghi khỏi dữ liệu.

| Loại | Điều kiện | Hành động |
| --- | --- | --- |
| Missing hợp lệ | `NA` hoặc chuỗi rỗng ở số đo/`wd` | Giữ missing, không impute |
| Sai định dạng số | Token không parse được, NaN dạng chữ, infinity | Lỗi; không biến âm thầm thành missing hợp lệ |
| Vi phạm vật lý | Nồng độ/RAIN/WSPM âm; PRES ≤ 0; TEMP/DEWP < −273,15 °C | Lỗi; chặn xuất, không tự sửa/xóa |
| Nồng độ cao | Vượt ngưỡng rà soát dương trong cấu hình | Cảnh báo; giữ nguyên |
| Khí tượng khác thường | Ngoài khoảng rà soát; DEWP > TEMP | Cảnh báo; giữ nguyên để đối chiếu thiết bị/metadata |
| Hướng gió khác tập 16 hướng la bàn | Giá trị không thiếu chưa nhận diện | Cảnh báo; không tự mã hóa hoặc thay thế |
| `No` sai định dạng | Không phải số nguyên dương | Cảnh báo về metadata; `No` vẫn bị loại khỏi bảng/feature |

Các điều kiện vật lý là kiểm tra miền giá trị trong dự án, không xác nhận nguyên nhân lỗi thiết bị. Ngưỡng rà soát là lựa chọn vận hành được ghi rõ, không phải ngưỡng sức khỏe, tiêu chuẩn pháp lý hay giới hạn hợp lệ do UCI công bố. Nồng độ cao có thể là số đo thật; không dùng IQR, clipping hoặc thay bằng missing. Audit cấu trúc không đảm bảo đã phát hiện mọi lỗi đo lường.

`No` không xuất trong bảng hợp nhất. `source_file` và `source_row` là metadata truy vết (source_row là thứ tự record CSV bắt đầu từ 2 sau header), không dùng làm feature. Feature được chọn tường minh bằng `FEATURE_COLUMNS`; Task 04 chưa fit bộ tiền xử lý, tạo target/lag hoặc huấn luyện.

Các bảng audit được lưu cả khi lỗi; không có output hợp nhất được chấp nhận nếu có lỗi. Script mặc định từ chối ghi đè output. Các test dùng fixture tổng hợp nhỏ trong thư mục tạm, tách khỏi dataset raw và số liệu báo cáo chính thức. Codex hỗ trợ cài đặt và kiểm thử; nhóm cần rà soát các cảnh báo trước task tiếp theo.
