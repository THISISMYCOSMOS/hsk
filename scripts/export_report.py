"""Export the archive replay and attach independently identified integration evidence."""
import json
import sys
from pathlib import Path
from integration.replay import ROOT, PUBLIC, replay, write

if __name__ == "__main__":
    out=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/"reports/agent-d/integration.json"
    report=replay()
    docs=ROOT/"docs/agents/agent-d"
    refs={"mainnetQuote":docs/"observed-quote.json","market30Days":PUBLIC/"market-30d.json",
          "forkContracts":PUBLIC/"settlement-fork.json","forkBrowserOrder":docs/"browser-fork.json"}
    report["integrationEvidence"]={key:json.loads(path.read_text()) for key,path in refs.items()}
    write(out,report)
    print(out)
