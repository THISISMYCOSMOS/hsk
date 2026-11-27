"""Exercise the retained synthetic routes and check per-user cash and quantities."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "scripts"))
from integration.replay import replay

plans = replay()["scenarios"]["plans"]
for name, expected in (("direct","direct+dex"),("too_costly","dex"),("no_opposite","dex"),("no_fill","no_fill")):
    p = plans[name]
    assert p["route"] == expected
    chosen = next(c for c in p["candidates"] if c["route"] == expected)
    print(json.dumps(dict(source="SYNTHETIC", scenario=name, route=expected, legs=chosen["legs"],
                          sellerOrTakerDifferenceUSDT=chosen["a_gain_raw"], makerDifferenceUSDT=chosen["b_gain_raw"],
                          receipt=None),ensure_ascii=False))
