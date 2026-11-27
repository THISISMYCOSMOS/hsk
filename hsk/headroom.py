"""Estimate the shared pre-cost margin for two hypothetical opposite orders."""

import argparse
import json
import re

from .agent import amount, raw


def compare(snapshot, token, sizes, match_bps, exact_in, exact_out, extra_cost=None):
    if token not in ("WHSK", "USDT"):
        raise ValueError("unsupported input token")
    if not 0 < match_bps <= 10_000:
        raise ValueError("match-bps must be in the range 1..10000")
    side, opposite, output = ("sell", "buy", "USDT") if token == "WHSK" else ("buy", "sell", "WHSK")
    rows = []
    for size in sizes:
        total = raw(size, token)
        matched = total * match_bps // 10_000
        if not matched:
            raise ValueError("hypothetical match rounds down to zero")
        residual = total - matched
        full_out = exact_in(snapshot, side, total)
        residual_out = exact_in(snapshot, side, residual) if residual else 0
        maker_budget = exact_out(snapshot, opposite, matched)
        shared_margin = maker_budget + residual_out - full_out
        # Seller receives clearing payment + residual DEX output. Buyer saves
        # its DEX budget minus that payment. The clearing payment cancels.
        rows.append(dict(input_raw=str(total), matched_raw=str(matched), residual_raw=str(residual),
                         full_dex_output_raw=str(full_out), residual_dex_output_raw=str(residual_out),
                         counterparty_dex_cost_raw=str(maker_budget),
                         shared_gross_margin_raw=str(shared_margin),
                         conditional_net_margin_raw=None if extra_cost is None else str(shared_margin - extra_cost)))
    return dict(token_in=token, report_token=output, match_bps=match_bps,
                evidence="pinned_block_dex_quotes_with_hypothetical_opposite_order",
                benchmark="independent direct-pool quotes from identical starting state",
                order_source="hypothetical", assumed_extra_cost_raw=None if extra_cost is None else str(extra_cost),
                participant_net_saving=None, realized_saving=None,
                rows=rows)


def main():
    from .market import get_snapshot, quote_exact_input, quote_exact_output

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token", choices=("WHSK", "USDT"), help="token spent by the first trader")
    parser.add_argument("amounts", nargs="+", help="exact-input amounts, in whole-token notation")
    parser.add_argument("--match-bps", type=int, required=True, help="hypothetical opposite size, in basis points")
    parser.add_argument("--json", action="store_true", help="emit raw integer quantities and source metadata")
    parser.add_argument("--extra-cost", help="assumed combined incremental cost per scenario, in the output token")
    parser.add_argument("--block", type=int, help="replay a specific mainnet block (default: latest)")
    args = parser.parse_args()
    try:
        extra_cost = None
        if args.extra_cost is not None:
            output = "USDT" if args.token == "WHSK" else "WHSK"
            extra_cost = 0 if re.fullmatch(r"0+(?:\.0+)?", args.extra_cost) else raw(args.extra_cost, output)
        snapshot = get_snapshot(block_number=args.block)
        result = compare(snapshot, args.token, args.amounts, args.match_bps, quote_exact_input, quote_exact_output,
                         extra_cost=extra_cost)
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"Mainnet comparison unavailable: {exc}\n")
    public_fields = ("chain_id", "block_number", "block_hash", "block_time_utc", "observed_at_utc",
                     "block_timestamp", "queried_at_utc",
                     "decimals_whsk", "decimals_usdt", "whsk", "usdt", "factory", "quoter", "pools", "provenance")
    result["snapshot"] = {key: snapshot[key] for key in public_fields if key in snapshot}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"HSK 메인넷 블록 {snapshot['block_number']}  {snapshot['block_hash']}")
    print(f"가상 반대 주문 비중 {args.match_bps / 100:g}% · 동일 블록 독립 DEX 견적 비교")
    for row in result["rows"]:
        size = amount(int(row["input_raw"]), args.token)
        baseline = amount(int(row["full_dex_output_raw"]), result["report_token"])
        margin = amount(int(row["shared_gross_margin_raw"]), result["report_token"])
        print(f"{size} 지출 · 전량 DEX 수령 {baseline} · 양측 합산 비용 전 차이 {margin}")
        if extra_cost is not None:
            net = amount(int(row["conditional_net_margin_raw"]), result["report_token"])
            print(f"  양측 합산 추가비용 가정 {amount(extra_cost, result['report_token'])} 적용 후 {net}")
    print("개인별 순절감액·실현 절감액 미측정")


if __name__ == "__main__":
    main()
