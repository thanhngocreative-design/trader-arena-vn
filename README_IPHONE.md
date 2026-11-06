# Trader Arena VN — iPhone-first / Cloud-ready

Đây là bản **mobile-first Web App** với 10 bot mô phỏng quy tắc công khai hoặc các chiến thuật nghiên cứu được gắn với Mark Minervini, William O’Neil, Nicolas Darvas (Mỹ), Takashi Kotegawa/BNF và CIS (Nhật Bản), Kristjan Kullamägi/Qullamaggie và Andrea Unger (châu Âu). Mỗi bot bắt đầu từ 100 triệu đồng **tiền ảo**. Không có API mua bán chứng khoán và KHÔNG KẾT NỐI TÀI KHOẢN BROKER.

**Bản có trong ZIP là một dự án sẵn sàng triển khai, KHÔNG PHẢI website đã được công khai, và không có tài khoản Telegram nào đã kết nối.** Mở `site/index.html` trước khi triển khai sẽ chỉ thấy chế độ `DEMO`: các số liệu đều mang tính minh họa.

## Người chỉ sử dụng iPhone cần làm gì?

### 1. Đưa project lên GitHub (làm một lần)

- Tạo tài khoản GitHub nếu chưa có. Cách đỡ phải thao tác máy tính nhất là **kết nối GitHub trong ChatGPT** để có thể yêu cầu trợ lý giúp chuẩn bị repository và đẩy mã nguồn (các quyền sẽ do bạn chấp thuận).
- Hoặc tải ZIP, giải nén và upload tất cả nội dung thư mục `trader_arena_mobile/` vào **gốc** một repository tên ví dụ `trader-arena-vn`, nhánh `main`.
- GitHub repo công khai + GitHub Pages công khai sẽ khiến người khác xem được dashboard. Nếu muốn dashboard riêng tư, cần nền tảng triển khai có đăng nhập hoặc tính năng phù hợp; **đừng** đưa dữ liệu tài khoản thật hoặc token vào repo.

### 2. Bật GitHub Pages (làm một lần)

- Trên GitHub, mở `Settings → Pages → Build and deployment → Source: GitHub Actions`.
- Trên repo, mở `Actions`, chạy workflow **Trader Arena VN daily paper contest** bằng nút **Run workflow** (hoặc để tự kích hoạt sau khi push mã).
- Workflow: cài Python 3.11 và vn-market-data v0.4.0; thử engine; lấy giá cổ phiếu và VN-Index; chạy backtest độc lập cho 10 bot và 5 khoảng thời gian; cập nhật ví tiền ảo; xuất `site/dashboard.json` và deploy `site/index.html` qua GitHub Pages.
- Lịch chạy mặc định **16:47 giờ Việt Nam thứ Hai–thứ Sáu** (09:47 UTC). GitHub có thể chạy trễ hoặc bỏ lượt; đừng coi đây là dịch vụ dữ liệu thời gian thực. Nếu thị trường nghỉ, không phát sinh phiên mới.
- Vào URL Pages do GitHub trả về. Mở trên Safari → Share → **Add to Home Screen** để dùng như một app iPhone.

### 3. Bật tin nhắn Telegram cuối ngày (tùy chọn)

- Trên Telegram, tạo bot qua **@BotFather**, lấy bot token. Bắt đầu chat với bot và xác định chat ID của bạn.
- Trên GitHub, vào `Settings → Secrets and variables → Actions → New repository secret`, thêm đúng hai secret tên `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID`. TUYỆT ĐỐI không gửi bot token qua chat hoặc commit token vào mã nguồn.
- Workflow chỉ gửi báo cáo khi có **phiên giao dịch mới** và đã build/deploy thành công. Không gửi trùng khi hệ thống chạy lại cùng phiên.
- Dữ liệu đang lấy qua các endpoint công khai của DNSE/Vietcap; tính khả dụng và hạn mức có thể thay đổi. Chương trình không bịa số nếu dữ liệu thất bại.

## Dashboard giải thích được gì?

