# Kế hoạch mô phỏng Monte Carlo

**Trạng thái: đã triển khai phiên bản đầu.** Monte Carlo có trang riêng và chỉ hiển thị kịch bản giả định. Các sổ Paper và Backtest tiếp tục dùng kết quả từ nến thật, không bị thay bằng đường mô phỏng.

Tham khảo phương pháp: [tài liệu bootstrap chuỗi thời gian của R](https://stat.ethz.ch/R-manual/R-devel/library/boot/help/ts.return.html). Lấy mẫu theo khối giữ nguyên các đoạn thời gian liên tiếp; với nhiều bot, lấy cùng đoạn ngày cho tất cả bot. Các tham số bên dưới là giả thuyết nghiên cứu của Arena, không được chọn theo kết quả đẹp nhất.

## 1. Chuẩn hóa và kiểm chứng đầu vào

- Phạm vi: 19 bot, 6 sổ, 3 rổ; mỗi tổ hợp sổ/rổ có một bảng NAV theo phiên chung cho các bot.
- Dùng NAV đã lưu, gồm tiền mặt, cổ phiếu, lãi/lỗ chưa thực hiện, chi phí và dự phòng định giá đang áp dụng. Không thay bằng giá cổ phiếu hoặc danh sách 40 giao dịch rút gọn trên UI.
- Đối chiếu vốn đầu kỳ, NAV cuối kỳ và từng phiên với sổ gốc. Vốn đầu kỳ là mốc tài sản để tính cả lợi nhuận phiên đầu, không phải một nến thị trường được tạo thêm.
- Không tự điền NAV bị thiếu. Chỉ dùng lịch phiên đã kiểm chứng, loại ngày nghỉ giao dịch. Lưu mã phiên bản mô hình, ngày chốt, danh sách bot và mã băm nguồn để tái lập.
- Với sổ phút và ngày + phút, bước đầu vẫn lấy lợi nhuận NAV theo ngày. Không coi mỗi phút là một quan sát lợi nhuận độc lập.
- Ghi cả số giao dịch và mức tham gia thị trường; bot chỉ giữ tiền mặt không được mô tả là một chiến thuật đã chứng minh không có rủi ro.

## 2. Tạo kịch bản từ dữ liệu đã quan sát

- Chạy 10.000 kịch bản cho kỳ hạn giả định 252 phiên.
- Lấy mẫu có hoàn lại từng khối 10 phiên liên tiếp. Ghép các khối, cắt khối cuối theo đúng kỳ hạn. Dùng cùng chỉ số lấy mẫu cho tất cả bot và các nhóm Mix trong cùng tổ hợp sổ/rổ.
- Kiểm tra độ nhạy thêm với khối 5 và 20 phiên; không chọn độ dài khối theo lợi nhuận đẹp nhất.
- Cố định và lưu hạt giống ngẫu nhiên, số phiên nguồn, cách lấy mẫu và phiên bản chương trình. Tính theo lô để giới hạn bộ nhớ.
- Báo cáo chính cần ít nhất 252 phiên lợi nhuận chung đã quan sát. Paper hiện mới có vài tuần sẽ hiện **chưa đủ lịch sử**, không suy ra xác suất cả năm từ 17 phiên.
- Đây là tái tổ hợp lợi nhuận NAV ròng, không phải tạo nến thật hay replay lại toàn bộ lệnh. Các đường giả định không tái tạo chi tiết lô 100 cổ phiếu, thanh khoản và T+ dưới một thị trường mới. Phương pháp cũng không bảo đảm mô phỏng được khủng hoảng chưa từng có trong mẫu.

## 3. Đánh giá từng bot và nhóm Mix cố định

- Xuất tài sản/lợi nhuận cuối kỳ ở các mức p5, p50, p95; drawdown trung vị và p95; tỷ lệ kịch bản kết thúc dưới vốn đầu kỳ; tỷ lệ chạm drawdown 20%/30%; mức lỗ cuối kỳ trung bình trong 5% kịch bản xấu nhất.
- Các tỷ lệ này chỉ đúng trong mẫu và giả định lấy mẫu đã công bố, không phải xác suất tương lai được bảo đảm.
- Phiên bản đầu tính sẵn từng bot, Bật tất cả và Mix 2–6 best trên cloud. Nhóm bật/tắt thủ công không trùng các nhóm này hiện báo chưa có kết quả, không lấy số liệu nhóm khác. Đây là lựa chọn ưu tiên tốc độ và bộ nhớ trên iPhone. Khóa thành viên trước khi mô phỏng; không chọn lại người thắng trong từng kịch bản.
- Mỗi bot vẫn có tài khoản riêng 100 triệu. Mix N bot có vốn đầu kỳ N × 100 triệu; tổng NAV bằng tổng các tài khoản tại từng bước, không tự tái cân bằng về tỷ trọng bằng nhau mỗi ngày.
- Best Mix được chọn bằng kết quả quá khứ có sai lệch chọn người thắng. Báo cáo bootstrap của nhóm này mang tính mô tả. Để đánh giá khả năng chọn Mix trong tương lai, cần thêm kiểm tra cuốn chiếu: chọn nhóm trên giai đoạn huấn luyện, khóa nhóm và đánh giá ở giai đoạn tiếp theo chưa dùng để chọn.

## 4. Kiểm thử và đưa lên dashboard

- Kiểm thử đối chiếu NAV thật, tái lập cùng hạt giống, cùng khối ngày giữa các bot, tính drawdown/tổn thất đuôi, khóa nhóm Mix và từ chối mẫu thiếu/ngắn. Lịch sử thật phải giữ nguyên.
- Chạy thử bằng một bộ NAV thật nhỏ đã lưu, sau đó mới chạy đủ 18 tổ hợp sổ/rổ.
- Tính trên cloud sau khi các sổ đã được xác minh. Chỉ xuất các phân vị, biểu đồ phân phối và thông tin kiểm chứng; iPhone không phải tải hoặc tính toàn bộ đường mô phỏng. Workflow `monte-carlo.yml` được gọi sau khi Backtest đã xác minh và xuất bản; có thể chạy riêng để phục hồi phần phân tích. Lỗi phân tích không thay đổi các sổ giao dịch đã được lưu và xuất bản trước đó.
- Trang riêng **Monte Carlo — kịch bản giả định**, đi theo Sổ/Rổ/Mix đang chọn. Hiển thị vùng kịch bản, phân phối kết quả cuối kỳ, chỉ số rủi ro, ngày dữ liệu và số phiên nguồn. Trục thời gian ghi phiên mô phỏng, không giả làm ngày thị trường đã xảy ra.
- p5 là phân vị của các kịch bản, không phải mức sàn được bảo đảm hay khoảng tin cậy cho lợi nhuận tương lai. Leaderboard hiện tại vẫn dùng kết quả đã quan sát.

Các bước có thể làm sau: kiểm tra chi phí tăng thêm theo khối lượng giao dịch thật, hoặc replay toàn bộ đường thị trường giả định bằng bộ khớp lệnh nhân quả. Phải có phương pháp và kiểm chứng riêng; không cộng chi phí hai lần, không bịa nến, giá trượt hoặc lệnh để biến bootstrap NAV thành một backtest mới.

## Vận hành và kiểm chứng

- `monte_carlo_sources.py` lấy NAV phút/kết hợp từ checkpoint đầy đủ; dựng lại NAV ngày bằng cùng engine, đối chiếu toàn bộ giao dịch ALL và từng điểm biểu đồ/giá trị cuối kỳ trước khi dùng. Không nội suy biểu đồ 90 mốc thành lịch sử hàng ngày.
- `monte_carlo.py` thực hiện lấy mẫu chung theo khối; `run_monte_carlo.py` chỉ ghi cache phân tích và thống kê giả định dưới `state/monte_carlo/` và `site/monte-carlo/`. Không ghi vào giá, lệnh hay checkpoint giao dịch.
- Mỗi nhóm giữ cố định thành viên; nguồn có hash, phiên bản mô hình và hạt giống. Phần đồ thị dùng p5/p50/p95 làm tròn đến đồng; xác suất/phần trăm làm tròn sáu chữ số thập phân trong dữ liệu xuất.
- Trang dùng chung Sổ – Rổ – Mix, giữ lựa chọn khi đổi trang, kiểm tra đúng phiên/model/NAV trước khi hiện số. Sổ ngắn hoặc nguồn mới hơn kết quả phân tích sẽ hiện trạng thái tương ứng, không đưa ra xác suất thay thế.
