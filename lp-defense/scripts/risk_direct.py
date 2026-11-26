# 실제 위험 직접 측정 (전략 모의 없음): 활동, 외부 시세 추종, 실제 가격 하락 빈도, LP가 차익거래에 잃은 금액
import json, sys, bisect, statistics as st, datetime as dt
D=sys.argv[1]
S=json.load(open(f'{D}/swaps_all.json')); X=json.load(open(f'{D}/ext.json'))
def i256(h):
    v=int(h,16); return v-(1<<256) if v>=1<<255 else v
def parse(logs):
    out=[]
    for l in logs:
        d=l['data'][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
        a0=i256(w[0])/1e18; a1=i256(w[1])/1e6; sp=int(w[2],16)
        p=(sp/2**96)**2*1e12; L=int(w[3],16)
        out.append((int(l['timeStamp'],16),int(l['blockNumber'],16),a0,a1,p,L))
    out.sort(key=lambda x:(x[1],));return out
def kst(t): return dt.datetime.fromtimestamp(t,dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d')
def q(v,p): v=sorted(v); return v[min(len(v)-1,int(p*len(v)))]
now=max(int(l['timeStamp'],16) for n in S for l in S[n])
print('기준 시각',kst(now))
EXT={'WETH':('eth_1h','eth_1m'),'WHSK':('hsk_1h','hsk_1m')}
START={'WETH':dt.datetime(2026,4,21,tzinfo=dt.timezone.utc).timestamp(),'WHSK':dt.datetime(2026,4,20,tzinfo=dt.timezone.utc).timestamp()}
for n in ('WETH','WHSK'):
    sw=parse(S[n]); ts=[s[0] for s in sw]
    print(f'\n===== {n}/USDT =====')
    # A. 활동
    for days in (7,30):
        t0=now-days*86400; w=[s for s in sw if s[0]>=t0]
        nb=days*96; used=set((s[0]-t0)//900 for s in w)
        vol=sum(abs(s[3]) for s in w)
        gaps=[b[0]-a[0] for a,b in zip(w,w[1:])]
        print(f'A 최근{days}일: 스왑 {len(w)}건, 거래대금 {vol:,.0f} USDT, 15분 구간 {nb}개 중 빈 구간 {nb-len(used)}개({(nb-len(used))/nb:.0%}), 간격 중앙값 {st.median(gaps)/60:.1f}분, 최장 {max(gaps)/3600:.1f}시간')
    # 가격 시계열: 각 시각의 마지막 스왑 가격
    def pool_at(t):
        i=bisect.bisect_right(ts,t)-1; return sw[i][4] if i>=0 else None
    START[n]=max(START[n],ts[0]+3600)
    eh=X[EXT[n][0]]; em=dict(X[EXT[n][1]])
    # B. 외부 추종 (1시간 종가, 큰 LP 이후)
    devs=[];pr=[];er=[]
    hh=[(t+3600,c) for t,c in eh if t>=START[n]]
    for t,c in hh:
        p=pool_at(t)
        if p: devs.append((p-c)/c*100)
    daily=[(t,c,pool_at(t)) for t,c in hh if (t%86400)==0]
    for a,b in zip(daily,daily[1:]):
        if a[2] and b[2]: er.append(b[1]/a[1]-1); pr.append(b[2]/a[2]-1)
    corr=st.correlation(pr,er)
    d30=[d for (t,c),d in zip([x for x in hh if pool_at(x[0])],devs) if t>=now-30*86400]
    print(f'B 최근 30일 |풀−외부| 중앙값 {st.median(map(abs,d30)):.2f}%, 90% {q(list(map(abs,d30)),.9):.2f}%, 최대 {max(map(abs,d30)):.2f}%')
    print(f'B 풀 가격 − 외부 가격(시간별, {kst(START[n])}~): 중앙값 {st.median(devs):+.2f}%, |차이| 중앙값 {st.median(map(abs,devs)):.2f}%, 90% {q(list(map(abs,devs)),.9):.2f}%, 최대 {max(map(abs,devs)):.2f}%')
    print(f'B 하루 수익률 상관(풀 vs 외부) {corr:.3f}, 일수 {len(pr)}')
    sp_pool=pool_at(START[n]); sp_ext=[c for t,c in hh][0]
    print(f'B 기간 전체 가격 변화: 풀 {pool_at(now)/sp_pool-1:+.1%}, 외부 {hh[-1][1]/sp_ext-1:+.1%}')
    # C. 실제 하락 빈도 (풀 가격, 30일 창, 매일 시작)
    for days in (7,30):
        res=[]
        t=START[n]
        while t+days*86400<=now:
            p0=pool_at(t); seg=[s[4] for s in sw if t<s[0]<=t+days*86400]
            if p0 and seg: res.append(min(seg)/p0-1)
            t+=86400
        f=lambda x: sum(1 for r in res if r<=x)/len(res)
        print(f'C {days}일 창 {len(res)}개: 시작가 대비 최저점이 −5% 이하 {f(-.05):.0%}, −10% 이하 {f(-.10):.0%}, −20% 이하 {f(-.20):.0%}, −30% 이하 {f(-.30):.0%}. 최악 {min(res):+.1%}')
    # D. LP가 거래 상대에게 잃은 금액 (외부 1분 종가로 평가, 최근 60일)
    t0=max(min(em),now-60*86400); tot=0;fee=0;cnt=0;miss=0
    for s in sw:
        if s[0]<t0: continue
        m=(s[0]//60)*60; c=em.get(m) or em.get(m-60)
        if not c: miss+=1; continue
        tot+=s[2]*c+s[3]; cnt+=1
        fee+= (s[2]*c if s[2]>0 else s[3])*0.003
    days=(now-t0)/86400
    print(f'D 최근 {days:.0f}일 스왑 {cnt}건(외부 시세 없음 {miss}): 외부가 기준 LP 순손익 {tot:+,.1f} USDT = 받은 수수료 {fee:+,.1f} + 가격 불리 {tot-fee:+,.1f}')
