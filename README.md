# Trader Arena VN

Bảng xếp hạng **11 bot giao dịch chứng khoán Việt Nam bằng tiền ảo**: 10 mô hình lấy cảm hứng từ trader và 1 mô hình Arena Hybrid. **Không đặt lệnh thật, không đọc thông tin tài khoản chứng khoán.**

- 📱 **Dashboard iPhone**: https://thanhngocreative-design.github.io/trader-arena-vn/
- 📅 **Paper EOD**: tự cập nhật sau phiên vào ngày giao dịch, có backtest 5 khoảng thời gian, 167 mã ứng viên, phí và quản trị rủi ro.
- 📡 **Paper intraday** (chỉ khi Cloud và DNSE kết nối): theo dõi giá chào mua/bán WebSocket G1, giả lập khớp **sau thời điểm lệnh được tạo** với kiểm tra độ mới và thanh khoản. Đây là một tài khoản thi đấu khác, không gộp vào EOD.

## Bật server intraday trên Render (1 bước tạo cloud, sau đó cấp quyền dữ liệu)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/thanhngocreative-design/trader-arena-vn)

1. Mở **Deploy to Render** bằng Safari, đăng nhập Render và xác nhận tạo Web Service theo `render.yaml`. Cấu hình hiện tại là gói **Starter trả phí** và ổ đĩa bền vững 1 GB để lịch sử lệnh không mất khi khởi động lại. **Kiểm tra tổng tiền Render hiển thị trước khi xác nhận.**
2. Ở mục environment variables / secrets của Render, nhập **DNSE_API_KEY** và **DNSE_API_SECRET** do tài khoản LightSpeed API của chính bạn tạo. **Không gửi API key/secret qua chat hoặc commit lên GitHub.** Nếu chưa có tài khoản và quyền dữ liệu, đăng ký chính thức tại https://developers.dnse.com.vn/docs/guide/faq/ .
3. Render trả URL máy chủ HTTPS. Truy cập `https://<hostname>/health` và `https://<hostname>/api/live`. Chỉ khi `configured=true` và phiên giao dịch thật phát sinh quote mới thì `feed.claims_realtime=true`. **Ngoài giờ hoặc không có API key, đây vẫn chưa phải live.**
4. Gửi **chỉ URL HTTPS public của Render**, không gửi bất kỳ secret nào, để kết nối `site/live-config.json` vào app iPhone. Đường dẫn server phải là hostname Render thực tế, không đoán theo tên service.

**Lưu ý an toàn:** server này chỉ dùng DNSE *market-data* WebSocket, không chứa bất kỳ phương thức đặt/hủy/sửa lệnh chứng khoán nào. Nguồn quote có thể được cung cấp theo giấy phép/hạn mức của DNSE; nếu không được phép phân phối công khai, phải giới hạn việc công bố dashboard.

**Giới hạn mô phỏng:** quote bid/ask không chứng minh một lệnh thật sẽ được khớp. Lúc đầu chế độ live dùng **ý định mua/bán đã ghi sau phiên hôm trước** và stop bảo vệ theo quote; nó chưa tự tái tạo đầy đủ chiến thuật intraday của từng trader. EOD và Live là hai tài khoản mô phỏng độc lập; không được cộng lãi/lỗ vào nhau.

Xem chi tiết mô hình, cảnh báo và quy trình trong [README_IPHONE.md](README_IPHONE.md).
