"""Run after forge build, from any directory."""

from pathlib import Path
import json

root = Path(__file__).resolve().parents[2]
artifact = json.loads(
    (root / "contracts/out/Settlement.sol/Settlement.json").read_text()
)
(root / "shared/abi/Settlement-v1.json").write_text(
    json.dumps(artifact["abi"], indent=2) + "\n"
)
build = dict(
    contract="Settlement",
    version="1",
    compiler=artifact["metadata"]["compiler"],
    settings=artifact["metadata"]["settings"],
    creationBytecode=artifact["bytecode"]["object"],
    methodIdentifiers=artifact["methodIdentifiers"],
)
(root / "shared/abi/Settlement-v1.build.json").write_text(
    json.dumps(build, indent=2) + "\n"
)
