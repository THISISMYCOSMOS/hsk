"""Block-pinned WHSK/USDT direct-pool quotes on HashKey mainnet."""

from datetime import datetime, timezone
import re

from backend.app.blockchain.rpc import A, CONFIG, RPC, addr_word, call, signed, utc, words


FEE_TIERS = (100, 500, 3000, 10000)
MIN_SQRT_RATIO = 4295128739
MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342


def _number(block_number):
    if block_number is None:
        return "latest"
    if type(block_number) is not int or block_number < 0:
        raise ValueError("block_number must be a nonnegative integer")
    return block_number


def _header(rpc, ref):
    block = rpc.block(ref)
    if not isinstance(block, dict) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", str(block.get("hash"))):
        raise ValueError("invalid or unavailable block")
    n = int(block["number"], 16)
    if isinstance(ref, int) and n != ref:
        raise ValueError("RPC returned a different block")
    return n, block["hash"].lower(), int(block["timestamp"], 16)


def _check_hash(rpc, n, h):
    if _header(rpc, n)[1] != h:
        raise ValueError("pinned block reorganized")


def get_head():
    """Lightweight poll result; use its block number with get_snapshot."""
    n, h, timestamp = _header(RPC(), "latest")
    return {"block_number": n, "block_hash": h, "block_timestamp": timestamp}


def _single(data):
    result = words(data)
    if len(result) != 1:
        raise ValueError("expected one ABI word")
    return result[0]


def get_snapshot(block_number=None):
    ref = _number(block_number)
    rpc = RPC()
    n, h, timestamp = _header(rpc, ref)
    tag = hex(n)
    lookups = [call(A["factory"], "1698ee82", A["WHSK"], A["USDT"], fee, block=tag)
               for fee in FEE_TIERS]
    checks = [call(A[name], "313ce567", block=tag) for name in ("WHSK", "USDT")]
    checks.append(call(A["quoter"], "c45a0155", block=tag))
    results = list(map(_single, rpc.batch(checks + lookups)))
    whsk_dec, usdt_dec, quoter_factory = results[:3]
    if (whsk_dec, usdt_dec) != (18, 6) or addr_word(quoter_factory) != A["factory"]:
        raise ValueError("unexpected token decimals or QuoterV2 factory")
    pairs = [(fee, addr_word(value)) for fee, value in zip(FEE_TIERS, results[3:]) if value]
    if not pairs:
        raise ValueError("no WHSK/USDT direct pools in monitored fee tiers")
    pools = []
    for fee, pool in pairs:
        selectors = ("0dfe1681", "d21220a7", "ddca3f43", "c45a0155", "1a686502", "3850c7bd")
        result = rpc.batch([call(pool, selector, block=tag) for selector in selectors])
        token0, token1, actual_fee, factory, liquidity = map(_single, result[:5])
        if ([addr_word(token0), addr_word(token1)] != [A["WHSK"], A["USDT"]]
                or actual_fee != fee or addr_word(factory) != A["factory"]):
            raise ValueError("pool identity mismatch")
        slot = words(result[5])
        if len(slot) != 7:
            raise ValueError("malformed slot0")
        pools.append(dict(address=pool, fee=fee, token0=addr_word(token0), token1=addr_word(token1),
                          active_liquidity=str(liquidity), sqrt_price_x96=str(slot[0]), tick=signed(slot[1])))
    _check_hash(rpc, n, h)
    return dict(chain_id=177, block_number=n, block_hash=h, block_timestamp=timestamp,
                block_time_utc=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                observed_at_utc=utc(), decimals_whsk=whsk_dec, decimals_usdt=usdt_dec,
                whsk=A["WHSK"], usdt=A["USDT"], factory=A["factory"], quoter=A["quoter"], pools=pools,
                provenance=dict(rpc=CONFIG["rpc"], network=CONFIG["network_source"], tokens=CONFIG["token_source"],
                                dex=CONFIG["dex_address_source"], fee_tiers=list(FEE_TIERS),
                                scope="direct, unsplit WHSK/USDT pools at listed fee tiers"))


def _quote(snapshot, side, amount, exact_out):
    if side not in ("buy", "sell") or type(amount) is not int or not 0 < amount < 2**255:
        raise ValueError("expected side buy/sell and positive int256 raw amount")
    if snapshot["chain_id"] != 177 or not snapshot["pools"]:
        raise ValueError("missing mainnet pools")
    tokens = (A["WHSK"], A["USDT"]) if side == "sell" else (A["USDT"], A["WHSK"])
    n, h = snapshot["block_number"], snapshot["block_hash"]
    selector = "bd21704a" if exact_out else "c6a5026a"
    rpc = RPC()
    req = [call(A["quoter"], selector, *tokens, amount, pool["fee"], 0, block=hex(n))
           for pool in snapshot["pools"]]
    req.append(("eth_getBlockByNumber", [hex(n), False]))
    *responses, header = rpc.batch(req)
    if not isinstance(header, dict) or header.get("hash", "").lower() != h or int(header["number"], 16) != n:
        raise ValueError("quote block hash mismatch")
    values = []
    for data in responses:
        out, sqrt_after, _, _ = words(data)
        if out == 0 or not MIN_SQRT_RATIO + 1 < sqrt_after < MAX_SQRT_RATIO - 1:
            raise ValueError("empty or potentially incomplete DEX fill")
        values.append(out)
    return min(values) if exact_out else max(values)


def quote_exact_input(snapshot, side, amount_in):
    """Output base units for exact input; sell spends WHSK and buy spends USDT."""
    return _quote(snapshot, side, amount_in, False)


def quote_exact_output(snapshot, side, amount_out):
    """Required input base units for exact output; buy receives WHSK."""
    return _quote(snapshot, side, amount_out, True)
