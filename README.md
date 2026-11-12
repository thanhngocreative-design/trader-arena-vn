# Trader Arena VN

Bảng xếp hạng **11 bot giao dịch chứng khoán Việt Nam bằng tiền ảo**: 10 mô hình lấy cảm hứng từ trader và 1 mô hình Arena Hybrid. **Không đặt lệnh thật, không đọc thông tin tài khoản chứng khoán.**

- 📱 **Dashboard iPhone**: https://thanhngocreative-design.github.io/trader-arena-vn/
Dashboard có **6 tab và 11 bot trong mỗi tab**:

| Tab | Dữ liệu và sổ giao dịch |
| --- | --- |
| Paper phút | Sổ mới `state/paper_intraday.json`, tín hiệu và ATR chỉ từ phút mới thực nhận. |
| Paper ngày | Sổ mùa hiện tại `state/paper_state.json`; xử lý lệnh ngày đã ghi trước phiên. |
| Paper kết hợp ngày + phút | Sổ mới riêng; bộ lọc ngày đã đóng + xác nhận, ATR và thoát theo phút. |
| Backtest phút | 146 mã, 747 phiên, Vietcap 1 phút thật; không dùng bộ lọc/ATR ngày. |
| Backtest ngày | Kết quả nghiên cứu 146 mã đã xác minh; 5 khoảng thời gian. |
| Backtest kết hợp ngày + phút | Kết quả 146 mã: bộ lọc và stop ngày + xác nhận/khớp theo phút. |

**Mùa paper mới bắt đầu chung ngày 13/11/2026 theo yêu cầu reset**: cả 33 tài khoản (11 bot × 3 chế độ) về 100 triệu đồng, không có vị thế hay giao dịch mang sang. Lịch sử trước đó nằm trong `state/paper_archive/before-2026-11-13/`, có manifest kiểm tra hash; backtest giữ nguyên. Paper ngày được chuẩn bị tín hiệu thật đã đóng ngày 12/11 để có thể xét khớp phiên 13/11, nhưng chưa ghi giao dịch hoặc điểm NAV nào trước mùa mới. Nến phút trước ngày bắt đầu không được tạo lệnh.

Ở trang **Các bot**, mỗi hồ sơ có bảng so sánh đủ 6 sổ: tài sản, lãi/lỗ tiền và %, drawdown đã ghi nhận, số lần mua/bán. Bảng luôn dùng toàn bộ 3 năm cho ba backtest; paper theo mùa hiện tại. Số liệu paper tính từ toàn bộ sổ, không từ danh sách giao dịch rút gọn. Chạm tên sổ để xem chi tiết. Khi chưa có NAV paper, DD hiển thị “—”.

Ba backtest là ba mô hình khác nhau, không đổi tên cùng một kết quả. Các chiến thuật là mô hình nghiên cứu lấy cảm hứng từ trader, không phải chiến thuật riêng được xác thực. **Hybrid thuần phút là đồng thuận tín hiệu phút**, còn Hybrid ngày/kết hợp dùng bộ chọn ngày theo quá khứ. Biến thể paper kết hợp quản trị ATR/thoát phút; giả định này khác stop ngày của backtest kết hợp, được ghi trên dashboard.

**Tự động paper phút**: `.github/workflows/paper-minute.yml` khởi động 09:10 giờ Việt Nam các ngày trong tuần, quan sát đến khoảng 14:35, nghỉ ngoài khung liên tục chung 09:15–11:29 và 13:00–14:29. GitHub có thể khởi động trễ. Worker lấy Vietcap công khai (không dùng tài khoản broker), giới hạn tốc độ, lưu sổ và bản công khai mỗi khoảng 5 phút. Dashboard đọc sổ công khai mới mỗi phút. Đây là mô phỏng theo nến, không phải báo giá bid/ask realtime hoặc cam kết khớp thật.

