# (가) risk-management backtest: plan rule (equal 25% at 4 points, full by lower bound) vs keeping the LP
import statistics as st
from ratio import run_sched, SCHED
from simmvp import _stay
from runratio import windows_pool, windows_bin
def report(label,wins,w):
    R=[]
    for win in wins:
        s=_stay(win,w,None,None,None,1000); r=run_sched(win,w,SCHED['균등'])
        R.append((s[0],s[2],r[0],r[2]))
    n=len(R); srt=sorted(R,key=lambda x:x[0]); k=max(1,n//10)
    worst_s=st.mean(x[0] for x in srt[:k]); worst_r=st.mean(x[2] for x in srt[:k])
    loss_s=[x[0]-1000 for x in R if x[0]<1000]; loss_r=[x[2]-1000 for x in R if x[2]<1000]
    saved=sum(max(x[2]-x[0],0) for x in R); given=sum(max(x[0]-x[2],0) for x in R)
    print(f'{label} ±{int(w*100)}% n={n} | 평균 최종 유지 {st.mean(x[0] for x in R):.1f} / 규칙 {st.mean(x[2] for x in R):.1f} | 평균 MDD 유지 {st.mean(x[1] for x in R)*100:.1f}% / 규칙 {st.mean(x[3] for x in R)*100:.1f}% | 최대 MDD 유지 {max(x[1] for x in R)*100:.1f}% / 규칙 {max(x[3] for x in R)*100:.1f}% | 최악 10% 구간 평균 유지 {worst_s:.1f} / 규칙 {worst_r:.1f} (그 구간들 기준) | 손실 구간 수 유지 {len(loss_s)} / 규칙 {len(loss_r)} | 손실 구간 평균 손실 유지 {st.mean(loss_s) if loss_s else 0:.1f} / 규칙 {st.mean(loss_r) if loss_r else 0:.1f} | 지킨 손실 합 {saved:.0f} ÷ 포기한 수익 합 {given:.0f} = {saved/given if given else float("inf"):.2f}')
for label,wins in [('HSKSwap WETH',windows_pool('WETH')),('HSKSwap WHSK',windows_pool('WHSK')),('Binance ETH 1y',windows_bin())]:
    for w in [0.10,0.20]: report(label,wins,w)
