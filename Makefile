PYTHON ?= python3
.PHONY: setup dev test test-fork demo-local backtest export-report
setup:
	$(PYTHON) scripts/integration/setup.py
	cd frontend && npm ci --no-audit --no-fund
	$(PYTHON) scripts/integration/replay.py
	cd frontend && npm run build
dev:
	$(PYTHON) scripts/integration/dev.py
test:
	cd frontend && npm run build && npm test
	$(PYTHON) scripts/integration/contract_test.py
	$(PYTHON) scripts/integration/role_tests.py
test-fork:
	$(PYTHON) scripts/integration/fork.py
	$(PYTHON) scripts/integration/settlement_fork.py
	$(PYTHON) scripts/integration/role_tests.py --fork
demo-local:
	$(PYTHON) scripts/demo/local.py
backtest:
	$(PYTHON) scripts/integration/replay.py
export-report:
	$(PYTHON) scripts/export_report.py

.PHONY: dev-fork market-report
dev-fork:
	.runtime/venv/bin/python scripts/integration/fork_app.py
market-report:
	$(PYTHON) scripts/integration/market_report.py

.PHONY: interfaces record-demo
interfaces:
	.runtime/venv/bin/python scripts/integration/interfaces.py
record-demo:
	node scripts/demo/record.cjs

.PHONY: package
package:
	$(PYTHON) scripts/integration/package.py
