# 300 mã mỗi tháng: giảm điều kiện chọn mã sống sót

Giữ nguyên bản nghiên cứu 146 cũ và toàn bộ lịch sử paper. Người dùng đã chọn
**300 mã tại mỗi thời điểm, chọn lại hàng tháng**; không phải đúng 300 tên
giữ cố định. Cửa sổ nghiên cứu vẫn 13/11/2023–12/11/2026, gồm 747 phiên thật.

## Chọn mẫu trước kỳ, không nhìn cuối kỳ

Nguồn khám phá mã là danh mục Vietcap đang lưu: 1.757 cổ phiếu, gồm cả nhóm
hiện giao dịch và nhóm nguồn xếp vào DELISTED. Không lọc bỏ nhóm DELISTED.
Lịch sử ngày tải từ 2021 để đủ thời gian làm nóng chỉ báo và chọn theo quá khứ.
Mỗi kỳ tháng lấy phiên thị trường đầu tháng làm ngày hiệu lực. Chỉ dùng những
phiên đã qua trước ngày đó để:

1. Yêu cầu ít nhất 252 quan sát ngày có khối lượng dương và OHLC hợp lệ.
2. Có ít nhất 40 quan sát hợp lệ trong 60 phiên thị trường gần nhất và ít nhất
   một quan sát trong 5 phiên gần nhất.
3. Xếp hạng tổng giá đóng ×khối lượng quan sát được trong 60 phiên, chia cho
   số phiên tham chiếu. Phiên thiếu không tự tạo giá/khối lượng; không góp vào
   tổng giá trị đã quan sát. Đây là thước đo thanh khoản trên dữ liệu nguồn.
4. Chọn 300 mã đứng đầu; đồng hạng thì theo mã chữ cái. Không dùng lợi nhuận
   tương lai, trạng thái còn tồn tại cuối kỳ hoặc độ phủ phút để chọn/thay mã.

37 kỳ có đủ 300 mã mỗi kỳ; tổng cộng **498 mã từng xuất hiện**. Trong đó có
11 mã hiện thuộc nhóm DELISTED của nguồn: BCG, BCR, HIO, HTP, LTG, PSH, RDP,
TC6, TDN, TKG, VOC. Đây là trạng thái danh mục nguồn hiện tại, không phải bản
chứng nhận ngày niêm yết/hủy niêm yết lịch sử của sở giao dịch.

SJF có trong kỳ chọn tháng 11/2023 theo thông tin trước kỳ. Nhưng giá ngày có
khối lượng dương và phút đều dừng ngày 10/11/2023, trước cửa sổ nghiên cứu.
Không thay SJF bằng mã sống sót khác; không có nến thì không có lệnh khớp.
Các nến khối lượng 0 hoặc OHLC lỗi được ghi nhận và loại ở cấp quan sát,
không loại toàn bộ công ty chỉ vì một nến lỗi/một giai đoạn ngừng giao dịch.

## So sánh 300 với 146

Ba lựa chọn trên dashboard:

- **300 xoay vòng:** mẫu theo từng tháng ở trên.
- **146 đối chiếu:** 146 tên cũ được tính lại trên cùng nguồn giá và cùng quy
  tắc thực thi/định giá với mẫu 300. Đây là nhóm kiểm soát, vẫn là nhóm chọn
  sau khi biết lịch sử liên tục; không tự trở thành mẫu không sai lệch.
- **146 cũ:** kết quả đã lưu trước khi mở rộng, giữ nguyên để xem lại.

Cả hai nghiên cứu mới có 13 bot và ba loại backtest ngày/phút/kết hợp.
Không chỉnh tham số chiến thuật sau khi nhìn kết quả mẫu 300. Hybrid chọn
nhóm chiến thuật bằng cửa sổ lịch sử trước đó, không dùng kết quả cuối kỳ.
Hai mô hình Buffett/Munger tiếp tục dùng báo cáo năm có ngày công bố/cập nhật
thật, thiếu số liệu thì không tự điền; phạm vi phi tài chính và giới hạn mô
phỏng được giữ. Chênh lệch với bản 146 cũ có thể gồm thay đổi nguồn/điều chỉnh
giá và quy tắc dữ liệu; dùng **146 đối chiếu** để so cùng phương pháp.

