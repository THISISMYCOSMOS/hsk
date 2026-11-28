"""Read-only holdout of 12 fixed HSK time slots; never submit transactions."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import requests

import hsk_bilateral_archive as prior
from hsk_retail_scenarios import fees_with_shared_cap


WORK = Path(__file__).resolve().parent
PRIOR_RESULTS = WORK / "HSKSwap-bilateral-backtest-results.json"
RESULT = WORK / "hsk_quote_holdout.json"
RPC = "https://mainnet.hsk.xyz"
QUOTER = "0x603f70466fDdbE3F238220B9a74FFF419a2BbFDD"
WHSK = "0xB210D2120d57b758EE163cFfb43e73728c471Cf1"
USDT = "0xF1B50eD67A9e2CC94Ad3c477779E2d4cBfFf9029"
KST = timezone(timedelta(hours=9))
GENESIS_TIMESTAMP = 1_734_347_135
SLOTS = [
    datetime(2026, 11, day, hour, tzinfo=KST)
    for day in (25, 26, 27)
    for hour in (0, 6, 12, 18)
]
SELLER_EXTRA_COST = 50_000
FIXED_FEE = 30_000


def quoter_call(selector: str, token_in: str, token_out: str, quantity: int) -> dict:
    words = (int(token_in, 16), int(token_out, 16), quantity * 10**18, 3000, 0)
    return {"to": QUOTER, "data": selector + "".join(f"{word:064x}" for word in words)}


QUOTES = {
    "sell_1000": quoter_call("0xc6a5026a", WHSK, USDT, 1000),
    "buy_600": quoter_call("0xbd21704a", USDT, WHSK, 600),
    "sell_remainder_400": quoter_call("0xc6a5026a", WHSK, USDT, 400),
}


def rpc_one(session: requests.Session, requests_body: dict | list):
    response = session.post(RPC, json=requests_body, timeout=12)
    response.raise_for_status()
    return response.json()


def collect(session: requests.Session, slot: datetime, previous_blocks: set[int]) -> dict:
    block = (int(slot.timestamp()) - GENESIS_TIMESTAMP) // 2
    assert block not in previous_blocks
    row = {"kst": slot.isoformat(), "block": block}
    keys = tuple(QUOTES)
    request_params = [("eth_getBlockByNumber", [hex(block), False])]
    request_params.extend(("eth_call", [QUOTES[key], hex(block)]) for key in keys)
    batch = [
        {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
        for i, (method, params) in enumerate(request_params)
    ]
    quote_amounts, missing = {}, {}
    try:
        response = rpc_one(session, batch)
        if isinstance(response, dict) and response.get("error"):
            error = response["error"]
            if error.get("code") == -32600 and "batch" in error.get("message", "").lower():
                response = [rpc_one(session, request) for request in batch]
        if not isinstance(response, list):
            raise ValueError(f"unexpected RPC batch output: {response!r}")
        replies = {item["id"]: item for item in response if "id" in item}
        header = replies.get(0, {}).get("result") or {}
        if int(header.get("number", "0"), 16) != block:
            raise ValueError(f"block header unavailable: {replies.get(0)}")
        timestamp = datetime.fromtimestamp(int(header["timestamp"], 16), KST)
        if not 0 <= (slot - timestamp).total_seconds() < 2:
            raise ValueError(f"block timestamp does not cover slot: {timestamp.isoformat()}")
        row["block_time_kst"], row["block_hash"] = timestamp.isoformat(), header["hash"]
        for index, key in enumerate(keys, 1):
            reply = replies.get(index, {})
            amount_data = reply.get("result")
            if not isinstance(amount_data, str) or len(amount_data) < 66:
                missing[key] = reply.get("error", "missing or incomplete response")
                continue
            quote_amounts[key] = int(amount_data[2:66], 16)
    except (requests.RequestException, ValueError, KeyError) as error:
        row["error"] = str(error)
    row["quotes_micro_usdt"], row["missing_quotes"] = quote_amounts, missing
    return row


def compare_policies(prior, prices: dict) -> dict:
    sell, buy, remainder = (prices[key] for key in QUOTES)
    # Adapt the archived comparator to same-block independent quotes. There is no
    # observation of two DEX legs executing sequentially in this holdout.
    case = prior.compare(
        {
            "seller_first": sell, "seller_second": sell,
            "buyer_first": buy, "buyer_second": buy, "residual": remainder,
        },
        SELLER_EXTRA_COST, 0,
    )
    direct_signed = sell >= prior.A_MIN and buy <= prior.B_MAX
    result = {"independent_dex_quotes_meet_both_limits": direct_signed, "mixed": case}
    if not case["eligible"]:
        return result

    a_gain, b_gain, payment = case["a_net_gain"], case["b_net_gain"], case["payment"]
    difference = abs(a_gain - b_gain)
    result["fairness_at_same_payment"] = {
        "gain_sum": {str(percent): difference * 100 <= percent * (a_gain + b_gain) for percent in (1, 2, 3)},
        "matched_payment": {str(percent): difference * 100 <= percent * payment for percent in (1, 2, 3)},
    }
    if not result["fairness_at_same_payment"]["gain_sum"]["3"]:
        return result
    seller_room, buyer_room = payment + remainder - prior.A_MIN, prior.B_MAX - payment
    fixed_pass = (
        FIXED_FEE <= min(seller_room, buyer_room, a_gain - 1, b_gain - 1)
        and difference * 100 <= 3 * (a_gain + b_gain - 2 * FIXED_FEE)
    )
    dynamic = {}
    for cost in (5_000, 8_000):
        advertised = min(cost // 2, min(a_gain, b_gain) * 3 // 100, FIXED_FEE) if direct_signed else 0
        fee, other_fee = fees_with_shared_cap(a_gain, b_gain, seller_room, buyer_room, advertised)
        assert fee == other_fee and 0 <= fee <= advertised
        assert fee <= min(seller_room, buyer_room, a_gain - 1, b_gain - 1)
        assert difference * 100 <= 3 * (a_gain + b_gain - 2 * fee)
        dynamic[str(cost)] = {"each_fee_micro_usdt": fee, "team_unrecovered_direct_cost_micro_usdt": cost - 2 * fee}
    result["same_payment_fee_comparison_at_3pct_imbalance"] = {
        "free_pass": True,
        "fixed_comparison_pass": fixed_pass,
        "dynamic": dynamic,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=RESULT)
    output = parser.parse_args().out
    if output.exists():
        raise FileExistsError(f"reuse saved results instead of recollecting: {output}")
    previous = json.loads(PRIOR_RESULTS.read_text(encoding="utf-8-sig"))
    previous_blocks = {item["block"] for item in previous["blocks"]}
    with requests.Session() as session:
        session.headers["User-Agent"] = "HSK-read-only-quote-study"
        rows = []
        for slot in SLOTS:
            rows.append(collect(session, slot, previous_blocks))
            time.sleep(0.35)

    for row in rows:
        quotes = row["quotes_micro_usdt"]
        if len(quotes) == len(QUOTES):
            row["comparison"] = compare_policies(prior, quotes)
    comparisons = [row["comparison"] for row in rows if "comparison" in row]
    fees = [row["same_payment_fee_comparison_at_3pct_imbalance"] for row in comparisons if "same_payment_fee_comparison_at_3pct_imbalance" in row]
    fairness = [row["fairness_at_same_payment"] for row in comparisons if "fairness_at_same_payment" in row]
    summary = {
        "slots_planned": len(SLOTS),
        "complete_slots": len(comparisons),
        "quotes_observed": sum(len(row["quotes_micro_usdt"]) for row in rows),
        "mixed_candidates_before_fairness": len(fairness),
        "fails_before_fairness": dict(Counter(row["mixed"]["reason"] for row in comparisons if not row["mixed"]["eligible"])),
        "independent_dex_quotes_meet_both_limits": sum(row["independent_dex_quotes_meet_both_limits"] for row in comparisons),
        "fairness_counts": {
            reference: {str(percent): sum(row[reference][str(percent)] for row in fairness) for percent in (1, 2, 3)}
            for reference in ("gain_sum", "matched_payment")
        },
        "free_pass": len(fees),
        "fixed_fee_pass": sum(fee["fixed_comparison_pass"] for fee in fees),
        "dynamic_pass": len(fees),
        "dynamic_fee_positive_by_cost": {
            str(cost): sum(fee["dynamic"][str(cost)]["each_fee_micro_usdt"] > 0 for fee in fees)
            for cost in (5_000, 8_000)
        },
    }
    data = {
        "sample": "Preselected KST 00:00/06:00/12:00/18:00, Nov 25-27, after Nov 18-24 calibration; block at or before slot",
        "limitations": "Public read-only same-block independent DEX quotes; simulated signed orders, costs, price midpoint and operator fees; no DEX sequential execution, buy/sell submission, approval estimate, or live matching demand. Fixed fee is a policy comparison, charged only if user conditions pass. Dynamic result is before operating subsidy budget.",
        "costs_micro_usdt": {"seller_incremental": SELLER_EXTRA_COST, "buyer_incremental": 0, "each_fixed": FIXED_FEE},
        "summary": summary, "rows": rows,
    }
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
