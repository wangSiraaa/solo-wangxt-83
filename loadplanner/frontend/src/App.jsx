import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Scene3D from "./components/Scene3D";
import ItemPanel from "./components/ItemPanel";
import ViolationPanel from "./components/ViolationPanel";
import MomentTable from "./components/MomentTable";

function NewPlanForm({ items, vehicles, onCreated }) {
  const [name, setName] = useState("");
  const [vehicleId, setVehicleId] = useState(vehicles[0]?.id ?? "");
  const [qty, setQty] = useState({});
  const chosen = Object.entries(qty).filter(([, q]) => q > 0);
  return (
    <details className="new-plan">
      <summary>新建方案</summary>
      <input placeholder="方案名称" value={name} onChange={(e) => setName(e.target.value)} />
      <select value={vehicleId} onChange={(e) => setVehicleId(Number(e.target.value))}>
        {vehicles.map((v) => (
          <option key={v.id} value={v.id}>{v.name}</option>
        ))}
      </select>
      {items.map((it) => (
        <label key={it.id} className="qty-row">
          {it.name}
          <input
            type="number" min="0" value={qty[it.id] ?? 0}
            onChange={(e) => setQty({ ...qty, [it.id]: Number(e.target.value) })}
          />
        </label>
      ))}
      <button
        disabled={!name || chosen.length === 0}
        onClick={() =>
          onCreated({
            name,
            vehicle_id: Number(vehicleId),
            items: chosen.map(([item_id, quantity]) => ({ item_id: Number(item_id), quantity })),
          })
        }
      >
        创建
      </button>
    </details>
  );
}

export default function App() {
  const [plans, setPlans] = useState([]);
  const [items, setItems] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [planId, setPlanId] = useState(null);
  const [state, setState] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api.plans(), api.items(), fetch("/api/vehicles").then((r) => r.json())]).then(
      ([ps, its, vs]) => {
        setPlans(ps);
        setItems(its);
        setVehicles(vs);
        if (ps.length) setPlanId(ps[0].id);
      }
    );
  }, []);

  const refresh = useCallback(
    (id) => {
      const pid = id ?? planId;
      if (!pid) return;
      return api.plan(pid).then(setState).catch((e) => setError(e.message));
    },
    [planId]
  );

  useEffect(() => {
    if (planId) {
      setState(null);
      setSelectedKey(null);
      refresh(planId);
    }
  }, [planId, refresh]);

  const run = useCallback(
    async (fn) => {
      setBusy(true);
      setError(null);
      try {
        const s = await fn();
        if (s) setState(s);
        setPlans(await api.plans());
      } catch (e) {
        setError(e.message);
        await refresh();
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const onSolve = () => run(() => api.solve(planId));
  const onClear = () => run(() => api.clearUnlocked(planId));
  const onLock = (row, form) =>
    run(() => api.upsertPlacement(planId, { plan_item_id: row.plan_item_id, ...form }));
  const onRemove = (row) => run(() => api.deletePlacement(row.placement.id));
  const onFixWeight = (itemId, weight) =>
    run(async () => {
      await api.patchItem(itemId, { weight_kg: weight });
      return api.plan(planId);
    });
  const onCreatePlan = (body) => run(async () => {
    const p = await api.createPlan(body);
    setPlanId(p.id);
    return api.plan(p.id);
  });

  if (!state) return <div className="loading">加载中…</div>;

  return (
    <div className="app">
      <header>
        <h1>装载试算培训系统</h1>
        <select value={planId ?? ""} onChange={(e) => setPlanId(Number(e.target.value))}>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <NewPlanForm items={items} vehicles={vehicles} onCreated={onCreatePlan} />
        <div className="actions">
          <button className="primary" disabled={busy} onClick={onSolve}>
            求解剩余部分
          </button>
          <button disabled={busy} onClick={onClear}>清除未锁定</button>
          <a href={api.exportCsvUrl(planId)} target="_blank" rel="noreferrer">导出CSV核对表</a>
          <a href={api.exportJsonUrl(planId)} target="_blank" rel="noreferrer">导出JSON</a>
        </div>
        {state.solve_status && <span className="solve-status">求解：{state.solve_status}</span>}
      </header>
      {error && <div className="error-banner">{error}</div>}
      <div className="main">
        <aside className="left">
          <ItemPanel
            rows={state.rows}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            onLock={onLock}
            onRemove={onRemove}
            onFixWeight={onFixWeight}
            busy={busy}
          />
        </aside>
        <section className="center">
          <Scene3D state={state} selectedKey={selectedKey} onSelect={setSelectedKey} />
          <div className="legend">
            <span><i className="dot red" />前轴</span>
            <span><i className="dot blue" />后轴</span>
            <span><i className="dot pink" />总质心</span>
            <span><i className="dot green" />横向允许走廊</span>
            <span>金边 = 人工锁定 · 红色 = 涉违规</span>
          </div>
        </section>
        <aside className="right">
          <ViolationPanel
            violations={state.analysis.violations}
            onFocus={(keys) => setSelectedKey(keys[0])}
          />
          <MomentTable state={state} />
        </aside>
      </div>
    </div>
  );
}
