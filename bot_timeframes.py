"""Describe the implemented engines, not the historical traders' usual style."""
from engine import TRADERS

def timeframe_manifest():
    result={}
    for mode in ('paper','backtest','hybrid'):
        bots={}
        for bot in TRADERS:
            if mode!='hybrid':
                detail='Tín hiệu từ nến ngày đã đóng; mô phỏng khớp ở giá mở cửa phiên tiếp theo. Không dùng nến phút.'
                info={'category':'daily_only','label':'Chỉ nến ngày','priority':'ngày','detail':detail}
            else:
                if bot=='BNF':
                    detail='Ưu tiên nhịp hồi trên nến 1 phút; vẫn lọc SMA25, RSI và thanh khoản từ ngày hôm trước.'
                    priority='phút'
                elif bot=='CIS':
                    detail='Ưu tiên breakout trên nến 1 phút; vẫn lọc xu hướng và thanh khoản từ ngày hôm trước.'
                    priority='phút'
                elif bot=='Hybrid':
                    detail='Chọn nhóm bot từ kết quả ngày đã có trong quá khứ; nến 1 phút xác nhận điểm vào và xét thoát.'
                    priority='lọc ngày, khớp phút'
                else:
                    detail='Nến ngày chọn cổ phiếu; nến 1 phút xác nhận điểm vào và xét thoát. Lệnh chỉ khớp từ nến quan sát tiếp theo.'
                    priority='lọc ngày, khớp phút'
                info={'category':'daily_and_minute','label':'Ngày + phút','priority':priority,'detail':detail}
            bots[bot]=info
        result[mode]={'basis':'implemented_engine','counts':{c:sum(b['category']==c for b in bots.values()) for c in ('minute_only','daily_only','daily_and_minute')},'bots':bots}
    return result
