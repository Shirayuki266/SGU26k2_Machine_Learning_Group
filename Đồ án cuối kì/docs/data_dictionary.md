# Từ điển dữ liệu — UCI 501

Nguồn: [metadata UCI chính thức](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data), mục Additional Variable Information, truy cập 12/10/2026 và đối chiếu lại 02/11/2026. Ý nghĩa và đơn vị dưới đây được diễn giải từ metadata, không suy đoán từ giá trị CSV.

| Trường | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| No | Số thứ tự dòng | — |
| year | Năm | — |
| month | Tháng | — |
| day | Ngày | — |
| hour | Giờ | — |
| PM2.5 | Nồng độ PM2.5 | µg/m³ |
| PM10 | Nồng độ PM10 | µg/m³ |
| SO2 | Nồng độ SO₂ | µg/m³ |
| NO2 | Nồng độ NO₂ | µg/m³ |
| CO | Nồng độ CO | µg/m³ |
| O3 | Nồng độ O₃ | µg/m³ |
| TEMP | Nhiệt độ | °C |
| PRES | Áp suất | hPa |
| DEWP | Nhiệt độ điểm sương | °C |
| RAIN | Lượng mưa | mm |
| wd | Hướng gió | Không nêu đơn vị |
| WSPM | Tốc độ gió | m/s |
| station | Tên trạm quan trắc | — |

Metadata công bố 420.768 dòng, 12 trạm, khoảng 01/03/2013–28/02/2017; `NA` biểu thị thiếu. Dấu `—` chỉ trường không có đơn vị vật lý. Kiểu CSV không được khai báo; script audit suy luận kiểu từ các giá trị không thiếu và ghi riêng trong JSON, không gọi đó là dtype pandas.

Chỉ ghép `year/month/day/hour` thành timestamp trong bộ nhớ để kiểm tra; không thêm cột hoặc sửa CSV raw. `No` không phải feature dự báo. `PM2.5(t)` là đầu vào được phép; target đúng +1 giờ cùng trạm sẽ được tạo trong task sau.

| Vai trò trong dự án | Quy tắc |
| --- | --- |
| `No` | Số thứ tự dòng gốc, không phải khóa thời gian, feature hoặc target |
| `year/month/day/hour` | Thành phần giờ quan trắc gốc; tạo timestamp, khóa `(station,timestamp)` và đặc trưng lịch biết tại t; giữ quy ước giờ gốc, không tự gắn UTC |
| `station` | Mã trạm/categorical và khóa nhóm; lag/rolling không nối qua trạm |
| Các số đo và `wd` tại t | Ứng viên feature khi đã có tại origin; bộ A chọn tường minh theo config, `wd` là categorical |
| `PM2.5` | Cùng cột raw nhưng vai trò theo thời gian: giá trị t là feature/persistence, giá trị đúng t+1 cùng trạm mới là target |
| `input_timestamp/target_timestamp` | Trường supervised sẽ tạo ở T05, chưa phải cột raw; split dựa target_timestamp, không lấy dòng kế tiếp thay +1 giờ |
| `source_file/source_row` | T04 thêm để truy vết, không thuộc schema raw/feature/target |

CSV là văn bản; audit phân loại giá trị không thiếu thành integer/real/string,
không khẳng định đó là pandas dtype. Khi nạp pandas, cột số có missing có thể
thành float/nullable; không dùng thay đổi dtype để suy ra thay đổi đơn vị hoặc
impute dữ liệu. Bộ A/B/C, cohort và target theo
[problem_definition.md](problem_definition.md), [experiment_plan.md](experiment_plan.md).

License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Trích dẫn chính thức: Chen, S. (2017). Beijing Multi-Site Air Quality [Dataset]. UCI Machine Learning Repository. [DOI: 10.24432/C5RK5G](https://doi.org/10.24432/C5RK5G).

Codex hỗ trợ diễn giải metadata và viết script Task 03; số liệu quan sát chỉ được lấy từ lần audit thực tế.
