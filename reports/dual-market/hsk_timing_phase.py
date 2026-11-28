"""Compare two decisions on one trace per local signed order. Public quotes are read-only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic_ns, sleep, time

import requests

from hsk_quote_holdout import RPC, USDT, WHSK, quoter_call

WORK = Path(__file__).resolve().parent
REPO = WORK.parents[1]
sys.path[:0] = [str(REPO), str(REPO / "backend" / "tests")]

from backend.app.api.main import create_app
from backend.app.optimizer.search import compare
from backend.app.quote_engine.market import MarketSnapshot, synthetic_snapshot
from conftest import UNIT, sign, terms
from eth_account import Account
from fastapi.testclient import TestClient

SIZE = 600
WINDOW_NS = 1_500_000_000
# Same archived 0.05 USDT amount, used as a declared tolerance around
# the observed initial quote. It is not a measured latency or a user order.
LIMIT_ROOM = 50_000
CASES = (
    ("existing_bid_early", "before", 0.45),
    ("existing_bid_after_cutoff", "before", 1.65),
    ("no_buy_order", "absent", 0.0),
    ("buy_order_added_after_start", "after", 0.85),
)


def rpc(session, body):
    response = session.post(RPC, json=body, timeout=10)
    response.raise_for_status()
    return response.json()


def capture(session):
    started_ns = monotonic_ns()
    header_query = dict(jsonrpc="2.0", id=0, method="eth_getBlockByNumber", params=["latest", False])
    header = rpc(session, header_query).get("result")
    if not header or not header.get("hash"):
        raise ValueError("missing HSK block")
    tag = header["number"]
    requests_body = [
        dict(jsonrpc="2.0", id=0, method=header_query["method"], params=[tag, False]),
        dict(jsonrpc="2.0", id=1, method="eth_call", params=[quoter_call("0xc6a5026a", WHSK, USDT, SIZE), tag]),
        dict(jsonrpc="2.0", id=2, method="eth_call", params=[quoter_call("0xbd21704a", USDT, WHSK, SIZE), tag]),
    ]
    replies = {reply["id"]: reply for reply in rpc(session, requests_body)}
    if (replies.get(0, {}).get("result") or {}).get("hash") != header["hash"]:
        raise ValueError("HSK quote block hash did not match")
    words = [replies[i].get("result", "") for i in (1, 2)]
    if any(len(word) < 66 for word in words):
        raise ValueError("unable to obtain both HSK quotes")
    amounts = [int(word[2:66], 16) for word in words]
    if min(amounts) <= 0:
        raise ValueError("empty HSK quote")
    return dict(started_ns=started_ns, received_ns=monotonic_ns(), block=int(tag, 16),
                hash=header["hash"], sell=amounts[0], buy=amounts[1])


def register(api, actor, sell, limit):
    signed = sign(actor, terms(
        actor, sell=sell, size=SIZE, limitAmount=str(limit), allowPartial=False,
        allowDex=sell, allowFallback=sell, priority="SPEED" if sell else "SAVINGS",
        timing="IMMEDIATE" if sell else "LIMIT", minSaving="0" if sell else "1",
    ))
    response = api.post("/orders", json=signed.model_dump())
    assert response.status_code == 200, response.status_code
    return response.json()["orderId"]


def current_book(api):
    response = api.get("/orderbook")
    assert response.status_code == 200, response.status_code
    return set(row["orderId"] for row in response.json())


def estimate(entry, opponents, quote, now):
    def full_quantity(selling, amount):
        if amount != SIZE * UNIT:
            raise ValueError("unexpected tested size")
        return quote["sell" if selling else "buy"]

    market = MarketSnapshot(quote["hash"], quote["block"], "OBSERVED_MAINNET",
                            full_quantity, synthetic_snapshot().costs)
    calculation = compare(entry, opponents, market, now)
    chosen = calculation["selected"]
    if chosen is None:
        return dict(route=None, executable_full=False, seller_net_micro_usdt=None,
                    candidate_reasons=[c["reason"] for c in calculation["candidates"]])
    outcome = chosen["savings"][0]
    cost = sum(int(value) for name, value in outcome["costs"].items() if name != "dex_lower")
    return dict(
        route=chosen["kind"],
        executable_full=int(chosen["fixedFilled"]) == SIZE * UNIT,
        seller_net_micro_usdt=int(outcome["gross"]) - cost,
        buyer_saving_micro_usdt=(
            int(chosen["savings"][1]["conservativeSaving"]) if len(chosen["savings"]) == 2 else None
        ),
        candidate_reasons=[c["reason"] for c in calculation["candidates"]],
    )


def elapsed_ms(absolute_ns, start_ns):
    return round((absolute_ns - start_ns) / 1_000_000, 3)


def run_case(session, case, directory):
    label, relationship, book_delay = case
    initial = capture(session)
    app = create_app("sqlite:///" + (directory / f"{label}.db").as_posix(), "READ_ONLY",
                     market=synthetic_snapshot, run_worker=False)
    store = app.state.worker.store
    with TestClient(app) as api:
        seller, buyer = Account.create(), Account.create()
        buyer_limit = initial["buy"] + LIMIT_ROOM
        if relationship == "before":
            register(api, buyer, False, buyer_limit)
        seller_id = register(api, seller, True, initial["sell"] - LIMIT_ROOM)
        at_start = current_book(api)
        started = monotonic_ns()
        wall_started = time()

        def lookup_book():
            if relationship == "after":
                sleep(0.35)
                register(api, buyer, False, buyer_limit)
                sleep(book_delay - 0.35)
            else:
                sleep(book_delay)
            ids = current_book(api)
            return monotonic_ns(), ids

        def refresh():
            try:
                return capture(session), None
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                return None, str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            book_future = pool.submit(lookup_book)
            quote_future = pool.submit(refresh)
            received_book, later_ids = book_future.result()
            fresh, refresh_error = quote_future.result()

        cutoff = min(received_book, started + WINDOW_NS)
        present_ids = ((at_start & later_ids) - {seller_id}) if received_book <= cutoff else set()
        b_quote = fresh if fresh and fresh["received_ns"] <= cutoff else initial
        with store.engine.connect() as conn:
            entries = {e.id: e for e in store.active(conn, int(time()))}
        before = estimate(entries[seller_id], [], initial, int(wall_started))
        after = estimate(entries[seller_id], [entries[id_] for id_ in present_ids], b_quote,
                         int(wall_started + (cutoff - started) / 1_000_000_000))
        assert api.get("/executions").json() == [], "unexpected local execution"
        return dict(
            scenario=label, injected_book_delay_ms=round(book_delay * 1000),
            initial_quote_age_ms=elapsed_ms(started, initial["received_ns"]),
            initial_quote=initial, subsequent_quote=fresh, subsequent_quote_error=refresh_error,
            subsequent_receipt_ms=elapsed_ms(fresh["received_ns"], started) if fresh else None,
            subsequent_quote_used_in_comparison=b_quote is not initial,
            decision_quote_age_ms=elapsed_ms(cutoff, b_quote["received_ns"]),
            book_return_ms=elapsed_ms(received_book, started), decision_ms=elapsed_ms(cutoff, started),
            existing_opposing_orders=len(at_start - {seller_id}), opposing_orders_evaluated=len(present_ids),
            late_new_orders_excluded=len(later_ids - at_start),
            immediate=before, compare_1500ms=after,
            local_executions=0,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=WORK / "hsk_timing_phase_result.json")
    output = parser.parse_args().out
    if output.exists():
        raise FileExistsError("Reuse the recorded run.")
    rows, missing = [], []
    with requests.Session() as session, TemporaryDirectory(prefix="hsk-timing-", dir=WORK) as folder:
        session.headers["User-Agent"] = "HSK-read-only-timing-study"
        chain = rpc(session, dict(jsonrpc="2.0", id=0, method="eth_chainId", params=[]))
        if int(chain.get("result", "0"), 16) != 177:
            raise ValueError("RPC is not the expected HSK chain")
        for case in CASES:
            try:
                rows.append(run_case(session, case, Path(folder)))
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                missing.append(dict(scenario=case[0], error=str(error)))
    paired = [(row["immediate"], row["compare_1500ms"]) for row in rows]
    got_higher_net = sum(a["executable_full"] and b["executable_full"]
                         and b["seller_net_micro_usdt"] > a["seller_net_micro_usdt"] for a, b in paired)
    got_lower_net = sum(a["executable_full"] and b["executable_full"]
                        and b["seller_net_micro_usdt"] < a["seller_net_micro_usdt"] for a, b in paired)
    summary = dict(
        fixed_scenarios=len(CASES), comparable=len(rows), no_result=len(missing),
        immediate_full=sum(a["executable_full"] for a, _ in paired),
        comparison_full=sum(b["executable_full"] for _, b in paired),
        lost=sum(a["executable_full"] and not b["executable_full"] for a, b in paired),
        gained=sum(b["executable_full"] and not a["executable_full"] for a, b in paired),
        got_higher_net=got_higher_net, got_lower_net=got_lower_net,
        fresh_quote_by_comparison_cutoff=sum(row["subsequent_quote_used_in_comparison"] for row in rows),
        observed_fresh_change=sum(
            row["subsequent_quote"] is not None and
            (row["initial_quote"]["sell"], row["initial_quote"]["buy"]) !=
            (row["subsequent_quote"]["sell"], row["subsequent_quote"]["buy"]) for row in rows
        ),
    )
    details = dict(
        scope="Local signed test orders and real HSK public quotes; hypothetical route decisions "
              "with the repository's synthetic cost bounds; no trade or fill observed.",
        quote_pool="same WHSK/USDT 0.30% pool as archived test",
        order_limits="600 WHSK; sell quote minus 0.05 USDT, buy quote plus 0.05 USDT; "
                     "computed from the initial quote before either decision",
        method="one shared initial and one follow-up market observation per order; "
               "the follow-up is usable only after it is received; book delivery delays injected",
        summary=summary, cases=rows, missing=missing,
    )
    output.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for row in rows:
        before, after = row["immediate"], row["compare_1500ms"]
        print(row["scenario"], before["route"], after["route"], row["decision_ms"],
              before["seller_net_micro_usdt"], after["seller_net_micro_usdt"])


if __name__ == "__main__":
    main()
