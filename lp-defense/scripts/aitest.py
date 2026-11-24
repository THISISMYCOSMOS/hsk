# AI evidence test: does a signal-driven withdrawal ratio beat the fixed (equal) ratio out of sample?
import json, math, bisect, statistics as st
from simpool import amts, sell
from gapsdef import gaps
GAS=0.03; D=43200; H=1800
CUM={'균등':[.25,.5,.75,1],'앞쪽':[.4,.7,.9,1],'뒤쪽':[.1,.3,.6,1]}
Phi=lambda z:0.5*(1+math.erf(z/math.sqrt(2)))
def p_hit(b,sig,T):  # zero drift
    if sig<=0: return 0.0
    return 2*Phi(-b/(sig*math.sqrt(T)))
class Feat:
    """features from data strictly before/at block t"""
    def __init__(self,blk,price,absvol,netsell):
        self.B=blk; self.P=price
        self.cv=[0]; self.cs=[0]
        for v,s in zip(absvol,netsell): self.cv.append(self.cv[-1]+v); self.cs.append(self.cs[-1]+s)
        # hourly EWMA variance of log returns (lambda .94)
        self.hb=[]; self.hv=[]; var=None; last=None
        b0=blk[0]-blk[0]%H
        for hb in range(b0, blk[-1]+H, H):
            i=bisect.bisect_right(blk,hb)-1
            if i<0: continue
            p=price[i]
            if last is not None:
                r=math.log(p/last); var=r*r if var is None else 0.94*var+0.06*r*r
            last=p; self.hb.append(hb); self.hv.append(var if var is not None else 0.0)
    def at(self,t):
        i1=bisect.bisect_right(self.B,t); i24=bisect.bisect_left(self.B,t-24*H); i7=bisect.bisect_left(self.B,t-7*24*H)
        v24=self.cv[i1]-self.cv[i24]; v7=(self.cv[i1]-self.cv[i7])/7; s24=self.cs[i1]-self.cs[i24]
        j=bisect.bisect_right(self.hb,t)-1; sig=math.sqrt(self.hv[j]) if j>=0 and self.hv[j] else 0.0
        return (v24/v7 if v7>0 else 0.0, s24/v24 if v24>0 else 0.0, sig)
def run(rows,w,policy,F,start_usdt=1000.0):
    P0=rows[0][1]; pa=P0*(1-w); pb=P0*(1+w); d=P0-pa
    ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    lv=[P0-f*d for f in (.25,.5,.75,1.0)]
    out=0.0; usdt=0.0; fees=0.0; gas=0.0; k=0; peak=None; mdd=0
    for blk,P,vol,Lact in rows:
        Lp=L0*(1-out)
        if Lp>0 and pa<=P<=pb and Lact>0: fees+=vol*0.003*Lp/(Lact+Lp)
        if k<4 and P<=lv[k]:
            while k<4 and P<=lv[k]: k+=1
            tgt=policy(k-1,F.at(blk),P,pa)
            take=max(0.0,min(1.0,tgt)-out)
            if take>1e-12:
                x,y=amts(L0*take,P,pa,pb); usdt+=y+sell(x,P,Lact); out+=take; gas+=GAS
        x,y=amts(L0*(1-out),P,pa,pb); v=x*P+y+usdt+fees-gas
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*(1-out),rows[-1][1],pa,pb)
    return x*rows[-1][1]+y+usdt+fees-gas, mdd
fixed=lambda name:(lambda k,f,P,pa:CUM[name][k])
def sig_policy(vr_th=1.5,sr_th=0.3):
    return lambda k,f,P,pa: CUM['앞쪽'][k] if (f[0]>=vr_th and f[1]>=sr_th) else CUM['뒤쪽'][k]
def prob_policy(th=0.5,T=72):
    return lambda k,f,P,pa: CUM['앞쪽'][k] if p_hit(math.log(P/pa),f[2],T)>=th else CUM['뒤쪽'][k]
def both_policy(th=0.5,T=72,vr_th=1.5,sr_th=0.3):
    return lambda k,f,P,pa: CUM['앞쪽'][k] if (p_hit(math.log(P/pa),f[2],T)>=th or (f[0]>=vr_th and f[1]>=sr_th)) else CUM['뒤쪽'][k]
# ---------- data ----------
def pool_data(n):
    S=json.load(open('swaps_all.json'))[n]
    def s(x):
        v=int(x,16); return v-2**256 if v>2**255 else v
    start,g0,g1=gaps[n]; R=[]
    for l in S:
        b=int(l['blockNumber'],16)
        if b<start: continue
        d=l['data'][2:]; a1=s(d[64:128])/1e6; sp=int(d[128:192],16)/2**96; L=int(d[192:256],16)/1e12
        R.append((b,sp*sp*1e12,abs(a1),L,-a1))
    R.sort()
    F=Feat([r[0] for r in R],[r[1] for r in R],[r[2] for r in R],[r[4] for r in R])
    rows=[r[:4] for r in R]; wins=[]; b=start+7*D
    while b+30*D<=rows[-1][0]:
        if not (b<g1+7*D and b+30*D>g0):
            win=[r for r in rows if b<=r[0]<b+30*D]
            if len(win)>=20: wins.append(win)
        b+=7*D
    return F,wins
def bin_data():
    K=json.load(open('eth_1y_vol.json')); B=[i*H for i in range(len(K))]
    F=Feat(B,[k[1] for k in K],[k[2] for k in K],[k[2]-2*k[3] for k in K])  # netsell = sell-buy = (q-tb)-tb
    rows=[(B[i],K[i][1],19637/720,1013.0) for i in range(len(K))]
    wins=[rows[i:i+720] for i in range(7*24,len(rows)-720,168)]
    return F,wins
