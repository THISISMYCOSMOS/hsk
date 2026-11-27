import { useState } from "react";
import { display } from "./network";
export interface Candidate {
  route: string;
  eligible: boolean;
  exclusion: string | null;
  legs: { source: string; whsk_raw: string; usdt_raw: string }[];
  a_net_usdt_raw: string | null;
  a_gain_raw: string | null;
  b_gain_raw: string | null;
  fee_paid_by_A_raw: string;
}
export interface Plan {
  side: string;
  route: string;
  amount_raw: string;
  full_raw: string;
  candidates: Candidate[];
}
interface Day {
  day: string;
  buy: string;
  sell: string;
  count: number;
}
export interface Evidence {
  version: string;
  market: { matchedLogs: number; accepted: number; days: Day[] };
  scenarios: { plans: Record<string, Plan> };
  quotes: {
    block: number;
    block_hash: string;
    timestamp_utc: string;
    quotes: {
      id: string;
      kind: string;
      amount_in_raw: string;
      amount_out_raw: string;
    }[];
  };
}
const compact = (v: bigint) => (v / 1000000n).toLocaleString("en-US");
export function Market({ data }: { data: Evidence }) {
  const { days, matchedLogs } = data.market;
  const peak = days.reduce((n, r) => {
    const x = BigInt(r.buy) + BigInt(r.sell);
    return x > n ? x : n;
  }, 1n);
  const total = days.reduce((n, r) => n + BigInt(r.buy) + BigInt(r.sell), 0n);
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <small>MARKET ACTIVITY</small>
          <h2>DEX 거래대금</h2>
        </div>
        <Tag>BACKTEST</Tag>
      </div>
      <div className="metric">
        {compact(total)} <em>USDT</em>
      </div>
      <p>
        {days[0].day} — {days.at(-1)?.day} UTC · 보관 로그 {matchedLogs}건
      </p>
      <div className="chart" aria-label="날짜별 매수·매도 거래대금">
        {days.map((r) => (
          <div
            className="bar-col"
            key={r.day}
            title={
              r.day +
              " · 매수 " +
              display(r.buy) +
              " / 매도 " +
              display(r.sell) +
              " USDT"
            }
          >
            <div className="bar">
              <i
                style={{
                  height: Number((BigInt(r.sell) * 10000n) / peak) / 100 + "%",
                }}
              />
              <b
                style={{
                  height: Number((BigInt(r.buy) * 10000n) / peak) / 100 + "%",
                }}
              />
            </div>
            <span>{r.day.slice(5)}</span>
          </div>
        ))}
      </div>
      <div className="legend">
        <span>● 매수</span>
        <span>● 매도</span>
      </div>
    </section>
  );
}
export const Tag = ({ children }: { children: React.ReactNode }) => (
  <span className="tag">{children}</span>
);
const names: Record<string, string> = {
  "direct+dex": "직접 매칭 + DEX",
  dex: "DEX 단독",
  no_fill: "미체결 유지",
  rfq: "RFQ",
};
const reasons: Record<string, string> = {
  cost_exceeds_surplus: "추가 비용이 절감 가능액을 초과",
  absent: "반대 주문 없음",
  A_signed_limit: "주문자 가격 한도 미충족",
  B_signed_limit: "상대방 가격 한도 미충족",
  participant_worse_than_baseline: "사용자별 기준 견적 미달",
};
export function Simulation({ data }: { data: Evidence }) {
  const [scenario, setScenario] = useState("direct");
  const plan = data.scenarios.plans[scenario];
  return (
    <div className="panel">
      <div className="section-head">
        <div>
          <small>ROUTE COMPARISON</small>
          <h2>체결 후보 비교</h2>
        </div>
        <Tag>SYNTHETIC</Tag>
      </div>
      <label>
        검증 시나리오
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {Object.entries({
            direct: "매도 · 600 직접 매칭 + 400 DEX",
            buy_direct: "매수 · 지정 수량 확보",
            too_costly: "추가 비용 초과",
            no_opposite: "반대 주문 없음",
            no_fill: "가격 한도 미충족",
          }).map(([id, t]) => (
            <option key={id} value={id}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <dl>
        <dt>비교 수량</dt>
        <dd>{display(plan.amount_raw, 18)} WHSK</dd>
        <dt>전량 DEX 기준</dt>
        <dd>{display(plan.full_raw)} USDT</dd>
        <dt>탐색 결과</dt>
        <dd>{names[plan.route]}</dd>
      </dl>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>후보</th>
              <th>WHSK 체결량 · 경로</th>
              <th>A 수령/지출</th>
              <th>A 차이</th>
              <th>B 차이</th>
              <th>A 수수료</th>
              <th>판정</th>
            </tr>
          </thead>
          <tbody>
            {plan.candidates
              .filter((c) => c.route !== "rfq")
              .map((c) => (
                <tr key={c.route}>
                  <th>{names[c.route]}</th>
                  <td>
                    {c.legs
                      .map(
                        (l) =>
                          display(l.whsk_raw, 18) +
                          " " +
                          (l.source === "fixed_DEX" ? "DEX" : "직접"),
                      )
                      .join(" + ") || "0"}
                  </td>
                  <td>{display(c.a_net_usdt_raw)}</td>
                  <td>{display(c.a_gain_raw)}</td>
                  <td>{display(c.b_gain_raw)}</td>
                  <td>{display(c.fee_paid_by_A_raw)}</td>
                  <td>
                    {c.exclusion
                      ? reasons[c.exclusion] || c.exclusion
                      : c.route === plan.route
                        ? "선택"
                        : "대안"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p>
        금액 단위 USDT. 고정 견적과 모의 수수료를 적용했습니다. 실제
        가스비·운영비·실현 순절감액은 미측정입니다.
      </p>
    </div>
  );
}
export function Analytics({ data }: { data: Evidence }) {
  return (
    <>
      <Market data={data} />
      <section className="panel">
        <div className="section-head">
          <h2>보관 블록 견적 재현</h2>
          <Tag>BACKTEST</Tag>
        </div>
        <p>
          블록 {data.quotes.block} · {data.quotes.timestamp_utc}
        </p>
        <code>{data.quotes.block_hash}</code>
        <dl>
          {data.quotes.quotes.map((q) => (
            <div className="dlrow" key={q.id}>
              <dt>{q.id}</dt>
              <dd>
                {q.kind === "exact_input"
                  ? display(q.amount_in_raw, 18) +
                    " WHSK → " +
                    display(q.amount_out_raw) +
                    " USDT"
                  : display(q.amount_in_raw) +
                    " USDT → " +
                    display(q.amount_out_raw, 18) +
                    " WHSK"}
              </dd>
            </div>
          ))}
        </dl>
        <p>
          보관 로그 {data.market.matchedLogs}건 중 기존 분석 조건에 맞는 건은{" "}
          {data.market.accepted}건입니다. 가상 주문 매칭률과 월간 실현 절감액은
          미측정입니다.
        </p>
      </section>
    </>
  );
}
