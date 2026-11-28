"""Compare retail fee policies using only archived prices and fork receipts."""

import argparse
import hashlib
import json
from pathlib import Path

from hsk_retail_scenarios import IMBALANCE_PERCENT, within_imbalance


WORK = Path(__file__).resolve().parent
REPO = WORK.parents[1]
ARCHIVE = WORK / "HSKSwap-bilateral-backtest-results.json"
SELLER_SIGNED_MIN = 81_000_000
BUYER_SIGNED_MAX = 49_200_000
SELLER_INCREMENTAL_COST = 50_000
MINIMUM_NET = 1
FEE_CAP_PER_SIDE = 30_000
FIXED_FEE_PER_SIDE = 30_000
SAVINGS_CAP_PERCENT = 3


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_cost_evidence():
    gas_dir = REPO / "reports/gas"
    receipt_report = read_json(gas_dir / "anvil-receipts.json")
    raw_receipts = {
        row["scenario"]: row["receipt"]
        for row in read_json(gas_dir / "anvil-raw.json")["transactions"]
    }
    receipt_rows = {}
    for row in receipt_report["rows"]:
        if row["scenario"] not in {"approve-WHSK", "approve-USDT", "hybrid-sell"}:
            continue
        raw = raw_receipts[row["scenario"]]
        assert int(raw["gasUsed"], 16) == row["gasUsed"]
        assert int(raw["status"], 16) == row["status"] == 1
        assert raw["transactionHash"] == row["localTxHash"]
        receipt_rows[row["scenario"]] = row
    assert len(receipt_rows) == 3

    economics_dir = REPO / "reports/economics"
    fork = read_json(economics_dir / "settlement_fork.json")
    economics = read_json(economics_dir / "fee_model.json")
    browser = read_json(REPO / "docs/agents/agent-d/browser-fork.json")
    assert receipt_report["upstreamHash"] == fork["source_hash"] == economics["hash"] == browser["anchor"]
    settlement = fork["settlement"]["results"]["partial"]
    charges = {row["name"]: row for row in economics["charges"]}
    price = charges["partial"]
    assert price["payer"] == settlement["payer"]
    assert price["gas_used"] == settlement["gas_used"]
    assert all(int(row["feeUSDT"]) == 0 for row in browser["participants"])
    order_fills = [
        log for log in settlement["logs"]
        if log["topics"][0] == "0x90217386c0199899e4f10195f2b08e2a1695e032f71ee1d70213b550cd7231f4"
    ]
    assert len(order_fills) == 2 and all(int(log["data"][194:258], 16) == 0 for log in order_fills)
    approval_costs = {}
    for side, index in (("seller_whsk", 0), ("buyer_usdt", 1)):
        approval_costs[side] = {}
        for path, approvals, name in (
            ("dex_router", fork["approvals"], f"dex_approval_{index}"),
            ("matching", fork["settlement"]["approvals"], f"settlement_approval_{index}"),
        ):
            charge = charges[name]
            assert charge["payer"] == approvals[index]["payer"]
            assert charge["gas_used"] == approvals[index]["gas_used"]
            approval_costs[side][path] = {
                "gas_used": int(charge["gas_used"]),
                "receipt_hash": approvals[index]["local_tx_hash"],
                "modeled_avoided_cost_lower": int(charge["avoided_cost_lower_usdt_raw"]),
                "modeled_replenishment_upper": int(charge["replenishment_upper_usdt_raw"]),
            }
    fresh = next(
        row for row in economics["partial_match"]
        if row["baseline"] == "A_sell_first" and row["fresh_approvals"] and row["no_trade_per_success"] == 0
    )
    approved = next(
        row for row in economics["partial_match"]
        if row["baseline"] == "A_sell_first" and not row["fresh_approvals"] and row["no_trade_per_success"] == 0
    )
    for side in ("seller", "buyer"):
        cost = approval_costs["seller_whsk" if side == "seller" else "buyer_usdt"]
        key = f"{side}_gain_before_service_fee_raw"
        assert int(fresh[key]) - int(approved[key]) == (
            cost["dex_router"]["modeled_avoided_cost_lower"] - cost["matching"]["modeled_replenishment_upper"]
        )
    return {
        "fork_block": economics["block"],
        "fork_block_hash": economics["hash"],
        "anvil_chain_id": receipt_report["anvilChainId"],
        "receipt_crosschecks": receipt_rows,
        "matching_economics_fork_receipt_hash": settlement["local_tx_hash"],
        "matching_economics_fork_gas": int(price["gas_used"]),
        "matching_browser_fork_gas": int(browser["gasUsed"]),
        "matching_browser_fork_receipt_hash": browser["txHash"],
        "archived_base_fee_per_gas_wei": economics["base_fee_per_gas_wei"],
        "archived_assumed_tip_wei": economics["assumed_tip_wei"],
        "estimated_wei_before_l1": price["l2_wei"],
        "estimated_l1_fee_upper_wei": price["l1_fee_upper_wei"],
        "modeled_avoided_cost_lower_at_fork_anchor": int(price["avoided_cost_lower_usdt_raw"]),
        "modeled_operator_replenishment_cost_upper_at_fork_anchor": int(price["replenishment_upper_usdt_raw"]),
        "approval_costs_by_route": approval_costs,
    }


