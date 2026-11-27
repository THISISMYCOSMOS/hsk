import { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { Observations, ForkHistory } from "./Reports";
import { Trade } from "./Trade";
import { Analytics, Simulation, Tag, type Evidence } from "./evidence";
import { useWallet, message } from "./wallet";
import { BackendView } from "./backend";
import "./style.css";
const tabs = [
  "Trade",
  "Orderbook",
  "Agent Activity",
  "Execution History",
  "Analytics & Verification",
  "Demo Mode",
] as const;
type Page = (typeof tabs)[number];
const titles: Record<Page, string> = {
  Trade: "거래 워크스페이스",
  Orderbook: "주문장",
  "Agent Activity": "에이전트 활동",
  "Execution History": "체결 내역",
  "Analytics & Verification": "시장 및 검증",
  "Demo Mode": "로컬 데모",
};
function activePage(): Page {
  return (
    tabs.find((t) => encodeURIComponent(t) === location.hash.slice(1)) ||
    "Trade"
  );
}
function App() {
  const [page, setPage] = useState<Page>(activePage),
    [data, setData] = useState<Evidence | null>(null),
    [error, setError] = useState("");
  const wallet = useWallet();
  const [engineMode, setEngineMode] = useState("UNVERIFIED");
  useEffect(() => {
    const abort = new AbortController();
    fetch("/engine/agent/status", { signal: abort.signal })
      .then((r) => r.json())
      .then((v) =>
        setEngineMode(
          v.mode === "FORK"
            ? "FORK_SIMULATION"
            : v.mode === "MOCK"
              ? "SYNTHETIC · MOCK"
              : "UNVERIFIED",
        ),
      )
      .catch(() => {});
    return () => abort.abort();
  }, [page]);
  const marketPage = page === "Trade" || page === "Analytics & Verification";

  useEffect(() => {
    const fn = () => setPage(activePage());
    window.addEventListener("hashchange", fn);
    return () => window.removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/evidence/replay.json", { signal: abort.signal })
      .then((r) => {
        if (!r.ok) throw Error("재현 데이터 없음 · make backtest");
        return r.json();
      })
      .then((d) => {
        if (d.version !== "agent-d-replay/1")
          throw Error("재현 데이터 버전 불일치");
        setData(d);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(message(e));
      });
    return () => abort.abort();
  }, []);
  return (
    <>
      <header>
        <div className="brand">
          <b className="logo">H</b>
          <span>
            HSK <strong>Smart Execution</strong>
          </span>
        </div>
        <button onClick={wallet.toggle}>
          {wallet.account
            ? wallet.account.slice(0, 6) +
              "…" +
              wallet.account.slice(-4) +
              " · 해제"
            : "지갑 연결"}
        </button>
      </header>
      <div className="shell">
        <aside>
          <small>WORKSPACE</small>
          <nav>
            {tabs.map((t, i) => (
              <a
                key={t}
                href={"#" + encodeURIComponent(t)}
                aria-current={t === page ? "page" : undefined}
              >
                <span aria-hidden>{["⇄", "▤", "⌁", "◷", "▥", "▷"][i]}</span>
                {t}
              </a>
            ))}
          </nav>
          <div className="network">
            <i /> {marketPage ? "HashKey Chain" : "Local engine"}{" "}
            <b>{marketPage ? "177" : "31337"}</b>
          </div>
        </aside>
        <main>
          <div className="page-head">
            <div>
              <small>Verification-based AI Optimal Execution Agent</small>
              <h1>{titles[page]}</h1>
            </div>
            <Tag>
              {page === "Analytics & Verification"
                ? "관측 및 백테스트"
                : page === "Trade"
                  ? "MAINNET · READ_ONLY"
                  : engineMode}
            </Tag>
          </div>
          {wallet.error && (
            <p className="error" role="alert">
              {wallet.error}
            </p>
          )}
          {wallet.account && (
            <section className="wallet">
              <code>{wallet.account}</code>
              <span>Chain {wallet.chain}</span>
              {wallet.chain !== 177 && page === "Trade" ? (
                <button onClick={wallet.switchChain}>HashKey Chain 전환</button>
              ) : wallet.chain === 177 ? (
                <span>
                  HSK / WHSK / USDT ·{" "}
                  {wallet.holdings.length
                    ? wallet.holdings.join(" / ")
                    : "잔액 조회 중 또는 미확인"}
                </span>
              ) : null}
            </section>
          )}
          {page === "Trade" ? (
            <>
              <Trade />
              <Observations />
            </>
          ) : page === "Analytics & Verification" ? (
            <>
              <Observations />
              {data && <Analytics data={data} />}
            </>
          ) : page === "Demo Mode" ? (
            <>
              {data && <Simulation data={data} />}
              <BackendView
                section="Local Order"
                account={wallet.account}
                chain={wallet.chain}
              />
            </>
          ) : (
            <>
              <BackendView
                key={page}
                section={page}
                account={wallet.account}
                chain={wallet.chain}
              />
              {page === "Execution History" && <ForkHistory />}
            </>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </main>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
