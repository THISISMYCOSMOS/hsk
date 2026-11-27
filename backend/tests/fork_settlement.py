"""Isolated Anvil fork test using Agent C's compiled ABI and HSKSwap. No external signer."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3, IPCProvider
from fastapi.testclient import TestClient
from backend.app.api.main import create_app
from backend.app.execution.fork import ForkExecution
from backend.app.orderbook.signatures import typed_data
from backend.app.economics.bounds import CostBreakdown
from backend.app.execution.journal import Journal
from backend.app.execution.settlement import abi_order, chain_message, project
from backend.app.optimizer.search import Entry, compare
from backend.app.orderbook.signatures import recover
from backend.app.quote_engine.market import MarketSnapshot
from backend.app.schemas.orders import Order, USDT, WHSK

BLOCK = 30592078
HASH = "0x8e9ec7357cca666d04911b91bb3f5cf0292a7b4e5150a4e6febe30daa1280bda"
MARKET = list(
    map(
        Web3.to_checksum_address,
        (
            WHSK,
            USDT,
            "0x4ff515761864e7838b0adb8b5b2b8b7a068905dc",
            "0x2c16f75b95cf1390c328ab70e2cee7f4b80bd8f3",
            "0x603f70466fddbe3f238220b9a74fff419a2bbfdd",
        ),
    )
)
UNIT = 10**18


@contextmanager
def fork(root, anvil, url):
    ipc = str(root / "node.ipc")
    command = [
        anvil,
        "--quiet",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--ipc",
        ipc,
        "--steps-tracing",
        "--mnemonic-random",
        "12",
        "--chain-id",
        "31337",
        "--fork-url",
        url,
        "--fork-block-number",
        str(BLOCK),
        "--fork-header",
        "User-Agent: HSK-Smart-Execution/1",
        "--fork-state-by-number",
    ]
    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(300):
            if proc.poll() is not None:
                raise RuntimeError("Anvil fork startup failed: " + proc.stderr.read().decode()[-500:])
            if Path(ipc).exists():
                break
            time.sleep(0.1)
        w3 = Web3(IPCProvider(ipc, timeout=90))
        assert w3.eth.chain_id == 31337 and w3.to_hex(w3.eth.get_block(BLOCK).hash) == HASH
        yield w3
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def rpc(w3, method, args):
    reply = w3.provider.make_request(method, args)
    if "error" in reply:
        raise RuntimeError(str(reply["error"]))
    return reply["result"]


def fund_token(w3, token, owner, amount):
    # Discover balance mapping through the locally traced ERC20 read. Change only fixture wallets.
    call = {"to": token.address, "data": token.encode_abi("balanceOf", args=[owner])}
    trace = rpc(w3, "debug_traceCall", [call, "latest", {}])
    slot = next(step["stack"][-1] for step in reversed(trace["structLogs"]) if step["op"] == "SLOAD")
    rpc(
        w3,
        "anvil_setStorageAt",
        [token.address, "0x" + slot.removeprefix("0x").zfill(64), "0x" + format(amount, "064x")],
    )
    assert token.functions.balanceOf(owner).call() == amount


def run(w3, compiled, tmp):
    def artifact(folder, name):
        return json.loads((compiled / (folder + ".sol") / (name + ".json")).read_text())

    s = artifact("Settlement", "Settlement")
    token_abi = artifact("IHSKSwap", "IERC20")["abi"]
    quoter = w3.eth.contract(address=MARKET[4], abi=artifact("IHSKSwap", "IQuoter")["abi"])
    base, stable = [w3.eth.contract(address=a, abi=token_abi) for a in MARKET[:2]]
    operator = Account.create()
    rpc(w3, "anvil_setBalance", [operator.address, hex(10**21)])
    deployer = w3.eth.accounts[0]
    factory = w3.eth.contract(abi=s["abi"], bytecode=s["bytecode"]["object"])
    h = factory.constructor(MARKET, deployer, operator.address, deployer).transact(
        {"from": deployer, "gas": 8_000_000}
    )
    deploy = w3.eth.wait_for_transaction_receipt(h)
    assert deploy.status == 1
    contract = w3.eth.contract(address=deploy.contractAddress, abi=s["abi"])
    actors = [Account.create() for _ in range(3)]
    for i, actor in enumerate(actors):
        token = stable if i else base
        fund_token(w3, token, actor.address, 1000 * UNIT if not i else 100_000_000)
        rpc(w3, "anvil_setBalance", [actor.address, hex(10**20)])
        rpc(w3, "anvil_impersonateAccount", [actor.address])
        tx = token.functions.approve(contract.address, 2**256 - 1).transact(
            {"from": actor.address, "gas": 150_000}
        )
        assert w3.eth.wait_for_transaction_receipt(tx).status == 1
        rpc(w3, "anvil_stopImpersonatingAccount", [actor.address])

    head = w3.eth.get_block("latest")

    def quote(sell, qty):
        params = (MARKET[0], MARKET[1], qty, 3000, 0) if sell else (MARKET[1], MARKET[0], qty, 3000, 0)
        f = quoter.functions.quoteExactInputSingle if sell else quoter.functions.quoteExactOutputSingle
        return f(params).call(block_identifier=head.number)[0]

    market = MarketSnapshot(
        w3.to_hex(head.hash),
        head.number,
        "FORK_SIMULATION",
        quote,
        lambda *_: CostBreakdown(0, 30, 120, 30, 5, 0, 0, 0, 10),
    )
    book, signed = [], {}
    for i, (actor, size) in enumerate(zip(actors, (1000, 600, 400))):
        sell = i == 0
        o = Order(
            maker=actor.address,
            tokenIn=MARKET[0 if sell else 1],
            tokenOut=MARKET[1 if sell else 0],
            kind="EXACT_IN" if sell else "EXACT_OUT",
            fixedAmount=str(size * UNIT),
            limitAmount=str((79_000 if sell else 84_000) * size),
            nonce="1",
            expiry=str(max(head.timestamp, int(time.time())) + 1800),
            timing="LIMIT",
            allowPartial=False,
            allowDex=False,
            allowFallback=False,
            priority="SAVINGS",
            maxCost="50000",
            minSaving="1",
        )
        body = project(
            o, recipient=o.maker, operator=operator.address, valid_after=0, max_service_fee=int(o.maxCost)
        )
        payload = chain_message(contract, 31337, body)
        signature = w3.to_hex(actor.sign_message(encode_typed_data(full_message=payload)).signature)
        digest = recover(payload, signature, o.maker)
        assert w3.to_hex(contract.functions.orderHash(abi_order(contract, body)).call()) == digest
        book.append(Entry(digest, o, int(o.fixedAmount), i))
        signed[digest] = body, signature

    result = compare(book[0], book[1:], market, head.timestamp)
    assert result["selected"]["kind"] == "MULTI_ORDER_MATCH"
    service = ForkExecution(
        w3,
        contract,
        operator,
        Journal(tmp / "journal.db"),
        gas_limit=2_000_000,
        fee_cap_wei=w3.eth.gas_price * 2,
        l1_upper_wei=10**16,
        budget_wei=10**20,
    )
    app = create_app(
        "sqlite:///" + str(tmp / "book.db"), "FORK", market=lambda: market, fork_execution=service
    )
    # Drop the transport reply once, after Anvil accepted the signed transaction.
    send = w3.eth.send_raw_transaction
    sends = []

    def lose_reply(raw):
        sends.append(send(raw))
        raise TimeoutError("injected lost send reply")

    w3.eth.send_raw_transaction = lose_reply
    with TestClient(app) as api:
        for i in (1, 2, 0):
            entry, actor = book[i], actors[i]
            reply = api.post("/orders/settlement-typed-data", json=entry.order.model_dump())
            assert reply.status_code == 200, reply.text
            onchain = reply.json()
            fixture_signature = w3.to_hex(
                actor.sign_message(encode_typed_data(full_message=onchain)).signature
            )
            policy_sig = w3.to_hex(
                actor.sign_message(encode_typed_data(full_message=typed_data(entry.order))).signature
            )
            posted = api.post(
                "/orders",
                json=dict(
                    order=entry.order.model_dump(),
                    signature=policy_sig,
                    settlementSignature=fixture_signature,
                ),
            )
            assert posted.status_code == 200, posted.text
        for _ in range(180):
            rows = api.get("/executions").json()
            if rows and rows[0]["status"] == "FORK_CONFIRMED":
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(str(api.get("/agent/events").json()[-10:]))
        assert len(rows) == 1
        view = api.get(f"/executions/{rows[0]['id']}/receipt").json()
        digest = view["transactionHash"]
        receipt = w3.eth.get_transaction_receipt(digest)
        actual = {
            p["settlementDigest"]: {
                k: p[k] for k in ("spent", "received", "feeUSDT", "cumulativeWHSK", "benchmarkUSDT")
            }
            for p in view["participants"]
        }
        for entry in book:
            assert int(actual[entry.id]["cumulativeWHSK"]) == entry.remaining
            assert contract.functions.filledAmount(entry.id).call() == entry.remaining
        assert all(o["status"] == "FILLED" and o["remaining"] == "0" for o in api.get("/orders").json())
        from sqlalchemy import select
        from backend.app.models import tables as db

        with app.state.worker.store.engine.connect() as conn:
            estimate = conn.scalar(select(db.jobs.c.estimate))
    assert len(sends) == 1
    return dict(
        lostReplyRecovered=True,
        settlementBroadcasts=len(sends),
        evidence="FORK_SIMULATION",
        forkBlock=str(BLOCK),
        forkHash=HASH,
        chainId="31337",
        settlementCodeHash=w3.to_hex(w3.keccak(w3.eth.get_code(contract.address))),
        forkTxHash=digest,
        market="HSKSwap single pool",
        orderCount=len(book),
        route="MULTI_ORDER_MATCH",
        gasEstimate=str(estimate),
        gasUsed=str(receipt.gasUsed),
        fills=actual,
        userCostBasis="SYNTHETIC upper bounds",
        operatorProfit=None,
        orderOrigin="ephemeral signed test orders",
        confirmedMainnetReceipt=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--compiled", type=Path, required=True)
    p.add_argument("--anvil", default=shutil.which("anvil"))
    p.add_argument("--rpc", default="https://mainnet.hsk.xyz")
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="hskb-", dir="/tmp") as directory:
        tmp = Path(directory)
        with fork(tmp, args.anvil, args.rpc) as w3:
            print(json.dumps(run(w3, args.compiled, tmp), indent=2))
