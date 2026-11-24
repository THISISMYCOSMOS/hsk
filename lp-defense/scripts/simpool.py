# Simulation on the REAL HSKSwap pool path (swap-by-swap), USDT units.
import json, math, statistics as st, datetime as dt, sys
S=json.load(open('swaps_all.json'))
def s(x):
    v=int(x,16); return v-2**256 if v>2**255 else v
def load(n):
    rows=[]
    for l in S[n]:
        d=l['data'][2:]; a1=s(d[64:128])/1e6; sp=int(d[128:192],16)/2**96; L=int(d[192:256],16)/1e12
        rows.append((int(l['blockNumber'],16), sp*sp*1e12, abs(a1), L))
    rows.sort(); return rows
def amts(L,P,pa,pb):
    q=min(max(math.sqrt(P),math.sqrt(pa)),math.sqrt(pb)); return L*(1/q-1/math.sqrt(pb)), L*(q-math.sqrt(pa))
def sell(dx,P,Lp):
    if dx<=0: return 0.0
    if Lp<=0: return 0.0
    x=Lp/math.sqrt(P); y=Lp*math.sqrt(P); return y-Lp*Lp/(x+dx*0.997)
def buy(dy,P,Lp):
    x=Lp/math.sqrt(P); y=Lp*math.sqrt(P); return x-Lp*Lp/(y+dy*0.997)
import os, bisect
START=os.environ.get('START','pre')   # 'pre': window starts at the pool price just before the window (team convention, = price an LP opened at that moment gets); 'first': price after the first swap in the window (old rerun)
def win_at(R,b,e):
    i=bisect.bisect_left(R,(b,)); j=bisect.bisect_left(R,(e,))
    w=R[i:j]
    if START=='pre' and i>0 and w: w=[(b,R[i-1][1],0.0,R[i-1][3])]+w
    return w
LAD=[(0.5,0.10),(0.75,0.30),(0.9,0.60),(1.0,1.0)]
def run(rows,width,mode,ref=None,pa=None,pb=None,start_usdt=1000.0,init=None):
    P0=rows[0][1]
    if pa is None: pa=P0*(1-width); pb=P0*(1+width)
    ref=ref or P0
    den_x,den_y=amts(1.0,P0,pa,pb); L0=start_usdt/(den_x*P0+den_y) if init is None else init
    frac=1.0; usdt=0.0; fees=0.0; done=0; d=ref-pa; nadj=0; peak=None; mdd=0
    for blk,P,vol,Lact in rows:
        Lp=L0*frac
        if Lp>0 and pa<=P<=pb: fees+=vol*0.003*Lp/(Lact+Lp) if Lact>0 else 0
        if mode in('full','ladder','ladder_re'):
            lad=[(1.0,1.0)] if mode=='full' else LAD
            while done<len(lad) and P<=ref-lad[done][0]*d:
                take=frac-(1-lad[done][1])
                if take>1e-12:
                    x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P,Lact); frac-=take; nadj+=1
                done+=1
            if mode=='ladder_re' and done>0 and usdt>0 and ref-lad[0][0]*d<P<pb:
                x1,y1=amts(1.0,P,pa,pb); lo,hi=0,usdt
                for _ in range(50):
                    dy=(lo+hi)/2
                    if buy(dy,P,Lact)/x1 < (usdt-dy)/y1: lo=dy
                    else: hi=dy
                frac+=min(buy(dy,P,Lact)/x1,(usdt-dy)/y1)/L0; usdt=0; done=0; nadj+=1
        x,y=amts(L0*frac,P,pa,pb); v=x*P+y+usdt+fees
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*frac,rows[-1][1],pa,pb)
    return x*rows[-1][1]+y+usdt+fees, nadj, mdd
if __name__=='__main__':
    BLK_DAY=43200
    for n in ['WETH','WHSK']:
        R=load(n); print(f'\n== {n}: swaps {len(R)}, blocks {R[0][0]}~{R[-1][0]}, price {R[0][1]:.5g} -> {R[-1][1]:.5g}')
        for w in [0.10,0.20]:
            res=[]
            b=R[0][0]
            while b+30*BLK_DAY<=R[-1][0]:
                win=[r for r in R if b<=r[0]<b+30*BLK_DAY]
                if len(win)>=20:
                    st_=run(win,w,'stay')[0]; fu=run(win,w,'full')[0]; la=run(win,w,'ladder')[0]; lr=run(win,w,'ladder_re')[0]
                    res.append((win[-1][1]/win[0][1]-1,st_,fu,la,lr,500+500*win[-1][1]/win[0][1]))
                b+=7*BLK_DAY
            print(f' ±{int(w*100)}% windows {len(res)}')
            for name,c in [('all',lambda r:True),('down',lambda r:r[0]<-0.10),('side',lambda r:-0.10<=r[0]<=0.10),('up',lambda r:r[0]>0.10)]:
                X=[r for r in res if c(r)]
                if not X: print(f'  {name}: none'); continue
                m=lambda j: st.mean(r[j] for r in X)
                print(f'  {name:4s} n={len(X):2d} stay {m(1):7.1f} full {m(2):7.1f} ladder {m(3):7.1f} ladder+re {m(4):7.1f} 50/50 {m(5):7.1f} | ladder>stay {sum(r[3]>r[1] for r in X)}/{len(X)} ladder>full {sum(r[3]>r[2] for r in X)}/{len(X)}')
