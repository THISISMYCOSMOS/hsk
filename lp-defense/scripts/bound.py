# At the lower bound: exit the remaining LP or keep it? Compare fixed choices, a waiting rule, and an AI signal rule.
import math, statistics as st
from simpool import amts, sell
from aitest import Feat, p_hit, pool_data, bin_data
GAS=0.03; H=1800
def run_bound(rows,w,F,mode,start_usdt=1000.0,wait_h=12):
    P0=rows[0][1]; pa=P0*(1-w); pb=P0*(1+w); d=P0-pa
    ux,uy=amts(1.0,P0,pa,pb); L0=start_usdt/(ux*P0+uy)
    cut50=P0-0.5*d; cut80=P0-0.8*d
    out=0.0; usdt=0.0; fees=0.0; gas=0.0; below_since=None; done=False; peak=None; mdd=0; exited_at=None
    def take(t,P,Lact):
        nonlocal out,usdt,gas
        t=max(0.0,min(1.0,t)-out)
        if t>1e-12:
            x,y=amts(L0*t,P,pa,pb); usdt+=y+sell(x,P,Lact); out+=t; gas+=GAS
    for blk,P,vol,Lact in rows:
        Lp=L0*(1-out)
        if Lp>0 and pa<=P<=pb and Lact>0: fees+=vol*0.003*Lp/(Lact+Lp)
        if P<=cut80: take(0.5,P,Lact)
        elif P<=cut50: take(0.25,P,Lact)
        if P<=pa and not done:
            if below_since is None: below_since=blk
            exit_now=False
            if mode=='full': exit_now=True
            elif mode=='wait': exit_now = blk-below_since>=wait_h*H
            elif mode=='ai':
                vr,sr,sig=F.at(blk)
                exit_now = (vr>=1.5 and sr>=0.3) or p_hit(math.log(P/(pa*0.95)),sig,72)>=0.5
            if exit_now: take(1.0,P,Lact); done=True
        elif P>pa: below_since=None
        x,y=amts(L0*(1-out),P,pa,pb); v=x*P+y+usdt+fees-gas
        peak=v if peak is None else max(peak,v); mdd=max(mdd,1-v/peak)
    x,y=amts(L0*(1-out),rows[-1][1],pa,pb)
    hit=min(r[1] for r in rows)<=pa
    return x*rows[-1][1]+y+usdt+fees-gas, mdd, hit
if __name__=='__main__':
    MODES=['keep','full','wait','ai']
    for label,(F,wins) in [('HSKSwap WETH',pool_data('WETH')),('HSKSwap WHSK',pool_data('WHSK')),('Binance ETH 1y',bin_data())]:
        for w in [0.10,0.20]:
            res=[]
            for win in wins:
                r={m:run_bound(win,w,F,m) for m in MODES}; r['chg']=win[-1][1]/win[0][1]-1; res.append(r)
            hitw=[r for r in res if r['keep'][2]]
            half=len(res)//2; hit_test=[r for r in res[half:] if r['keep'][2]]
            if not hitw: print(f'{label} ±{int(w*100)}%: 하단 도달 구간 없음'); continue
            m=lambda R,k: st.mean(x[k][0] for x in R)
            best=lambda R: st.mean(max(x['keep'][0],x['full'][0]) for x in R)
            # split by what happened after: continued fall vs bounce (final price vs bound)
            print(f'{label} ±{int(w*100)}% 하단 도달 구간 {len(hitw)}/{len(res)} | 남기기 {m(hitw,"keep"):.1f} | 전부 {m(hitw,"full"):.1f} | 12시간 대기 후 전부 {m(hitw,"wait"):.1f} | AI 판단 {m(hitw,"ai"):.1f} | 완벽한 선택 {best(hitw):.1f} | AI−남기기 {st.mean(x["ai"][0]-x["keep"][0] for x in hitw):+.1f} AI−전부 {st.mean(x["ai"][0]-x["full"][0] for x in hitw):+.1f} | AI가 둘 중 나은 쪽과 같거나 나은 구간 {sum(x["ai"][0]>=max(x["keep"][0],x["full"][0])-0.5 for x in hitw)}/{len(hitw)}')
            if hit_test: print(f'    시험 절반: 하단 도달 {len(hit_test)} | 남기기 {m(hit_test,"keep"):.1f} 전부 {m(hit_test,"full"):.1f} 대기 {m(hit_test,"wait"):.1f} AI {m(hit_test,"ai"):.1f} 완벽 {best(hit_test):.1f}')
