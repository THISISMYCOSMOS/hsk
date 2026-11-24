from rpc import *
import json, math, datetime as dt
N=json.load(open('npm_logs.json')); MB=json.load(open('mintburn.json'))
pools={'WETH':('0xb92b79ed6b370d5cfee2e14b1d0983c258304c16',18,6),'WHSK':('0x4ff515761864e7838b0adb8b5b2b8b7a068905dc',18,6),'WBTC':('0xd9ea2ce468957ba49ccc38c4758ed6ecd561449a',8,6)}
def s(x):
    v=int(x,16); return v-2**256 if v>2**255 else v
def ts(l): return dt.datetime.fromtimestamp(int(l['timeStamp'],16),dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
txpool={}
for p in MB:
    for l in MB[p]['mint']:
        txpool[l['transactionHash']]=(p,s(l['topics'][2]),s(l['topics'][3]))
tok={}
for l in N['inc']:
    tid=int(l['topics'][1],16); d=l['data'][2:]
    if l['transactionHash'] in txpool:
        p,tl,tu=txpool[l['transactionHash']]; tok.setdefault(tid,{'pool':p,'tl':tl,'tu':tu,'ev':[]})
    if tid in tok:
        tok[tid]['ev'].append(('inc',int(l['blockNumber'],16),ts(l),int(d[0:64],16),int(d[64:128],16),int(d[128:192],16)))
for l in N['dec']:
    tid=int(l['topics'][1],16); d=l['data'][2:]
    if tid in tok: tok[tid]['ev'].append(('dec',int(l['blockNumber'],16),ts(l),int(d[0:64],16),int(d[64:128],16),int(d[128:192],16)))
for l in N['col']:
    tid=int(l['topics'][1],16); d=l['data'][2:]
    if tid in tok: tok[tid]['ev'].append(('col',int(l['blockNumber'],16),ts(l),0,int(d[64:128],16),int(d[128:192],16)))
for l in N['tr']:
    if len(l['topics'])==4:
        tid=int(l['topics'][3],16)
        if tid in tok: tok[tid]['ev'].append(('tr',int(l['blockNumber'],16),ts(l),addr(l['topics'][1]),addr(l['topics'][2]),0))
def price_at(p,blk):
    a,d0,d1=pools[p]
    r=ecall(a,'0x3850c7bd',hex(blk)); return (int(r[2:66],16)/2**96)**2*10**(d0-d1)
out={}
for tid in sorted(tok):
    t=tok[tid]; p=t['pool']; a,d0,d1=pools[p]
    lo=1.0001**t['tl']*10**(d0-d1); hi=1.0001**t['tu']*10**(d0-d1)
    rng='full' if t['tl']<-800000 else f'{lo:.6g}~{hi:.6g}'
    print(f'\n#{tid} {p} range {rng}')
    for e in sorted(t['ev'],key=lambda e:(e[1],['tr','inc','dec','col'].index(e[0]))):
        if e[0]=='tr': print('  ',e[2],'transfer',e[3][:10],'->',e[4][:10]); continue
        try: px=price_at(p,e[1])
        except Exception as ex: px=float('nan')
        a0=e[4]/10**d0; a1=e[5]/10**d1
        print('  ',e[2],e[0],'L',e[3],f'tok {a0:.6g} usdt {a1:.4f}',f'px {px:.6g}', f'val {a0*px+a1:.2f}')
    out[tid]=t
json.dump({str(k):v for k,v in out.items()},open('hist.json','w'))
