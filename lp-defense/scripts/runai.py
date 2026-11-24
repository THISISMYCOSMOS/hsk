import statistics as st, json
from aitest import *
POL={'균등(B)':fixed('균등'),'앞쪽':fixed('앞쪽'),'뒤쪽':fixed('뒤쪽'),'AI-신호':sig_policy(),'AI-확률':prob_policy(),'AI-둘중하나':both_policy()}
def summarize(label,res):
    print(f'\n== {label}  windows {len(res)}')
    for name,c in [('전체',lambda r:True),('하락',lambda r:r['chg']<-0.10),('횡보',lambda r:-0.10<=r['chg']<=0.10),('상승',lambda r:r['chg']>0.10)]:
        X=[r for r in res if c(r)]
        if not X: continue
        m=lambda k: st.mean(r[k][0] for r in X)
        ceil=st.mean(max(r['균등(B)'][0],r['앞쪽'][0],r['뒤쪽'][0]) for r in X)
        line=' | '.join(f'{k} {m(k):7.1f}' for k in POL)
        print(f'  {name} n={len(X):2d} | {line} | 최대치 {ceil:7.1f}')
    for k in ['AI-신호','AI-확률','AI-둘중하나']:
        dif=[r[k][0]-r['균등(B)'][0] for r in res]
        print(f'   {k} − 균등: 평균 {st.mean(dif):+6.2f}, 이긴 구간 {sum(d>0.01 for d in dif)}/{len(dif)}, 진 구간 {sum(d<-0.01 for d in dif)}/{len(dif)}, 최악 {min(dif):+.1f}, 최고 {max(dif):+.1f}')
allout={}
for label,(F,wins) in [('HSKSwap WETH',pool_data('WETH')),('HSKSwap WHSK',pool_data('WHSK')),('Binance ETH 1y',bin_data())]:
    for w in [0.10,0.20]:
        res=[]
        for win in wins:
            r={'chg':win[-1][1]/win[0][1]-1,'start':win[0][0]}
            for k,pol in POL.items(): r[k]=run(win,w,pol,F)
            res.append(r)
        half=len(res)//2
        summarize(f'{label} ±{int(w*100)}% [전체]',res)
        summarize(f'{label} ±{int(w*100)}% [뒤쪽 절반 = 시험 기간]',res[half:])
        allout[f'{label}|{w}']=res
json.dump(allout,open('ai_out.json','w'),ensure_ascii=False)
