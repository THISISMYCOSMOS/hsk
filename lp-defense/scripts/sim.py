import json, math, statistics as st, datetime as dt
K=json.load(open('eth_1y.json'))
LPOOL=1013.0; FEE_HR=19637/720*0.003   # pool full-range L (human), fee USDT per hour (actual 10-25~11-23 volume)
def amts(L,P,pa,pb):
    s=min(max(math.sqrt(P),math.sqrt(pa)),math.sqrt(pb))
    return L*(1/s-1/math.sqrt(pb)), L*(s-math.sqrt(pa))
def sell(dx,P):
    if dx<=0: return 0.0
    x=LPOOL/math.sqrt(P); y=LPOOL*math.sqrt(P); x2=x+dx*0.997; return y-LPOOL**2/x2
def run(path, width, ladder):
    P0=path[0]; pa=P0*(1-width); pb=P0*(1+width)
    den=2*math.sqrt(P0)-P0/math.sqrt(pb)-math.sqrt(pa); L0=1000/den
    frac_in=1.0; usdt=0.0; fees=0.0; done=0; d=P0-pa; n_adj=0; peak=1000; mdd=0
    for P in path:
        if frac_in>0 and pa<=P<=pb:
            Lp=L0*frac_in; fees+=FEE_HR*Lp/(LPOOL+Lp)
        while done<len(ladder) and P<=P0-ladder[done][0]*d:
            target=ladder[done][1]; take=frac_in-(1-target)
            if take>1e-12:
                x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P); frac_in-=take; n_adj+=1
            done+=1
        x,y=amts(L0*frac_in,P,pa,pb); v=x*P+y+usdt+fees
        peak=max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*frac_in,path[-1],pa,pb)
    return x*path[-1]+y+usdt+fees, n_adj, mdd
STAY=[]; FULL=[(1.0,1.0)]; LAD=[(0.5,0.10),(0.75,0.30),(0.9,0.60),(1.0,1.0)]
def window(i0,hours=720): return [p for _,p in K[i0:i0+hours]]
if __name__=='__main__':
    # reproduce teammate window 10-25 00:00 KST ~ 11-23
    t0=int(dt.datetime(2026,10,24,15,tzinfo=dt.timezone.utc).timestamp())
    i0=[i for i,(t,_) in enumerate(K) if t>=t0][0]
    path=window(i0)
    print('teammate window', round(path[0],1),'->',round(path[-1],1))
    for w in [0.10,0.20]:
        r={k:run(path,w,v) for k,v in [('LP유지',STAY),('하단전량',FULL),('분할',LAD)]}
        print(f'±{int(w*100)}%',{k:(round(a,2),n,round(m*100,1)) for k,(a,n,m) in r.items()},'반반',round(500+500/path[0]*path[-1],2))
    # rolling 30-day windows every 7 days over 1 year
    for w in [0.10,0.20]:
        rows=[]
        for i in range(0,len(K)-720,168):
            p=window(i); s=run(p,w,STAY)[0]; f=run(p,w,FULL)[0]; l=run(p,w,LAD)[0]
            rows.append((p[-1]/p[0]-1, s,f,l))
        n=len(rows)
        print(f'\n±{int(w*100)}% windows',n)
        for name,cond in [('all',lambda r:True),('down<-10%',lambda r:r[0]<-0.10),('side ±10%',lambda r:-0.10<=r[0]<=0.10),('up>10%',lambda r:r[0]>0.10)]:
            R=[r for r in rows if cond(r)]
            if not R: continue
            print(f' {name:10s} n={len(R):2d}  mean 분할-유지 {st.mean(r[3]-r[1] for r in R):+7.2f}  mean 전량-유지 {st.mean(r[2]-r[1] for r in R):+7.2f}  mean 분할-전량 {st.mean(r[3]-r[2] for r in R):+7.2f}  분할>유지 {sum(r[3]>r[1] for r in R)}/{len(R)}  분할>전량 {sum(r[3]>r[2] for r in R)}/{len(R)}  worst 분할-유지 {min(r[3]-r[1] for r in R):+.1f}')
