"""Make a static, read-only smartphone dashboard from daily VN market bars.

Fails closed if any data feed is stale; never replaces real results with fake data.
The demo is embedded only in the HTML preview and permanently watermarked.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import pandas as pd
from datafeed import update_prices, load_prices, parse_symbols, DEFAULT_TICKERS
from engine import TRADERS, Settings, backtest
from paper_forward import update_paper

ROOT=Path(__file__).resolve().parent


def simple_number(n):
    return float(round(n,4)) if n is not None else None


def strip_na(frame, limit=60):
    if frame is None or frame.empty: return []
    result=[]
    for row in frame.tail(limit).to_dict('records'):
        clean={}
        for k,v in row.items():
            if pd.isna(v): clean[k]=None
            elif hasattr(v,'isoformat'):clean[k]=v.isoformat()
            elif hasattr(v,'item'):clean[k]=v.item()
            else:clean[k]=v
        result.append(clean)
    return result


def summary_backtest(r):
    curve=r['curve'].reset_index()
    # Sample by position, keeping first & last. Up to ~90 plot points.
    if len(curve)>90:
        idx=sorted(set([round(i*(len(curve)-1)/89) for i in range(90)]))
        curve=curve.iloc[idx]
    series=[{'date':d.strftime('%d/%m/%y'),'nav':round(float(nav)),
             'bot':round(float(pct),2),'index':round(float(b),2)}
             for d,nav,pct,b in zip(curve.date,curve.nav,
                                     curve.return_pct,curve.benchmark_return_pct)]
    trades=r['trades']
    # Avoid NaN in JSON
    recent=[]
    if not trades.empty:
        for row in trades.tail(40).iloc[::-1].to_dict('records'):
            recent.append({k:(None if pd.isna(v) else float(v) if isinstance(v,float) else v)
                           for k,v in row.items()})
    actions=strip_na(r['actions'])
    holdings=strip_na(r['holdings'])
    return {'nav':round(r['nav']),'cash':round(r['cash']),
            'return_pct':round(r['return_pct'],2),
            'benchmark_return_pct':round(r['benchmark_return_pct'],2),
            'max_drawdown_pct':round(r['max_drawdown_pct'],2),
            'win_rate':None if r['win_rate'] is None else round(r['win_rate'],1),
            'closed_trades':int(r['closed_trades']),'buy_count':int(r['buy_count']),
            'holdings':holdings,'actions':actions,'trades':recent,'curve':series}


def build(symbols, history_start, out_path):
    status=update_prices(symbols,start='2021-01-01')
    # Important: NEVER reuse cached files after a failure or stale update.
    if status['errors']:
        raise RuntimeError('Không xuất dashboard: lỗi tải dữ liệu '+str(status['errors']))
    prices,benchmark,missing=load_prices(symbols)
    if missing or benchmark is None:
        raise RuntimeError('Không xuất dashboard: thiếu dữ liệu '+str(missing))
    last=benchmark.index.max()
    if any(p.index.max()!=last for p in prices.values()):
        stale=[s for s,p in prices.items() if p.index.max()!=last]
        raise RuntimeError('Không xuất dashboard: mã chưa đồng bộ phiên '+str(stale))
    if len(benchmark)<252 or any(len(p)<252 for p in prices.values()):
        raise RuntimeError('Không đủ dữ liệu tính chiến thuật (>=252 phiên)')
    settings=Settings()
    results={k:summary_backtest(backtest(prices,benchmark,k,history_start,settings=settings))
             for k in TRADERS}
    paper_state, changed=update_paper(prices,benchmark,settings=settings)
    benchmark_start=benchmark.loc[benchmark.index>=pd.Timestamp(history_start)]['close']
    if len(benchmark_start)<2:
        raise RuntimeError('Không đủ dữ liệu benchmark trong khoảng')
    base_index=float(benchmark_start.iloc[0]); now_index=float(benchmark_start.iloc[-1])
    out={'version':1,'mode':'real_market_data','generated_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='seconds'),
         'last_session':last.date().isoformat(),'start_date':history_start,
         'capital_each':settings.initial_cash,'source':status['source'],
         'universe':symbols,
         'market':{'index':'VN-Index','level':round(now_index/1000,2),
                   'return_since_backtest_start':round((now_index/base_index-1)*100,2)},
         'traders':TRADERS,'backtests':results,
         'paper':{k:{'cash':round(b['cash']),
                     'nav':b['history'][-1]['nav'],'return_pct':b['history'][-1]['return_pct'],
                     'holdings':b.get('latest',{}).get('holdings',[]),
                     'orders_next':b['orders_next'][:10],
                     'trades':list(reversed(b['trades'][-30:])),
                     'history':b['history'][-150:]}
                  for k,b in paper_state['bots'].items()},
         'paper_started_at':paper_state['started_at'],
         'warnings':paper_state.get('warnings',[])[-5:]+[
             'Tín hiệu của bot chỉ lấy cảm hứng từ quy tắc công khai của các trader Mỹ.',
             'Kết quả backtest chưa phản ánh đầy đủ cổ tức, chia tách, mất thanh khoản và hủy niêm yết.',
             'Paper-forward là giao dịch giả lập tại giá mở cửa có trượt giá/phí; không chứng minh lệnh thật khớp được.'
         ],'is_new_session':bool(changed)}
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    tmp=out_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(out,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=str),encoding='utf-8')
    tmp.replace(out_path)
    return out


def send_telegram(payload):
    token=os.environ.get('TELEGRAM_BOT_TOKEN','')
    chat=os.environ.get('TELEGRAM_CHAT_ID','')
    if not (token and chat) or not payload['is_new_session']:
        return False
    # No token is ever logged or committed.
    from urllib.request import Request,urlopen
    from urllib.parse import urlencode
    session=payload['last_session']
    title='🏁 TRADER ARENA VN · '+session
    leaderboard=sorted(payload['paper'].items(),key=lambda kv:kv[1]['return_pct'],reverse=True)
    lines=[title,'Tài khoản tiền ảo · KHÔNG dùng tiền thật','']
    for i,(name,b) in enumerate(leaderboard,1):
        net=round(b['nav']-payload['capital_each'])
        lines.append(f'{i}. {name}: {b["nav"]:,.0f}đ ({b["return_pct"]:+.2f}%, lãi/lỗ {net:+,.0f}đ)')
    lines.append('')
    lines.append('Lệnh giả lập mới hôm nay:')
    had=False
    for name,b in payload['paper'].items():
        for tr in b['trades']:
            if tr['date']==session:
                lines.append(f'• {name}: {tr["side"]} {tr["qty"]} {tr["symbol"]}');had=True
    if not had: lines.append('• Chưa có lệnh mới')
    url=os.environ.get('DASHBOARD_URL','').strip()
    if url: lines.append('') ; lines.append(url)
    request=Request(f'https://api.telegram.org/bot{token}/sendMessage',
        data=urlencode({'chat_id':chat,'text':'\n'.join(lines)}).encode(),
        headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    with urlopen(request,timeout=20) as res:
        body=json.loads(res.read().decode())
        if not body.get('ok'):raise RuntimeError('Telegram declined message')
    return True


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'site'/'dashboard.json'))
    parser.add_argument('--symbols',default=DEFAULT_TICKERS)
    parser.add_argument('--start',default='2023-01-03')
    args=parser.parse_args()
    data=build(parse_symbols(args.symbols),args.start,args.output)
    print(f'Đã tạo dữ liệu đến phiên {data["last_session"]}; newly recorded: {data["is_new_session"]}')
    try:
        sent=send_telegram(data)
        print('Telegram sent' if sent else 'Telegram skipped (no new session or missing secrets)')
    except Exception as e:
        print(f'Cảnh báo: không gửi được Telegram ({type(e).__name__})')
