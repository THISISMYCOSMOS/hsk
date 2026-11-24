# (나) demo-liquidity backtest: selling S USDT worth of token into the pool at each 6h sample
import json, math, statistics as st, datetime as dt
R=json.load(open('liq_6h.json'))
def loss(S,P,L):
    if L<=0: return 1.0
    r=S/(math.sqrt(P)*L); return 1-0.997/(1+0.997*r)
for n in ['WETH','WHSK']:
    X=sorted([r for r in R if r[0]==n and r[2] is not None],key=lambda r:r[1])
    print(f'\n== {n}: samples {len(X)} ({dt.datetime.utcfromtimestamp(X[0][2]):%Y-%m-%d} ~ {dt.datetime.utcfromtimestamp(X[-1][2]):%Y-%m-%d})')
    tvl=lambda r: 2*r[4]*math.sqrt(r[3])  # full-range-equivalent pool value in USDT
    for lab,sub in [('전체 기간',X),('큰 LP 입금 이후(WETH 04-21, WHSK 04-20~)',[r for r in X if r[2]>=dt.datetime(2026,4,21,6,tzinfo=dt.timezone.utc).timestamp()])]:
        print(f' [{lab}] n={len(sub)}')
        for S in [100,1000,10000]:
            ls=sorted(loss(S,r[3],r[4]) for r in sub)
            print(f'   {S:>6} USDT 매도: 손실 중앙값 {ls[len(ls)//2]*100:5.2f}% | 나쁜 10% {ls[int(len(ls)*0.9)]*100:6.2f}% | 2% 넘는 시점 {sum(x>0.02 for x in ls)/len(ls)*100:5.1f}% | 10% 넘는 시점 {sum(x>0.10 for x in ls)/len(ls)*100:5.1f}%')
        tv=sorted(tvl(r) for r in sub); print(f'   풀 규모(전 구간 환산) 중앙값 {tv[len(tv)//2]:,.0f} USDT, 나쁜 10% {tv[int(len(tv)*0.1)]:,.0f}')
    # empty / thin stretches after big LP: pool value < 1,000 USDT
    thin=[r for r in X if tvl(r)<1000 and r[2]>=dt.datetime(2026,4,21,6,tzinfo=dt.timezone.utc).timestamp()]
    if thin: print(f'   큰 LP 입금 이후 풀 규모 1,000 USDT 미만 시점: {len(thin)}개, {dt.datetime.utcfromtimestamp(thin[0][2]):%m-%d %H시} ~ {dt.datetime.utcfromtimestamp(thin[-1][2]):%m-%d %H시} UTC')
    last=X[-1]; print(f'   현재: 가격 {last[3]:.5g}, 풀 규모 {tvl(last):,.0f} USDT, 100/1,000/10,000 USDT 매도 손실 {loss(100,last[3],last[4])*100:.2f}% / {loss(1000,last[3],last[4])*100:.2f}% / {loss(10000,last[3],last[4])*100:.2f}%')
