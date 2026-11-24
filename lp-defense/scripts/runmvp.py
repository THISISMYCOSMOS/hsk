import json, statistics as st, datetime as dt, math
from simpool import load, run
from simmvp import run_mvp, _stay, BPH
H=json.load(open('hist.json'))
def blk(tid,kind,i=0): return [e for e in sorted(H[tid]['ev'],key=lambda e:e[1]) if e[0]==kind][i][1]
gaps={'WETH':(blk('20','inc',1), blk('20','dec',-1), blk('35','inc')), 'WHSK':(blk('19','inc'), blk('19','dec',-1), blk('33','inc'))}
D=43200
def table(res,label):
    print(f' {label} windows {len(res)}')
    for name,c in [('all',lambda r:True),('down',lambda r:r[0]<-0.10),('side',lambda r:-0.10<=r[0]<=0.10),('up',lambda r:r[0]>0.10)]:
        X=[r for r in res if c(r)]
        if not X: continue
        m=lambda j: st.mean(r[j][0] for r in X); mm=lambda j: st.mean(r[j][2] for r in X)*100
        print(f'  {name:4s} n={len(X):2d} | stay {m(1):7.1f} mdd {mm(1):4.1f}% | ladder {m(2):7.1f} mdd {mm(2):4.1f}% | MVP0h {m(3):7.1f} mdd {mm(3):4.1f}% | MVP1h {m(4):7.1f} mdd {mm(4):4.1f}% | MVP6h {m(5):7.1f} mdd {mm(5):4.1f}% | 50/50 {st.mean(r[6] for r in X):7.1f} | MVP1h>stay {sum(r[4][0]>r[1][0] for r in X)}/{len(X)} worst {min(r[4][0]-r[1][0] for r in X):+.1f} best {max(r[4][0]-r[1][0] for r in X):+.1f} adj {st.mean(r[4][1] for r in X):.1f}')
def one(win,w):
    return (win[-1][1]/win[0][1]-1, _stay(win,w,None,None,None,1000), run(win,w,'ladder'), run_mvp(win,w,conf_h=0), run_mvp(win,w,conf_h=1), run_mvp(win,w,conf_h=6), 500+500*win[-1][1]/win[0][1])
out={}
print('### A. HSKSwap real pool path (big LP present, 6-day empty-pool gap excluded)')
for n in ['WETH','WHSK']:
    start,g0,g1=gaps[n]; R=[r for r in load(n) if r[0]>=start]
    print(f'== {n}')
    for w in [0.10,0.20]:
        res=[]; b=start
        while b+30*D<=R[-1][0]:
            if not (b<g1 and b+30*D>g0):
                win=[r for r in R if b<=r[0]<b+30*D]
                if len(win)>=20: res.append(one(win,w))
            b+=7*D
        table(res,f'±{int(w*100)}%'); out[f'pool_{n}_{w}']=res
print('\n### B. Binance ETH 1y hourly (Lact=1013, vol=27.27/h)')
K=json.load(open('eth_1y.json')); VOLH=19637/720
rowsK=[(i*BPH,p,VOLH,1013.0) for i,(t,p) in enumerate(K)]
for w in [0.10,0.20]:
    res=[one(rowsK[i:i+720],w) for i in range(0,len(rowsK)-720,168)]
    table(res,f'±{int(w*100)}%'); out[f'bin_{w}']=res
print('\n### C. Teammate month 10-25~11-23 KST on pool path')
t0=dt.datetime(2026,10,24,15,tzinfo=dt.timezone.utc).timestamp(); t1=dt.datetime(2026,11,23,15,tzinfo=dt.timezone.utc).timestamp()
sp=json.load(open('swaps_parsed.json'))
blkrange={n:(min(r['blk'] for r in sp[n]),max(r['blk'] for r in sp[n])) for n in sp}
for n in ['WETH','WHSK']:
    a,b=blkrange[n]; win=[r for r in load(n) if a<=r[0]<=b]
    for w in [0.10,0.20]:
        r=one(win,w)
        print(f' {n} ±{int(w*100)}% start {win[0][1]:.5g} end {win[-1][1]:.5g} | stay {r[1][0]:.2f} (mdd {r[1][2]*100:.2f}%) | MVP0h {r[3][0]:.2f} adj {r[3][1]} mdd {r[3][2]*100:.2f}% | MVP1h {r[4][0]:.2f} adj {r[4][1]} mdd {r[4][2]*100:.2f}% | MVP6h {r[5][0]:.2f} adj {r[5][1]} | ladder {r[2][0]:.2f}')
print('\n### D. Real range position #14 (ref = registration price)')
t=H['14']; st0=[e for e in t['ev'] if e[0]=='inc'][0][1]
R=[r for r in load('WHSK') if r[0]>=st0]; pa=1.0001**t['tl']*1e12; pb=1.0001**t['tu']*1e12; L=17219076875308/1e12
for scale,lab in [(1,'2 USDT'),(500,'1000 USDT')]:
    s=_stay(R,None,pa,pb,L*scale,0); lad=run(R,None,'ladder',ref=pb,pa=pa,pb=pb,init=L*scale)
    res=[run_mvp(R,ref=R[0][1],pa=pa,pb=pb,init=L*scale,conf_h=c) for c in (0,1,6)]
    print(f' {lab}: stay {s[0]:.4g} mdd {s[2]*100:.1f}% | ladder {lad[0]:.4g} mdd {lad[2]*100:.1f}% | MVP0h {res[0][0]:.4g} adj {res[0][1]} mdd {res[0][2]*100:.1f}% | MVP1h {res[1][0]:.4g} adj {res[1][1]} mdd {res[1][2]*100:.1f}% | MVP6h {res[2][0]:.4g} adj {res[2][1]} mdd {res[2][2]*100:.1f}%')
json.dump({k:v for k,v in out.items()},open('mvp_out.json','w'))
