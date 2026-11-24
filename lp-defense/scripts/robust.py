# Robustness checks for the plan rule (25% of L0 at 25/50/75/100% of the distance to the lower bound).
#   python3 robust.py grid      : range width x window length, 4 price paths
#   python3 robust.py single    : split vs one-shot full exit at a single line (regret by market regime)
#   python3 robust.py poll      : keeper checks the price only every N minutes/hours
#   python3 robust.py stress    : thinner pool, higher gas
# Paths: HSKSwap WETH/WHSK real swaps (big-LP period, empty-pool gap excluded),
#        Binance ETH/BTC hourly 2018-01 ~ 2026-11 with an HSKSwap-WETH-like pool (83,630 USDT deep, 27.27 USDT/h volume).
import json, math, sys, statistics as st
from simpool import load, amts, sell, win_at
from gapsdef import gaps
D=43200; H=1800
PLAN=((.25,.5,.75,1.0),(.25,.5,.75,1.0))
def single(f): return ((f,),(1.0,))
STRAT={'유지':((),()),'분할(기획)':PLAN,'한 번에 25%선':single(.25),'한 번에 50%선':single(.5),'한 번에 75%선':single(.75),'한 번에 하단':single(1.0),
       '팀 원안(최저 50%)':((.5,.8),(.25,.5))}
def run(rows,w,strat,poll=0,gas=0.03,depth=1.0,start_usdt=1000.0):
    levels,cum=strat
    P0=rows[0][1]; pa=P0*(1-w); pb=P0*(1+w); d=P0-pa
    ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    lv=[P0-f*d for f in levels]
    out=0.0; usdt=0.0; fees=0.0; g=0.0; k=0; nxt=rows[0][0]; peak=None; mdd=0.0
    for blk,P,vol,Lact in rows:
        Lp=L0*(1-out)
        if Lp>0 and pa<=P<=pb and Lact>0: fees+=vol*0.003*Lp/(Lact+Lp)
        if k<len(lv) and blk>=nxt:
            if poll: nxt=blk+poll
            kk=k
            while kk<len(lv) and P<=lv[kk]: kk+=1
            if kk>k:
                take=cum[kk-1]-out; k=kk
                if take>1e-12:
                    x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P,Lact*depth); out+=take; g+=gas
        x,y=amts(L0*(1-out),P,pa,pb); v=x*P+y+usdt+fees-g
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    return v, mdd
# ---------- paths ----------
def pool_rows(n):
    start,g0,g1=gaps[n]; return [r for r in load(n) if r[0]>=start],(g0,g1,start)
def bin_rows(sym):
    K=json.load(open(f'{sym}_long.json'))
    return [(i*H,p,19637/720,83630/(2*math.sqrt(p))) for i,(t,p) in enumerate(K)]
def windows(rows,days,step_days=7,gap=None):
    out=[]; b=gap[2] if gap else rows[0][0]; end=rows[-1][0]
    while b+days*D<=end:
        if not (gap and b<gap[1] and b+days*D>gap[0]):
            win=win_at(rows,b,b+days*D)
            if len(win)>=20: out.append(win)
        b+=step_days*D
    return out
_cache={}
def paths():
    if not _cache:
        for n in ('WETH','WHSK'): _cache['HSKSwap '+n]=pool_rows(n)
        for s,lab in (('ethusdt','Binance ETH 2018~'),('btcusdt','Binance BTC 2018~')): _cache[lab]=(bin_rows(s),None)
    return _cache
REG=[('하락',lambda c:c<-0.10),('횡보',lambda c:-0.10<=c<=0.10),('상승',lambda c:c>0.10)]
def compare(wins,w,names,**kw):
    res=[]
    for win in wins:
        r={'chg':win[-1][1]/win[0][1]-1}
        for nm in names: r[nm]=run(win,w,STRAT[nm],**kw)
        res.append(r)
    return res
