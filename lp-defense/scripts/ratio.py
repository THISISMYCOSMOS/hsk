# Fixed-ratio staged withdrawal: 4 points at 25/50/75/100% of distance ref->lower; per-point share of L0 given by schedule.
import json, statistics as st
from simpool import load, amts, sell
from simmvp import _stay, BPH
GAS=0.03
SCHED={'균등':[0.25,0.25,0.25,0.25],'앞쪽':[0.40,0.30,0.20,0.10],'뒤쪽':[0.10,0.20,0.30,0.40]}
def run_sched(rows,w,sched,start_usdt=1000.0):
    P0=rows[0][1]; pa=P0*(1-w); pb=P0*(1+w); d=P0-pa
    ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    lv=[P0-f*d for f in (0.25,0.5,0.75,1.0)]
    frac=1.0; usdt=0.0; fees=0.0; gas=0.0; done=0; peak=None; mdd=0; n=0
    for blk,P,vol,Lact in rows:
        Lp=L0*frac
        if Lp>0 and pa<=P<=pb and Lact>0: fees+=vol*0.003*Lp/(Lact+Lp)
        take=0.0
        while done<4 and P<=lv[done]: take+=sched[done]; done+=1
        take=min(take,frac)
        if take>1e-12:
            x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P,Lact); frac-=take; gas+=GAS; n+=1
        x,y=amts(L0*frac,P,pa,pb); v=x*P+y+usdt+fees-gas
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*frac,rows[-1][1],pa,pb)
    return x*rows[-1][1]+y+usdt+fees-gas, n, mdd