- **Thi đấu mỗi ngày:** sổ tiền ảo được ghi nối tiếp vào `state/paper_state.json`. Lần chạy đầu tiên **không tự bịa giao dịch trong quá khứ**; tín hiệu chốt ngày đầu sẽ được chờ tới phiên tiếp theo, lệnh ảo chỉ được xác nhận sau khi có giá mở cửa thực tế của phiên đó. Nếu hệ thống bỏ lỡ một ngày, KHÔNG tạo lệnh ảo đã khớp trong ngày bị bỏ lỡ; thông báo độ tin cậy bị giảm.
- **Thử lại quá khứ:** backtest trên 12 mã cổ phiếu được lựa chọn mặc định và VN-Index từ ngày 03/01/2023, sử dụng dữ liệu giá lịch sử tải từ DNSE/Vietcap qua vn-market-data. Backtest được tính lại hàng ngày và có thể thay đổi khi nguồn điều chỉnh giá lịch sử.
- **Các bot:** 10 bot thuộc bốn khu vực (Mỹ / Nhật / châu Âu / Việt Nam) có tiền mặt, danh mục, lãi/lỗ, vì sao mua bán và lệnh dự định của ngày kế tiếp.
- **Nhật ký:** ngày, mã, số lượng, giá khớp GIẢ ĐỊNH, lý do và lãi/lỗ mô phỏng.
- **Giải thích:** ngôn ngữ dễ hiểu, phân biệt backtest với paper-forward.

## Quy tắc và giới hạn

- Bot được **lấy cảm hứng từ sách/quy tắc công khai**; KHÔNG chứng minh chính là lịch sử lệnh thực tế của các trader được nêu tên.
  - Mỹ: Minervini (Trend Template rút gọn), O’Neil (breakout/volume/market filter), Darvas (box-breakout proxy). Không có VCP/CAN SLIM đầy đủ.
  - Nhật: BNF (độ lệch dưới SMA25 và nhịp hồi, proxy), CIS (bám đà tăng ngắn hạn, proxy). Không có thông số lệnh gốc được xác thực.
  - Châu Âu: Qullamaggie (momentum breakout sau vùng tích lũy, proxy); Unger (breakout có lọc ATR, **chỉ là chuyển thể** từ tư duy systematic trading, khác thị trường futures gốc).
  - Việt Nam: Thái Phạm (VSA price-volume breakout proxy), Dương Văn Chung (oversold bounce proxy), P.Thai Capital (momentum+ATR multi-factor proxy; không dùng mã nguồn hay tín hiệu độc quyền V20).
  - Mỗi bot mới bắt đầu paper-forward từ ngày được thêm vào; tài khoản các bot cũ không bị làm lại, không có lệnh được tự tạo lùi ngày. Cả 10 bot có backtest riêng cho từng thời lượng, chỉ là thành tích giả lập.
- Data: `vn-market-data` v0.4.0, gọi `get_ohlcv()` qua DNSE và Vietcap, giá cổ phiếu quy đổi từ VND sang đơn vị nghìn VND cho backtester. Đây là **dữ liệu từ bên trung gian**, không phải kết nối trực tiếp sàn HOSE; cần tuân thủ điều kiện sử dụng của nhà cung cấp.
- Danh sách 12 mã (FPT, HPG, VCB, MBB, TCB, ACB, MWG, VNM, SSI, PNJ, DGC, VHM) cố định có thiên lệch chọn mẫu/survivorship. Không đại diện toàn bộ thị trường.
- Tài khoản giả lập, phí mua/bán 0,15% mỗi chiều, thuế bán 0,1%, trượt giá 0,15%, lô 100 và tối đa 4 vị thế. Bán T+3 ở giá mở cửa mô phỏng để tránh giả định bán được trước T+2 chiều.
- **Chưa xử lý chính xác:** cổ tức, chia tách, hủy niêm yết, trần/sàn, order book, lệnh có thể không khớp, ảnh hưởng giá khi giao dịch và thay đổi giá quá khứ sau điều chỉnh. Backtest không phải lời hứa lợi nhuận.
- Không thêm giá giả vào báo cáo dữ liệu thật. Khi nguồn dữ liệu lỗi, script **thất bại** thay vì xuất kết quả mới bằng dữ liệu cũ; website đã triển khai lần trước có thể vẫn đang hiển thị kỳ dữ liệu gần nhất, xem nhãn **Phiên** để nhận biết.
- GitHub Pages website không có đăng nhập mặc định và GitHub Actions chỉ chạy theo lịch **best-effort**; muốn sản phẩm thương mại cần bổ sung xác thực, giám sát job và license dữ liệu.

## Cấu trúc mã