def summary(res,a='분할(기획)',b='유지'):
    dn=[r for r in res if r['chg']<-0.10]; ot=[r for r in res if r['chg']>=-0.10]
    saved=sum(max(r[a][0]-r[b][0],0) for r in res); given=sum(max(r[b][0]-r[a][0],0) for r in res)
    return dict(n=len(res),n_down=len(dn),
        down_gain=st.mean(r[a][0]-r[b][0] for r in dn) if dn else float('nan'),
        down_win=f"{sum(r[a][0]>r[b][0] for r in dn)}/{len(dn)}",
        other_cost=st.mean(r[a][0]-r[b][0] for r in ot) if ot else float('nan'),
        all_gain=st.mean(r[a][0]-r[b][0] for r in res),
        ratio=saved/given if given else float('inf'),
        mdd=(st.mean(r[b][1] for r in res)*100, st.mean(r[a][1] for r in res)*100),
        worst_mdd=(max(r[b][1] for r in res)*100, max(r[a][1] for r in res)*100))
def fmt(s):
    return (f"구간 {s['n']:3d} (하락 {s['n_down']:3d}) | 하락 구간 평균 {s['down_gain']:+6.1f}, 이긴 비율 {s['down_win']:>7s} | 그 밖 구간 평균 {s['other_cost']:+6.1f} | "
            f"전체 평균 {s['all_gain']:+6.1f} | 지킨÷포기 {s['ratio']:4.1f}배 | 평균 MDD {s['mdd'][0]:4.1f}%→{s['mdd'][1]:4.1f}% | 최악 MDD {s['worst_mdd'][0]:4.1f}%→{s['worst_mdd'][1]:4.1f}%")
def grid():
    for lab,(rows,gap) in paths().items():
        print(f'\n== {lab}')
        for days in (14,30,60):
            wins=windows(rows,days,7,gap)
            for w in (0.05,0.10,0.15,0.20,0.30):
                print(f' {days:2d}일 ±{int(w*100):2d}% | '+fmt(summary(compare(wins,w,['유지','분할(기획)']))))
        if lab.startswith('Binance'):
            wins=windows(rows,30,30,gap)
            for w in (0.10,0.20):
                print(f' 30일 겹치지 않는 구간 ±{int(w*100)}% | '+fmt(summary(compare(wins,w,['유지','분할(기획)']))))
def single_cmp():
    names=list(STRAT)
    for w in (0.10,0.20):
        print(f'\n######## ±{int(w*100)}%, 30일 구간, 평균 최종 자산 (1,000 USDT 시작)')
        for lab,(rows,gap) in paths().items():
            res=compare(windows(rows,30,7,gap),w,names)
            print(f'== {lab}')
            means={}
            for rn,c in REG:
                X=[r for r in res if c(r['chg'])]
                if not X: continue
                means[rn]={nm:st.mean(r[nm][0] for r in X) for nm in names}
                print(f'  {rn} ({len(X):3d}) | '+' | '.join(f'{nm} {means[rn][nm]:7.1f}' for nm in names))
            print('  최악 MDD      | '+' | '.join(f'{nm} {max(r[nm][1] for r in res)*100:5.1f}%' for nm in names))
            reg={nm:max(max(means[rn].values())-means[rn][nm] for rn in means) for nm in names}
            print('  장세별 최대 후회(그 장세 1등과의 차이 중 가장 큰 값) | '+' | '.join(f'{nm} {reg[nm]:5.1f}' for nm in names))
def poll_cmp():
    for lab,(rows,gap) in paths().items():
        wins=windows(rows,30,7,gap); polls=[0,300,H,6*H] if lab.startswith('HSK') else [0,6*H,24*H]
        for w in (0.10,0.20):
            base=None
            for p in polls:
                s=summary(compare(wins,w,['유지','분할(기획)'],poll=p))
                tag='매 스왑' if (p==0 and lab.startswith('HSK')) else ('1시간 봉' if p==0 else f'{p/H:g}시간')
                if p==300: tag='10분'
                print(f'{lab} ±{int(w*100)}% 감시 주기 {tag:6s} | '+fmt(s))
def stress():
    for lab,(rows,gap) in paths().items():
        wins=windows(rows,30,7,gap)
        for w in (0.10,):
            for kw,tag in (({},'기본'),({'depth':0.5},'풀 깊이 절반'),({'depth':0.25},'풀 깊이 1/4'),({'gas':0.3},'가스 10배')):
                print(f'{lab} ±{int(w*100)}% {tag:8s} | '+fmt(summary(compare(wins,w,['유지','분할(기획)'],**kw))))
if __name__=='__main__':
    {'grid':grid,'single':single_cmp,'poll':poll_cmp,'stress':stress}[sys.argv[1]]()
