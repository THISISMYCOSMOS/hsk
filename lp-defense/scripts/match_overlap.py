# 새 제안(직접 매칭) 점검: 최근 7일·30일 WHSK/USDT 스왑의 거래자 구성, 주문 크기, 반대 주문이 겹칠 수 있는 물량 상한
import json,sys,statistics as st,collections as C
D=sys.argv[1]; S=json.load(open(f'{D}/swaps_all.json'))
def i256(h):
    v=int(h,16); return v-(1<<256) if v>=1<<255 else v
now=max(int(l['timeStamp'],16) for n in S for l in S[n])
for n in ('WHSK','WETH'):
  for days in (7,30):
    rows=[]
    for l in S[n]:
        t=int(l['timeStamp'],16)
        if t<now-days*86400: continue
        d=l['data'][2:]; a0=i256(d[:64])/1e18; a1=i256(d[64:128])/1e6
        rows.append((t,'0x'+l['topics'][1][-40:],'0x'+l['topics'][2][-40:],a0,a1,l['transactionHash']))
    vol=sum(abs(r[4]) for r in rows)
    sizes=sorted(abs(r[4]) for r in rows)
    byrec=C.Counter(); 
    for r in rows: byrec[r[2]]+=abs(r[4])
    txs=len(set(r[5] for r in rows))
    top=byrec.most_common(3)
    print(f'\n{n} 최근 {days}일: 스왑 {len(rows)}건(거래 {txs}), 거래대금 {vol:,.0f}, 받는 주소 {len(byrec)}개')
    print(f'  주문 크기 중앙값 {st.median(sizes):.2f}, 90% {sizes[int(.9*len(sizes))]:.1f}, 최대 {sizes[-1]:.0f} USDT')
    print('  상위 받는 주소 거래대금 비중:',', '.join(f'{a[:8]} {v/vol:.0%}' for a,v in top))
    # 반대 방향 겹침 상한: 창 안에서 min(매도, 매수)
    for w in (900,3600,86400):
        b=C.defaultdict(lambda:[0,0])
        for t,_,_,a0,a1,_ in rows:
            if a0>0: b[t//w][0]+=abs(a1)   # 트레이더가 토큰 매도
            else: b[t//w][1]+=abs(a1)      # 트레이더가 토큰 매수
        ov=sum(min(x,y) for x,y in b.values())
        print(f'  창 {w//60}분: 양쪽이 겹치는 물량 상한 {ov:,.0f} USDT ({ov/vol:.0%}) → 수수료 0.3%×2쪽 절감 상한 {ov*0.006:,.2f} USDT')
