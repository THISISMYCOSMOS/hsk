# 전 구간 LP(운영 주소와 같은 형태)에 분할 회수를 적용했을 때의 효과. 수수료는 제외.
import pandas as pd, numpy as np, math
import bt
P, T = bt.P, bt.T
def run(i0, days, steps, sell=False, C=1000.0):
    p0 = P[i0]; L = C / (2 * math.sqrt(p0)); x0, y0 = L / math.sqrt(p0), L * math.sqrt(p0)
    tend = T[i0] + np.timedelta64(days, 'D'); Lr = L; wx = wy = 0; done = set(); i = i0
    while i < len(P) - 1 and T[i] < tend:
        i += 1; p = P[i]
        for k, (lvl, frac) in enumerate(steps):
            if k not in done and p <= p0 * (1 - lvl):
                d = min(L * frac, Lr); ax, ay = d / math.sqrt(p), d * math.sqrt(p); Lr -= d; done.add(k)
                if sell: wy += ay + ax * p * 0.995
                else: wx += ax; wy += ay
    pe = P[i]; val = Lr * 2 * math.sqrt(pe) + wx * pe + wy; hodl = x0 * pe + y0
    return val / C - 1, val / hodl - 1
starts = []; t = pd.Timestamp('2026-05-02')
while t < pd.Timestamp('2026-10-20'):
    starts.append(np.searchsorted(bt.sw.ts.values, np.datetime64(t))); t += pd.Timedelta(days=3)
S = {'hold': [], 'split(-5/-10/-15%: 20/30/50%)': [(0.05, .2), (0.10, .3), (0.15, .5)], 'allout -10%': [(0.10, 1.0)]}
for n, st in S.items():
    for sell in [False, True]:
        if n == 'hold' and sell: continue
        r = np.array([run(i, 30, st, sell) for i in starts])
        print("%-32s sell=%s vsUSDT mean %.4f worst %.4f | vsHODL mean %.4f worst %.4f" % (n, sell, r[:, 0].mean(), r[:, 0].min(), r[:, 1].mean(), r[:, 1].min()))