Phút được tải theo danh sách đã chọn xong, không chọn mẫu theo mã có phút.
Dùng các nến quan sát thực, có khối lượng dương, trong cửa sổ liên tục chung
09:15–11:29 và 13:00–14:29. Không nội suy. Khoảng thiếu, nến 0 khối lượng,
phiên lệch giá ngày/phút vượt giới hạn kiểm chứng đều được thống kê riêng;
không tạo giá/lệnh để đạt một con số độ phủ đẹp. Kiểm dấu thời gian tín hiệu,
ngày báo cáo, điều kiện thành viên và lô/khối lượng dựa trên quá khứ.

Mã ra khỏi nhóm ở kỳ mới không được mua thêm; yêu cầu thoát chỉ được khớp
trên quan sát thật sau khi đủ thời gian chờ bán. Không bán lùi ở “ngày giao
dịch cuối” mà sau này mới biết. Vị thế chưa bán được vẫn chiếm chỗ và không
giải phóng tiền mặt giả. Sau 20 phiên không có giá quan sát, NAV thận trọng
dự phòng 100% giá trị đang treo; đồng thời công khai NAV theo giá quan sát
cuối. **Dự phòng không phải giá thị trường 0, lệnh bán, hay kết luận cổ đông
đã mất toàn bộ giá trị.** Giá thật xuất hiện lại thì cập nhật lại định giá.

## Phần sai lệch còn lại

Đây là cải thiện cách lấy mẫu, **không tuyên bố xóa hết sai lệch**:

- Danh mục hiện tại cộng phần mã cũ nguồn còn giữ không phải kho danh mục
  chứng khoán lịch sử đầy đủ. Mã bị xóa hoàn toàn vẫn có thể vắng mặt.
- OHLCV có thể đã điều chỉnh theo quyền về sau, không phải bản giá gốc từng
  thời điểm; thanh khoản tính theo giá và các ngưỡng giá tuyệt đối còn có thể
  chịu ảnh hưởng. Chưa dựng đầy đủ tổng lợi nhuận, cổ tức và quyền.
- Báo cáo tài chính là các phiên bản nhà cung cấp hiện trả; giữ lại đến ngày
  công bố/cập nhật +1 ngày giúp tránh dùng quá sớm, nhưng không tái tạo được
  toàn bộ phiên bản cũ. Mã thiếu báo cáo có thể tạo thêm sai lệch độ phủ.
- Phân ngành là ICB hiện tại, dùng mô tả giao dịch và giới hạn phi tài chính của hai bot giá trị; chưa có lịch sử ngành nên phần loại ngành này cũng chưa phải dữ liệu theo từng thời điểm.
- Kết quả vẫn là mô phỏng với phí, thuế, trượt giá và giới hạn thanh khoản,
  không phải giao dịch broker hay kiểm chứng lợi nhuận tương lai.

Nguồn tham khảo phương pháp: [QuantConnect Research Guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide).
Nguồn số liệu: Vietcap public chart OHLCV và IQ; SHA từng nguồn/ngày chốt được
lưu trong cấu hình và kiểm toán xuất bản. Mọi ví dụ giả trong kiểm thử chỉ ở
tệp/thư mục kiểm thử, không tham gia danh sách hoặc kết quả công khai.

## Tái chạy

`collect_pit_daily.py` → `pit_universe.py` → `collect_pit_minute.py` →
`value_fundamentals.py --config config/research-300.json --output data/pit_results/fundamentals.json --allow-missing`
→ `pit_daily.py` → `pit_intraday.py` → `publish_pit.py`.
Nguồn thô/bộ nhớ đệm ở `data/pit_*`, không trộn với `data/prices` của paper.
Khi thay quy tắc/nguồn phải dùng bộ đệm kết quả mới; dấu kiểm nguồn chặn tái
sử dụng kết quả kết hợp với đầu vào khác. Báo cáo tài chính nguồn dùng cho
nghiên cứu được đóng băng riêng, không ghi đè snapshot của hai bot cũ.

Từ revision `strict_next_candle_v1`, cả ba backtest dùng đúng nến kế tiếp;
thiếu nến đó thì bỏ lượt khớp, không dời lệnh qua 1–3 phút. Paper chuyển sang
replay sau phiên từ 13/11/2026 và dùng chung bộ máy; sổ forward cũ được lưu
nguyên byte. Không biến kết quả ba năm thành lịch sử paper. Xem
[quy tắc và vận hành replay](replay-protocol.md). Snapshot 146 cũ vẫn giữ riêng.
