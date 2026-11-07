# Trader Arena VN — bật mô phỏng theo giá trong phiên (iPhone)

**Trạng thái mặc định: CHƯA KẾT NỐI.** Bộ mã nguồn quote/paper đã vượt CI, nhưng GitHub Pages **không** chạy WebSocket 24/7. Dịch vụ live cần (1) DNSE market-data access hợp lệ, (2) một Render server giữ SQLite trên persistent disk, và (3) bật bridge URL của dashboard.

## I. DNSE API Key & Secret

1. Mở tài liệu chính thức https://developers.dnse.com.vn/docs/guide/intro/api_platform/ để xin OpenAPI credentials phù hợp với môi trường **Production market data**.
2. Chỉ lấy quyền đọc dữ liệu thị trường nếu DNSE hỗ trợ phân quyền. Không bật trading token, không chia sẻ mật khẩu, OTP, Trading Token cho app này.
3. **Không** gửi key/secret qua chat, issue, file GitHub, screenshot, hay `site/live-config.json`. Chỉ nhập dưới dạng **Environment Variables** riêng trên Render.

Nguồn phát: `wss://ws-openapi.dnse.com.vn`. SDK dùng `dnse-sdk-openapi`; quote `price` ở đơn vị nghìn VND và `quantity` ở số cổ phiếu. Quote G1 chỉ là sổ lệnh chào mua/chào bán, **không** là xác nhận khớp lệnh thật.

## II. Tạo Render service từ iPhone

1. Dùng **Safari**, đăng nhập https://dashboard.render.com , liên kết tài khoản GitHub `thanhngocreative-design`.
2. Mở https://dashboard.render.com/blueprints → **New Blueprint Instance** (cách hiển thị có thể thay đổi) → chọn repository `thanhngocreative-design/trader-arena-vn`.
3. Render đọc `render.yaml` tại thư mục gốc: tạo một **Web Service Docker**, region Singapore, **Starter plan** và **persistent disk 1GB** tại `/data`.
4. Trên Render → Environment / Blueprint variables, nhập:
   - `DNSE_API_KEY` = API key của DNSE;
   - `DNSE_API_SECRET` = API secret của DNSE.
   - `LIVE_DB_PATH` đã có sẵn ở `render.yaml`: `/data/live-papers.sqlite`.
5. Review mức phí Render **trước khi** bấm Deploy. Compute Starter + disk là tài nguyên tính phí; không tự triển khai hay tự thanh toán.
6. Sau khi service triển khai, mở `https://<your-service>.onrender.com/health`.

Một dịch vụ có thể trả về `service: online` ngay cả khi chưa được cấp credentials, chưa nhận giá thị trường, hoặc đang ngoài giờ giao dịch. **KHÔNG đánh đồng trạng thái web server với feed real-time.**

## III. Kết nối dashboard (không đưa secret vào repo)

Sau khi server online, lấy chính xác HTTPS URL của Render service rồi sửa **DUY NHẤT** `site/live-config.json` thành:

```json
{
  "enabled": true,
  "api_base": "https://<your-service>.onrender.com",
  "note": "Realtime paper quote estimates; no broker orders."
}
```

Thay `<your-service>` bằng host thật. Mã UI từ `site/index.html` sẽ gọi `/api/live` mỗi 5 giây khi được bật. `/api/live` có CORS cho **đúng** origin `https://thanhngocreative-design.github.io`.

**Cẩn thận:** đường dẫn API là công khai; endpoint chỉ trả kết quả tiền ảo và không có mã khóa/đặt lệnh. Không dùng nó cho tài khoản thật.

## IV. Kiểm tra chất lượng triển khai

- Trên Render `/health`: `configured=true` khi credentials đã nhập chính xác; `stream=true` nghĩa là kết nối WebSocket đang mở nhưng chưa đảm bảo có dữ liệu mới.
- Trên Render `/api/live`: `feed.claims_realtime=true` chỉ khi nhận quote hợp lệ trong khoảng 10 giây, trong giờ giao dịch; `recent_fills` chỉ hiển thị các lệnh **mô phỏng**.
- Khi mất mạng, quá 8 giây không có quote hợp lệ, đang ATO/ATC hoặc cuối tuần: engine không tự dựng giá để khớp lệnh.
- Khi mở iPhone dashboard, giữ **hai bảng tách biệt**: kết quả cuối ngày (GitHub) và kết quả mô phỏng bid/ask trong phiên (Render). Dịch vụ live dùng vốn tiền ảo riêng; không nhập nhằng lợi nhuận hai phương pháp.
- Nếu `feed.configured=false`, `last_error` có giá trị, hoặc chưa nhận quote, kiểm tra Render logs và quyền OpenAPI.

## V. Phạm vi giới hạn kỹ thuật

Bản đầu **chưa** làm toàn bộ 167 mã giao dịch intraday. Nó chỉ subscribe mã đang có lệnh chờ từ paper tín hiệu chốt phiên trước và mã đang nắm giữ; có thử điểm dừng bảo vệ qua quote G1.
- Không hỗ trợ intraday signal discovery trên toàn sàn, nến 1 phút cho chiến thuật CIS/BNF, ATO/ATC hay khớp lệnh hàng đợi thật.
- Tồn tại sai lệch vì giá BBO chưa chắc khớp thật; depth công bố không đảm bảo khối lượng thực được fill. Mỗi lệnh giả lập có phí và slippage.
- Ledger live nằm riêng trong `/data/live-papers.sqlite` và không nối ngược lại `state/paper_state.json`.
- Lịch Python EOD vẫn chạy độc lập qua GitHub Actions. Không bật order API hay đặt lệnh tiền thật.
- Không nên dùng gói host ngủ đông hoặc ổ đĩa tạm để nhận dữ liệu liên tục trong phiên.

## Link kiểm chứng

- DNSE docs: https://developers.dnse.com.vn/docs/guide/market-data/connect/
- DNSE Python SDK: https://github.com/dnse-tech/openapi-sdk/tree/main/python
- Render Blueprints: https://render.com/docs/blueprint-spec
- Render Pricing: https://render.com/pricing

**Mọi kết quả chỉ nhằm mục đích nghiên cứu paper trading; không phải lời khuyên mua bán.**
