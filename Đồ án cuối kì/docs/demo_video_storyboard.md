# T14 — Storyboard video demo (CHƯA QUAY)

Đây là kịch bản đề xuất khoảng 3 phút, không phải yêu cầu thời lượng của thầy.
**Chưa có video thật. Thành viên tự quay và kiểm nội dung trước nộp.**
Người nhận T14: hoanglecodingmachine; họ tên/MSSV, người quay, người thuyết minh,
URL video và yêu cầu riêng của thầy: [CẦN BỔ SUNG]. Không dùng ảnh chụp để tuyên
bố đã có video. Tài liệu chạy: [demo.md](demo.md).

| Thời gian gợi ý | Thao tác trên màn hình | Nội dung nói / bằng chứng |
| --- | --- | --- |
| 00:00–00:20 | Giới thiệu tiêu đề, nguồn dữ liệu | Dự báo PM2.5 t+1 tại trạm đã quan sát, input đến t, µg/m³, UCI501; đây là lịch sử nghiên cứu |
| 00:20–00:45 | Terminal chạy Streamlit, mở localhost | Không training khi rerun. Nếu thiếu model, lấy đúng bundle/checksum theo demo.md |
| 00:45–01:10 | Mở thông tin mô hình | RF A chọn bằng validation, run24cd6d…, fit train+validation đến nhãn29/02/2016 23h;20→65 chiều, version/schema |
| 01:10–01:45 | Aotizhongxin,01/03/2016,12:00; bấm dự báo | Giờ đích13:00, hiện104.8µg/m³; số đo tại t103.0, đối chiếu sau predict112.0. Đây là ví dụ, không metric tổng hợp mới |
| 01:45–02:10 | Chỉ lịch sử48h và điểm t+1 | Đường lịch sử chỉ đến t; dự báo/actual riêng. Giờ khuyết giữ khoảng trống; lịch t+1 biết trước không phải số đo tương lai |
| 02:10–02:40 | Changping,02/03/2016,17:00; bấm dự báo | PM2.5(t) thiếu, pipeline đã fit xử lý, không điền0; dự báo59.8, actual109.0µg/m³. Cohort thiếu PM2.5(t) chưa được đánh giá trong test primary |
| 02:40–03:00 | Đổi giờ/checkbox và kết thúc | Không fit lại, kết quả cũ xóa khi đổi input. Không AQI/nhãn sức khỏe, không cảnh báo thực tế; chưa deploy. Ghi nguồn và AI hỗ trợ |

Số liệu trên lấy từ pipeline thật và ảnh browser T14, không nhập dự đoán vào UI.
Nếu artifact/model thay đổi ngoài recipe, dừng kiểm tra, không sửa lời thoại để
che khác biệt. Replay sau fit dùng một tuần test đã đánh giá T13; không tuyên bố
test chưa từng xem hoặc chọn lại model từ đoạn demo. Không suy importance thành nhân quả.

Trước quay: restore/check model, chạy app, kiểm dấu tiếng Việt và độ đọc được của
chữ/đơn vị, chỉ ghi cửa sổ cần thiết. Sau quay: thành viên tự xem video, đối chiếu
run/giờ/giá trị với artifact, bổ sung URL/quyền truy cập và người phụ trách thật.
Không lưu token/secrets trong video. Rubric gốc/file bài giảng [CẦN BỔ SUNG].
