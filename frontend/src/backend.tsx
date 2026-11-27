import { useEffect, useState } from "react";
import type { Address, Hex } from "viem";
import { api, signLocal, type LocalOrder } from "./engine";
import { AgentQuery } from "./AgentQuery";
import { LocalOrderForm } from "./LocalOrder";
import { display } from "./network";
import { message } from "./wallet";
import { Tag } from "./evidence";
type OrderView = {
  orderId: Hex;
  order: LocalOrder;
  remaining: string;
  status: string;
};
type Event = {
  id: number;
  at: number;
  kind: string;
  payload: {
    orderId?: string;
    quoteId?: string;
    reason?: string;
    executionId?: string;
  };
};
type Receipt = {
  mode: string;
  evidence: string;
  transactionHash: string | null;
  gasUnits: string;
  walletDeltas: {
    maker: string;
    token: string;
    change: string;
    debited: string;
  }[];
  participants: {
    orderId: string;
    fixed?: string;
    spent?: string;
    received?: string;
    feeUSDT?: string;
    cumulativeWHSK?: string;
    benchmarkUSDT?: string;
  }[];
};
type Execution = { id: number; status: string; receipt: Receipt | null };
type Info = { mode: string; broadcastEnabled: boolean; lastError?: string };
interface Candidate {
  kind: string;
  fixedFilled: string;
  remaining: string;
  dexFixed: string;
  eligible: boolean;
  reason: string | null;
  savings: {
    orderId: string;
    conservativeSaving: string;
    gross: string;
    dexGross: string;
    costs: Record<string, string>;
  }[];
}
type Comparison = {
  comparison: {
    evidence: string;
    blockHash: string;
    blockNumber: string;
    truncated: boolean;
    candidates: Candidate[];
    selected: Candidate | null;
  };
};
const short = (s: string) => s.slice(0, 8) + "…" + s.slice(-4);
function Candidates({ result }: { result: Comparison }) {
  const r = result.comparison;
  return (
    <div>
      <h3>체결 후보 · {r.evidence}</h3>
      <p>
        기준 블록 {r.blockNumber} · {short(r.blockHash)} · 탐색 결과{" "}
        {r.selected?.kind || "미선택"}
        {r.truncated ? " · 탐색 한도 도달" : ""}
      </p>
      {r.candidates.map((c, i) => (
        <details key={i}>
          <summary>
            {c.kind} · {display(c.fixedFilled, 18)} WHSK ·{" "}
            {c.eligible ? "조건 충족" : c.reason}
          </summary>
          <p>
            직접{" "}
            {display(
              (BigInt(c.fixedFilled) - BigInt(c.dexFixed)).toString(),
              18,
            )}{" "}
            / DEX {display(c.dexFixed, 18)} / 잔량 {display(c.remaining, 18)}{" "}
            WHSK
          </p>
          {c.savings.map((s) => (
            <div key={s.orderId}>
              <code>{s.orderId}</code>
              <p>
                기준 {display(s.dexGross)} · 경로 {display(s.gross)} · 보수적
                순절감액 {display(s.conservativeSaving)} USDT
              </p>
              <p>
                {Object.entries(s.costs)
                  .map(([k, v]) => k + " " + display(v))
                  .join(" / ")}{" "}
                USDT
              </p>
            </div>
          ))}
        </details>
      ))}
    </div>
  );
}
export function BackendView({
  section,
  account,
  chain,
}: {
  section: string;
  account: Address | null;
  chain: number | null;
}) {
  const [info, setInfo] = useState<Info | null>(null),
    [orders, setOrders] = useState<OrderView[]>([]),
    [events, setEvents] = useState<Event[]>([]),
    [execs, setExecs] = useState<Execution[]>([]);
  const [problem, setProblem] = useState(""),
    [readError, setReadError] = useState(""),
    [comp, setComp] = useState<Comparison | null>(null),
    [revision, refresh] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let stream: EventSource | undefined;
    async function read() {
      try {
        const status = await api<Info>(
          "/agent/status",
          undefined,
          abort.signal,
        );
        if (abort.signal.aborted) return;
        setInfo(status);
        if (section === "Orderbook")
          setOrders(await api<OrderView[]>("/orders", undefined, abort.signal));
        if (section === "Execution History")
          setExecs(
            await api<Execution[]>("/executions", undefined, abort.signal),
          );
        if (section === "Agent Activity" && !stream) {
          stream = new EventSource("/engine/agent/events/stream");
          stream.onopen = () => setReadError("");
          stream.onmessage = (m) => {
            try {
              const row: Event = JSON.parse(m.data);
              setEvents((prev) =>
                prev.some((e) => e.id === row.id)
                  ? prev
                  : [row, ...prev].sort((a, b) => b.id - a.id).slice(0, 150),
              );
            } catch {
              setReadError("이벤트 형식 오류");
            }
          };
          stream.onerror = () =>
            setReadError("이벤트 스트림 연결 중단 · 재연결 대기");
        }
        if (section !== "Agent Activity") setReadError("");
      } catch (e) {
        if (!abort.signal.aborted) {
          setInfo(null);
          setReadError(message(e));
        }
      }
      if (!abort.signal.aborted) timer = setTimeout(read, 4000);
    }
    void read();
    return () => {
      abort.abort();
      clearTimeout(timer);
      stream?.close();
    };
  }, [section, revision]);
  async function action(f: () => Promise<void>) {
    setProblem("");
    try {
      await f();
    } catch (e) {
      setProblem(message(e));
    }
  }
  const comparison = (path: string, body?: unknown) =>
    action(async () => setComp(await api<Comparison>(path, body)));
  if (section === "Local Order")
    return (
      <LocalOrderForm
        key={String(account) + chain}
        account={account}
        chain={chain}
      />
    );
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{section}</h2>
        <Tag>
          {info?.mode === "MOCK"
            ? "SYNTHETIC · MOCK"
            : info?.mode || "UNVERIFIED"}
        </Tag>
      </div>
      {readError && (
        <p role="alert" className="error">
          {readError}
        </p>
      )}
      {info?.lastError && <p className="error">{info.lastError}</p>}
      {section === "Orderbook" && (
        <>
          <p>
            오프체인 취소는 Agent B의 주문 접수를 종료합니다. 온체인 무효화는
            별도 정산 컨트랙트 호출이 필요합니다.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  {[
                    "주문 ID",
                    "방향",
                    "등록 WHSK",
                    "누적 체결",
                    "잔여 WHSK",
                    "USDT 한도",
                    "만료 UTC",
                    "상태",
                    "작업",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((r) => (
                  <tr key={r.orderId}>
                    <td title={r.orderId}>{short(r.orderId)}</td>
                    <td>{r.order.kind === "EXACT_IN" ? "매도" : "매수"}</td>
                    <td>{display(r.order.fixedAmount, 18)}</td>
                    <td>
                      {display(
                        (
                          BigInt(r.order.fixedAmount) - BigInt(r.remaining)
                        ).toString(),
                        18,
                      )}
                    </td>
                    <td>{display(r.remaining, 18)}</td>
                    <td>{display(r.order.limitAmount)}</td>
                    <td>
                      {new Date(Number(r.order.expiry) * 1000).toISOString()}
                    </td>
                    <td>{r.status}</td>
                    <td>
                      {r.status === "OPEN" && (
                        <>
                          <button
                            onClick={() =>
                              void comparison("/quotes", { orderId: r.orderId })
                            }
                          >
                            후보 비교
                          </button>
                          {account?.toLowerCase() ===
                            r.order.maker.toLowerCase() && (
                            <button
                              disabled={
                                chain !== 31337 ||
                                !["MOCK", "FORK"].includes(info?.mode || "")
                              }
                              onClick={() =>
                                void action(async () => {
                                  const { signature } = await signLocal(
                                    account!,
                                    r.orderId,
                                  );
                                  await api(
                                    "/orders/" + r.orderId + "/cancel",
                                    { signature },
                                  );
                                  refresh((n) => n + 1);
                                })
                              }
                            >
                              오프체인 취소
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {info && !orders.length && <p>등록된 주문이 없습니다.</p>}
        </>
      )}
      {section === "Agent Activity" && (
        <>
          <AgentQuery />
          {!events.length && info && <p>새 이벤트 대기 중</p>}
          {events.map((e) => (
            <div className="event" key={e.id}>
              <code>
                #{e.id} · {new Date(e.at * 1000).toISOString()}
              </code>
              <h3>{e.kind}</h3>
              {e.payload.orderId && <code>{e.payload.orderId}</code>}{" "}
              {e.payload.reason}{" "}
              {e.payload.quoteId && (
                <button
                  onClick={() =>
                    void comparison("/quotes/" + e.payload.quoteId)
                  }
                >
                  후보 #{e.payload.quoteId}
                </button>
              )}
            </div>
          ))}
        </>
      )}
      {section === "Execution History" && (
        <>
          {info && !execs.length && <p>기록된 실행이 없습니다.</p>}
          {execs.map((e) => (
            <div className="review" key={e.id}>
              <h3>
                #{e.id} · {e.status}
              </h3>
              {e.receipt && (
                <>
                  <Tag>{e.receipt.evidence}</Tag>
                  <p>
                    {e.receipt.mode === "FORK"
                      ? "포크 영수증 가스 사용량"
                      : "모의 가스 단위"}{" "}
                    {e.receipt.gasUnits} · 실제 L1/L2 수수료, 승인 비용, 실현
                    절감액 미측정
                  </p>
                  <p>거래 해시 {e.receipt.transactionHash || "없음"}</p>
                  {e.receipt.mode === "FORK" &&
                    e.receipt.participants.map((p) => (
                      <p key={p.orderId}>
                        주문 {short(p.orderId)} · 지출 {p.spent} / 수령{" "}
                        {p.received} (각 토큰 최소 단위) · 누적 체결{" "}
                        {display(p.cumulativeWHSK || "0", 18)} WHSK · 수수료{" "}
                        {display(p.feeUSDT ?? null)} USDT
                      </p>
                    ))}
                  {e.receipt.walletDeltas.map((w, i) => (
                    <p key={i}>
                      {short(w.maker)} ·{" "}
                      {w.token.toLowerCase().startsWith("0xb210")
                        ? display(w.change, 18) + " WHSK"
                        : display(w.change) + " USDT"}
                    </p>
                  ))}
                </>
              )}
              <button
                onClick={() =>
                  void comparison("/executions/" + e.id + "/comparison")
                }
              >
                사용자별 비용 및 경로
              </button>
            </div>
          ))}
        </>
      )}
      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}
      {comp && <Candidates result={comp} />}
    </section>
  );
}
