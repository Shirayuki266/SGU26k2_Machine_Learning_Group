# Issue #35 — Guard categorical thiếu trong T08

Đây là bug-fix T08, mã công việc PR35 theo yêu cầu người dùng, **không có T17**.
Một [Issue #35](https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group/issues/35),
branch `fix/pr35-categorical-missing-guard`, một PR. Người nhận: hoanglecodingmachine,
kế thừa người phụ trách T14 cho lỗi phát hiện khi tích hợp T14; đã gán Issue trước sửa.
PR thực tế [#37](https://github.com/Shirayuki266/SGU26k2_Machine_Learning_Group/pull/37)
(PR35 là tên công việc, không phải số PR GitHub). Commit sửa code `a819acf`;
commit tài liệu/bằng chứng xem lịch sử PR. Không merge trong task này.
Thành viên đọc/hiểu trước merge: [CẦN BỔ SUNG]. Không suy tên/MSSV/tỷ lệ từ Git.

## Phát hiện và tái hiện

Lỗi được phát hiện trong T14 khi một request inference có toàn bộ `wd` thiếu.
`FeatureSchema._validated` T08 lấy `observed = category.dropna()`, gọi
`observed.map(lambda value: isinstance(value, str)).all()`. Với observed rỗng,
pandas giữ dtype string thay vì boolean; reduction `all` của ArrowStringArray
không được hỗ trợ và ném `TypeError: Cannot perform reduction 'all' with string dtype`.
Request dừng trước categorical imputer, dù missing là đầu vào hợp lệ.

Môi trường tái hiện thực: Python3.12.10, pandas3.0.6, numpy2.5.4,
scikit-learn1.9.1; phiên bản joblib/pyarrow đầy đủ ở
[before.json](../reports/issue35/before.json). Chưa kiểm pandas phiên bản khác;
không khẳng định mọi pandas3.x hoặc mọi phiên bản cũ đều có cùng hành vi.

T14 đã thêm adapter chuyển categorical sang object, nên test cũ qua boundary đó
đã pass. PR35 bổ sung vào chính test được yêu cầu một lần gọi pipeline **trực tiếp**
với `string[pyarrow]`, trước adapter. Fixture SQLite TEST_ONLY có wd/PM2.5 thiếu,
không đọc sample CSV thực, dù timestamp tổng hợp có thể trùng lịch dữ liệu.
Trước sửa source, lệnh dưới đây thất bại1test tại `preprocessing.py:58` với đúng lỗi:

```powershell
.\.venv\python.exe -m pytest tests/test_demo.py::test_missing_current_pm25_uses_saved_median_not_zero_or_fit -q -p no:cacheprovider --basetemp=artifacts/issue35_TEST_red --junitxml=artifacts/issue35/red.xml
```

[QA](../reports/issue35/qa.json) lưu lỗi/kết quả và phạm vi; XML đầy đủ ở thư mục
artifacts cục bộ, không là model log. Không dựng lịch sử run hoặc sửa test exposure T13.

## Cách sửa và phạm vi

Thay guard bằng `all(isinstance(value, str) for value in observed)`. Python `all`
trả True cho observed rỗng, kiểm từng giá trị đã quan sát mà không phụ thuộc dtype
reduction của pandas. Giá trị non-string và token dành riêng vẫn bị từ chối.
Giữ nguyên bước chuyển None/pd.NA thành np.nan đã có; categorical imputer đã fit
tiếp tục thay bằng token missing theo config. Không điền0 vào số đo hay sửa model.

Không đổi class path, constructor, tham số, thuộc tính đã fit, tên feature,
categorical vocabulary, numeric median/scaler hoặc output schema. Giữ adapter
T14 để giới hạn phạm vi; không refactor demo trong bug-fix này.

Ghim `pandas==3.0.6` trong `pyproject.toml` (file dependencies duy nhất) và README.
Metadata pandas cài thực tế yêu cầu Python>=3.11 nên khai báo Python tối thiểu
được đồng bộ từ3.10 lên3.11. Nạp weights T13 vẫn yêu cầu Python3.12 và phiên bản
đã lưu; không cài lại/thay phiên bản môi trường hiện tại để che lỗi.

## Bằng chứng giữ nguyên kết quả

`scripts/verify_issue35.py` chụp `before.json` **trước khi sửa** và `after.json`
sau sửa. Chỉ nạp weights Ridge/RF T13 và tạo4hàng có ID `TEST_ONLY_ISSUE35_*`.
Không đọc train/validation/test samples hoặc saved predictions, không gọi fit.
Bảy trường hợp: valid và mixed missing/unknown với object, string[python],
string[pyarrow], cùng all-missing object vốn chạy được trước sửa.

Hai model ×7trường hợp ×4hàng = **56 giá trị dự báo**. So sánh IDs/hash giá trị
fixture, `rtol=0`, `atol=1e-12`: **max absolute difference=0.0**. Đây là kiểm
tương thích phần mềm trên fixture, không phải metric đánh giá mô hình hoặc bằng
chứng bao phủ toàn bộ dataset. Không tính MAE/RMSE/R²/%MAE mới từ fixture.

Tệp bằng chứng mới: [before](../reports/issue35/before.json),
[after](../reports/issue35/after.json), [QA](../reports/issue35/qa.json).
Script từ chối ghi đè bằng chứng. Tái lập before cần checkout source trước sửa
ở workspace riêng và dùng cùng fixture/script; sau sửa dùng snapshot đó và
`--phase after --output-dir <thư mục QA mới trong project>`. Không chạy lại
`--phase before` trên source đã sửa rồi gọi đó là bằng chứng trước sửa.

## Fingerprint, serialization và lịch sử

| Thành phần | Kết quả / tác động |
| --- | --- |
| Source preprocessing.py trước | `3e121c4f6f5226b3764f053f1ceafdc9087ff3bbc97382dcc75242044b5d241f` |
| Source sau | `a5279de8fc43f4b484ad0b0829e648bf5b1f0cb030f46c00455b77a7826fd2ef` |
| Custom transformer | Vẫn `beijing_air.preprocessing.FeatureSchema`, constructor giữ nguyên; không có field serialization version mới |
| Package | Giữ0.1.0; dùng commit/sourceSHA phân biệt bản sửa, không tự nâng version model hoặc sửa metadata run |
| Weights/recipe/log | SHA trong before/after giữ nguyên; cả hai weights nạp được, không refit/patch/resave vào đường dẫn lịch sử |
| T13 frozen source gate | Trước pass; sau từ chối `Frozen input changed: src/beijing_air/preprocessing.py` như dự kiến |
| Cache T14 | Fingerprint hiện chỉ bao gồm model/metadata/config, chưa có codeSHA; không đổi dù guard đã sửa |

**Không cập nhật fingerprint trong configs/final_evaluation.json hoặc artifact cũ.**
T13 runner/verifier kiểm đúng source cũ nên không thể gọi là pass trên branch này.
Đề xuất giữ kiểm chứng lịch sử tại commit T13 `30163f8` và chỉ dùng bản sửa cho
inference/code tiếp theo; nếu T16 cần kiểm lịch sử cùng bản mới, tạo thay đổi
review riêng để phân biệt source của run với compatibility fix. Không bỏ guard,
không viết lại frozen manifest để làm xanh verifier. Chưa chạy verifier T13
vì ngoài phạm vi và nó đọc saved test predictions sau gate.

Joblib lưu tên class/state, nên load weights cũ trong tiến trình mới dùng method
đã sửa; bytes weights giữ nguyên. Phải dừng/khởi động lại Streamlit/Python sau
cập nhật để dùng code mới. Có thể đề xuất bổ sung sourceSHA/phiên bản code vào
cache/release manifest trong PR riêng trước T16; **chưa triển khai hoặc đổi artifact**.

Trong kiểm tra, so `joblib.hash` RF giữa hai lần load độc lập cho giá trị khác
nhau dù cùng file. Chẩn đoán tại [hash_diagnostic.json](../reports/issue35/hash_diagnostic.json)
cho thấy các field của node đầu tiên bằng nhau; byte khác chỉ ở padding57–63
của record64bytes. Vì thế không dùng hash object RF làm bằng chứng bất biến qua
tiến trình/save-load. Giữ số hash đo được trong before/after, không sửa cho bằng
nhau; dùng SHA file weights và dự báo/transform/schema. Tests vẫn kiểm hash
trong vòng đời **cùng một instance** trước/sau inference để phát hiện mutation.

## Kiểm tra sau sửa

```powershell
.\.venv\python.exe -m pytest tests/test_issue35.py tests/test_demo.py::test_missing_current_pm25_uses_saved_median_not_zero_or_fit -q -p no:cacheprovider --basetemp=artifacts/issue35_TEST_green2 --junitxml=artifacts/issue35/green2.xml
.\.venv\python.exe -m pytest tests/test_preprocessing.py tests/test_demo.py tests/test_demo_ui.py -k "not real_demo_schema_and_script_parity" -q -p no:cacheprovider --basetemp=artifacts/issue35_TEST_regression --junitxml=artifacts/issue35/regression.xml
.\.venv\python.exe scripts/verify_issue35.py --phase after
.\.venv\python.exe -m pip check
```

Lệnh đầu **28passed**: một/toàn batch wd missing, None/np.nan/pd.NA, object và
hai StringDtype, unknown, valid, reserved/non-string, save/load bản sao tạm,
numeric median không0, fit bị chặn trong tests mới. Lệnh regression
**55passed/1deselected**; loại test real_demo_schema_and_script_parity vì nó mở
resource từ test period. Test T08 cũ chỉ fit toy fixture để kiểm factory; không
refit bất kỳ model nghiên cứu hoặc training trên dataset dự án.

Verifier pass56giá trị, protected hashes giữ nguyên; pip check không lỗi, pandas
đang cài khớp pin. Chưa kiểm OS mới, pandas khác hoặc toàn test dataset; không
mở test để nâng mức bằng chứng. Ba lỗi ban đầu của test roundtrip mới là giả định
hash RF bằng nhau giữa hai load; đã ghi chẩn đoán và sửa assertion để kiểm output,
transform, schema và bất biến từng instance, không thay source guard thêm.

## Dùng cho T15 / bài giảng / AI

T15 có thể dùng mục này làm ví dụ phát hiện lỗi inference và kiểm chứng tái lập.
Chủ đề05: phân biệt lỗi phần mềm với chất lượng dự báo;06/Ensemble: giữ pipeline
Ridge/RF đã chốt, không tuning hay chọn lại. File/trang bài giảng và rubric gốc
[CẦN BỔ SUNG], không tự khẳng định thầy đã dạy guard này hoặc đã đạt điểm.

Codex hỗ trợ tái hiện/sửa/test/QA/tài liệu và thao tác GitHub được giao; người
phụ trách hoanglecodingmachine cần đọc/hiểu trước merge. Git identity kiểm trước
commit, không đổi global config/co-author. Bug-fix không ghi công học thuật hoặc
tỷ lệ thay thành viên. Các Issue hoàn thành #20/#22/#24/#26/#27/#30/#32/#34 đã
đóng theo yêu cầu trực tiếp lần này sau đối chiếu PR đã merge; không coi đó là
quyền merge #35. Bản giữa kỳ vẫn có chỗ nhóm tự bổ sung theo bàn giao cũ.
