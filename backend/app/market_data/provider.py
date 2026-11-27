"""Agent A read-only provider v1.0. Amounts at the JSON boundary are decimal strings."""

from collections import OrderedDict
from copy import deepcopy
import time
from backend.app.blockchain.rpc import (
    A,
    CONFIG,
    RPC,
    SWAP,
    address,
    addr_word,
    call,
    logs,
    signed,
    utc,
    words,
)


MARKET_TOPICS = [
    SWAP,
    "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde",  # Mint
    "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c",  # Burn
    "0x98636036cb66a9c19a37435efc1e90142190214e8abeb821bdba3f2990dd4c95",
]  # Initialize


class MarketData:
    def __init__(self, rpc=None):
        self.rpc = rpc if rpc is not None else RPC()
        self.cache = OrderedDict()

    def _read(self, ref, fn, key=None):
        result = dict(
            version="1.0",
            chain_id=CONFIG["chain_id"],
            source=self.rpc.url,
            queried_at=utc(),
            block_number=None,
            block_hash=None,
            error=None,
            data=None,
            evidence="UNVERIFIED",
        )
        try:
            header = self.rpc.block(ref)
            n, h = header["number"], header["hash"]
            result.update(block_number=int(n, 16), block_hash=h)
            cache_key = (h, key)
            if key is not None and cache_key in self.cache:
                return deepcopy(self.cache[cache_key])
            value = fn(n, header)
            if self.rpc.block(int(n, 16))["hash"] != h:
                raise ValueError("block reorganized during read")
            result.update(evidence="OBSERVED_MAINNET", data=value)
            if key is not None:
                self.cache[cache_key] = deepcopy(result)
                if len(self.cache) > 512:
                    self.cache.popitem(last=False)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            result["error"] = str(exc)
        return result

    def get_chain_state(self):
        return self._read(
            "latest",
            lambda n, h: dict(
                timestamp=int(h["timestamp"], 16), parent_hash=h["parentHash"]
            ),
        )

    def get_pool_state(self, pool_address, block_ref="latest"):
        def read(n, h):
            results = self.rpc.batch(
                [
                    call(pool_address, selector, block=n)
                    for selector in (
                        "0dfe1681",
                        "d21220a7",
                        "ddca3f43",
                        "1a686502",
                        "3850c7bd",
                        "c45a0155",
                    )
                ]
            )
            t0, t1, fee, liq, slot, factory = map(words, results)
            if addr_word(factory[0]) != A["factory"]:
                raise ValueError("unexpected pool factory")
            resolved = self.rpc.one(
                *call(
                    A["factory"],
                    "1698ee82",
                    addr_word(t0[0]),
                    addr_word(t1[0]),
                    fee[0],
                    block=n,
                )
            )
            if addr_word(words(resolved)[0]) != address(pool_address):
                raise ValueError("factory does not resolve pool")
            return dict(
                pool=address(pool_address),
                token0=addr_word(t0[0]),
                token1=addr_word(t1[0]),
                fee=fee[0],
                active_liquidity=str(liq[0]),
                sqrt_price_x96=str(slot[0]),
                tick=signed(slot[1]),
            )

        return self._read(block_ref, read, ("pool", pool_address))

    def get_token_metadata(self, token_address, block_ref="latest"):
        def read(n, h):
            decimals, symbol = self.rpc.batch(
                [call(token_address, s, block=n) for s in ("313ce567", "95d89b41")]
            )
            raw = bytes.fromhex(symbol[2:])
            if len(raw) == 32:
                name = raw.rstrip(b"\x00").decode()
            else:
                offset = int.from_bytes(raw[:32], "big")
                size = int.from_bytes(raw[offset : offset + 32], "big")
                if offset != 32 or offset + 32 + size > len(raw):
                    raise ValueError("malformed ERC20 symbol")
                name = raw[offset + 32 : offset + 32 + size].decode()
            return dict(
                address=address(token_address), symbol=name, decimals=words(decimals)[0]
            )

        return self._read(block_ref, read, ("metadata", token_address))

    def _quote(self, token_in, token_out, amount, ref, exact_out):
        def read(n, h):
            if amount <= 0 or {address(token_in), address(token_out)} != {
                A["WHSK"],
                A["USDT"],
            }:
                raise ValueError("unsupported pair or quantity")
            sel = "bd21704a" if exact_out else "c6a5026a"
            fee = words(self.rpc.one(*call(A["pool"], "ddca3f43", block=n)))[0]
            pool = addr_word(
                words(
                    self.rpc.one(
                        *call(
                            A["factory"], "1698ee82", token_in, token_out, fee, block=n
                        )
                    )
                )[0]
            )
            if pool != A["pool"]:
                raise ValueError("pool lookup mismatch")
            quoted, after, crossed, gas = words(
                self.rpc.one(
                    *call(
                        A["quoter"], sel, token_in, token_out, amount, fee, 0, block=n
                    )
                )
            )
            if (
                quoted <= 0
                or after <= 4295128740
                or after >= 1461446703485210103287273052203988822378723970341
            ):
                raise ValueError("insufficient executable liquidity")
            return dict(
                kind="exact_out" if exact_out else "exact_in",
                pool=pool,
                token_in=address(token_in),
                token_out=address(token_out),
                amount_in=str(quoted if exact_out else amount),
                amount_out=str(amount if exact_out else quoted),
                sqrt_price_after_x96=str(after),
                initialized_ticks_crossed=crossed,
                quoter_gas=str(gas),
                fee=fee,
            )

        return self._read(ref, read, ("quote", token_in, token_out, amount, exact_out))

    def get_dex_quote_exact_in(
        self, token_in, token_out, amount_in, block_ref="latest"
    ):
        return self._quote(token_in, token_out, amount_in, block_ref, False)

    def get_dex_quote_exact_out(
        self, token_in, token_out, amount_out, block_ref="latest"
    ):
        return self._quote(token_in, token_out, amount_out, block_ref, True)

    def get_wallet_balance(self, wallet, token, block_ref="latest"):
        def read(n, h):
            if token is None:
                return str(
                    int(self.rpc.one("eth_getBalance", [address(wallet), n]), 16)
                )
            return str(
                words(self.rpc.one(*call(token, "70a08231", wallet, block=n)))[0]
            )

        return self._read(block_ref, read, ("balance", wallet, token))

    def get_allowance(self, wallet, token, spender, block_ref="latest"):
        return self._read(
            block_ref,
            lambda n, h: str(
                words(self.rpc.one(*call(token, "dd62ed3e", wallet, spender, block=n)))[
                    0
                ]
            ),
            ("allowance", wallet, token, spender),
        )

    def get_execution_fee_estimate(self, transaction):
        def read(n, h):
            gas = int(self.rpc.one("eth_estimateGas", [transaction, n]), 16)
            price = int(self.rpc.one("eth_gasPrice", []), 16)
            return dict(
                estimated_gas=str(gas),
                suggested_gas_price_wei=str(price),
                estimated_l2_wei=str(gas * price),
                l1_fee_wei=None,
                total_fee_wei=None,
                l1_reason="requires exact serialized transaction",
            )

        return self._read("latest", read)

    def get_transaction_receipt(self, tx_hash):
        def read(n, h):
            row = self.rpc.one("eth_getTransactionReceipt", [tx_hash])
            if (
                not row
                or row["blockHash"] != h["hash"]
                or row["transactionHash"] != tx_hash
            ):
                raise ValueError("receipt missing or reorganized")
            return row

        try:
            row = self.rpc.one("eth_getTransactionReceipt", [tx_hash])
            if not row:
                raise ValueError("receipt unavailable")
        except (ValueError, OSError) as exc:
            return dict(
                version="1.0",
                chain_id=177,
                source=self.rpc.url,
                queried_at=utc(),
                block_number=None,
                block_hash=None,
                error=str(exc),
                data=None,
                evidence="UNVERIFIED",
            )
        return self._read(int(row["blockNumber"], 16), read)

    def backfill_market_events(self, start_block, end_block):
        def read(n, h):
            if not 0 <= start_block <= end_block:
                raise ValueError("invalid closed block interval")
            events = {}
            for lo in range(start_block, end_block + 1, 5000):
                for row in self.rpc.one(
                    *logs(A["pool"], MARKET_TOPICS, lo, min(lo + 4999, end_block))
                ):
                    key = (int(row["blockNumber"], 16), int(row["logIndex"], 16))
                    if row.get("removed") or key in events and events[key] != row:
                        raise ValueError("conflicting or removed event")
                    events[key] = row
            return [events[k] for k in sorted(events)]

        return self._read(end_block, read)

    def subscribe_market_events(self, start_block=None, poll_seconds=2):
        """Yield finalized nonempty log batches. Resume at last end block + 1."""
        cursor = start_block
        while True:
            head = int(self.rpc.block("finalized")["number"], 16)
            if cursor is None:
                cursor = head
            if cursor <= head:
                end = min(cursor + 4999, head)
                batch = self.backfill_market_events(cursor, end)
                if batch["error"]:
                    yield batch
                    time.sleep(poll_seconds)
                    continue
                if batch["data"]:
                    yield batch
                cursor = end + 1
                if cursor <= head:
                    continue
            time.sleep(poll_seconds)
