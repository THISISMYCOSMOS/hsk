import json
H=json.load(open('hist.json'))
def blk(tid,kind,i=0): return [e for e in sorted(H[tid]['ev'],key=lambda e:e[1]) if e[0]==kind][i][1]
gaps={'WETH':(blk('20','inc',1), blk('20','dec',-1), blk('35','inc')), 'WHSK':(blk('19','inc'), blk('19','dec',-1), blk('33','inc'))}
