"""Pin code, deployed interfaces and calls to an observed block. Re-run with --block."""

import argparse
import hashlib
import json
import zipfile
from backend.app.blockchain.rpc import (
    A,
    CONFIG,
    ROOT,
    RPC,
    SWAP,
    addr_word,
    call,
    fetch,
    logs,
    utc,
)
from backend.app.market_data.provider import MarketData
from backtest.collect import save

SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


def probe(block):
    rpc = RPC()
    provider = MarketData(rpc)
    header = rpc.block(block)
    n = header["number"]
    archive = zipfile.ZipFile(ROOT / "backtests/HSK_Session2_Quotes.zip")
    expected = json.loads(archive.read("quotes.json"))
    checks = {}
    for row in expected["quotes"]:
        fn = (
            provider.get_dex_quote_exact_in
            if row["kind"] == "exact_input"
            else provider.get_dex_quote_exact_out
        )
        qty = row["amount_in_raw" if row["kind"] == "exact_input" else "amount_out_raw"]
        obs = fn(row["token_in"], row["token_out"], int(qty), expected["block"])
        checks[row["id"]] = dict(
            response=obs,
            agrees=obs["block_hash"] == expected["block_hash"]
            and obs["data"] is not None
            and all(
                obs["data"][k] == row[f"{k}_raw"] for k in ("amount_in", "amount_out")
            )
            and obs["data"]["sqrt_price_after_x96"] == row["sqrt_price_after_x96"],
        )
    save(ROOT / "reports/economics/reference_quotes.json", checks)
    net = dict(
        version="1.0",
        queried_at=utc(),
        chain_id=int(rpc.one("eth_chainId", []), 16),
        latest=provider.get_chain_state(),
        verified_at=block,
        block_hash=header["hash"],
        mean_interval_seconds=(
            int(header["timestamp"], 16) - int(rpc.block(block - 1000)["timestamp"], 16)
        )
        / 1000,
        interval_blocks=1000,
        log_probe=rpc.one(*logs(A["pool"], SWAP, block, block)),
        fee_probe=provider.get_execution_fee_estimate(
            {"to": A["WHSK"], "data": "0x313ce567"}
        ),
        historical_samples={},
    )
    for b in [0, 1, 1000000, expected["block"], block]:
        try:
            h = rpc.block(b)
            net["historical_samples"][b] = dict(
                hash=h["hash"],
                whsk_code_bytes=(len(rpc.one("eth_getCode", [A["WHSK"], hex(b)])) - 2)
                // 2,
            )
        except (ValueError, OSError) as e:
            net["historical_samples"][b] = dict(error=str(e))
    save(ROOT / "config/network/probe.json", net)
    calls = {
        "WHSK": [("decimals", "313ce567"), ("symbol", "95d89b41")],
        "USDT": [("decimals", "313ce567"), ("symbol", "95d89b41")],
        "pool": [
            ("token0", "0dfe1681"),
            ("token1", "d21220a7"),
            ("fee", "ddca3f43"),
            ("liquidity", "1a686502"),
            ("slot0", "3850c7bd"),
        ],
        "router": [("factory", "c45a0155")],
        "quoter": [
            ("factory", "c45a0155"),
            (
                "quoteExactInputSingle",
                "c6a5026a",
                A["WHSK"],
                A["USDT"],
                10**18,
                3000,
                0,
            ),
        ],
        "factory": [("getPool", "1698ee82", A["WHSK"], A["USDT"], 3000)],
        "oracle": [("version", "54fd4d50"), ("l1BaseFee", "519b4bd3")],
    }
    registry = dict(
        version="1.0",
        block_number=block,
        block_hash=header["hash"],
        rpc=rpc.url,
        queried_at=utc(),
        contracts={},
    )
    for name, addr in A.items():
        code = rpc.one("eth_getCode", [addr, n])
        item = registry["contracts"][name] = dict(
            address=addr,
            source=CONFIG["token_source"]
            if name in ("WHSK", "USDT")
            else "https://specs.optimism.io/protocol/predeploys.html"
            if name == "oracle"
            else CONFIG["dex_address_source"],
            bytecode_bytes=(len(code) - 2) // 2,
            code_sha256=hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
            calls={},
        )
        for label, sel, *args in calls[name]:
            try:
                c = call(addr, sel, *args, block=n)
                item["calls"][label] = dict(
                    calldata=c[1][0]["data"], response=rpc.one(*c)
                )
            except (ValueError, OSError) as e:
                item["calls"][label] = dict(error=str(e))
        item["read_verified"] = bool(item["bytecode_bytes"]) and all(
            "response" in v and v["response"] != "0x" for v in item["calls"].values()
        )
        try:
            impl = addr_word(int(rpc.one("eth_getStorageAt", [addr, SLOT, n]), 16))
            target = addr if int(impl, 16) == 0 else impl
            source = f"{CONFIG['explorer']}/api/v2/smart-contracts/{target}"
            item.update(abi_source=source, abi_address=target)
            doc = fetch(source)
            if not doc.get("abi") or not doc.get("is_verified"):
                raise ValueError("verified ABI unavailable from explorer")
            path = ROOT / f"config/network/abi/{name}.json"
            save(path, doc["abi"])
            item.update(
                abi_file=str(path.relative_to(ROOT)),
                abi_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        except (ValueError, OSError) as e:
            item["abi_error"] = str(e)
        save(ROOT / "config/verified_contracts.json", registry)
    if rpc.block(block)["hash"] != header["hash"]:
        raise ValueError("block changed")
    print(
        {
            k: (v["read_verified"], "abi_file" in v)
            for k, v in registry["contracts"].items()
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", required=True, type=int)
    probe(parser.parse_args().block)
