import React, { useState } from "react";

const ORIENT_LABELS = {
  0: "正放", 1: "正放·转90°", 2: "侧放", 3: "侧放·转90°", 4: "立放", 5: "立放·转90°",
};

function PlacementEditor({ row, onLock, onRemove, busy }) {
  const p = row.placement;
  const [form, setForm] = useState({
    x: p?.x ?? 0, y: p?.y ?? 0, z: p?.z ?? 0, orientation: p?.orientation ?? 0,
  });
  const set = (k) => (e) => setForm({ ...form, [k]: Number(e.target.value) });

  return (
    <div className="placement-editor">
      <div className="coord-inputs">
        {["x", "y", "z"].map((k) => (
          <label key={k}>
            {k}
            <input type="number" min="0" value={form[k]} onChange={set(k)} />
          </label>
        ))}
        <label>
          朝向
          <select value={form.orientation} onChange={set("orientation")}>
            {Object.entries(ORIENT_LABELS).map(([c, n]) => (
              <option key={c} value={c}>{c} {n}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="btn-row">
        <button disabled={busy} onClick={() => onLock(row, form)}>
          锁定摆放
        </button>
        {p && (
          <button disabled={busy} className="ghost" onClick={() => onRemove(row)}>
            移除（交还求解器）
          </button>
        )}
      </div>
    </div>
  );
}

export default function ItemPanel({ rows, stops, selectedKey, onSelect, onLock, onRemove, onFixWeight, onAssignStop, busy }) {
  const [weightDraft, setWeightDraft] = useState({});

  return (
    <div className="item-panel">
      <h3>货物清单（{rows.length} 件）</h3>
      {rows.map((row) => {
        const it = row.item;
        const p = row.placement;
        return (
          <div
            key={row.key}
            className={`item-card ${selectedKey === row.key ? "selected" : ""}`}
            onClick={() => onSelect(row.key)}
          >
            <div className="item-head">
              <span className="swatch" style={{ background: it.color }} />
              <b>{row.label}</b>
              {p ? (
                <span className={`badge ${p.locked ? "locked" : "solver"}`}>
                  {p.locked ? "🔒 人工锁定" : "求解器"}
                </span>
              ) : (
                <span className="badge unplaced">未摆放</span>
              )}
            </div>
            <div className="item-meta">
              {it.l}×{it.w}×{it.h} mm ·{" "}
              {it.weight_kg === null ? (
                <span className="unknown-weight">
                  重量未知
                  <input
                    type="number"
                    min="0"
                    placeholder="kg"
                    value={weightDraft[it.id] ?? ""}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setWeightDraft({ ...weightDraft, [it.id]: e.target.value })}
                  />
                  <button
                    disabled={busy || !weightDraft[it.id]}
                    onClick={(e) => {
                      e.stopPropagation();
                      onFixWeight(it.id, Number(weightDraft[it.id]));
                    }}
                  >
                    补录
                  </button>
                </span>
              ) : (
                `${it.weight_kg} kg`
              )}
              {it.no_flip && <span className="tag">禁止倒置</span>}
              {it.stackable && <span className="tag">可堆叠≤{it.max_top_load_kg ?? "∞"}kg</span>}
              {stops.length > 0 && (
                <select
                  className="stop-select"
                  value={row.stop_seq ?? ""}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    onAssignStop(row, e.target.value === "" ? null : Number(e.target.value))
                  }
                >
                  <option value="">随车不卸</option>
                  {stops.map((s) => (
                    <option key={s.seq} value={s.seq}>
                      站点{s.seq} {s.name}{s.cancelled ? "（已取消）" : ""}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {p && (
              <div className="item-pos">
                位置 ({p.x}, {p.y}, {p.z}) · 朝向 {p.orientation} · 占位 {p.dx}×{p.dy}×{p.dz}
              </div>
            )}
            <div onClick={(e) => e.stopPropagation()}>
              <PlacementEditor row={row} onLock={onLock} onRemove={onRemove} busy={busy} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
