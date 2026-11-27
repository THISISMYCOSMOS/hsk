"""Disposable fork service for browser integration. Only the child Anvil receives writes."""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from paths import ROOT,role

def main():
    b,c=role("B"),role("C")
    sys.path.insert(0,str(b))
    import uvicorn
    from eth_account import Account
    from web3 import Web3, IPCProvider
    from backend.tests.fork_settlement import MARKET, BLOCK, HASH, rpc, fund_token
    from backend.app.api.main import create_app
    from backend.app.execution.fork import ForkExecution
    from backend.app.execution.journal import Journal
    from backend.app.quote_engine.market import MarketSnapshot
    from backend.app.economics.bounds import CostBreakdown
    with tempfile.TemporaryDirectory(prefix="hsk-d-",dir="/tmp") as folder:
        temp=Path(folder)
        shutil.copytree(c/"contracts",temp/"contracts",ignore=shutil.ignore_patterns("out","cache","broadcast"))
        forge=shutil.which("forge") or str(Path.home()/".foundry/bin/forge")
        subprocess.run([forge,"build","--offline","--quiet"],cwd=temp/"contracts",check=True)
        out=temp/"contracts/out"
        ipc=str(temp/"fork.ipc")
        anvil=shutil.which("anvil") or str(Path.home()/".foundry/bin/anvil")
        node=subprocess.Popen([anvil,"--silent","--host","127.0.0.1","--port","8754","--ipc",ipc,
                               "--mnemonic-random","12","--accounts","4","--chain-id","31337","--steps-tracing",
                               "--fork-url",os.getenv("HSK_FORK_RPC","https://mainnet.hsk.xyz"),
                               "--fork-block-number",str(BLOCK),"--fork-header","User-Agent: HSK-Smart-Execution/1"],
                              stdout=subprocess.DEVNULL)
        ui=None
        try:
            for _ in range(300):
                if node.poll() is not None: raise RuntimeError("Anvil startup failed")
                if Path(ipc).exists():break
                time.sleep(.1)
            w3=Web3(IPCProvider(ipc,timeout=90))
            if w3.eth.chain_id!=31337 or w3.to_hex(w3.eth.get_block(BLOCK).hash)!=HASH or "anvil" not in w3.client_version.lower():
                raise RuntimeError("unexpected fork")
            def artifact(file,contract):
                return json.loads((out/(file+".sol")/(contract+".json")).read_text())
            abi=artifact("Settlement","Settlement")
            seller,buyer,second,deployer=w3.eth.accounts[:4]
            operator=Account.create()
            rpc(w3,"anvil_setBalance",[operator.address,hex(10**20)])
            factory=w3.eth.contract(abi=abi["abi"],bytecode=abi["bytecode"]["object"])
            init=factory.constructor(MARKET,deployer,operator.address,deployer).transact({"from":deployer,"gas":8_000_000})
            rec=w3.eth.wait_for_transaction_receipt(init)
            if rec.status!=1:raise RuntimeError("local deployment reverted")
            contract=w3.eth.contract(address=rec.contractAddress,abi=abi["abi"])
            for idx,user in enumerate([seller,buyer,second]):
                tok=w3.eth.contract(address=MARKET[0 if idx==0 else 1],abi=artifact("IHSKSwap","IERC20")["abi"])
                fund_token(w3,tok,user,2000*10**18 if idx==0 else 200*10**6)
            quoter=w3.eth.contract(address=MARKET[4],abi=artifact("IHSKSwap","IQuoter")["abi"])
            def market():
                head=w3.eth.get_block("latest")
                def quote(sell,qty):
                    src,dst=(MARKET[0],MARKET[1]) if sell else (MARKET[1],MARKET[0])
                    fn=quoter.functions.quoteExactInputSingle if sell else quoter.functions.quoteExactOutputSingle
                    return fn((src,dst,qty,3000,0)).call(block_identifier=head.number)[0]
                return MarketSnapshot(w3.to_hex(head.hash),head.number,"FORK_SIMULATION",quote,
                                      lambda *_:CostBreakdown(0,30,120,30,5,0,0,0,10))
            service=ForkExecution(w3,contract,operator,Journal(temp/"journal.db"),gas_limit=2_000_000,
                                  fee_cap_wei=w3.eth.gas_price*2,l1_upper_wei=10**16,budget_wei=10**20)
            app=create_app("sqlite:///"+str(temp/"orders.db"),"FORK",market=market,fork_execution=service)
            @app.get("/integration/fork")
            def manifest():
                return dict(chainId=31337,anchor=HASH,contract=contract.address,operator=operator.address,
                            codeHash=w3.to_hex(w3.keccak(w3.eth.get_code(contract.address))),
                            wallets=[seller,buyer,second],costEvidence="SYNTHETIC")
            ui=subprocess.Popen(["npm","run","dev","--","--port","5189"],cwd=ROOT/"frontend",start_new_session=True,
                                env={**os.environ,"AGENT_B_API":"http://127.0.0.1:8767"})
            print("Fork UI http://127.0.0.1:5189 · wallet RPC http://127.0.0.1:8754 · disposable fixture orders",flush=True)
            uvicorn.run(app,host="127.0.0.1",port=8767,log_level="warning")
        finally:
            if ui and ui.poll() is None:
                os.killpg(ui.pid,signal.SIGTERM)
                ui.wait(timeout=10)
            node.terminate()
            node.wait(timeout=10)
if __name__=="__main__":
    main()
