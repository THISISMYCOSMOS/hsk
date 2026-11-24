import json, statistics as st
from simpool import load, run
H=json.load(open('hist.json'))
def blk(tid,kind,i=0): return [e for e in sorted(H[tid]['ev'],key=lambda e:e[1]) if e[0]==kind][i][1]
gaps={'WETH':(blk('20','inc',1), blk('20','dec',-1), blk('35','inc')), 'WHSK':(blk('19','inc'), blk('19','dec',-1), blk('33','inc'))}
D=43200; out={}
for n in ['WETH','WHSK']:
    start,g0,g1=gaps[n]; R=[r for r in load(n) if r[0]>=start]
    print(f'\n== {n} big LP from block {start}, gap {g0}~{g1}, {len(R)} swaps, price {R[0][1]:.5g} -> {R[-1][1]:.5g}')
    for w in [0.10,0.20]:
        res=[]; b=start
        while b+30*D<=R[-1][0]:
            if not (b<g1 and b+30*D>g0):
                win=[r for r in R if b<=r[0]<b+30*D]
                if len(win)>=20:
                    res.append((win[-1][1]/win[0][1]-1,run(win,w,'stay')[0],run(win,w,'full')[0],run(win,w,'ladder')[0],run(win,w,'ladder_re')[0],500+500*win[-1][1]/win[0][1]))
            b+=7*D
        print(f' ±{int(w*100)}% windows {len(res)}')
        out[f'{n}{w}']=res
        for name,c in [('all',lambda r:True),('down',lambda r:r[0]<-0.10),('side',lambda r:-0.10<=r[0]<=0.10),('up',lambda r:r[0]>0.10)]:
            X=[r for r in res if c(r)]
            if not X: print(f'  {name}: none'); continue
            m=lambda j: st.mean(r[j] for r in X)
            print(f'  {name:4s} n={len(X):2d} stay {m(1):7.1f} full {m(2):7.1f} ladder {m(3):7.1f} ladder+re {m(4):7.1f} 50/50 {m(5):7.1f} | ladder>stay {sum(r[3]>r[1] for r in X)}/{len(X)} ladder>full {sum(r[3]>r[2] for r in X)}/{len(X)} | worst ladder-stay {min(r[3]-r[1] for r in X):+.1f} best {max(r[3]-r[1] for r in X):+.1f}')
json.dump(out,open('simpool_out.json','w'))
