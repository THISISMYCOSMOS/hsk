# 처분 규칙 C: 회수 시점에 거래소(KuCoin) 24시간 수익률이 -X% 이하이면 회수한 WHSK를 판다.
import pandas as pd, numpy as np, math, sys
import bt
k=pd.read_pickle('kucoin_hsk_1h.pkl').set_index('ts').c
r24=(k/k.shift(24)-1)
P,V,LP,T=bt.P,bt.V,bt.LP,bt.T
def ret24(t):
    i=r24.index.searchsorted(pd.Timestamp(t))-1
    return r24.iloc[max(i,0)]
def run(i0,width,steps,mode,X=0.05,C=1000.0):
    p0=P[i0]; pa,pb=p0*(1-width),p0*(1+width)
    x,y=bt.amts(1,p0,pa,pb); L=C/(x*p0+y); x0,y0=x*L,y*L
    tend=T[i0]+np.timedelta64(30,'D'); Lr=L; wx=wy=fee=0.0; done=set(); i=i0
    while i<len(P)-1 and T[i]<tend:
        i+=1; p=P[i]
        if pa<p<pb and Lr>0: fee+=V[i]*0.003*Lr/(LP[i]+Lr)
        for kk,(lvl,frac) in enumerate(steps):
            if kk not in done and p<=pa*(1+lvl):
                d=min(L*frac,Lr); ax,ay=bt.amts(d,p,pa,pb); Lr-=d; done.add(kk); wy+=ay
                sell = mode=='always' or (mode=='rule' and ret24(T[i])<=-X)
                if sell: wy+=ax*p*0.995
                else: wx+=ax
    pe=P[i]; rx,ry=bt.amts(Lr,pe,pa,pb); val=(rx+wx)*pe+ry+wy+fee
    return val/C-1, min(P[i0:i+1])<=pa
steps=[(0.10,0.2),(0.05,0.3),(0.0,0.5)]
starts=[]; t=pd.Timestamp('2026-05-02')
while t<pd.Timestamp('2026-10-20'):
    starts.append(np.searchsorted(bt.sw.ts.values,np.datetime64(t))); t+=pd.Timedelta(days=3)
for width in [0.10,0.15]:
    res={}
    for name,mode,X in [('A 항상 보유','never',0),('B 항상 매도','always',0),('C 24h<=-3%','rule',0.03),('C 24h<=-5%','rule',0.05),('C 24h<=-8%','rule',0.08)]:
        out=[run(i,width,steps,mode,X) for i in starts]; res[name]=out
    touched=[o[1] for o in res['A 항상 보유']]
    print("width",width,"touched",sum(touched))
    base=np.array([o[0] for o,tc in zip(res['A 항상 보유'],touched) if tc])
    for n,out in res.items():
        v=np.array([o[0] for o,tc in zip(out,touched) if tc])
        print("  %-14s mean %.4f worst %.4f | vs A: better %d worse %d"%(n,v.mean(),v.min(),(v>base+1e-9).sum(),(v<base-1e-9).sum()))