def score(gains, signed_rooms, fee, operator_cost):
    net = [gain - fee for gain in gains]
    failures = []
    if any(room < fee for room in signed_rooms):
        failures.append("signed_price")
    if min(net) < MINIMUM_NET:
        failures.append("minimum_net")
    if not within_imbalance(*net):
        failures.append("distribution")
    if fee > FEE_CAP_PER_SIDE:
        failures.append("signed_fee_cap")
    revenue = 0 if failures else 2 * fee
    return {
        "fee_each": fee,
        "seller_net_if_applied": net[0],
        "buyer_net_if_applied": net[1],
        "user_conditions_pass": not failures,
        "user_condition_failures": failures,
        "potential_revenue_if_executed": revenue,
        "operator_cost_if_executed": None if failures else operator_cost,
        "unrecovered_direct_cost_if_executed": None if failures else max(0, operator_cost - revenue),
    }


def dynamic_fee_caps(gains, signed_rooms, operator_cost):
    distribution_room = (
        IMBALANCE_PERCENT * sum(gains) - 100 * abs(gains[0] - gains[1])
    ) // (2 * IMBALANCE_PERCENT)
    return {
        "operator_cost_half": operator_cost // 2,
        "smaller_savings_three_percent": min(gains) * SAVINGS_CAP_PERCENT // 100,
        "common_approved_cap": FEE_CAP_PER_SIDE,
        "signed_price_headroom": min(signed_rooms),
        "minimum_net_headroom": min(gains) - MINIMUM_NET,
        "distribution_headroom": max(0, distribution_room),
    }


def score_block(block, operator_cost):
    quotes = block["router_amounts"]
    case = next(case for case in block["cases"] if case["a_incremental_cost"] == SELLER_INCREMENTAL_COST)
    dex_proof = (
        quotes["seller_first"] >= SELLER_SIGNED_MIN and quotes["buyer_second"] <= BUYER_SIGNED_MAX
        or quotes["seller_second"] >= SELLER_SIGNED_MIN and quotes["buyer_first"] <= BUYER_SIGNED_MAX
    )
    assert dex_proof == block["at_least_one_dex_sequence_meets_both_signed_limits"]
    row = {"block": block["block"], "archive_price_candidate": case["eligible"], "dex_proof": dex_proof}
    if not case["eligible"]:
        return row | {"archive_rejection": case["reason"]}

    payment = case["payment"]
    seller_cash = payment + quotes["residual"]
    gains = [
        seller_cash - max(quotes["seller_first"], quotes["seller_second"]) - SELLER_INCREMENTAL_COST,
        min(quotes["buyer_first"], quotes["buyer_second"]) - payment,
    ]
    assert gains == [case["a_net_gain"], case["b_net_gain"]]
    signed_rooms = [seller_cash - SELLER_SIGNED_MIN, BUYER_SIGNED_MAX - payment]
    dynamic_caps = dynamic_fee_caps(gains, signed_rooms, operator_cost)
    dynamic_fee = min(dynamic_caps.values()) if dex_proof and within_imbalance(*gains) else 0
    return row | {
        "recorded_payment": payment,
        "pre_fee_seller_net": gains[0],
        "pre_fee_buyer_net": gains[1],
        "seller_signed_price_headroom": signed_rooms[0],
        "buyer_signed_price_headroom": signed_rooms[1],
        "dynamic_caps": dynamic_caps,
        "zero": score(gains, signed_rooms, 0, operator_cost),
        "fixed": score(gains, signed_rooms, FIXED_FEE_PER_SIDE, operator_cost),
        "dynamic": score(gains, signed_rooms, dynamic_fee, operator_cost),
    }


def compare_approval_states(row, costs):
    operator_cost = costs["modeled_operator_replenishment_cost_upper_at_fork_anchor"]
    scenarios = {}
    for name, fresh_matching, fresh_dex in (
        ("already_approved_for_both", False, False),
        ("initial_approval_for_both", True, True),
        ("initial_approval_for_matching_only", True, False),
        ("initial_approval_for_dex_only", False, True),
    ):
        gains = []
        deltas = []
        rooms = []
        for role, token in (("seller", "whsk"), ("buyer", "usdt")):
            approval = costs["approval_costs_by_route"][f"{role}_{token}"]
            dex_credit = approval["dex_router"]["modeled_avoided_cost_lower"] if fresh_dex else 0
            matching_cost = approval["matching"]["modeled_replenishment_upper"] if fresh_matching else 0
            deltas.append(dex_credit - matching_cost)
            gains.append(row[f"pre_fee_{role}_net"] + deltas[-1])
            rooms.append(row[f"{role}_signed_price_headroom"])
        fee = min(dynamic_fee_caps(gains, rooms, operator_cost).values()) if within_imbalance(*gains) else 0
        scenarios[name] = {
            "conservative_change_to_seller_pre_fee_net": deltas[0],
            "conservative_change_to_buyer_pre_fee_net": deltas[1],
            "seller_pre_fee_net": gains[0],
            "buyer_pre_fee_net": gains[1],
            "dynamic": score(gains, rooms, fee, operator_cost),
        }
    assert scenarios["already_approved_for_both"]["dynamic"] == row["dynamic"]
    return {
        "block": row["block"],
        "same_recorded_payment": row["recorded_payment"],
        "assumption": "For this separate sensitivity the existing 0.05 seller cost excludes these approval deltas. Either participant may need approval for either path, based on their independent allowance state. The scenario labels apply the same illustrative allowance condition to each side.",
        "scenarios": scenarios,
    }


