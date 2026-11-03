# T14 — Demo dự báo đúng pipeline nghiên cứu

Issue [#34](https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group/issues/34),
người nhận hoanglecodingmachine được người dùng xác nhận. Đây là demo nghiên cứu
trên lịch sử, chạy cục bộ; chưa deploy, chưa quay video, không phải cảnh báo vận hành.

## Chạy app trong PowerShell

Đứng tại root `Đồ án cuối kì`, dùng môi trường T13 hiện có:

```powershell
.\.venv\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1
```

Mở địa chỉ localhost do Streamlit in ra (mặc định cổng 8501). `.streamlit/config.toml`
tắt thu thập usage và chỉ bind loopback. Ctrl+C để dừng. Không cần chạy training,
download raw hoặc đọc toàn bộ test mỗi lần mở app.

Máy khác cần Python 3.12, source cùng phiên bản và artifact T13 tin cậy. Với venv
chuẩn (đường dẫn Python khác môi trường portable trên máy đã kiểm):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c reports/submission/constraints.txt .
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1
```

Model kiểm Python major/minor và chính xác scikit-learn 1.9.1, pandas 3.0.6,
numpy 2.5.4, joblib 1.6.0 trước load. Đã kiểm Python 3.12.10/Streamlit 1.66.1
hiện có; chưa xác minh cài lại trên OS/máy mới. Snapshot constraints giữ nguyên
từ MK02; không cập nhật lịch sử môi trường cũ. Phiên bản package không khớp thì
app dừng với hướng dẫn, không tự thay hoặc train lại model.

## Lấy/khôi phục model

Weights không commit vào Git. Cần chuyển bundle cục bộ
`reports/final_evaluation/t13_runs.zip` cùng source; **chưa có URL download công khai**.
Người nhận yêu cầu người giữ artifact chuyển đúng bundle, không thay bằng model khác.
Bundle 102162012 bytes, SHA256:
`5362ebf0c51961d96537f5c3a8ffae39b4e1da0b7f6daa6230593445a8e471c1`.

```powershell
Get-FileHash reports/final_evaluation/t13_runs.zip -Algorithm SHA256
.\.venv\python.exe scripts/package_final_artifacts.py --verify reports/final_evaluation/t13_runs.zip
.\.venv\python.exe scripts/package_final_artifacts.py --restore reports/final_evaluation/t13_runs.zip
```

Restore helper chỉ bổ sung file thiếu, không ghi đè run/ledger lịch sử. Xem thêm
[bàn giao T13](final_evaluation.md). Chỉ deserialize artifact do nhóm cung cấp,
đã đối chiếu checksum; không load joblib từ nguồn không tin cậy.

| Metadata | Giá trị cố định |
| --- | --- |
| Phương án chọn bằng validation | RF A, development run `780ecb7fb59d48bea58d5e4a076f1f26` |
| Final refit run T13 | `24cd6d765f214d52aa26e5988380e2cd` |
| Fit | 307344 primary train+validation; nhãn cuối 2016-02-29 23:00 |
| Params | 80 cây, max_depth=12, min_samples_leaf=2, n_jobs=1, seed=42 |
| Schema | 20 feature A → 65 chiều preprocessing; median/indicator/OHE đã fit |
| Hậu xử lý | identity, không clipping |
| Weights | `artifacts/experiments/24cd6d765f214d52aa26e5988380e2cd/artifacts/model/pipeline.joblib` |
| Weights SHA256 | `0b696574847be1a19a8eb4c21ee813efe81266eb0a3bc37efd301a8a9c6e4009` |

`load_demo_model` đối chiếu handoff, frozen config, run metadata/config, params,
schema và tên feature trước predict. UI trình bày version, giai đoạn fit và run ID.
Không chọn lại model bằng test. Handoff ở `reports/final_evaluation/final_model.json`.

## Dữ liệu, tính nhân quả và missing

SQLite 491520 bytes và manifest trong `app/resources/` được commit để mở app
không cần raw. Nguồn UCI 501 nhiều trạm/license CC BY 4.0 đã xác minh trong T03;
URL/checksum nguồn và schema nằm ở `demo_manifest.json`. Cửa sổ được chốt theo
lịch trong `configs/demo.json`: origin từ 2016-03-01 00:00 đến trước 2016-03-08,
12 trạm, 1992 origin, 2554 quan sát gồm buffer 48 giờ. Không chọn ví dụ theo lỗi.

Đây là phát lại phần test **đã mở/đánh giá T13**, không gọi là test chưa xem.
Builder đọc snapshot T05 test sau khi xác nhận T13 completed/exposed; buffer chỉ
đọc số đo validation quá khứ. Không có metric tổng hợp hoặc lựa chọn model mới.
Không dùng các origin validation trước fit cuối để giả lập dự báo ngoài thời gian fit.

`DemoStore` mở SQLite read-only. Index chỉ đọc station/timestamp. Mỗi yêu cầu lấy
đúng trạm, chỉ số đo trong [t−47h,t]; `features_for_prediction` T07 tạo A, gồm
lịch t+1 biết trước. `forecast_at` từ chối origin trước nhãn fit cuối, timestamp
không tròn giờ/timezone khác, trạm lạ hoặc không có quan sát t. Không tạo mẫu giả.
Sau `pipeline.predict`, UI mới gọi `actual_after` để đọc bảng actuals riêng.
Đối chiếu không được dùng trong feature hay fit. Timestamp giữ theo nguồn, không
tự chuyển sang múi giờ máy. PM2.5 luôn µg/m³, horizon đúng 1 giờ.

Thiếu đầu vào được giữ missing và xử lý bằng pipeline đã fit; không điền 0 hoặc
fit lại. A chỉ cần số đo tại t, thiếu các giờ trước vẫn dự báo được; khoảng trống
trên hình được giữ, reindex chỉ dùng vẽ. Nếu thiếu actual, UI ghi “Chưa có”.
Resource giữ 13 origin thiếu PM2.5(t); chưa đánh giá cohort này trong T13 primary.
T05 chỉ giữ hàng có target quan sát, nên resource không đại diện missingness raw,
không phải benchmark mới. Trường hợp thiếu actual được kiểm bằng fixture TEST_ONLY.

Lỗi T08 cũ: một hàng thiếu wd dạng pandas StringDtype gây lỗi kiểm schema.
[Issue #35](https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group/issues/35)
báo riêng để sửa sau; T14 chỉ chuyển representation categorical sang object/string
và np.nan, giữ nguyên giá trị, imputation, weights và source T08. Không sửa lịch sử.

Model/store được cache theo fingerprint; đổi file làm mất cache. Các số đo được
query theo yêu cầu; không cache toàn bộ tương lai. Thay selector xóa kết quả cũ,
lỗi predict không hiển thị lại kết quả trước. Checkbox/rerun không fit hoặc predict lại.
Không suy PM2.5 thành AQI/nhãn sức khỏe và không tuyên bố quan hệ nhân quả.

## Tạo lại resource và kiểm tra

Thông thường dùng resource đã commit. Chỉ khi chưa có resource, đã khôi phục T13
và có snapshot T05 đúng SHA, chạy `scripts/build_demo_data.py`. Script từ chối
ghi đè resource hiện hữu; không tự xóa để chạy lại. Lưu bản chuẩn bị cũ riêng
nếu thực sự cần sửa dữ liệu minh họa. Không ghi dữ liệu kiểm tra vào Experiment Log.

```powershell
.\.venv\python.exe -m pytest tests/test_demo.py tests/test_demo_ui.py -q -p no:cacheprovider --basetemp=artifacts/t14_TEST_final_contracts
.\.venv\python.exe scripts/verify_demo.py
```

19 tests pass: input/schema/version/checksum, missing/giờ khuyết, cách ly trạm,
thay tương lai không đổi feature, chặn trước fit, actual sau predict, cache/rerun
và không gọi fit. Tests dùng tmp có nhãn TEST_ONLY, bản sao weights thật T13;
không tạo run giả. Nếu máy chưa restore weights, test phụ thuộc artifact sẽ skip:
skip không phải bằng chứng đã kiểm model. Máy bàn giao đã restore và 19/19 pass.
Verifier 36 mẫu/12 trạm khớp script và saved T13 predictions, sai lệch lớn nhất
1.4210854715202004e-14 (sai số dấu phẩy động), không tính lại metric test.

Browser QA đã kiểm localhost:8514, health HTTP200, Chromium156.0.8078.4, 5 ảnh thật,
không page error; đã xem nhãn/dấu/đơn vị/metadata/desktop và mobile. Tái chụp tùy chọn:

```powershell
.\.venv\python.exe -m pip install -c reports/submission/constraints.txt ".[demo-test]"
.\.venv\python.exe -m playwright install chromium
# Giữ app đang chạy cổng 8501 ở terminal khác:
.\.venv\python.exe scripts/capture_demo_screenshots.py --url http://127.0.0.1:8501
```

Trên máy đã kiểm, Playwright/browser đặt riêng ở `artifacts/t14_tools/` ignored.
Không cần các công cụ này khi chỉ sử dụng app. Xem
[kiểm inference](../reports/demo/inference_verification.json),
[kiểm browser/chỉ mục SHA ảnh](../reports/demo/browser_verification.json)
và [QA bàn giao](../reports/demo/qa.json).

| Hình thật | Nội dung |
| --- | --- |
| [01_ready](../reports/demo/screenshots/01_ready.png) | Trước predict, actual chưa query |
| [02_forecast](../reports/demo/screenshots/02_forecast.png) | Aotizhongxin 01/03/2016 12→13, 104.8 µg/m³ |
| [03_model_details](../reports/demo/screenshots/03_model_details.png) | Version/schema/fit/nguồn và lựa chọn bằng validation |
| [04_missing_current](../reports/demo/screenshots/04_missing_current.png) | Changping 02/03/2016 17h, missing giữ nguyên |
| [05_mobile](../reports/demo/screenshots/05_mobile.png) | Cùng app trên viewport rộng 430px |

Đây là minh chứng inference/UI, không có run training mới hoặc dòng model log T14.
Lệnh/giá trị đầy đủ truy vết trong JSON. Chưa kiểm trình duyệt khác, OS sạch hoặc
nhiều người dùng đồng thời. Thiếu video thật và xác nhận thành viên đã đọc/hiểu;
xem [storyboard](demo_video_storyboard.md), [AI disclosure](ai_disclosure.md).
