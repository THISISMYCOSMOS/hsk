from rpc import *
import json, time
def getlogs(address, topic0, frm=0, to='latest'):
    out=[]; page_from=frm
    while True:
        r=bs(f'/api?module=logs&action=getLogs&address={address}&topic0={topic0}&fromBlock={page_from}&toBlock={to}')
        items=r.get('result') or []
        if not isinstance(items,list): print('err',r); break
        out+=items
        if len(items)<1000: break
        last=int(items[-1]['blockNumber'],16)
        # drop items of last block to avoid dup, refetch from last block
        out=[x for x in out if int(x['blockNumber'],16)<last]
        page_from=last
    return out