- `site/index.html`: dashboard responsive, offline demo fallback, không có quảng cáo hay Javascript ngoài.
- `generate_dashboard.py`: đồng bộ dữ liệu, chạy backtest và xuất JSON cho dashboard, gửi Telegram nếu cấu hình đủ.
- `paper_forward.py`: lưu sổ tiền ảo nối tiếp mỗi phiên; chống chạy trùng.
- `engine.py`: chiến thuật và backtesting engine phiên bản MVP.
- `datafeed.py`: tải và kiểm tra OHLCV qua DNSE/Vietcap (thư viện vn-market-data).
- `.github/workflows/daily.yml`: lịch chạy GitHub Actions, lưu lại kết quả/ledger, GitHub Pages deploy.
- `tests/`: test engine, tránh lookahead và kiểm tra ledger.

## Kiểm tra bằng môi trường Python (không bắt buộc cho người dùng iPhone)

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python generate_dashboard.py
```

Để chạy pipeline thật cần Internet và phải tuân thủ hạn mức/quyền sử dụng dữ liệu của nhà cung cấp. Ứng dụng đã từng chạy end-to-end thành công qua GitHub Actions, dữ liệu thực do nhà cung cấp thị trường trả về. Việc bổ sung bot phải vượt kiểm thử trên GitHub trước khi xem là triển khai ổn định.


## Tài liệu gốc để phân biệt dữ kiện và giả thuyết

- BNF: https://h9nfp.com/bnf/ (nguồn thứ cấp, không phải nhật ký lệnh gốc).
- CIS: https://diamond.jp/zai/articles/-/197112 (phỏng vấn) và https://www.kadokawa.co.jp/topics/2730/ (nhà xuất bản).
- Qullamaggie: https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/ (bài của trader).
- Andrea Unger: https://ungeracademy.com/blog/the-trading-edge và https://newcitytrader.com/conversation-with-andrea-unger/ (bài viết và phỏng vấn).

Nguồn tham khảo không chứng minh bộ mã này phản ánh chính xác toàn bộ quy trình giao dịch của người gốc.

## Cập nhật bản 10 bot — bộ điều khiển trên iPhone

- **Khoảng backtest:** 3 tháng, 6 tháng, 1 năm, 2 năm hoặc từ 03/01/2023. `generate_dashboard.py` chạy riêng từng cửa sổ thời gian, mỗi lần reset 100.000.000đ tiền ảo, với dữ liệu chỉ có sẵn trước ngày giao dịch. Không chỉ cắt/đổi gốc đường NAV cũ.
- **Bật/tắt trên màn hình:** các công tắc trong thẻ từng bot dùng `localStorage` của iPhone để chọn bot tham gia bảng xếp hạng. Điều này KHÔNG tác động đến server hay lịch sử paper. Reset dữ liệu Safari có thể xóa các công tắc hiển thị.
- **Bật/tắt thực sự trên cloud:** `config/bots.json` được backend đọc mỗi phiên. Dùng workflow `Bat/tat bot tien ao` tại `Actions → Run workflow` để chọn tên bot + `on/off` (hoặc nhờ ChatGPT cập nhật file), không cần máy tính. Tắt cloud có nghĩa không mở/chốt lệnh ảo mới; các cổ phiếu đã giữ vẫn được định giá theo thị trường, không tự động bán. Khi bật lại, kế hoạch giao dịch mới được tính ở phiên tiếp theo.
- **Chart mã cổ phiếu:** dữ liệu OHLCV theo ngày của 12 mã đang nghiên cứu được đính vào `site/dashboard.json`; chạm tên mã trong Giỏ cổ phiếu, Nhật ký, Kế hoạch mua/bán, hoặc danh sách mã ở Trang chủ. Chọn 1 tháng / 3 tháng / 6 tháng / 1 năm / tối đa; chạm biểu đồ để xem giá và khối lượng.
- **Giới hạn:** GitHub Pages là site tĩnh; công tắc trên web không thể trực tiếp thay đổi cấu hình server một cách an toàn nếu không có phần đăng nhập/ủy quyền phía backend. Repo Pages công khai; cần xem xét điều kiện tái phân phối dữ liệu thị trường của nhà cung cấp.
- **Nguồn tham khảo Việt Nam:** https://www.youtube.com/watch?v=r_SSPGd88mE · https://happy.live/cau-truc-toan-dien-cua-phuong-phap-luan-wyckoff/ · https://pthaicapital.io.vn/en/methodology . Mọi thông số trong bot là giả thuyết thử nghiệm, không được diễn giải thành hệ thống giao dịch cá nhân đã xác minh.
