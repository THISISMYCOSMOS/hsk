import { useEffect, useState } from "react";
import { Tag } from "./evidence";
import { display } from "./network";
import { message } from "./wallet";
interface Day {
  day: string;
  buy: string;
  sell: string;
  count: number;
}
interface Observed {
  operations: {
    mode: string;
    worker_evaluations: number;
    market_loads: number;
    ai_calls: number;
    live_rpc_calls: number;
  }[];
  modeledEconomics: {
    baseline: string;
    fresh_approvals: boolean;
    operator_cost_upper_raw: string;
    combined_modeled_lower_raw: string;
    no_trade_per_success: number;
    expired_reverts_per_success: number;
    operator_break_even_bps_on_direct_cash: number;
  }[];
  source: string;
  start: string;
  end: string;
  block: string;
  hash: string;
  pool: string;
  matchedLogs: number;
  days: Day[];
  fees: { l1_fee_wei: { p50: string }; l2_execution_wei: { p50: string } };
  poolMetrics: {
    usdt_notional_raw: string;
    internal_gap_seconds: { p50: string; max: string };
    usdt_trade_size_raw: { p50: string };
    directions: Record<string, { events: number; token1_volume_raw: string }>;
  };
  scenarios: {
    hours: number;
    participation_pct: number;
    limit_bps: number;
    orders: number;
    orders_with_fill: number;
    direct_usdt_once_raw: string;
    partial: boolean;
    max_makers: number;
    delay_seconds: number;
    min_saving_each_usdt_raw: string;
    assumed_approval_cost_each_fill_usdt_raw: string;
    margin_each_fill_usdt_raw: string;
  }[];
}
interface Fork {
  source: string;
  sourceBlock: string;
  sourceHash: string;
  contract: string;
  cases: Record<
    string,
    {
      local_tx_hash: string;
      gas_used: string;
      payer: string;
      quoter_subcalls_gas: string;
      block: string | null;
      wallet_deltas: Record<string, { WHSK: string; USDT: string }>;
    }
  >;
  approvals: { gas_used: string; payer: string }[];
}
function useReport<T>(name: string) {
  const [result, set] = useState<T | null>(null),
    [error, problem] = useState("");
  useEffect(() => {
    const ctrl = new AbortController();
    fetch("/evidence/" + name + ".json", { signal: ctrl.signal })
      .then((r) => {
        if (!r.ok || !r.headers.get("content-type")?.includes("json"))
          throw Error("검증 보고서 없음");
        return r.json();
      })
      .then(set)
      .catch((e) => {
        if (!ctrl.signal.aborted) problem(message(e));
      });
    return () => ctrl.abort();
  }, [name]);
  return { result, error };
}
export function Observations() {
  const { result: r, error } = useReport<Observed>("market-30d");
  const [scenario, setScenario] = useState(0);
  if (!r) return <p>{error || "시장 관측 자료 읽는 중…"}</p>;
  const m = r.poolMetrics,
    s = r.scenarios[scenario],
    biggest = r.days.reduce((n, d) => {
      const sum = BigInt(d.buy) + BigInt(d.sell);
      return sum > n ? sum : n;
    }, 1n);
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <small>MARKET OBSERVATIONS</small>
          <h2>WHSK / USDT · 30일 거래대금</h2>
        </div>
        <Tag>{r.source}</Tag>
      </div>
      <div className="metric">
        {display(m.usdt_notional_raw)} <em>USDT</em>
      </div>
      <p>
        {r.start.slice(0, 10)} — {r.end.slice(0, 10)} UTC ·{" "}
        {r.matchedLogs.toLocaleString()}건 ·{" "}
        <a
          href={"https://hsk.blockscout.com/block/" + r.hash}
          target="_blank"
          rel="noreferrer"
        >
          기준 블록 {r.block} ↗
        </a>
      </p>
      <div className="chart observed" aria-label="관측 일자별 USDT 거래대금">
        {r.days.map((d, i) => (
          <div
            className="bar-col"
            key={d.day}
            title={
              d.day +
              " · 매수 " +
              display(d.buy) +
              " / 매도 " +
              display(d.sell) +
              " USDT"
            }
          >
            <div className="bar">
              <i
                style={{
                  height:
                    Number((BigInt(d.sell) * 10000n) / biggest) / 100 + "%",
                }}
              />
              <b
                style={{
                  height:
                    Number((BigInt(d.buy) * 10000n) / biggest) / 100 + "%",
                }}
              />
            </div>
            <span>{i % 7 === 0 ? d.day.slice(5) : " "}</span>
          </div>
        ))}
      </div>
      <div className="legend">
        <span>● 매수</span>
        <span>● 매도</span>
      </div>
      <dl>
        <dt>매수 / 매도 건수</dt>
        <dd>
          {m.directions.buy_token0.events} / {m.directions.sell_token0.events}
        </dd>
        <dt>건당 거래대금 중앙값</dt>
        <dd>{display(m.usdt_trade_size_raw.p50)} USDT</dd>
        <dt>체결 간격 중앙값 / 최대</dt>
        <dd>
          {m.internal_gap_seconds.p50} / {m.internal_gap_seconds.max}초
        </dd>
        <dt>기존 거래 전체 L1 / L2 수수료 중앙값</dt>
        <dd>
          {display(r.fees.l1_fee_wei.p50, 18)} /{" "}
          {display(r.fees.l2_execution_wei.p50, 18)} HSK
        </dd>
      </dl>
      <h3>
        사전 주문 시나리오 <Tag>BACKTEST</Tag>
      </h3>
      <label>
        가상 주문 조건
        <select
          value={scenario}
          onChange={(e) => setScenario(Number(e.target.value))}
        >
          {r.scenarios.map((v, i) => (
            <option key={i} value={i}>
              {v.hours}시간 · 참여 {v.participation_pct}% · 한도 {v.limit_bps}bp
              · 상대 최대 {v.max_makers} · 지연 {v.delay_seconds}초 · 부분{" "}
              {v.partial ? "허용" : "차단"} · 최소절감{" "}
              {display(v.min_saving_each_usdt_raw)} USDT · 승인{" "}
              {display(v.assumed_approval_cost_each_fill_usdt_raw)} · 마진{" "}
              {display(v.margin_each_fill_usdt_raw)}
            </option>
          ))}
        </select>
      </label>
      <dl>
        <dt>가상 주문 중 일부 이상 매칭</dt>
        <dd>
          {s.orders_with_fill} / {s.orders}건
        </dd>
        <dt>직접 매칭 거래대금</dt>
        <dd>{display(s.direct_usdt_once_raw)} USDT</dd>
        <dt>실현 순절감액 / 운영자 순이익</dt>
        <dd>미측정</dd>
      </dl>
      <h3>
        운영 비용 비교 <Tag>BACKTEST</Tag>
      </h3>
      <p>
        같은 24시간 이벤트 재생 · 관측된 112건에 가상 주문을 적용한 Agent A
        실험입니다.
      </p>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>실행 방식</th>
              <th>재평가</th>
              <th>시장 로드</th>
              <th>실제 RPC</th>
              <th>LLM</th>
            </tr>
          </thead>
          <tbody>
            {r.operations.map((o) => (
              <tr key={o.mode}>
                <td>{o.mode}</td>
                <td>{o.worker_evaluations}</td>
                <td>{o.market_loads}</td>
                <td>{o.live_rpc_calls}</td>
                <td>{o.ai_calls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>부분 매칭 비용 모델 · 기준 블록 30,592,078</summary>
        <p>
          각 행은 정산·승인·가스비 환산과 운영비 가정을 적용한 Agent A
          보고값입니다. 실패/미체결 횟수는 성공 1건당 가정입니다.
        </p>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                {[
                  "순차 DEX 기준",
                  "신규 승인",
                  "미체결 / 실패",
                  "운영비 상한 USDT",
                  "전체 추정 하한 USDT",
                  "손익분기 bp",
                ].map((x) => (
                  <th key={x}>{x}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.modeledEconomics.map((s, i) => (
                <tr key={i}>
                  <td>{s.baseline}</td>
                  <td>{s.fresh_approvals ? "포함" : "기승인"}</td>
                  <td>
                    {s.no_trade_per_success} / {s.expired_reverts_per_success}
                  </td>
                  <td>{display(s.operator_cost_upper_raw)}</td>
                  <td>{display(s.combined_modeled_lower_raw)}</td>
                  <td>{s.operator_break_even_bps_on_direct_cash}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
const names: Record<string, string> = {
  direct: "전량 직접 매칭",
  partial: "부분 매칭 + DEX",
  multi: "복수 주문 매칭",
  no_trade: "경제성 부족",
  fallback: "허용된 DEX fallback",
  cancel: "온체인 취소",
  expired: "만료 주문 거부",
};
export function ForkHistory() {
  const { result: r, error } = useReport<Fork>("settlement-fork"),
    [name, setName] = useState("partial");
  if (!r) return <p>{error || "포크 영수증 읽는 중…"}</p>;
  const c = r.cases[name];
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <small>SETTLEMENT VERIFICATION</small>
          <h2>포크 정산 영수증</h2>
        </div>
        <Tag>{r.source}</Tag>
      </div>
      <label>
        정산 검증 경로
        <select value={name} onChange={(e) => setName(e.target.value)}>
          {Object.keys(r.cases).map((k) => (
            <option key={k} value={k}>
              {names[k] || k}
            </option>
          ))}
        </select>
      </label>
      <dl>
        <dt>HSK 원본 블록</dt>
        <dd>
          <a
            href={"https://hsk.blockscout.com/block/" + r.sourceHash}
            target="_blank"
            rel="noreferrer"
          >
            {r.sourceBlock} ↗
          </a>
        </dd>
        <dt>포크 체인 / 로컬 블록</dt>
        <dd>31337 / {c.block || "미수집"}</dd>
        <dt>정산 계약</dt>
        <dd>
          <code>{r.contract}</code>
        </dd>
        <dt>포크 거래 해시</dt>
        <dd>
          <code>{c.local_tx_hash}</code>
        </dd>
        <dt>가스 사용량 / Quoter 호출</dt>
        <dd>
          {c.gas_used} / {c.quoter_subcalls_gas} gas
        </dd>
        <dt>가스 부담자</dt>
        <dd>
          <code>{c.payer}</code>
        </dd>
        <dt>별도 토큰 승인</dt>
        <dd>{r.approvals.map((a) => a.gas_used).join(" / ")} gas</dd>
        <dt>실현 순절감액 · 실제 메인넷 비용</dt>
        <dd>미측정</dd>
      </dl>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>포크 지갑</th>
              <th>WHSK 변화량</th>
              <th>USDT 변화량</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(c.wallet_deltas).map(([actor, d]) => (
              <tr key={actor}>
                <td title={actor}>
                  {actor.slice(0, 10)}…{actor.slice(-4)}
                </td>
                <td>{display(d.WHSK, 18)}</td>
                <td>{display(d.USDT)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        포크에서 만든 시연 주문입니다. 가스 사용량과 토큰 변화량은 해당 로컬
        실행에서 측정했습니다.
      </p>
    </section>
  );
}
