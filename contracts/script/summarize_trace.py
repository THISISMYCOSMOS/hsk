"""Extract measured calls from forge test --match-contract ForkTest -vvvvv --json."""

import json
import sys
from pathlib import Path
from eth_abi import decode
from eth_utils import keccak

SAMPLE = "0x" + keccak(text="Sample(string,uint256,uint256)").hex()
QUOTES = "0x" + keccak(text="Quotes(string,uint256,uint256)").hex()


def summarize(suite):
    rows = []
    comparisons = []
    for name, result in suite["test_results"].items():
        if result["status"] != "Success":
            raise ValueError(name)
        arena = next(
            trace["arena"] for kind, trace in result["traces"] if kind == "Execution"
        )
        # The log follows its measured outer call. Snapshots may erase logs from
        # receipts but the execution arena preserves the complete call ordering.
        root = arena[0]
        measured = None
        for action in root["ordering"]:
            kind, index = next(iter(action.items()))
            if kind == "Call":
                node = arena[root["children"][index]]
                t = node["trace"]
                if t["data"][:10] in ("0xe6bed115", "0x04e45aaf", "0x5023b4df"):
                    measured = node
                continue
            if kind != "Log":
                continue
            event = root["logs"][index]
            event = event.get("raw_log", event)
            topic = event["topics"][0]
            if topic not in (SAMPLE, QUOTES):
                continue
            label, a, b = decode(
                ["string", "uint256", "uint256"], bytes.fromhex(event["data"][2:])
            )
            if topic == QUOTES:
                comparisons.append(
                    dict(test=name, scenario=label, beforeRaw=str(a), afterRaw=str(b))
                )
                continue
            if measured is None:
                raise ValueError(f"missing call {label}")
            nodes = [measured]
            for entry in nodes:
                nodes.extend(arena[child] for child in entry["children"])
            t = measured["trace"]
            assert (len(t["data"]) - 2) // 2 == b
            rows.append(
                dict(
                    test=name,
                    scenario=label,
                    callerMeasuredGas=a,
                    calleeTraceGas=t["gas_used"],
                    calldataBytes=b,
                    nestedCalls=len(nodes) - 1,
                    sstoreOpcodes=sum(
                        step["op"] == 0x55
                        for entry in nodes
                        for step in entry["trace"]["steps"]
                    ),
                    returnData=t["output"],
                    success=t["success"],
                )
            )
            measured = None
    return dict(
        evidence="FORK_SIMULATION",
        chainId=177,
        blockNumber=30592078,
        rows=rows,
        comparisons=comparisons,
    )


if __name__ == "__main__":
    suite = next(iter(json.loads(Path(sys.argv[1]).read_text()).values()))
    print(json.dumps(summarize(suite), indent=2))
