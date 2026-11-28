"""Enumerate two retries for an existing 600/400/200 offline scenario."""

from itertools import permutations
import json

from hsk_retail_scenarios import can_send_again


def simulate(events: tuple[str, ...], *, recheck_on_reserve: bool) -> dict:
    order_quantity, already_filled, retry_quantity = 600, 400, 200
    status = "confirmed"
    observed: dict[str, bool] = {}
    submitted = []

    for event in events:
        worker = event.lower()
        if event.islower():
            observed[worker] = can_send_again(status, already_filled, order_quantity, retry_quantity)
            continue

        eligible = observed[worker]
        if recheck_on_reserve:
            # This abstract operation is indivisible in the model.
            eligible = eligible and can_send_again(status, already_filled, order_quantity, retry_quantity)
        if eligible:
            submitted.append(worker)
            status = "pending"

    total_if_submitted_fills = already_filled + len(submitted) * retry_quantity
    return {
        "submitted": submitted,
        "reserved_total_if_executed": total_if_submitted_fills,
        "exceeds_order_total": total_if_submitted_fills > order_quantity,
    }


def main() -> None:
    rows = []
    for events in permutations("aAbB"):
        if events.index("a") > events.index("A") or events.index("b") > events.index("B"):
            continue

        before = simulate(events, recheck_on_reserve=False)
        after = simulate(events, recheck_on_reserve=True)
        rows.append({"events": "".join(events), "snapshot_only": before, "recheck_and_reserve": after})

    assert len(rows) == 6
    assert sum(row["snapshot_only"]["exceeds_order_total"] for row in rows) == 4
    assert all(len(row["recheck_and_reserve"]["submitted"]) == 1 for row in rows)
    print(json.dumps({"kind": "offline_model_all_legal_interleavings", "cases": rows}, indent=2))


if __name__ == "__main__":
    main()
