from rpc import *
import json,sys
T={"0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67":"Swap","0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde":"Mint","0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c":"Burn","0x70935338e69775456a85ddef226c395fb668b63fa0115f5f20610b388e6ca9c0":"Collect"}
def dec(l):
    t=l['topics']; k=T.get(t[0],t[0][:10]); w=words(l['data']); b=int(l['blockNumber'],16)
    d={"ev":k,"block":b,"tx":l['transactionHash'],"li":int(l['logIndex'],16)}
    if k=="Swap":
        d.update(sender=addr(t[1]),recipient=addr(t[2]),a0=toint(w[0],1),a1=toint(w[1],1),sqrtP=toint(w[2]),L=toint(w[3]),tick=toint(w[4],1))
    elif k=="Mint":
        d.update(owner=addr(t[1]),tl=toint(t[2],1),tu=toint(t[3],1),sender=addr(w[0]),amt=toint(w[1]),a0=toint(w[2]),a1=toint(w[3]))
    elif k=="Burn":
        d.update(owner=addr(t[1]),tl=toint(t[2],1),tu=toint(t[3],1),amt=toint(w[0]),a0=toint(w[1]),a1=toint(w[2]))
    elif k=="Collect":
        d.update(owner=addr(t[1]),tl=toint(t[2],1),tu=toint(t[3],1),recipient=addr(w[0]),a0=toint(w[1]),a1=toint(w[2]))
    return d
if __name__=="__main__":
    L=[dec(l) for l in json.load(open(sys.argv[1]))]
    L.sort(key=lambda d:(d['block'],d['li']))
    json.dump(L,open(sys.argv[2],'w'))
    from collections import Counter
    print(Counter(d['ev'] for d in L))