Không phát sinh lệnh từ nến trước thời điểm khởi tạo hoặc nến nhận muộn hơn 75 giây sau đóng. Lệnh phải được lưu trước nến tương lai dùng để khớp; bỏ khoảng thiếu trên 3 phút, không chạy bù lúc mất kết nối. Chỉ dùng khối lượng nến tín hiệu để giới hạn 5% tham gia, có phí/thuế/trượt giá, lô 100, tối thiểu giữ 5 phiên và cooldown 7 phiên. **Trade theo phút không có nghĩa được bán T+0.** Hai paper mới có thể hợp lệ ở trạng thái chưa giao dịch, nhất là khi khởi tạo sau giờ đóng cửa.

Nguồn backtest là lịch sử Vietcap thật đã kiểm tra hash và độ phủ. Không nội suy nến thiếu. 146 mã được chọn sau khi biết có dữ liệu ngày liên tục đủ ba năm, nên có sai lệch chọn mẫu. Nến phút không khẳng định cổ phiếu có giao dịch ở mọi phút. Đầu vào gốc không được commit lên repo; chỉ công bố kết quả mô phỏng và thông tin độ phủ.

Chạy lại nghiên cứu thuần phút từ cache đã xác minh: `python run_minute_research.py`. Kiểm tra/khởi tạo paper tại thời điểm chạy: `python paper_intraday.py`; chạy trong phiên: `python paper_intraday.py --minutes 4`. Chạy này không bao giờ biến lịch sử backtest thành paper.

Nguồn DNSE bid/ask bên dưới là một thành phần tùy chọn riêng, chưa được cấu hình; không phải điều kiện để hai sổ paper theo nến Vietcap hoạt động.

## Bật server intraday trên Render (1 bước tạo cloud, sau đó cấp quyền dữ liệu)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/thanhngocreative-design/trader-arena-vn)

1. Mở **Deploy to Render** bằng Safari, đăng nhập Render và xác nhận tạo Web Service theo `render.yaml`. Cấu hình hiện tại là gói **Starter trả phí** và ổ đĩa bền vững 1 GB để lịch sử lệnh không mất khi khởi động lại. **Kiểm tra tổng tiền Render hiển thị trước khi xác nhận.**
2. Ở mục environment variables / secrets của Render, nhập **DNSE_API_KEY** và **DNSE_API_SECRET** do tài khoản LightSpeed API của chính bạn tạo. **Không gửi API key/secret qua chat hoặc commit lên GitHub.** Nếu chưa có tài khoản và quyền dữ liệu, đăng ký chính thức tại https://developers.dnse.com.vn/docs/guide/faq/ .
3. Render trả URL máy chủ HTTPS. Truy cập `https://<hostname>/health` và `https://<hostname>/api/live`. Chỉ khi `configured=true` và phiên giao dịch thật phát sinh quote mới thì `feed.claims_realtime=true`. **Ngoài giờ hoặc không có API key, đây vẫn chưa phải live.**
4. Gửi **chỉ URL HTTPS public của Render**, không gửi bất kỳ secret nào, để kết nối `site/live-config.json` vào app iPhone. Đường dẫn server phải là hostname Render thực tế, không đoán theo tên service.

**Lưu ý an toàn:** server này chỉ dùng DNSE *market-data* WebSocket, không chứa bất kỳ phương thức đặt/hủy/sửa lệnh chứng khoán nào. Nguồn quote có thể được cung cấp theo giấy phép/hạn mức của DNSE; nếu không được phép phân phối công khai, phải giới hạn việc công bố dashboard.

**Giới hạn mô phỏng:** quote bid/ask không chứng minh một lệnh thật sẽ được khớp. Lúc đầu chế độ live dùng **ý định mua/bán đã ghi sau phiên hôm trước** và stop bảo vệ theo quote; nó chưa tự tái tạo đầy đủ chiến thuật intraday của từng trader. EOD và Live là hai tài khoản mô phỏng độc lập; không được cộng lãi/lỗ vào nhau.

Xem chi tiết mô hình, cảnh báo và quy trình trong [README_IPHONE.md](README_IPHONE.md).
