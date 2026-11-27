"""Agent A v1. Refuse incomplete data or quotes from another block."""

from ..schemas.orders import WHSK, USDT
from .market import MarketSnapshot


def read_market(provider):
    def data(envelope, block=None):
        if (
            envelope.get("error")
            or envelope.get("evidence") != "OBSERVED_MAINNET"
            or envelope.get("chain_id") != 177
            or not envelope.get("block_hash")
            or block is not None
            and envelope["block_hash"] != block
        ):
            raise ValueError("RPC_UNAVAILABLE")
        return envelope["data"]

    head = provider.get_chain_state()
    data(head)
    number, block = head["block_number"], head["block_hash"]

    def quote(selling, quantity):
        if selling:
            row = data(provider.get_dex_quote_exact_in(WHSK, USDT, quantity, number), block)
        else:
            row = data(provider.get_dex_quote_exact_out(USDT, WHSK, quantity, number), block)
        source, target = (WHSK, USDT) if selling else (USDT, WHSK)
        if (row["token_in"].lower(), row["token_out"].lower()) != (source, target) or int(
            row["amount_in" if selling else "amount_out"]
        ) != quantity:
            raise ValueError("QUOTE_MISMATCH")
        return int(row["amount_out" if selling else "amount_in"])

    return MarketSnapshot(block, number, "OBSERVED_MAINNET", quote, lambda *_: None)
