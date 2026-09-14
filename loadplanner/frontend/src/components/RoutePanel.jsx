import React, { useEffect, useState } from "react";

const DOOR_NAMES = { rear: "尾门", side: "侧门" };

function StopEditor({ stops, onSave, busy }) {
  const [draft, setDraft] = useState(stops);
  useEffect(() => setDraft(stops), [stops]);

  const update = (i, patch) =>
    setDraft(draft.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  const toggleAccess = (i, kind) => {
    const cur = new Set(draft[i].access);
    cur.has(kind) ? cur.delete(kind) : cur.add(kind);
    update(i, { access: [...cur] });
  };

  return (
    <div className="stop-editor">
      {draft.map((s, i) => (
        <div key={i} className={`stop-row ${s.cancelled ? "cancelled" : ""}`}>
          <span className="seq">#{s.seq}</span>
          <input value={s.name} onChange={(e) => update(i, { name: e.target.value })} />
          <label><input type="checkbox" checked={s.access.includes("rear")}
            onChange={() => toggleAccess(i, "rear")} />尾门</label>
          <label><input type="checkbox" checked={s.access.includes("side")}
            onChange={() => toggleAccess(i, "side")} />侧门</label>
          <label><input type="checkbox" checked={!!s.cancelled}
            onChange={(e) => update(i, { cancelled: e.target.checked })} />取消</label>
          <button className="ghost" onClick={() => setDraft(draft.filter((_, k) => k !== i))}>✕</button>
        </div>
      ))}
      <div className="btn-row">
        <button className="ghost" onClick={() =>
          setDraft([...draft, {
            seq: draft.length ? Math.max(...draft.map((s) => s.seq)) + 1 : 1,
            name: `站点${draft.length + 1}`, access: ["rear"], cancelled: false,
          }])}>+ 站点</button>
        <button disabled={busy} onClick={() => onSave(draft)}>保存站点设置</button>
      </div>
    </div>
  );
}

export default function RoutePanel({ stops, route, routeError, stageIdx, onStage, onSaveStops, busy }) {
  const stage = stageIdx != null && route ? route.stages[stageIdx] : null;
  return (
    <div className="route-panel">
      <h3>站点与线路</h3>
      <StopEditor stops={stops} onSave={onSaveStops} busy={busy} />
      {routeError && <div className="route-error">{routeError}</div>}
      {route && (
        <>
          <div className={`route-verdict ${route.valid ? "ok" : "bad"}`}>
            {route.valid ? "整程有效" : "整程无效（任一中间状态失败即无效）"}
            <span className="moves-total">总倒箱 {route.total_moves} 次</span>
          </div>
          <div className="stage-stepper">
            {route.stages.map((s, i) => (
              <button key={i}
                className={`stage-btn ${s.valid ? "ok" : "bad"} ${stageIdx === i ? "active" : ""}`}
                onClick={() => onStage(stageIdx === i ? null : i)}>
                {s.seq === 0 ? "初始" : `#${s.seq}`}
              </button>
            ))}
            {stageIdx != null && (
              <button className="ghost" onClick={() => onStage(null)}>退出回放</button>
            )}
          </div>
          {stage && (
            <div className="stage-detail">
              <b>{stage.name}</b>
              {stage.unloaded_labels.length > 0 && (
                <div>卸下：{stage.unloaded_labels.join("、")}</div>
              )}
              {stage.moves.map((m) => (
                <div key={m.key} className="move-line">
                  「{m.label}」经{DOOR_NAMES[m.door]}取出，倒箱 {m.count} 次
                  {m.count > 0 && `（先搬移：${m.blockers.map((b) => b.label).join("、")}）`}
                </div>
              ))}
              {stage.axle && (
                <div className="stage-axle">
                                  前轴 {stage.axle.front.toFixed(0)}/{stage.axle.front_limit.toFixed(0)} kg ·
                  后轴 {stage.axle.rear.toFixed(0)}/{stage.axle.rear_limit.toFixed(0)} kg
                </div>
              )}
              {stage.violations.filter((v) => v.severity === "error").map((v, i) => (
                <div key={i} className="violation error"><span className="vmsg">{v.message}</span></div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
