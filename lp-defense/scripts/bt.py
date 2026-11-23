import pandas as pd, numpy as np, math
sw=pd.read_pickle('whsk_sw.pkl'); sw=sw[sw.ts>='2026-05-01'].reset_index(drop=True)
P=sw.px.values; V=sw.usd.values; LP=sw.Lk.values/1e12; T=sw.ts.values
def amts(L,p,pa,pb):
    sp,sa,sb=math.sqrt(p),math.sqrt(pa),math.sqrt(pb)
    if p<=pa: return L*(1/sa-1/sb),0.0
    if p>=pb: return 0.0,L*(sb-sa)
    return L*(1/sp-1/sb),L*(sp-sa)
def run(i0,horizon_days,width,strat,C=1000.0):
    p0=P[i0]; pa,pb=p0*(1-width),p0*(1+width)
    x,y=amts(1,p0,pa,pb); L=C/(x*p0+y); x0,y0=x*L,y*L
    tend=T[i0]+np.timedelta64(horizon_days,'D')
    Lr=L; wx=wy=0.0; fee=0.0; steps=strat.get('steps',[]); done=set(); sold=False
    i=i0
    while i<len(P)-1 and T[i]<tend:
        i+=1; p=P[i]
        if pa<p<pb and Lr>0: fee+=V[i]*0.003*Lr/(LP[i]+Lr)
        for k,(lvl,frac) in enumerate(steps):
            if k not in done and p<=pa*(1+lvl):
                d=L*frac; d=min(d,Lr); ax,ay=amts(d,p,pa,pb); wx+=ax; wy+=ay; Lr-=d; done.add(k)
                if strat.get('sell'): wy+=ax*p*(1-0.003-0.002); wx-=ax  # sell withdrawn WHSK, fee+slippage
    pe=P[i]; rx,ry=amts(Lr,pe,pa,pb)
    val=(rx+wx)*pe+ry+wy+fee; hodl=x0*pe+y0
    return dict(start=pd.Timestamp(T[i0]),p0=p0,pend=pe,chg=pe/p0-1,val=val,hodl=hodl,usdt=C,fee=fee,touched=min(P[i0:i+1])<=pa)
S={'hold':{},
   'allout_at_+5%':{'steps':[(0.05,1.0)]},
   'split_3':{'steps':[(0.10,0.2),(0.05,0.3),(0.0,0.5)]},
   'split_3_sell':{'steps':[(0.10,0.2),(0.05,0.3),(0.0,0.5)],'sell':True},
   'allout_sell':{'steps':[(0.05,1.0)],'sell':True}}
if __name__=="__main__":
    import sys
    width=float(sys.argv[1]) if len(sys.argv)>1 else 0.15
    starts=[]; t=pd.Timestamp('2026-05-02')
    while t<pd.Timestamp('2026-10-20'):
        idx=np.searchsorted(sw.ts.values,np.datetime64(t)); starts.append(idx); t+=pd.Timedelta(days=3)
    rows=[]
    for name,st in S.items():
        for i0 in starts:
            r=run(i0,30,width,st); r['strat']=name; rows.append(r)
    df=pd.DataFrame(rows)
    df['pnl_vs_usdt']=df.val/df.usdt-1; df['pnl_vs_hodl']=df.val/df.hodl-1
    print("width ±%d%%, episodes %d, touched lower %d"%(width*100,len(starts),df[df.strat=='hold'].touched.sum()))
    g=df.groupby('strat').agg(mean_vs_usdt=('pnl_vs_usdt','mean'),worst_vs_usdt=('pnl_vs_usdt','min'),mean_vs_hodl=('pnl_vs_hodl','mean'),worst_vs_hodl=('pnl_vs_hodl','min'),fee=('fee','mean'))
    print(g.round(4))
    t=df[df.touched]; print("only episodes that touched lower bound:"); print(t.groupby('strat').agg(n=('val','size'),mean_vs_usdt=('pnl_vs_usdt','mean'),worst=('pnl_vs_usdt','min'),mean_vs_hodl=('pnl_vs_hodl','mean')).round(4))
    df.to_pickle(f'bt_{width}.pkl')
