# Buffett và Munger: sáu sổ mô phỏng độc lập

Hai mô hình nghiên cứu độc lập với 11 bot cũ. Không thay đổi snapshot
`site/research-146.json`, lịch sử paper hay quy tắc giao dịch của các bot đó.
Mở rộng mẫu 300–500 mã được hoãn theo yêu cầu người dùng.

Tư tưởng tham khảo: [thư Berkshire 1989](https://www.berkshirehathaway.com/letters/1989.html)
về chất lượng doanh nghiệp, lợi nhuận trên vốn và sở hữu dài hạn. Các ngưỡng
dưới đây do Arena đặt, không phải công thức của hai nhà đầu tư.

| Điều kiện | Buffett | Munger |
|---|---:|---:|
| ROE bình quân 3 năm, vốn chủ bình quân đầu/cuối năm | ≥15% | ≥20% |
| Biên lợi nhuận ròng tối thiểu từng năm trong 3 năm | ≥8% | ≥12% |
| Nợ vay/vốn chủ năm gần nhất | ≤1 | ≤0,6 |
| Tổng CFO/tổng lợi nhuận 3 năm | ≥0,8 | ≥0,8 |
| Từng năm: lợi nhuận, CFO, CFO − trị tuyệt đối capex | Đều dương | Đều dương |
| Giá đóng cửa/MA200 để xét mua | ≤0,95 | ≤1,15 |
| Số vị thế tối đa | 6 | 4 |

MA200 chỉ là mốc giá tham chiếu, **không phải giá trị nội tại**. Chưa mô hình
hóa lợi thế cạnh tranh hay chất lượng quản trị bằng dữ liệu định tính. Cần
4 báo cáo liên tiếp để tính 3 ROE. Không mua bằng số liệu thiếu. Loại ngân hàng,
bảo hiểm, dịch vụ tài chính vì bộ lọc CFO/nợ không tương đương; ICB hiện tại
được áp dụng cho lịch sử và có thể tạo sai lệch.

Nguồn: Vietcap IQ financial-statement/metrics, giữ toàn bộ báo cáo năm và
`publicDate`, `updateDate`, `createDate`. Sử dụng từ ngày muộn nhất cộng 1 ngày.
Thiếu ngày công bố thì loại. Đây không phải kho phiên bản báo cáo gốc: báo cáo
bị cập nhật về sau sẽ bị giữ lại đến ngày cập nhật đó, làm giảm cơ hội lịch sử.
Snapshot số liệu có kiểm chứng ở `config/value-fundamentals.json`; SHA và
SHA toàn bộ 146 tệp giá nằm trong kết quả công khai.

Rà soát ở phiên đầu mỗi tháng và lần khởi tạo. Giữ doanh nghiệp đang đạt bộ
lọc, không xoay vòng chỉ vì mã khác có điểm cao hơn. Bán khi chất lượng không
còn đạt hoặc báo cáo quá cũ; không có cắt lỗ ATR/ngưỡng giá ngắn hạn. Báo cáo
mới nhất phải thuộc tối thiểu năm hiện tại trừ 2. Tín hiệu sau đóng cửa, khớp
mở cửa phiên quan sát tiếp theo, hết hạn nếu lỡ phiên đó; chờ tối thiểu 5 phiên
theo mô hình thanh toán cũ. Không vay, lô 100; tối đa 0,5% khối lượng bình quân
20 phiên cho mỗi lần khớp cả mua/bán; phí 0,15% mỗi chiều, thuế bán 0,1%,
trượt giá nền 0,15% và phụ phí thanh khoản của Arena. Mỗi mã tối đa NAV/số vị
thế khi mua, không tái cân bằng cơ học về tỷ trọng mục tiêu.

Backtest dùng cùng giá/cửa sổ 146 mã, có sai lệch chọn mẫu sống sót. Chưa tái
dựng đầy đủ cổ tức/quyền/giá chưa điều chỉnh; kết quả không phải tổng lợi
nhuận của một tài khoản đầu tư dài hạn được tái dựng hoàn chỉnh. Không dùng
giá đã điều chỉnh để ghép với EPS cũ rồi gọi đó là P/E lịch sử.

Paper bắt đầu đúng thời điểm đăng ký, vốn 100 triệu/bot. Chỉ khớp ý định đã
lưu trước giờ mở cửa, không phát lại các tín hiệu chưa từng được lưu. Những
phiên bị bỏ lỡ không tự tạo lệnh bù. Sổ riêng `state/value_paper.json` được
cập nhật sau đóng cửa bởi workflow daily; lỗi tải báo cáo giữ bộ đã xác minh
trước đó, hiển thị ngày lấy dữ liệu.

## Phút và ngày + phút: biến thể thử nghiệm

Theo yêu cầu bổ sung, mỗi bot có thêm Paper phút, Paper kết hợp, Backtest phút
và Backtest kết hợp. Đây là cách Arena thử chuyển bộ lọc chất lượng sang giao
dịch phút, không phải cách Buffett/Munger thực sự đầu tư. Bản ngày ở trên
được giữ nguyên cả kết quả và sổ paper.

Tất cả biến thể dùng báo cáo tài chính đã biết từ **cuối phiên thị trường
trước đó**, giữ nguyên điều kiện chất lượng và phạm vi phi tài chính. Bản
phút không dùng chỉ báo OHLCV ngày. Bản kết hợp bổ sung đóng cửa ngày trước
≤0,95×MA200 (Buffett) hoặc ≤1,15×MA200 (Munger), giá ≥5.000 đồng và giá trị
khớp bình quân 20 ngày ≥3 tỷ đồng. Không lấy đóng cửa của ngày đang chạy.

| Quy tắc phút | Buffett | Munger |
|---|---|---|
| Vào lệnh | Đóng ≤0,998×MA20, cao hơn nến trước; khối lượng ≥0,8×bình quân 20 nến trước | MA20 ≤đóng ≤1,005×MA20, đóng >MA10; khối lượng ≥bình quân 20 nến trước |
| Thoát lệnh | Đóng <0,985×MA20 hoặc <0,925×giá mua, hoặc chất lượng năm không đạt | Đóng <0,99×MA20 hoặc <0,94×giá mua, hoặc chất lượng năm không đạt |

MA10/MA20 trong bảng là trung bình **nến phút** đã đóng, khởi động sau 30
nến mỗi phiên. Không phát tín hiệu qua đoạn gián đoạn 10 nến gần nhất có
khoảng cách trên 120 giây; lọc biến động và bước nhảy giá để tránh tín hiệu
từ chuỗi quá phẳng hoặc đứt quãng. Cả hai vẫn chờ tối thiểu 5 phiên mới bán,
nghỉ 7 phiên sau bán; tối đa 6/4 mã, vốn mỗi lần mua ≤NAV/6 hoặc NAV/4 và
không vượt tiền mặt. Mỗi lệnh không vượt 5% khối lượng của nến tín hiệu trước.
Không dùng ATR để phân bổ hai biến thể này. Phí/thuế/trượt giá dùng mô hình
thực thi chung của Arena. Lệnh chỉ khớp nến quan sát sau 60–180 giây;
qua phiên hoặc khoảng thiếu dài hơn thì hết hạn, không nội suy.

`run_value_intraday.py` kiểm SHA của **toàn bộ 146 lịch sử phút** với snapshot
đã xác minh, rồi chỉ tính chỉ báo cho những mã có thể đạt chất lượng ở thời
điểm tương ứng hoặc đang nắm giữ. Chọn theo thông tin tài chính thời điểm đó,
không chọn theo lợi nhuận cuối kỳ. Bộ 146 ban đầu vẫn có sai lệch sống sót.
Kiểm tra toàn bộ lệnh mua có ngày báo cáo ≤ngày xét chất lượng <ngày giao
dịch; toàn bộ lệnh khớp sau tín hiệu và sau thời điểm gửi. Công khai SHA nguồn,
747 điểm NAV mỗi kết quả, thống kê ngành từ toàn bộ sổ lệnh.

Paper phút/kết hợp ở `state/value_intraday.json`, xuất riêng
`site/value-intraday.json`; không chép kết quả backtest thành lịch sử paper.
Worker `paper_intraday.py` dùng chung lượt lấy nến thật của 146 mã cho cả 13
bot, lưu ý định lệnh trước khi cho phép khớp nến tương lai. Khởi tạo đúng thời
điểm thêm hai bot, bỏ qua nến cũ; khởi động GitHub trễ hoặc gián đoạn không
được tạo giao dịch bù. Workflow phút lưu cả hai tệp mới cùng sổ 11 bot cũ;
workflow ngày làm mới `state/value_daily_gates.json` sau đóng cửa. Bộ lọc ngày
thiếu/quá hạn thì hai biến thể tạm ngừng phát/khớp lệnh, không giả định đạt.
