# Team MVP rule (HSK_LP_MVP.md §3): targets of L0 = 100/75/50%, cut lines at 50%/80% of distance ref->lower,
# recovery lines at 45%/15% (sustained for CONF blocks), withdrawn risk asset fully sold to USDT, gas 0.03/adj.
import math
from simpool import amts, sell, buy
GAS=0.03; BPH=1800  # blocks per hour (2s)
def run_mvp(rows,width=None,ref=None,pa=None,pb=None,start_usdt=1000.0,init=None,conf_h=1.0):
    P0=rows[0][1]
    if pa is None: pa=P0*(1-width); pb=P0*(1+width)
    ref=ref or P0
    if init is None:
        ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    else: L0=init
    d=ref-pa
    cut50=ref-0.5*d; cut80=ref-0.8*d; rec45=ref-0.45*d; rec15=ref-0.15*d
    frac=1.0; usdt=0.0; fees=0.0; gas=0.0; nadj=0; above_since={0.45:None,0.15:None}
    peak=None; mdd=0
    for blk,P,vol,Lact in rows:
        Lp=L0*frac
        if Lp>0 and pa<=P<=pb and Lact>0: fees+=vol*0.003*Lp/(Lact+Lp)
        # cuts (jump straight to deepest target)
        tgt=frac
        if P<=cut80: tgt=min(tgt,0.5)
        elif P<=cut50: tgt=min(tgt,0.75)
        if tgt<frac-1e-12:
            take=frac-tgt; x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P,Lact); frac=tgt; nadj+=1; gas+=GAS
            above_since={0.45:None,0.15:None}
        # recovery bookkeeping
        for k,line in ((0.45,rec45),(0.15,rec15)):
            if P>=line: above_since[k]=above_since[k] if above_since[k] is not None else blk
            else: above_since[k]=None
        want=frac
        if frac<0.75-1e-9 and above_since[0.45] is not None and blk-above_since[0.45]>=conf_h*BPH: want=0.75
        if frac<1.0-1e-9 and frac>=0.75-1e-9 and above_since[0.15] is not None and blk-above_since[0.15]>=conf_h*BPH: want=1.0
        if want>frac+1e-9 and usdt>0:
            dL=L0*(want-frac); x1,y1=amts(1.0,P,pa,pb)
            need_x=x1*dL; need_y=y1*dL
            # cost to buy need_x ETH
            lo,hi=0.0,usdt
            if need_x>0:
                for _ in range(60):
                    m=(lo+hi)/2
                    if buy(m,P,Lact)<need_x: lo=m
                    else: hi=m
                dy=hi
            else: dy=0.0
            if dy+need_y<=usdt: addL=dL; spend=dy+need_y
            else:  # scale down to budget
                s=usdt/(dy+need_y); addL=dL*s*0.999; 
                # recompute cost at scaled size
                nx=x1*addL; ny=y1*addL; lo,hi=0.0,usdt
                if nx>0:
                    for _ in range(60):
                        m=(lo+hi)/2
                        if buy(m,P,Lact)<nx: lo=m
                        else: hi=m
                spend=(hi if nx>0 else 0)+ny
            if addL>=0.01*L0 and spend<=usdt+1e-9:   # skip dust re-adds (leftover budget), never overspend
                frac+=addL/L0; usdt-=spend; nadj+=1; gas+=GAS
        x,y=amts(L0*frac,P,pa,pb); v=x*P+y+usdt+fees-gas
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*frac,rows[-1][1],pa,pb)
    return x*rows[-1][1]+y+usdt+fees-gas, nadj, mdd
def run_stay(rows,width=None,ref=None,pa=None,pb=None,init=None,start_usdt=1000.0):
    return run_mvp(rows,width,ref,pa,pb,start_usdt,init,conf_h=1e9) if False else _stay(rows,width,pa,pb,init,start_usdt)
def _stay(rows,width,pa,pb,init,start_usdt):
    P0=rows[0][1]
    if pa is None: pa=P0*(1-width); pb=P0*(1+width)
    if init is None:
        ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    else: L0=init
    fees=0; peak=None; mdd=0
    for blk,P,vol,Lact in rows:
        if pa<=P<=pb and Lact>0: fees+=vol*0.003*L0/(Lact+L0)
        x,y=amts(L0,P,pa,pb); v=x*P+y+fees; peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0,rows[-1][1],pa,pb); return x*rows[-1][1]+y+fees,0,mdd
if __name__=='__main__':
    # sanity: illustrative example from MVP doc (P0=2000, 1800~2200): path 2000->1900->1805 and 2000->1900->1995
    for path in ([2000,1900,1805],[2000,1900,1995]):
        rows=[(i*BPH*10,p,0.0,1e9) for i,p in enumerate(path)]  # huge Lact -> no impact
        v,n,m=run_mvp(rows,pa=1800,pb=2200,ref=2000,conf_h=1e9)
        s,_,_=_stay(rows,None,1800,2200,None,1000)
        print(path,'mvp',round(v,2),'stay',round(s,2),'adj',n)
