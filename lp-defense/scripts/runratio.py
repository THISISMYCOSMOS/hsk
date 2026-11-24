import json, statistics as st
from simpool import load
from simmvp import _stay, BPH
from ratio import run_sched, SCHED
H=json.load(open('hist.json'))
def blk(tid,kind,i=0): return [e for e in sorted(H[tid]['ev'],key=lambda e:e[1]) if e[0]==kind][i][1]
gaps={'WETH':(blk('20','inc',1), blk('20','dec',-1), blk('35','inc')), 'WHSK':(blk('19','inc'), blk('19','dec',-1), blk('33','inc'))}
D=43200
def windows_pool(n):
    start,g0,g1=gaps[n]; R=[r for r in load(n) if r[0]>=start]; out=[]; b=start
    while b+30*D<=R[-1][0]:
        if not (b<g1 and b+30*D>g0):
            win=[r for r in R if b<=r[0]<b+30*D]
            if len(win)>=20: out.append(win)
        b+=7*D
    return out
def windows_bin():
    K=json.load(open('eth_1y.json')); rows=[(i*BPH,p,19637/720,1013.0) for i,(t,p) in enumerate(K)]
    return [rows[i:i+720] for i in range(0,len(rows)-720,168)]
if __name__=="__main__":
    names=list(SCHED)
    allres={}
    for label,wins in [('HSKSwap WETH',windows_pool('WETH')),('HSKSwap WHSK',windows_pool('WHSK')),('Binance ETH 1y',windows_bin())]:
        for w in [0.10,0.20]:
            res=[]
            for win in wins:
                r={'chg':win[-1][1]/win[0][1]-1,'유지':_stay(win,w,None,None,None,1000)}
                for k in names: r[k]=run_sched(win,w,SCHED[k])
                r['최대치']=max(r[k][0] for k in names)
                res.append(r)
            allres[f'{label} {w}']=res
            print(f'\n== {label} ±{int(w*100)}%  windows {len(res)}')
            for name,c in [('전체',lambda r:True),('하락',lambda r:r['chg']<-0.10),('횡보',lambda r:-0.10<=r['chg']<=0.10),('상승',lambda r:r['chg']>0.10)]:
                X=[r for r in res if c(r)]
                if not X: continue
                m=lambda k: st.mean(r[k][0] for r in X); md=lambda k: st.mean(r[k][2] for r in X)*100
                best={k:sum(1 for r in X if r[k][0]==r['최대치']) for k in names}
                print(f'  {name} n={len(X):2d} | 유지 {m("유지"):7.1f} ({md("유지"):4.1f}%) | 균등 {m("균등"):7.1f} ({md("균등"):4.1f}%) | 앞쪽 {m("앞쪽"):7.1f} ({md("앞쪽"):4.1f}%) | 뒤쪽 {m("뒤쪽"):7.1f} ({md("뒤쪽"):4.1f}%) | 최대치 {st.mean(r["최대치"] for r in X):7.1f} | 최대치-균등 {st.mean(r["최대치"]-r["균등"][0] for r in X):+5.1f} | 1등 횟수 {best}')
    json.dump({k:[{kk:(vv if kk in("chg","최대치") else list(vv)) for kk,vv in r.items()} for r in v] for k,v in allres.items()},open('ratio_out.json','w'),ensure_ascii=False)
