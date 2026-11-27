"""Read Agent A's RPC only while orders are open. Persist observations with outbox events."""

import asyncio
import time
from sqlalchemy import select
from eth_utils import keccak
from ..models import tables as db

POOL = "0x4ff515761864e7838b0adb8b5b2b8b7a068905dc"
TOPICS = {
    "0x" + keccak(text=sig).hex(): kind
    for sig, kind in [
        ("Swap(address,address,int256,int256,uint160,uint128,int24)", "POOL_SWAP"),
        ("Mint(address,address,int24,int24,uint128,uint256,uint256)", "POOL_LIQUIDITY_CHANGED"),
        ("Burn(address,int24,int24,uint128,uint256,uint256)", "POOL_LIQUIDITY_CHANGED"),
    ]
}


class ChainMonitor:
    def __init__(self, worker, provider_factory, spender=None):
        self.worker, self.factory, self.spender = worker, provider_factory, spender
        self.provider = None

    def poll(self):
        store = self.worker.store
        with store.engine.connect() as conn:
            active = store.active(conn, int(time.time()))
            if not active:
                return False
            previous = conn.execute(select(db.cursor)).mappings().first()
        if self.provider is None:
            self.provider = self.factory()
        rpc = self.provider.rpc
        finalized = rpc.block("finalized")
        height = int(finalized["number"], 16)
        start = previous["height"] + 1 if previous else height
        if previous and rpc.block(previous["height"])["hash"] != previous["hash"]:
            raise ValueError("FINALIZED_CURSOR_REORG")
        if start > height:
            return False
        end = min(start + 4999, height)
        block = rpc.block(end)["hash"]
        logs = rpc.one(
            "eth_getLogs", [dict(address=POOL, topics=[list(TOPICS)], fromBlock=hex(start), toBlock=hex(end))]
        )
        observations = {}
        changes = []

        def observe(label, value, kind):
            observations[label] = value
            if previous and previous["state"].get(label) != value:
                changes.append((kind, {"field": label, "blockHash": block}, f"{block}:{label}"))

        observe("gasPriceWei", rpc.one("eth_gasPrice", []), "GAS_COST_CHANGED")
        for owner, token in sorted({(e.order.maker, e.order.tokenIn) for e in active}):
            for method, kind, params in [
                ("get_wallet_balance", "BALANCE_CHANGED", [owner, token]),
                ("get_allowance", "ALLOWANCE_CHANGED", [owner, token, self.spender]),
            ]:
                if method == "get_allowance" and not self.spender:
                    continue
                row = getattr(self.provider, method)(*params, end)
                if row.get("error") or row["block_hash"] != block:
                    raise ValueError("UNVERIFIED_WALLET_STATE")
                observe(":".join([kind, *params]), row["data"], kind)
        last_index = -1
        for log in sorted(logs, key=lambda row: (int(row["blockNumber"], 16), int(row["logIndex"], 16))):
            if log.get("removed") or log["address"].lower() != POOL:
                raise ValueError("REMOVED_OR_UNEXPECTED_LOG")
            index = int(log["logIndex"], 16)
            if int(log["blockNumber"], 16) == end:
                last_index = index
            changes.append(
                (
                    TOPICS[log["topics"][0]],
                    dict(blockHash=log["blockHash"], logIndex=str(index)),
                    f"{log['blockHash']}:{index}",
                )
            )
        if rpc.block(end)["hash"] != block:
            raise ValueError("BLOCK_REORG")
        with store.write() as conn:
            current = conn.execute(select(db.cursor)).mappings().first()
            if (current and current["hash"]) != (previous and previous["hash"]):
                return False
            for kind, payload, key in changes:
                store.emit(conn, kind, payload, key=key, work=True)
            values = dict(height=end, hash=block, log_index=last_index, state=observations)
            if current:
                conn.execute(db.cursor.update().values(**values))
            else:
                conn.execute(db.cursor.insert().values(id=1, **values))
        return bool(changes)

    async def run(self):
        delay = 6
        failed = False
        while True:
            try:
                if await asyncio.to_thread(self.poll):
                    self.worker.wakeup.set()
                delay, failed = 6, False
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                self.provider = None
                if not failed:
                    with self.worker.store.write() as conn:
                        self.worker.store.emit(
                            conn, "RPC_UNAVAILABLE", {"source": "monitor", "reason": type(exc).__name__}
                        )
                delay, failed = min(60, delay * 2), True
            await asyncio.sleep(delay)
