# Does "high volume + strong net selling" over the last 24h predict a further fall? (HSKSwap pools, big-LP periods)
import json, statistics as st, bisect
from runratio import gaps
S=json.load(open('swaps_all.json'))
def s(x):
    v=int(x,16); return v-2**256 if v>2**255 else v
H1=1800
for n in ['WETH','WHSK']:
    start,g0,g1=gaps[n]
    sw=[]
    for l in S[n]:
        b=int(l['blockNumber'],16)
        if b<start or g0<=b<=g1: continue
        d=l['data'][2:]; a1=s(d[64:128])/1e6; sp=int(d[128:192],16)/2**96
        sw.append((b,sp*sp*1e12,a1))   # a1>0: USDT into pool = buy token; a1<0: sell token
    sw.sort(); B=[x[0] for x in sw]
    def price_at(b):
        i=bisect.bisect_right(B,b)-1; return sw[i][1] if i>=0 else None
    rows=[]
    for t in range(start+8*24*H1, sw[-1][0]-7*24*H1, H1):
        if g0-8*24*H1<=t<=g1+7*24*H1: continue
        i0=bisect.bisect_left(B,t-24*H1); i1=bisect.bisect_right(B,t)
        j0=bisect.bisect_left(B,t-7*24*H1)
        last=sw[i0:i1]; wk=sw[j0:i1]
        vol24=sum(abs(x[2]) for x in last); volwk=sum(abs(x[2]) for x in wk)/7
        if volwk<=0: continue
        net=sum(-x[2] for x in last)  # positive = net selling of token (USDT out)
        sellr=net/vol24 if vol24>0 else 0
        p=price_at(t); 
        if p is None: continue
        hi7=max(x[1] for x in wk) if wk else p
        fwd=[x[1] for x in sw[i1:bisect.bisect_right(B,t+7*24*H1)]]
        if not fwd: continue
        ret3=price_at(t+72*H1)/p-1; dd7=min(fwd)/p-1
        rows.append(dict(vr=vol24/volwk, sr=sellr, fall=p/hi7-1, ret3=ret3, dd7=dd7))
    print(f'\n== {n}: hourly samples {len(rows)}')
    def grp(name,R):
        if len(R)<20: print(f'  {name:34s} n={len(R)} (too few)'); return
        print(f'  {name:34s} n={len(R):5d} | 3일 뒤 평균 수익률 {st.mean(r["ret3"] for r in R)*100:+5.2f}% | 7일 안에 −5% 더 하락 확률 {sum(r["dd7"]<=-0.05 for r in R)/len(R)*100:5.1f}%')
    grp('전체',rows)
    hv=lambda r:r['vr']>=1.5; ss=lambda r:r['sr']>=0.3
    grp('거래대금 많음(평소 1.5배+)',[r for r in rows if hv(r)])
    grp('매도세 강함(순매도 30%+)',[r for r in rows if ss(r)])
    grp('둘 다',[r for r in rows if hv(r) and ss(r)])
    grp('둘 다 아님',[r for r in rows if not hv(r) and not ss(r)])
    F=[r for r in rows if r['fall']<=-0.05]
    print('  -- 이미 7일 고점 대비 5% 이상 내려온 시점만(하단 접근 상황) --')
    grp('전체',F); grp('둘 다',[r for r in F if hv(r) and ss(r)]); grp('둘 다 아님',[r for r in F if not hv(r) and not ss(r)])
    grp('매도세 강함',[r for r in F if ss(r)]); grp('매도세 약함(순매도 30% 미만)',[r for r in F if not ss(r)])
