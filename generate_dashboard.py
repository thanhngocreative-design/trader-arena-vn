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
from datafeed import update_prices, load_prices, parse_symbols, DEFAULT_TICKERS, MIN_USABLE
from engine import TRADERS, Settings, backtest
from fast_engine import FastContext, CORE, build_hybrid_signals
from paper_forward import update_paper
from intraday_data import load_minute
from hybrid_backtest import build_hybrid_backtests

ROOT=Path(__file__).resolve().parent

PERIOD_LABELS = {
    '3M': '3 tháng', '6M': '6 tháng', '1Y': '1 năm',
    '2Y': '2 năm', 'ALL': 'Từ đầu 2023',
}


def load_cloud_config():
    """GitHub-controlled, trusted source of actual cloud-run bot activation."""
    p=ROOT/'config'/'bots.json'
    if not p.exists():
        return set(TRADERS)
    data=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or any(k not in TRADERS for k in data):
        raise ValueError('Sai cấu trúc config/bots.json')
    if any(not isinstance(v,bool) for v in data.values()):
        raise ValueError('Các công tắc bot phải là true hoặc false')
    return {k for k in TRADERS if data.get(k,True)}


def stock_chart_payload(frame):
    """Last ~3 years of real daily VND OHLCV; compact 6-column arrays."""
    bars=[]
    for d,row in frame.tail(780).iterrows():
        if not pd.notna(row['close']):
            continue
        bars.append([
            d.strftime('%Y-%m-%d'),
            round(float(row['open'])), round(float(row['high'])),
            round(float(row['low'])), round(float(row['close'])),
            int(row['volume'])])
    return bars



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
    # Candidate failures are disclosed but cannot silently pass as data.
    if status['errors']:
        raise RuntimeError('Không xuất dashboard: lỗi tải dữ liệu '+str(status['errors']))
    accepted=[k for k in symbols if k in status['success']]
    required=min(MIN_USABLE,len(symbols))
    if len(accepted)<required:
        raise RuntimeError(f"Chỉ có {len(accepted)}/{len(symbols)} mã đủ dữ liệu; cần tối thiểu {required}. Lỗi mẫu: "+str(list(status['skipped'].items())[:8]))
    prices,benchmark,missing=load_prices(accepted)
    if missing or benchmark is None:
        raise RuntimeError('Không xuất dashboard: thiếu giá '+str(missing))
    last=benchmark.index.max()
    if any(p.index.max()!=last for p in prices.values()):
        stale=[s for s,p in prices.items() if p.index.max()!=last]
        raise RuntimeError('Không xuất dashboard: mã chưa đồng bộ phiên '+str(stale))
    if len(benchmark)<252 or any(len(p)<252 for p in prices.values()):
        raise RuntimeError('Không đủ dữ liệu tính chiến thuật (>=252 phiên)')
    settings=Settings()
    active_ids=load_cloud_config()
    # Build numpy-ready matrices once: 11 bots x 5 windows x many symbols,
    # without repeatedly evaluating dataframe row lookups.
    context=FastContext(prices,benchmark,settings)
    # Fitted only on PAST simulated NAVs for each day (pre-2023 warm-up).
    # IMPORTANT: never pick winners using 2026 final total returns at 2023 entry.
    training_start=max(benchmark.index.min(),pd.Timestamp('2022-01-03'))
    reference={k:backtest(prices,benchmark,k,start_date=str(training_start.date()),
                          settings=settings,features_cache=context) for k in CORE}
    hybrid_info=build_hybrid_signals(context,{k:v['curve'] for k,v in reference.items()})
    periods={
        '3M': max(pd.Timestamp(history_start),last-pd.DateOffset(months=3)),
        '6M': max(pd.Timestamp(history_start),last-pd.DateOffset(months=6)),
        '1Y': max(pd.Timestamp(history_start),last-pd.DateOffset(years=1)),
        '2Y': max(pd.Timestamp(history_start),last-pd.DateOffset(years=2)),
        'ALL': pd.Timestamp(history_start),
    }
    by_period={}
    for period,start in periods.items():
        by_period[period]={
            k:summary_backtest(backtest(prices,benchmark,k,start_date=str(start.date()),
                                         settings=settings,features_cache=context))
            for k in TRADERS
        }
    results=by_period['ALL']
    # A missing real minute feed never silently falls back to Daily candles.
    minute_frames,minute_errors=load_minute(accepted,daily=prices)
    minute_results,minute_audit=build_hybrid_backtests(context,minute_frames,settings)
    minute_audit['rejected_symbols']=minute_errors
    minute_payload={k:summary_backtest(v) for k,v in minute_results.items()}
    last_idx=len(context.dates)-1
    prepared_rows={
        symbol:pd.Series({
            **{k:float(context.a[k][i,last_idx]) for k in context.a},
            **{f'buy_{name}':bool(context.buy[name][i,last_idx]) for name in TRADERS},
        })
        for i,symbol in enumerate(context.symbols)
    }
    paper_state, changed=update_paper(
        prices,benchmark,settings=settings,active_ids=active_ids,prepared_rows=prepared_rows)
    # Keep huge chart datasets out of the dashboard's initial network request.
    outdir=Path(out_path).parent/'stocks'
    outdir.mkdir(parents=True,exist_ok=True)
    for symbol,frame in prices.items():
        path=outdir/f"{symbol}.json"
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(stock_chart_payload(frame),ensure_ascii=False,
                                  separators=(',',':')),encoding='utf-8')
        tmp.replace(path)
    benchmark_start=benchmark.loc[benchmark.index>=pd.Timestamp(history_start)]['close']
    if len(benchmark_start)<2:
        raise RuntimeError('Không đủ dữ liệu benchmark trong khoảng')
    base_index=float(benchmark_start.iloc[0]); now_index=float(benchmark_start.iloc[-1])
    out={'version':1,'mode':'real_market_data','generated_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='seconds'),
         'last_session':last.date().isoformat(),'start_date':history_start,
         'capital_each':settings.initial_cash,'source':status['source'],
         'universe':accepted,
         'universe_audit':{
             'candidate_count':len(symbols),'tradable_history_count':len(accepted),
             'excluded_count':len(status['skipped']),
             'universe_asof':status['candidate_set_asof'],
             'note':status['universe_note'],
             'skipped_examples':dict(list(status['skipped'].items())[:10]),
         },
         'execution_model':{
             'broker_fee_each_side':settings.fee_rate,
             'sell_tax':settings.sell_tax,
             'slippage_floor_each_side':settings.slippage,
             'slippage':'Depends on past 20d turnover and order participation; capped 1.25% each side',
             'cooldown_sessions':settings.cooldown_sessions,
             'minimum_hold_sessions':settings.minimum_hold_sessions,
             'max_daily_participation':settings.max_daily_participation,
             'min_average_value':settings.min_average_value,
         },
         'hybrid_model':hybrid_info,
         'market':{'index':'VN-Index','level':round(now_index/1000,2),
                   'return_since_backtest_start':round((now_index/base_index-1)*100,2)},
         'traders':TRADERS,'backtests':results,
          'hybrid_backtests':minute_payload,
          'hybrid_backtest_audit':minute_audit,
         'backtest_periods':by_period,
         'backtest_options':[{ 'key': key, 'label': PERIOD_LABELS[key],
                               'start':str(date.date()), 'end':str(last.date())}
                              for key,date in periods.items()],
         'cloud_enabled':{key:key in active_ids for key in TRADERS},
         'stock_symbols':sorted(prices),
         'stocks':{},  # loaded on demand from ./stocks/<symbol>.json
         'paper':{k:{'cash':round(b['cash']),
                     'nav':b['history'][-1]['nav'],'return_pct':b['history'][-1]['return_pct'],
                     'holdings':b.get('latest',{}).get('holdings',[]),
                     'orders_next':b['orders_next'][:10],
                     'trades':list(reversed(b['trades'][-30:])),
                     'history':b['history'][-150:]}
                  for k,b in paper_state['bots'].items()},
         'paper_started_at':paper_state['started_at'],
         'warnings':paper_state.get('warnings',[])[-5:]+[
             'Tín hiệu là mô hình đơn giản lấy cảm hứng từ phương pháp được thảo luận bởi các trader Mỹ, Nhật, châu Âu và Việt Nam; không phải lệnh thực tế của họ.',
             'Kết quả backtest chưa phản ánh đầy đủ cổ tức, chia tách, mất thanh khoản và hủy niêm yết.',
             'Paper-forward là giao dịch giả lập tại giá mở cửa có trượt giá/phí; không chứng minh lệnh thật khớp được.',
             'Vũ trụ chỉ gồm các ứng viên còn niêm yết trong năm 2026, không có thành phần lịch sử đúng từng thời điểm: survivorship bias vẫn tồn tại.',
             'Arena Hybrid chỉ chọn mô hình theo kết quả 126 phiên đã qua; không dùng thành tích tương lai để tạo tín hiệu.',
              'Backtest kết hợp thử nghiệm chỉ dùng nến 1 phút thật đã xác minh, giới hạn mã/phiên; không trộn với Daily và paper.'
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
    print(f'Đã tạo dữ liệu đến phiên {data["last_session"]}; coverage {data["universe_audit"]["tradable_history_count"]}/{data["universe_audit"]["candidate_count"]}; newly recorded: {data["is_new_session"]}')
    try:
        sent=send_telegram(data)
        print('Telegram sent' if sent else 'Telegram skipped (no new session or missing secrets)')
    except Exception as e:
        print(f'Cảnh báo: không gửi được Telegram ({type(e).__name__})')