def summarize(rows, policy):
    selected = [row for row in rows if row.get(policy, {}).get("user_conditions_pass")]
    results = [row[policy] for row in selected]
    fees_with_dex_proof = [row[policy]["fee_each"] for row in selected if row["dex_proof"] and row[policy]["fee_each"]]
    fees_without_dex_proof = [row["block"] for row in selected if not row["dex_proof"] and row[policy]["fee_each"]]
    return {
        "passes_user_conditions": len(selected),
        "fee_induced_losses_relative_to_zero": [
            row["block"] for row in rows
            if row.get("zero", {}).get("user_conditions_pass") and not row[policy]["user_conditions_pass"]
        ],
        "count_positive_fee": sum(result["fee_each"] > 0 for result in results),
        "count_positive_fee_with_dex_proof": len(fees_with_dex_proof),
        "positive_fee_without_dex_proof": fees_without_dex_proof,
        "positive_fee_each_range": [min(fees_with_dex_proof), max(fees_with_dex_proof)] if fees_with_dex_proof else None,
        "seller_net_range": [min(result["seller_net_if_applied"] for result in results), max(result["seller_net_if_applied"] for result in results)],
        "buyer_net_range": [min(result["buyer_net_if_applied"] for result in results), max(result["buyer_net_if_applied"] for result in results)],
        "hypothetical_revenue_before_budget_check": sum(result["potential_revenue_if_executed"] for result in results),
        "modeled_direct_cost_if_all_passes_execute": sum(result["operator_cost_if_executed"] for result in results),
        "unrecovered_direct_cost_if_all_passes_execute": sum(result["unrecovered_direct_cost_if_executed"] for result in results),
        "passes_if_no_net_deficit_budget": sum(result["unrecovered_direct_cost_if_executed"] == 0 for result in results),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--out", type=Path, default=WORK / "hsk_fee_phase_results.json")
    args = parser.parse_args()
    archive = read_json(args.archive)
    costs = load_cost_evidence()
    rows = [
        score_block(block, costs["modeled_operator_replenishment_cost_upper_at_fork_anchor"])
        for block in archive["blocks"]
    ]
    assert len(rows) == len({row["block"] for row in rows}) == archive["sample_observed_count"] == 24
    assert not archive["missing_blocks"]
    budget_sensitivity = {}
    summaries = {policy: summarize(rows, policy) for policy in ("zero", "fixed", "dynamic")}
    assert summaries["zero"]["passes_user_conditions"] == summaries["dynamic"]["passes_user_conditions"]
    for assumed_cost in (5_000, 8_000):
        old_rows = [score_block(block, assumed_cost) for block in archive["blocks"]]
        budget_sensitivity[str(assumed_cost)] = summarize(old_rows, "dynamic")
    report = {
        "archived_quote_input_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
        "units": "micro-USDT unless indicated as gas or wei",
        "assumptions": {
            "seller_whsk": 1000, "buyer_whsk": 600, "dex_residual_sell_whsk": 400,
            "seller_signed_min": SELLER_SIGNED_MIN, "buyer_signed_max": BUYER_SIGNED_MAX,
            "seller_incremental_cost": SELLER_INCREMENTAL_COST, "buyer_incremental_cost": 0,
            "minimum_net_each": MINIMUM_NET, "approved_fee_cap_each": FEE_CAP_PER_SIDE,
            "fixed_fee_each": FIXED_FEE_PER_SIDE,
            "fairness_percent_of_combined_post_fee_net": IMBALANCE_PERCENT,
            "dynamic_savings_cap_percent": SAVINGS_CAP_PERCENT,
            "fixed_comparator": "The legacy fixed fee does not require DEX proof. Rows violating proof are reported separately.",
            "budget": "Hypothetical no net deficit budget after revenue. Settlement still needs gross upfront funding.",
            "cost_proxy": "Same upper estimate from one archived zero-fee hybrid fork receipt applied across all policies and 24 market blocks. Paid fee transfers, retries, and fixed costs are outside this success-only model.",
            "approvals": "Charged to users when needed. Existing seller incremental cost is preserved and the separate approval estimate is not added to it or the operator cost.",
        },
        "cost_evidence": costs,
        "blocks": len(rows),
        "archive_candidates_before_fairness": sum(row["archive_price_candidate"] for row in rows),
        "summary": summaries,
        "approval_sensitivity_same_price_example": compare_approval_states(
            next(row for row in rows if row["block"] == 30444756), costs
        ),
        "previous_assumed_cost_comparisons": budget_sensitivity,
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
