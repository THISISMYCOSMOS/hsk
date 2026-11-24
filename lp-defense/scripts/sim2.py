from sim import *
def buy_cost(dy,P):  # USDT spent dy -> ETH out
    x=LPOOL/math.sqrt(P); y=LPOOL*math.sqrt(P); y2=y+dy*0.997; return x-LPOOL**2/y2
def run_r(path,width,ladder):
    P0=path[0]; pa=P0*(1-width); pb=P0*(1+width); d=P0-pa
    den=2*math.sqrt(P0)-P0/math.sqrt(pb)-math.sqrt(pa); L0=1000/den
    frac=1.0; usdt=0.0; fees=0.0; done=0; n=0
    for P in path:
        if frac>0 and pa<=P<=pb: fees+=FEE_HR*L0*frac/(LPOOL+L0*frac)
        while done<len(ladder) and P<=P0-ladder[done][0]*d:
            take=frac-(1-ladder[done][1])
            if take>1e-12:
                x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P); frac-=take; n+=1
            done+=1
        if done>0 and usdt>0 and P>P0-ladder[0][0]*d and P<pb:   # recovered above first level: re-supply all USDT
            x1,y1=amts(1.0,P,pa,pb)  # per unit L
            # spend part of usdt on ETH so ratio matches: choose dy with dy->eth, usdt-dy as y
            lo,hi=0,usdt
            for _ in range(60):
                dy=(lo+hi)/2; e=buy_cost(dy,P)
                if e/x1 < (usdt-dy)/y1: lo=dy
                else: hi=dy
            e=buy_cost(dy,P); Ladd=min(e/x1,(usdt-dy)/y1)
            frac+=Ladd/L0; usdt=0; done=0; n+=1
    x,y=amts(L0*frac,path[-1],pa,pb)
    return x*path[-1]+y+usdt+fees, n
t0=int(dt.datetime(2026,10,24,15,tzinfo=dt.timezone.utc).timestamp())
i0=[i for i,(t,_) in enumerate(K) if t>=t0][0]; path=window(i0)
for w in [0.10,0.20]:
    print(f'teammate window ±{int(w*100)}%: stay {run(path,w,STAY)[0]:.1f} full {run(path,w,FULL)[0]:.1f} ladder {run(path,w,LAD)[0]:.1f} ladder+resupply {run_r(path,w,LAD)[0]:.1f} (adj {run_r(path,w,LAD)[1]})')
for w in [0.10,0.20]:
    rows=[]
    for i in range(0,len(K)-720,168):
        p=window(i); rows.append((p[-1]/p[0]-1, run(p,w,STAY)[0], run(p,w,FULL)[0], run(p,w,LAD)[0], run_r(p,w,LAD)[0], 500+500*p[-1]/p[0]))
    print(f'\n±{int(w*100)}%  (mean final USDT; hold USDT=1000)')
    for name,cond in [('all',lambda r:True),('down',lambda r:r[0]<-0.10),('side',lambda r:-0.10<=r[0]<=0.10),('up',lambda r:r[0]>0.10)]:
        R=[r for r in rows if cond(r)]
        m=lambda j: st.mean(r[j] for r in R)
        print(f' {name:5s} n={len(R):2d} stay {m(1):7.1f} full {m(2):7.1f} ladder {m(3):7.1f} ladder+re {m(4):7.1f} 50/50 {m(5):7.1f}  ladder>full {sum(r[3]>r[2] for r in R)}/{len(R)}  re>ladder {sum(r[4]>r[3] for r in R)}/{len(R)}')
# fee income check
print('\nfee per month for 1000USDT ±10% fully in range ~', round(720*FEE_HR*210/(LPOOL+210),2), 'USDT')
