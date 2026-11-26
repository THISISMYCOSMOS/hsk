# 외부 시세: ETH (Binance data-api), HSK (Gate.io). 1시간봉 전체 + 1분봉 최근 60일.
import json, sys, time, urllib.request
OUT=sys.argv[1]
def get(u):
    for i in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'user-agent':'research-script'}),timeout=60))
        except Exception as e: time.sleep(2*(i+1))
    raise Exception(u)
now=int(time.time())
def binance(interval,sec,start):
    rows=[];s=start*1000
    while s<now*1000:
        k=get(f'https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval={interval}&startTime={s}&limit=1000')
        if not k: break
        rows+=[(r[0]//1000,float(r[4])) for r in k]; s=k[-1][0]+sec*1000
    return rows
def kucoin1m(start):
    rows=[];s=start
    while s<now:
        e=min(s+60*1500,now)
        k=get(f'https://api.kucoin.com/api/v1/market/candles?type=1min&symbol=HSK-USDT&startAt={s}&endAt={e}')['data']
        rows+=[(int(r[0]),float(r[2])) for r in k]; s=e; time.sleep(0.3)
    return sorted(set(rows))
def gate(interval,sec,start):
    rows=[];s=start
    while s<now:
        e=min(s+sec*999,now)
        k=get(f'https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=HSK_USDT&interval={interval}&from={s}&to={e}')
        rows+=[(int(r[0]),float(r[2])) for r in k]; s=e+sec; time.sleep(0.2)
    return sorted(set(rows))
y=now-410*86400; m=now-60*86400
d={'eth_1h':binance('1h',3600,y),'hsk_1h':gate('1h',3600,y),'eth_1m':binance('1m',60,m),'hsk_1m':kucoin1m(m)}
for k,v in d.items(): print(k,len(v),v[0],v[-1])
json.dump(d,open(OUT,'w'))
