"""Causal, predeclared Arena proxies; no retrospective chart labels or tuning."""
import pandas as pd

MODES = ['paper_minute', 'paper', 'paper_combo', 'backtest_minute', 'backtest', 'hybrid']
PROFILES = {
    'Wyckoff': dict(name='Wyckoff', emoji='🔎', region='US', flag='🇺🇸',
        tag='Spring · phá hỗ trợ giả rồi xác nhận',
        explain='Chờ giá xuyên hỗ trợ rồi đóng trở lại trong vùng tích lũy; mua sau khi vượt đỉnh nến spring với khối lượng xác nhận.',
        detail='Proxy spring của Arena, không phải bộ nhận diện mọi pha Wyckoff. Hỗ trợ/kháng cự từ 30 nến trước; biên độ tối đa 25% ngày hoặc 4% phút. Spring xuyên hỗ trợ tối đa 3% ngày hoặc 0,8% phút, đóng trở lại trên hỗ trợ, volume ≥0,8 lần bình quân 20 nến trước. Trong 10 nến ngày/20 nến phút tiếp theo, mua một lần khi đóng vượt đỉnh spring và volume >1,2 lần bình quân; hủy cấu trúc nếu thủng đáy spring. Tối đa 5 mã. Thoát ngày khi lỗ 8% hoặc giảm 2,5 ATR từ đỉnh; phút dưới MA20 hoặc lỗ 8%. Ngày + phút dùng tín hiệu ngày hôm trước và xác nhận phút chung. Tham số đặt trước, chưa tối ưu theo lợi nhuận.',
        source='https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial', supported_modes=MODES.copy()),
    'Ichimoku': dict(name='Ichimoku', emoji='☁️', region='JP', flag='🇯🇵',
        tag='Mây Ichimoku · thuận xu hướng',
        explain='Mua khi giá trên mây, Tenkan trên Kijun, động lượng và mây dự phóng cùng tích cực; chỉ phát tín hiệu khi mới đủ điều kiện.',
        detail='Thông số 9/26/52, mây hiện tại lấy Senkou A/B tính từ 26 nến trước. Giá phải trên cả hai biên mây, Tenkan>Kijun, đóng cửa cao hơn 26 nến trước và Senkou A tính hiện tại>Senkou B tính hiện tại. Không dùng shift âm hay giá tương lai của Chikou. Một tín hiệu khi chuyển sang trạng thái đủ điều kiện; cần ít nhất 78 nến. Phút là biến thể thử nghiệm tính trên nến phút thật trong phiên. Tối đa 6 mã. Thoát ngày dưới Kijun hoặc lỗ 8%; phút dưới MA20 hoặc lỗ 8%. Ngày + phút dùng tín hiệu ngày hôm trước và xác nhận phút chung. Cùng vốn, ATR, phí/T+ và luật khớp nến kế tiếp của Arena.',
        source='https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/ichimoku-cloud', supported_modes=MODES.copy()),
}


def ichimoku_lines(high, low):
    def midpoint(n):
        return (high.rolling(n).max() + low.rolling(n).min()) / 2
    conversion, base, slow = midpoint(9), midpoint(26), midpoint(52)
    return conversion, base, (conversion + base) / 2, slow


def ichimoku_entries(close, high, low):
    conversion, base, a, b = ichimoku_lines(high, low)
    regime = ((close > a.shift(26)) & (close > b.shift(26)) &
              (conversion > base) & (close > close.shift(26)) & (a > b)).fillna(False)
    return regime & ~regime.shift(fill_value=False)


def wyckoff_entries(close, high, low, volume, *, minute=False):
    if isinstance(close, pd.DataFrame):
        return pd.DataFrame({k: wyckoff_entries(close[k], high[k], low[k], volume[k], minute=minute)
                             for k in close}, index=close.index)
    floor = low.shift().rolling(30).min()
    roof = high.shift().rolling(30).max()
    average = volume.shift().rolling(20).mean()
    penetration, width, expiry = (.008, .04, 20) if minute else (.03, .25, 10)
    spring = ((low < floor) & (low >= floor * (1 - penetration)) &
              (close > floor) & (close <= roof) & (roof / floor - 1 <= width) &
              (volume >= average * .8)).fillna(False)
    group = spring.cumsum()
    trigger = high.where(spring).ffill(limit=expiry)
    invalidation = low.where(spring).ffill(limit=expiry)
    # A later breach invalidates the whole current structure permanently.
    intact = low.groupby(group).cummin() >= invalidation
    hit = ((close > trigger) & intact & (volume > average * 1.2)).fillna(False)
    return (hit & (hit.groupby(group).cumsum() == 1)).rename(close.name)


def entries(close, high, low, volume, *, minute=False):
    return {'Wyckoff': wyckoff_entries(close, high, low, volume, minute=minute),
            'Ichimoku': ichimoku_entries(close, high, low)}
