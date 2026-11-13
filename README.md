# Trader Arena VN

Bảng xếp hạng **13 bot giao dịch chứng khoán Việt Nam bằng tiền ảo**: 10 mô hình trader, Arena Hybrid và hai mô phỏng Buffett/Munger. **Không đặt lệnh thật, không đọc thông tin tài khoản chứng khoán.**

- 📱 **Dashboard iPhone**: https://thanhngocreative-design.github.io/trader-arena-vn/
Dashboard có **6 tab và 13 bot trong mỗi tab**. Quy tắc hiện hành: [rổ tháng và replay nến kế tiếp](docs/replay-protocol.md).

| Tab | Dữ liệu và sổ giao dịch |
| --- | --- |
| Paper phút | Replay sau phiên, nến đã đóng → mở cửa đúng phút kế tiếp; thiếu thì bỏ lệnh. |
| Paper ngày | Replay sau phiên; tín hiệu ngày → mở cửa phiên thị trường kế tiếp. |
| Paper kết hợp ngày + phút | Bộ lọc ngày trước, quyết định phút; cùng quy tắc khớp phút với backtest. |
| Backtest phút | 300 mã mỗi tháng, 498 mã từng xuất hiện; 747 phiên; nến phút thật, không nội suy. |
| Backtest ngày | Rổ tháng chọn theo quá khứ; 13 bot, 5 khoảng thời gian; 146 đối chiếu riêng. |
| Backtest kết hợp ngày + phút | Cùng rổ tháng, dữ liệu ngày trước + phút đã đóng; đúng phút kế tiếp. |

**Paper replay từ 13/11/2026**: 78 tài khoản (13 bot × 3 sổ × 2 rổ: Rổ tháng và Rổ cố định 146 mã sống sót), mỗi tài khoản 100 triệu đồng. Workflow `paper-replay.yml` chạy 16:47 và thử lại 18:47 giờ Việt Nam. Trước 16:00 không xử lý phiên hiện tại. Cùng phiên chạy lại không cộng thêm giao dịch; phiên mới không được sửa giao dịch đã chốt. Các sổ forward cuối cùng được lưu nguyên byte trong `state/paper_archive/before-eod-replay-2026-11-13/`; không cộng vào sổ replay. `state/paper_replay.json` giữ sổ đầy đủ; `site/paper-replay.json` là nguồn hiển thị ba paper. Các mục bên dưới về forward/146 mô tả triển khai cũ được giữ làm đối chiếu, không phải lịch chạy hiện hành.

Ở trang **Các bot**, mỗi hồ sơ có bảng so sánh đủ 6 sổ: tài sản, lãi/lỗ tiền và %, drawdown đã ghi nhận, số lần mua/bán. Bảng luôn dùng toàn bộ 3 năm cho ba backtest; paper theo mùa hiện tại. Số liệu paper tính từ toàn bộ sổ, không từ danh sách giao dịch rút gọn. Chạm tên sổ để xem chi tiết. Khi chưa có NAV paper, DD hiển thị “—”.

**Sửa luật thoát Darvas phút:** đáy thoát được tính từ **20 nến đã đóng trước nến tín hiệu**, không chứa đáy của chính nến đang xét. Sửa này áp dụng cho Darvas ở Backtest phút, Paper phút và Paper kết hợp (hai sổ paper dùng chung hàm thoát phút). Không đổi luật của 10 bot còn lại, Backtest ngày hoặc Backtest kết hợp. Kết quả Darvas phút trước sửa bị vô hiệu; bản chạy lại có revision `darvas_prior_low20_v2` trong audit. Có thể chạy lại riêng một bot bằng `python run_minute_research.py --bot Darvas`, giữ nguyên các kết quả khác; điểm tiếp tục được lưu sau các phiên hoàn tất.

Tab **Ngành** thống kê phân bố 146 mã theo ICB cấp 2 từ Vietcap, kèm danh sách mã và tỷ trọng số mã so với danh sách cổ phiếu hiện hành của cùng nguồn. Số liệu ngành là phân loại hiện tại, không phải lịch sử phân ngành theo từng ngày. Phần bot cho chọn đủ 6 sổ và 11 bot, so theo giá trị mua cộng dồn hoặc số lần mua. Không dùng danh sách 30–40 giao dịch gần nhất: backtest đã đối chiếu đủ 33 sổ hoàn chỉnh; paper đọc toàn bộ sổ riêng khi cập nhật. Giá trị mua cộng dồn không phải trọng số NAV; lãi/lỗ theo ngành là phần đã bán, không gồm vị thế đang giữ. Mã không có phân ngành vào nhóm “Chưa phân loại”, không tự đoán.

`python build_sector_stats.py` dựng lại thống kê từ cache đã xác minh; nến ngày được chạy lại chỉ để lấy đầy đủ giao dịch và phải khớp kết quả đã công bố trước khi xuất. Darvas phút dùng file revision v2. `python audit_market_expansion.py --symbols BVH,PVI,DHG,DMC,DRC,CSM` kiểm tra thử mã ngoài mẫu; mẫu phút đầu/cuối kỳ **không** chứng minh đủ toàn bộ lịch sử phút. `config/research-expansion-candidates.json` là danh sách ứng viên thực từ Vietcap, chưa phải tập 500–600 mã đã đủ điều kiện và không thay nhóm 146 đang chạy. Muốn nghiên cứu 500–600 mã, cần audit toàn bộ ngày/phút, nới giới hạn parser 210 và tách các kiểm tra cố định 146 sang một nghiên cứu mới; không đổi sổ paper hoặc bù nến thiếu để đạt số lượng.

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
