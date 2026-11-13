"""Predeclared educational models; complexity is not a promise of performance.

Sources explain the concepts, not these Arena-specific numerical parameters.
The minute versions are separate experimental adaptations, not day indicators
calculated from the future session close. No parameter search is performed.
"""
PROFILES={
    'Beginner':dict(name='Beginner Trader',emoji='🌱',region='MIX',flag='🌍',
        tag='Cơ bản · giao cắt đường trung bình',
        explain='Mua khi SMA20 cắt lên SMA50, giá trên SMA20; thoát khi xu hướng đảo hoặc lỗ 8%.',
        detail='Mô hình học đường trung bình: ngày dùng SMA20/50; phút dùng MA5/20 của chính phiên. Tối đa 4 mã, cùng phân bổ ATR và luật khớp nến kế tiếp như các bot khác. Ngày + phút yêu cầu tín hiệu ngày hôm trước và xác nhận giá trên MA5/VWAP ở phút đã đóng.',
        source='https://www.cmegroup.com/education/courses/technical-analysis/understanding-moving-averages'),
    'Intermediate':dict(name='Intermediate Trader',emoji='🧭',region='MIX',flag='🌍',
        tag='Trung cấp · breakout và khối lượng',
        explain='Mua vượt đỉnh 20 phiên, khối lượng trên 1,2 lần bình quân, giá trên SMA50 và thị trường thuận lợi.',
        detail='Ngày dùng breakout 20 phiên + volume + bộ lọc VN-Index; phút dùng breakout 20 nến + MA10/20 + volume của chính phiên. Thoát mất SMA20/MA20 hoặc lỗ 7%. Tối đa 6 mã; ngày + phút thêm xác nhận breakout/VWAP sau bộ lọc ngày hôm trước.',
        source='https://www.schwab.com/learn/story/ways-volume-can-help-confirm-price-trends'),
    'Pro':dict(name='Pro Trader',emoji='🔬',region='MIX',flag='🌍',
        tag='Nâng cao · sức mạnh tương đối và biến động',
        explain='Kết hợp xu hướng SMA50/100/200, vượt đỉnh 55 phiên, mạnh hơn VN-Index và kiểm soát biến động ATR.',
        detail='Ngày: SMA50>SMA100>SMA200, giá vượt đỉnh 55 phiên, RS60>5%, ATR14/giá 1–5%, volume>1,3 lần, thị trường thuận lợi. Phút: MA5>MA10>MA20, vượt đỉnh 30 nến, đà 30 nến>1,5%, volume>1,4 lần, độ lệch chuẩn/giá 0,3–3%. Thoát ngày dưới SMA50, lỗ 8% hoặc giảm 2,5 ATR từ đỉnh; phút dưới MA20 hoặc lỗ 6%. Tối đa 8 mã. Tên Pro chỉ độ phức tạp, không bảo đảm thắng hai cấp còn lại.',
        source='https://www.fidelity.com/learning-center/trading-investing/technical-analysis'),
}
MODES=['paper_minute','paper','paper_combo','backtest_minute','backtest','hybrid']
for profile in PROFILES.values():profile['supported_modes']=MODES.copy()


def daily_signals(p):
    c=p['close'];v=p['volume']
    return {
        'Beginner':(p.sma20>p.sma50)&(p.sma20.shift()<=p.sma50.shift())&(c>p.sma20),
        'Intermediate':(c>p.high20_prev)&(c>p.sma50)&(v>p.vol20_prev*1.2)&p.market_ok,
        'Pro':(p.sma50>p.sma100)&(p.sma100>p.sma200)&(c>p.high55_prev)&(p.rs60>.05)&(p.atr14/c).between(.01,.05)&(v>p.vol20_prev*1.3)&p.market_ok,
    }


def minute_signals(c,h,l,v,ma5,ma10,ma20,hi20,hi30,vf,m30,vol):
    # Accept Series or column-wise DataFrames: canonical and vectorized engines
    # share exactly the same definitions and independent per-symbol warm-up.
    return {
        'Beginner':(ma5>ma20)&(ma5.shift()<=ma20.shift())&(c>ma5),
        'Intermediate':(c>hi20)&(ma10>ma20)&(vf>1.2),
        'Pro':(ma5>ma10)&(ma10>ma20)&(c>hi30)&(m30>.015)&(vf>1.4)&(vol>=.003)&(vol<=.03),
    }


def daily_exit(bot,row,p):
    c=row['close'];price=p['price']
    if bot=='Beginner':return c<price*.92 or row.get('sma20',float('nan'))<row.get('sma50',float('nan'))
    if bot=='Intermediate':return c<price*.93 or c<row.get('sma20',float('nan'))
    if bot=='Pro':return c<price*.92 or c<row.get('sma50',float('nan')) or c<p['high_water']-2.5*row.get('atr14',float('nan'))
    return False
