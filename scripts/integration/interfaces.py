"""Validate A/B/C-owned artifacts without publishing a second shared schema."""
import json
import subprocess
import sys
from paths import ROOT,role


def main():
    b,c=role("B"),role("C")
    sys.path.insert(0,str(b))
    from backend.app.schemas import results, orders
    from backend.app.orderbook.signatures import recover,typed_data
    fixtures=json.loads((b/"shared/engine-0.1/fixtures.json").read_text())
    schemas=json.loads((b/"shared/engine-0.1/schemas.json").read_text())["$defs"]
    names=("Order","SignedOrder","MarketSnapshot","DexQuote","ExecutionCandidate","ExecutionPlan",
           "CostBreakdown","UserSavings","SimulationResult","ExecutionReceipt","AgentEvent")
    for name in names:
        cls=getattr(orders,name,None) or getattr(results,name)
        if name not in schemas:
            raise ValueError(f"published schema missing {name}")
        cls.model_validate(fixtures["examples"][name])
    for signed in fixtures["signedOrders"]:
        order=orders.Order.model_validate(signed["order"])
        recover(typed_data(order),signed["signature"],order.maker)
    subprocess.run(["node",str(ROOT/"scripts/integration/check-vectors.cjs"),
                    str(c/"data/fixtures/contract/order-vectors-v1.json"),
                    str(b/"shared/engine-0.1/fixtures.json")],check=True)
    print("11 published B projections, signed fixtures and C Settlement v1 vectors validated")

if __name__=="__main__":
    main()
