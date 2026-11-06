# Trader Arena VN — Real-time paper trading (v1)

**TRẠNG THÁI:** Code đã được triển khai lên GitHub; **chưa có kết nối DNSE live thực tế cho tới khi chủ tài khoản tự cấp khóa và tạo dịch vụ Render**. Phần này không được âm thầm ghi đè dữ liệu thi đấu EOD từ 06/11/2026.

## Mục tiêu

- Theo dõi **giá mua/bán cấp G1** từ **DNSE OpenAPI Market Data WebSocket**, không sử dụng khối đặt lệnh thật.
- Đo mô phỏng khớp từ **best ask khi mua**, **best bid khi bán**, phí môi giới và thuế hiện có, thêm slippage tối thiểu 0,15%/chiều.
- Mỗi lệnh ảo chỉ khớp sau khi được **đăng ký trước quote**. Không khớp ngược bằng giá quá khứ của thời điểm chạy.
- Nhận quote và cập nhật danh mục khi đang trong giờ giao dịch liên tục, ghi mỗi lần giả lập mua/bán và tổng NAV vào SQLite đĩa bền vững.
- Đảm bảo phân biệt **thị trường thật**, **khớp lệnh giả định**, và **lệnh chứng khoán thật** (không có).
- Một thiết bị iPhone dùng Safari là đủ để theo dõi. Backend chạy 24/7 trên cloud.

## Kiến trúc

```
Dữ liệu cuối ngày (GitHub Actions 16:47)
       |
       v
state/paper_state.json (tín hiệu, đã ghi từ phiên trước)
       |
       v
Render always-on service (1 instance, persistent disk)
   -> DNSE WebSocket: top_price.G1.json (có API key và secret)
   -> Chỉ nhận/simulate quote, không gửi order
   -> SQLite: tiền, lệnh chờ, vị thế, khớp giả lập, log
   -> GET /api/live (public, read-only)
       |
       v
GitHub Pages: dashboard iPhone, poll mỗi 3 giây (HTTPS)
```

Mô hình nguồn quote và SDK được mô tả tại:
- https://developers.dnse.com.vn/docs/guide/market-data/connect/
- https://github.com/dnse-tech/openapi-sdk/tree/main/python/websocket-marketdata

## Những việc cần làm **một lần** trên iPhone

### 1) Xin quyền dùng Market Data API tại DNSE

