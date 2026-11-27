"""Mine local-only Anvil receipts from a fixed HSK fork. No external signing.
Requires anvil on PATH, compiled Foundry artifacts, eth-account + eth-abi.
Run from repo root. All writes connect only to the subprocess's loopback port.
"""

import contextlib
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from verify_deployment import verify

ROOT = Path(__file__).resolve().parents[2]
OBS = json.loads((ROOT / "data/fixtures/contract/hsk-177.json").read_text())
ADDR = OBS["addresses"]
W, U, POOL, ROUTER, QUOTER = (
    ADDR[k] for k in ("whsk", "usdt", "pool", "router", "quoter")
)
TYPES = json.loads((ROOT / "shared/typed-data/order-v1.json").read_text())["types"]
WALLETS = [Account.from_key(i.to_bytes(32, "big")) for i in (101, 102, 103)]
Q = 10**18
ZERO = "0x" + "00" * 20


def calldata(sig, types, values):
    return "0x" + (keccak(text=sig)[:4] + encode(types, values)).hex()


def artifact(name, file):
    return json.loads((ROOT / f"contracts/out/{file}.sol/{name}.json").read_text())


@contextlib.contextmanager
def node():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    anvil = shutil.which("anvil") or str(Path.home() / ".foundry/bin/anvil")
    flags = [
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--fork-url",
        OBS["rpc"],
        "--fork-block-number",
        str(OBS["blockNumber"]),
        "--chain-id",
        "31337",
        "--hardfork",
        "cancun",
        "--no-storage-caching",
        "--silent",
    ]
    with subprocess.Popen([anvil, *flags], stdout=subprocess.DEVNULL) as server:

        def rpc(method, params):
            req = urllib.request.Request(
                url,
                json.dumps(
                    dict(jsonrpc="2.0", id=1, method=method, params=params)
                ).encode(),
                {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as res:
                obj = json.load(res)
            if "error" in obj:
                raise RuntimeError((method, obj["error"]))
            return obj["result"]

        try:
            for _ in range(240):
                if server.poll() is not None:
                    raise RuntimeError("local Anvil exited")
                try:
                    client = rpc("web3_clientVersion", [])
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("local Anvil startup timed out")
            assert (
                "anvil" in client.lower() and int(rpc("eth_chainId", []), 16) == 31337
            )
            assert (
                rpc("eth_getBlockByNumber", [hex(OBS["blockNumber"]), False])["hash"]
                == OBS["blockHash"]
            )
            yield url, rpc, client
        finally:
            server.terminate()


def run(url, rpc, client):
    operator = rpc("eth_accounts", [])[0]

    def read(to, data):
        return rpc("eth_call", [dict(to=to, data=data), "latest"])

    def send(sender, to, data, success=True):
        tx = dict(data=data, **{"from": sender}, gas=hex(12_000_000))
        if to:
            tx["to"] = to
        txid = rpc("eth_sendTransaction", [tx])
        for _ in range(200):
            receipt = rpc("eth_getTransactionReceipt", [txid])
            if receipt is not None:
                break
            time.sleep(0.15)
        else:
            raise TimeoutError(f"pending local transaction {txid}")
        assert (int(receipt["status"], 16) == 1) == success, (txid, receipt["status"])
        return receipt

    def fund(token, owner, amount):
        payload = calldata("balanceOf(address)", ["address"], [owner])
        access = rpc("eth_createAccessList", [dict(to=token, data=payload), "latest"])[
            "accessList"
        ]
        slots = next(
            e["storageKeys"] for e in access if e["address"].lower() == token.lower()
        )
        for slot in slots:
            value = "0x" + amount.to_bytes(32, "big").hex()
            override = {token: {"stateDiff": {slot: value}}}
            try:
                trial = rpc(
                    "eth_call", [dict(to=token, data=payload), "latest", override]
                )
            except RuntimeError:
                continue
            if trial != "0x" and int(trial, 16) == amount:
                rpc("anvil_setStorageAt", [token, slot, value])
                assert int(read(token, payload), 16) == amount
                return
        raise ValueError("balance slot")

    rows = []
    raw = []

    def measure(label, receipt, data):
        raw.append(dict(scenario=label, calldata=data, receipt=receipt))
        rows.append(
            dict(
                scenario=label,
                gasUsed=int(receipt["gasUsed"], 16),
                calldataBytes=(len(data) - 2) // 2,
                status=int(receipt["status"], 16),
                localTxHash=receipt["transactionHash"],
            )
        )

    for acct in WALLETS:
        rpc("anvil_impersonateAccount", [acct.address])
        rpc("anvil_setBalance", [acct.address, hex(10**20)])
        fund(W, acct.address, 3000 * Q)
        fund(U, acct.address, 2000 * 10**6)

    def deploy(name):
        prod = name == "Settlement"
        art = artifact(name, "Settlement" if prod else "GuardResearch")
        args = [(W, U, POOL, ROUTER, QUOTER), operator]
        types = ["(address,address,address,address,address)", "address"]
        if prod:
            args.extend([operator, ZERO])
            types.extend(["address", "address"])
        if name == "StateMatchResearch":
            args.append(1000 * Q)
            types.append("uint256")
        receipt = send(
            operator, None, art["bytecode"]["object"] + encode(types, args).hex()
        )
        address = receipt["contractAddress"]
        for acct in WALLETS:
            for token, limit in ((W, 2000 * Q), (U, 2000 * 10**6)):
                d = calldata(
                    "approve(address,uint256)", ["address", "uint256"], [address, limit]
                )
                approval = send(acct.address, token, d)
                if prod and acct == WALLETS[0]:
                    measure(
                        "approve-" + ("WHSK" if token == W else "USDT"), approval, d
                    )
        return address, receipt

    st, dep = deploy("Settlement")
    manifest = dict(
        chainId=31337,
        blockNumber=int(dep["blockNumber"], 16),
        blockHash=dep["blockHash"],
        addresses=dict(
            **ADDR, settlement=st, admin=operator, operator=operator, feeRecipient=ZERO
        ),
    )
    code_hash = verify(url, manifest)

    def quote(sell, qty):
        name = "quoteExactInputSingle" if sell else "quoteExactOutputSingle"
        p = (W, U, qty, 3000, 0) if sell else (U, W, qty, 3000, 0)
        d = calldata(
            name + "((address,address,uint256,uint24,uint160))",
            ["(address,address,uint256,uint24,uint160)"],
            [p],
        )
        return int(read(QUOTER, d)[2:66], 16)

    def mid(qty):
        return (quote(True, qty) + quote(False, qty)) // 2

    order_type = "(" + ",".join(f["type"] for f in TYPES["Order"]) + ")"
    leg_type = "((" + order_type + ",bytes),uint256,uint256,uint256)"
    plan_type = "(bytes32,uint256," + leg_type + "[],uint256,uint256,bool)"

    def leg(acct, sell, qty, cash, verifier):
        fields = dict(
            owner=acct.address,
            recipient=acct.address,
            tokenIn=W if sell else U,
            tokenOut=U if sell else W,
            orderKind=0 if sell else 1,
            amountIn=1000 * Q if sell else 1000 * 10**6,
            amountOut=10**6 if sell else 1000 * Q,
            validAfter=0,
            deadline=2**40,
            nonce=1,
            partiallyFillable=True,
            allowDexFallback=True,
            executionPriority=1,
            maxFeeAmount=0,
            minImprovementAmount=0,
            allowedExecutor=operator,
            allowDex=True,
            immediate=True,
        )
        domain = dict(
            name="HSK Smart Execution",
            version="1",
            chainId=31337,
            verifyingContract=verifier,
        )
        msg = encode_typed_data(
            full_message=dict(
                domain=domain, types=TYPES, primaryType="Order", message=fields
            )
        )
        signature = acct.sign_message(msg).signature
        ordering = tuple(fields[f["name"]] for f in TYPES["Order"])
        return ((ordering, signature), qty, cash, 0)

    def settle(
        label,
        target=st,
        sell=True,
        parts=(1000,),
        dex=0,
        bad=False,
        fallback=False,
        revoke=False,
    ):
        snap = rpc("evm_snapshot", [])
        try:
            qty = sum(parts) * Q
            cashes = [mid(n * Q) for n in parts]
            if bad:
                cashes[0] *= 2
            legs = [leg(WALLETS[0], sell, qty, sum(cashes), target)]
            legs.extend(
                leg(acct, not sell, n * Q, c, target)
                for acct, n, c in zip(WALLETS[1:], parts, cashes)
            )
            if revoke:
                d = calldata(
                    "approve(address,uint256)", ["address", "uint256"], [target, 0]
                )
                send(WALLETS[1].address, U if sell else W, d)
            p = (
                bytes.fromhex("01" * 32),
                2**40,
                legs,
                dex * Q,
                (1 if sell else dex * 10**6) if dex else 0,
                fallback,
            )
            d = calldata("settle(" + plan_type + ")", [plan_type], [p])
            receipt = send(operator, target, d, not revoke)
            if not revoke:
                result = int(receipt["logs"][-1]["data"], 16)
                assert result == (2 if fallback and bad else 0 if bad else 1), (
                    label,
                    result,
                )
            measure(label, receipt, d)
        finally:
            assert rpc("evm_revert", [snap])

    for label, kwargs in [
        ("direct", {}),
        ("hybrid-sell", dict(parts=(600,), dex=400)),
        ("hybrid-buy", dict(sell=False, parts=(600,), dex=400)),
        ("multi", dict(parts=(300, 500))),
        ("no-trade", dict(bad=True)),
        ("fallback", dict(bad=True, fallback=True)),
        ("revert", dict(revoke=True)),
    ]:
        settle(label, **kwargs)
    for variant in ("SingleBandResearch", "StateMatchResearch", "SignedOnlyResearch"):
        target, _ = deploy(variant)
        settle(variant, target)
    snap = rpc("evm_snapshot", [])
    for sell in (True, False):
        sender = WALLETS[0 if sell else 1].address
        d = calldata(
            "approve(address,uint256)",
            ["address", "uint256"],
            [ROUTER, 1000 * Q if sell else 1000 * 10**6],
        )
        send(sender, W if sell else U, d)
        function = "exactInputSingle" if sell else "exactOutputSingle"
        params = (
            W if sell else U,
            U if sell else W,
            3000,
            sender,
            1000 * Q,
            quote(sell, 1000 * Q),
            0,
        )
        arg = "(address,address,uint24,address,uint256,uint256,uint160)"
        d = calldata(function + "(" + arg + ")", [arg], [params])
        measure(
            "sequential-dex-" + ("sell" if sell else "buy"), send(sender, ROUTER, d), d
        )
    assert rpc("evm_revert", [snap])
    return dict(
        evidence="FORK_SIMULATION",
        upstreamChainId=177,
        anvilChainId=31337,
        upstreamBlock=OBS["blockNumber"],
        upstreamHash=OBS["blockHash"],
        hardfork="cancun",
        client=client,
        verifiedRuntimeHash=code_hash,
        rows=rows,
        raw=raw,
    )


if __name__ == "__main__":
    with node() as environment:
        data = run(*environment)
    raw = data.pop("raw")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(
            json.dumps(dict(evidence="FORK_SIMULATION", transactions=raw), indent=2)
            + "\n"
        )
    out = json.dumps(data, indent=2) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(out)
    else:
        print(out)
