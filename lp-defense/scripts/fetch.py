# Rebuild raw data files used by the simulation scripts (not committed because of size).
#   python3 fetch.py chain   -> swaps_all.json, mintburn.json, npm_logs.json, swaps.json
#   python3 fetch.py binance -> eth_1y.json, eth_1y_vol.json
import json, sys, time, datetime as dt, urllib.request
from concurrent.futures import ThreadPoolExecutor
from rpc import call
POOLS={'WETH':'0xb92b79ed6b370d5cfee2e14b1d0983c258304c16','WHSK':'0x4ff515761864e7838b0adb8b5b2b8b7a068905dc','WBTC':'0xd9ea2ce468957ba49ccc38c4758ed6ecd561449a'}
NPM='0xdf0a9b833db0e4ceea103a4408f3b68e7fc0cad5'
T={'swap':'0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67',
   'mint':'0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde',
   'burn':'0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c',
   'inc':'0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f',
   'dec':'0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4',
   'col':'0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01',
   'tr':'0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'}
STEP=5000
END=[None]
def chunk(b):
    for i in range(8):
        try:
            r=call('eth_getLogs',[{'address':list(POOLS.values())+[NPM],'fromBlock':hex(b),'toBlock':hex(min(b+STEP-1,END[0]))}])
            for l in r: l['timeStamp']=l.get('blockTimestamp')
            return r
        except Exception as e:
            time.sleep(3*(i+1))
    raise Exception(f'failed {b}')
def chain(start=int(sys.argv[2]) if len(sys.argv)>2 else 14_000_000):
    end=int(call('eth_blockNumber',[]),16)-5; END[0]=end
    with ThreadPoolExecutor(8) as ex: parts=list(ex.map(chunk,range(start,end+1,STEP)))
    logs=[l for p in parts for l in p]
    print('logs',len(logs),'blocks',start,end)
    inv={v:k for k,v in POOLS.items()}
    S={n:[] for n in POOLS}; MB={n:{'mint':[],'burn':[]} for n in POOLS}; N={k:[] for k in ('inc','dec','col','tr')}
    for l in logs:
        a=l['address'].lower(); t=l['topics'][0]
        if a in inv:
            n=inv[a]
            if t==T['swap']: S[n].append(l)
            elif t==T['mint']: MB[n]['mint'].append(l)
            elif t==T['burn']: MB[n]['burn'].append(l)
        elif a==NPM:
            for k in N:
                if t==T[k]: N[k].append(l)
    for n in POOLS:
        b=[int(l['blockNumber'],16) for l in S[n]+MB[n]['mint']]
        print(n,'swaps',len(S[n]),'mint',len(MB[n]['mint']),'burn',len(MB[n]['burn']),'first block',min(b) if b else None)
    print({k:len(v) for k,v in N.items()})
    json.dump(S,open('swaps_all.json','w')); json.dump(MB,open('mintburn.json','w')); json.dump(N,open('npm_logs.json','w'))
    t0=dt.datetime(2026,10,24,15,tzinfo=dt.timezone.utc).timestamp(); t1=dt.datetime(2026,11,23,15,tzinfo=dt.timezone.utc).timestamp()
    json.dump({n:[l for l in S[n] if t0<=int(l['timeStamp'],16)<t1] for n in ('WETH','WHSK')},open('swaps.json','w'))
def binance(end=dt.datetime(2026,11,24,0,tzinfo=dt.timezone.utc)):
    e=int(end.timestamp()*1000); s=e-8760*3600*1000; rows=[]
    while s<e:
        u=f'https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1h&startTime={s}&limit=1000'
        k=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'user-agent':'research-script'}),timeout=60))
        if not k: break
        rows+=[r for r in k if r[0]<e]; s=k[-1][0]+3600*1000
    print('binance hours',len(rows),dt.datetime.fromtimestamp(rows[0][0]/1000,dt.timezone.utc),dt.datetime.fromtimestamp(rows[-1][0]/1000,dt.timezone.utc))
    json.dump([(r[0]//1000+3600,float(r[4])) for r in rows],open('eth_1y.json','w'))
    json.dump([(r[0]//1000+3600,float(r[4]),float(r[7]),float(r[10])) for r in rows],open('eth_1y_vol.json','w'))
def binance_long(sym, start=dt.datetime(2018,1,1,tzinfo=dt.timezone.utc), end=dt.datetime(2026,11,24,tzinfo=dt.timezone.utc)):
    s=int(start.timestamp()*1000); e=int(end.timestamp()*1000); rows=[]
    while s<e:
        u=f'https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1h&startTime={s}&limit=1000'
        k=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'user-agent':'research-script'}),timeout=60))
        if not k: break
        rows+=[r for r in k if r[0]<e]; s=k[-1][0]+3600*1000
    print(sym,'hours',len(rows))
    json.dump([(r[0]//1000+3600,float(r[4])) for r in rows],open(f'{sym.lower()}_long.json','w'))
if __name__=='__main__':
    if sys.argv[1]=='long':
        for sym in ('ETHUSDT','BTCUSDT'): binance_long(sym)
    else: {'chain':chain,'binance':binance}[sys.argv[1]]()
