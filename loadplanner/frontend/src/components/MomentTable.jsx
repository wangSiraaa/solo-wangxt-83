import React from "react";

function AxleBar({ name, value, limit }) {
  const pct = Math.min(100, (value / limit) * 100);
  const over = value > limit;
  return (
    <div className="axle-bar">
      <div className="axle-label">
        {name} <b className={over ? "over" : ""}>{value.toFixed(0)}</b> / {limit.toFixed(0)} kg
      </div>
      <div className="bar-track">
        <div className={`bar-fill ${over ? "over" : ""}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function MomentTable({ state }) {
  const mt = state.moment_table;
  const a = state.analysis;
  return (
    <div className="moment-panel">
      <h3>力矩核对表（对前轴取矩）</h3>
      {!a.complete && (
        <div className="incomplete-banner">
          存在未知重量或未摆放箱体：以下汇总仅覆盖已知部分，不能作为最终依据
        </div>
      )}
      {a.axle && (
        <div className="axle-bars">
          <AxleBar name="前轴" value={a.axle.front} limit={a.axle.front_limit} />
          <AxleBar name="后轴" value={a.axle.rear} limit={a.axle.rear_limit} />
          {a.lateral && (
            <div className={`lateral-line ${a.lateral.ok ? "" : "over"}`}>
              横向偏移 {a.lateral.offset_mm} mm（允许 ±{a.lateral.limit_mm}）
            </div>
          )}
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>标签</th><th>重量kg</th><th>质心x</th><th>力臂mm</th>
            <th>力矩kg·m</th><th>横向偏心</th>
          </tr>
        </thead>
        <tbody>
          {mt.rows.map((r) => (
            <tr key={r.key} className={r.weight_kg === null ? "unknown" : ""}>
              <td>{r.label}</td>
              <td>{r.weight_kg === null ? "未知" : r.weight_kg}</td>
              <td>{r.x_center_mm}</td>
              <td>{r.arm_front_axle_mm}</td>
              <td>{r.moment_kg_m === null ? "—" : r.moment_kg_m}</td>
              <td>{r.y_offset_mm}</td>
            </tr>
          ))}
          <tr className="totals">
            <td>合计（已知部分）</td>
            <td>{mt.totals.known_weight_kg}</td>
            <td>{mt.totals.cg_x_mm ?? "—"}</td>
            <td>—</td>
            <td>{mt.totals.known_moment_kg_m}</td>
            <td>{mt.totals.cg_y_mm ?? "—"}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