Mở [Hướng dẫn đăng ký LightSpeed API](https://developers.dnse.com.vn/docs/guide/intro/register_guide/).
Tài khoản DNSE ACTIVE là điều kiện đăng ký OpenAPI theo tài liệu. Trong DNSE, vào **Thông tin tài khoản → LightSpeed API → Đăng ký**, xác nhận OTP, sau đó lấy cặp **API Key / API Secret**. DNSE có thể áp dụng hạn mức, quyền dữ liệu và điều kiện sử dụng khác nhau.

**Không gửi key/secret vào ChatGPT, GitHub repo, commit, email hay tài liệu công khai.** Chỉ nhập trực tiếp vào mục **Environment / Secrets** của dịch vụ cloud tạo ở bước tiếp theo. Nếu muốn dùng tài khoản đặc quyền xem dữ liệu riêng biệt, hãy hỏi DNSE về việc cấp khóa có phạm vi chỉ đọc; ứng dụng này không gọi endpoint đặt lệnh.

### 2) Deploy backend lên Render

Bấm [Deploy to Render](https://render.com/deploy?repo=https://github.com/thanhngocreative-design/trader-arena-vn) bằng Safari. Đăng nhập Render và kết nối GitHub nếu được yêu cầu. Blueprint `render.yaml` trong repo mô tả một web service Python chạy liên tục, với **persistent disk** `/data`.

Render sẽ hỏi hai biến **DNSE_API_KEY** và **DNSE_API_SECRET** — điền vào ô bí mật của Render. Service được cấu hình gói **starter (có phí)** vì phiên bản miễn phí thường ngủ và không cung cấp persistent disk. Duy trì một process luôn-on; không scale thành nhiều instance vì sẽ ghi trùng lệnh vào cùng ledger.

Chạy xong, mở địa chỉ HTTPS của **chính service Render trả về** và kiểm tra:
- `/health` có `configured: true`.
- `/api/live` có `mode: realtime_paper` và `feed.configured: true`.
- `feed.claims_realtime` chỉ true khi đang có quote mới thực sự nhận được trong phiên; trước giờ giao dịch/ngoài giờ thường là false.

**Đừng nhầm** service đang online với giá đang realtime: cần có quote được đẩy về, timestamp thị trường không cũ quá 8 giây, và chỉ quote trên board `G1` trong giờ liên tục mới hợp lệ.

### 3) Nối dashboard iPhone

Sau khi dịch vụ Render hoạt động và đã có URL thật, mở `site/live-config.json` trong GitHub để sửa hai trường:

```json
{"enabled":true,"api_base":"https://DUONG-DAN-THUC-TE-DO-RENDER-CAP"}
```

**Không tự đoán URL.** File này chỉ chứa URL công khai, không chứa API key. Sửa và commit, GitHub Pages sẽ có file cấu hình mới khi được deploy lại qua workflow **Trader Arena VN daily paper contest → Run workflow**. Nếu cần cập nhật cấu hình ngay mà không chờ phiên chiều, vẫn có thể chạy workflow thủ công. Dashboard sẽ poll backend mỗi 7 giây khi `enabled=true`.

### 4) Đọc đúng trạng thái

- **CHƯA KẾT NỐI**: chưa có Cloud/URL đã xác minh, bảng EOD cũ còn hoạt động.
- **CHỜ DỮ LIỆU GIÁ**: service có thể đã online nhưng chưa có quote mới, đang ngoài giờ/đứt stream.
- **ĐANG NHẬN GIÁ**: service nhận quote đủ mới từ nguồn WebSocket, backend đã xác nhận tính mới.
- **MẤT KẾT NỐI**: dashboard không đọc được service; không giả vờ thị trường đang live.

## Thời gian Việt Nam

V1 chỉ mô phỏng khớp qua **lệnh giới hạn sổ lệnh G1 trong phiên liên tục thông thường**:
- 09:15–11:30 và 13:00–14:30 (thứ Hai–thứ Sáu).
- ATO (09:00–09:15 HOSE), ATC (14:30–14:45) và giờ nghỉ không được coi là khớp lệnh hợp lệ trong mô hình này.
- Nguồn đã bao gồm metadata `marketId` để phân biệt `STO`/HOSE, `STX`/HNX, `UPX`/UPCOM; cấu hình giờ cố tình thu hẹp vào hai cửa sổ liên tục giao nhau để tránh giả lập nhầm với đấu giá/giờ sau phiên trên HNX/UPCOM.
- Ngày nghỉ lễ không có quote hợp lệ; bot không tự tạo nến/trade. Khớp lệnh chỉ được ghi khi có thời gian thị trường hợp lệ, cập nhật từ G1 sau khi lệnh chờ tồn tại.

Tham khảo: https://www.ssi.com.vn/khach-hang-ca-nhan/quy-dinh-giao-dich/quy-dinh-giao-dich-co-phieu

## Phân biệt thời gian thực và phản ứng chiến thuật

- **Thời điểm mô phỏng khớp:** từ quote sau khi lệnh đã tồn tại, thường trong vài giây kể từ khi update được xử lý; KHÔNG phải xác nhận từ sở giao dịch.
- **Tín hiệu MUA** của các bot: hiện vẫn phát từ dữ liệu nến **cuối ngày trước đó**. Live service nhận kế hoạch trước phiên từ GitHub và thực thi **theo sổ lệnh trong phiên tiếp theo**.
- **BÁN bảo vệ**: sau tối thiểu 5 phiên nắm giữ, worker có thể đặt lệnh bán ảo nếu giá bid trong phiên vi phạm stop, nhưng chỉ mô phỏng khớp ở **quote tiếp theo** sau tín hiệu.
- **Không phải HFT, scalping hay true intraday strategy engine**. Để bot CIS/BNF và các bot khác tự quyết định vào lệnh mới trong phiên, cần nghiên cứu và test chiến thuật 1 phút riêng, yêu cầu dữ liệu nến đóng / lịch sử intraday + điều kiện thanh khoản, chưa coi là hoàn thành.
- Vì cổ phiếu cơ sở Việt Nam có chu kỳ thanh toán T+2,5, không được bán chính cổ phiếu vừa mua ngay trong phiên như thị trường T+0; mô phỏng giữ tối thiểu 5 phiên để bảo thủ hơn.

## Nguyên tắc khớp lệnh và cảnh báo quan trọng

- Tài khoản **live riêng biệt** bắt đầu với 100 triệu đồng ảo/bot. Cuộc thi EOD và backtest cũ **không thay đổi**. Không tự import giao dịch cũ thành giao dịch real-time mới.
- Lệnh chờ xuất phát từ `state/paper_state.json` được tải trước phiên. Nếu không có EOD hợp lệ từ ngày làm việc trước đó, từ chối queue mới (ngày nghỉ đặc biệt có thể dẫn đến tạm nghỉ hơn 1 ngày; đây là fail-closed).
- Không nhận quote không có timestamp, quote trễ hơn 8 giây, dữ liệu quá sớm hoặc sau giờ, book thiếu bid/offer hoặc spread quá 1,8%.
- Chỉ dùng tối đa **5% khối lượng chào tại mức giá tốt nhất**, lô 100, không mô phỏng lặp lại cùng phút; một lệnh BUY chỉ mô phỏng khớp một phần đã kiểm chứng, không giả định toàn bộ dư bán là thanh khoản chắc chắn.
- Giá giả lập vẫn cộng thêm phí, thuế và một mức trượt giá. Giá bid/ask **chưa bảo đảm** khớp thực: thứ tự ưu tiên lệnh, lệnh hủy, tranh mua/bán và độ trễ thực tế có thể làm lệnh không khớp.
- Quản lý sell theo số phiên đã nhận dữ liệu thực tế trong ledger; nếu worker tắt vài ngày, không suy diễn ngày khớp đã bỏ lỡ. Điều này bảo thủ hơn quy tắc thanh toán thực tế.
- Backend không có endpoint tạo lệnh thật và không gọi API broker đặt lệnh, chỉ `subscribe_quotes` tới websocket thị trường. Key cần cất kín và thu hồi khi không dùng.
- **Chưa có giấy phép tái phân phối** dữ liệu thị trường tới người khác được xác nhận. API `/api/live` chỉ xuất snapshot mô phỏng, không trả nguyên luồng bid/ask.
- Renderer số liệu EOD và live hoàn toàn riêng biệt. Khi live chưa chạy, site **không** hiển thị số liệu ngẫu nhiên thay cho live.

## Kiểm thử

CI: https://github.com/thanhngocreative-design/trader-arena-vn/actions/workflows/live-ci.yml

```bash
python -m pip install pandas numpy pytest
python -m pytest -q tests/test_live_paper.py
```

Chỉ test trên quote **tổng hợp mô phỏng cố định**; không khẳng định kết nối live đã hoạt động. Kết nối thực tế cần xác thực token DNSE + hosting cloud có persistent disk và quyền truy cập mạng được người dùng cấp.
