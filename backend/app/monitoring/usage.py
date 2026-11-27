from collections import Counter
from threading import Lock


class Usage:
    def __init__(self):
        self.methods = Counter()
        self.lock = Lock()

    def provider(self):
        try:
            from backend.app.market_data.provider import MarketData
            from backend.app.blockchain.rpc import RPC
        except ImportError as exc:
            raise RuntimeError("AGENT_A_PROVIDER_UNAVAILABLE") from exc

        class MeteredRPC(RPC):
            def batch(rpc, calls):
                with self.lock:
                    self.methods.update(m for m, _ in calls)
                return super().batch(calls)

        return MarketData(MeteredRPC())

    def snapshot(self):
        with self.lock:
            return dict(self.methods)
