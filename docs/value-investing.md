# Buffett và Munger: mô phỏng theo ngày, phiên bản 1

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
trước đó, hiển thị ngày lấy dữ liệu. Bốn sổ phút/kết hợp không áp dụng.
