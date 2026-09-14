import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from . import models, schemas
from .analysis import box_spec, build_state, load_plan, vehicle_spec
from .db import Base, engine, get_db
from .domain import allowed_codes, dims_for
from .export import build_csv
from .route import fits_orientation, simulate_route, vehicle_doors
from .solver import OBJECTIVE_TEXT, solve_positions


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    if os.environ.get("SEED_DEMO", "1") != "0":
        db = next(get_db())
        try:
            from .seed import seed
            seed(db)
        finally:
            db.close()
    yield


app = FastAPI(title="装载试算培训系统", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_plan_or_404(db: Session, plan_id: int) -> models.Plan:
    plan = load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(404, f"方案 {plan_id} 不存在")
    return plan


# ---------- 车辆 ----------

@app.get("/api/vehicles", response_model=list[schemas.VehicleOut])
def list_vehicles(db: Session = Depends(get_db)):
    return db.query(models.Vehicle).all()


@app.post("/api/vehicles", response_model=schemas.VehicleOut)
def create_vehicle(body: schemas.VehicleIn, db: Session = Depends(get_db)):
    v = models.Vehicle(**body.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


# ---------- 箱体 ----------

@app.get("/api/items", response_model=list[schemas.ItemOut])
def list_items(db: Session = Depends(get_db)):
    return db.query(models.Item).all()


@app.post("/api/items", response_model=schemas.ItemOut)
def create_item(body: schemas.ItemIn, db: Session = Depends(get_db)):
    it = models.Item(**body.model_dump())
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


@app.patch("/api/items/{item_id}", response_model=schemas.ItemOut)
def patch_item(item_id: int, body: schemas.ItemPatch, db: Session = Depends(get_db)):
    it = db.get(models.Item, item_id)
    if it is None:
        raise HTTPException(404, "箱体不存在")
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(it, k, val)
    db.commit()
    db.refresh(it)
    return it


# ---------- 方案 ----------

@app.get("/api/plans", response_model=list[schemas.PlanOut])
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(models.Plan).order_by(models.Plan.id).all()
    return [
        schemas.PlanOut(id=p.id, name=p.name, vehicle_id=p.vehicle_id,
                        allow_stacking=p.allow_stacking, item_count=len(p.plan_items))
        for p in plans
    ]


@app.post("/api/plans", response_model=schemas.PlanOut)
def create_plan(body: schemas.PlanIn, db: Session = Depends(get_db)):
    if db.get(models.Vehicle, body.vehicle_id) is None:
        raise HTTPException(404, "车辆不存在")
    plan = models.Plan(name=body.name, vehicle_id=body.vehicle_id,
                       allow_stacking=body.allow_stacking)
    db.add(plan)
    db.flush()
    for entry in body.items:
        it = db.get(models.Item, entry.item_id)
        if it is None:
            raise HTTPException(404, f"箱体 {entry.item_id} 不存在")
        for copy in range(1, entry.quantity + 1):
            db.add(models.PlanItem(plan_id=plan.id, item_id=it.id, copy_index=copy,
                                   label=f"{it.name} #{copy}"))
    db.commit()
    db.refresh(plan)
    return schemas.PlanOut(id=plan.id, name=plan.name, vehicle_id=plan.vehicle_id,
                           allow_stacking=plan.allow_stacking,
                           item_count=len(plan.plan_items))


@app.get("/api/plans/{plan_id}")
def get_plan_state(plan_id: int, db: Session = Depends(get_db)):
    return build_state(db, _get_plan_or_404(db, plan_id))


# ---------- 人工摆放（锁定） ----------

@app.post("/api/plans/{plan_id}/placements")
def upsert_placement(plan_id: int, body: schemas.PlacementIn, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, plan_id)
    pi = db.get(models.PlanItem, body.plan_item_id)
    if pi is None or pi.plan_id != plan.id:
        raise HTTPException(404, "该方案中不存在此件")
    p = pi.placement
    if p is None:
        p = models.Placement(plan_item_id=pi.id)
        pi.placement = p
        db.add(p)
    p.x, p.y, p.z, p.orientation = body.x, body.y, body.z, body.orientation
    p.locked = True
    p.source = "manual"
    db.commit()
    db.expire_all()
    return build_state(db, load_plan(db, plan_id))


@app.delete("/api/placements/{placement_id}")
def delete_placement(placement_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Placement, placement_id)
    if p is None:
        raise HTTPException(404, "摆放不存在")
    plan_id = p.plan_item.plan_id
    db.delete(p)
    db.commit()
    db.expire_all()
    return build_state(db, load_plan(db, plan_id))


# ---------- 站点与线路 ----------

@app.patch("/api/plans/{plan_id}/stops")
def update_stops(plan_id: int, body: schemas.StopsUpdate, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, plan_id)
    seqs = [s.seq for s in body.stops]
    if len(set(seqs)) != len(seqs):
        raise HTTPException(422, "站点序号重复")
    for s in body.stops:
        bad = [a for a in s.access if a not in ("rear", "side")]
        if bad:
            raise HTTPException(422, f"未知可接近方向: {bad}")
    plan.stops_json = [s.model_dump() for s in body.stops]
    valid_seqs = set(seqs)
    for pid, seq in body.assignments.items():
        pi = db.get(models.PlanItem, int(pid))
        if pi is None or pi.plan_id != plan.id:
            raise HTTPException(404, f"该方案中不存在货物 {pid}")
        if seq is not None and seq not in valid_seqs:
            raise HTTPException(422, f"站点 {seq} 不存在")
        pi.stop_seq = seq
    db.commit()
    db.expire_all()
    return build_state(db, load_plan(db, plan_id))


@app.get("/api/plans/{plan_id}/route")
def replay_route(plan_id: int, db: Session = Depends(get_db)):
    """从同一清单（当前摆放 + 站点定义）确定性重放全程，逐站给出状态。"""
    plan = _get_plan_or_404(db, plan_id)
    boxes = [box_spec(pi) for pi in plan.plan_items]
    unplaced = [b.label for b in boxes if not b.placed]
    if unplaced:
        raise HTTPException(409, {
            "detail": "存在未摆放货物，无法重放线路。请先求解或完成人工摆放。",
            "items": unplaced,
        })
    result = simulate_route(vehicle_spec(plan.vehicle), boxes,
                            plan.stops_json or [], plan.allow_stacking)
    result["plan_id"] = plan.id
    return result


# ---------- 求解 ----------

@app.post("/api/plans/{plan_id}/solve")
def solve_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, plan_id)
    boxes = [box_spec(pi) for pi in plan.plan_items]

    unknown = [b.label for b in boxes if b.weight_kg is None]
    if unknown:
        raise HTTPException(422, {
            "detail": "存在未知重量的箱体，不能按 0 参与计算。请先补录重量。",
            "items": unknown,
        })

    free = [b for b in boxes if not (b.placed and b.locked)]
    if not free:
        state = build_state(db, plan)
        state["solve_status"] = "NOTHING_TO_SOLVE"
        return state

    # 站点可接近性预检：分配到站点的货物必须存在能通过该站可用门的朝向
    v = vehicle_spec(plan.vehicle)
    stops = plan.stops_json or []
    stop_access = {s["seq"]: s.get("access", ["rear"]) for s in stops}
    doors = vehicle_doors(v)
    unsatisfiable = []
    for b in boxes:
        if b.stop_seq is None:
            continue
        if b.stop_seq not in stop_access:
            unsatisfiable.append({"stop_seq": b.stop_seq, "label": b.label,
                                  "reason": "站点不存在"})
            continue
        usable = [d for d in doors if d["kind"] in stop_access[b.stop_seq]]
        fits = any(
            fits_orientation(dims_for(b.l, b.w, b.h, c), d)
            for c in allowed_codes(b.no_flip, b.can_rotate_yaw)
            for d in usable
        )
        if not fits:
            unsatisfiable.append({
                "stop_seq": b.stop_seq, "label": b.label,
                "reason": f"箱体截面 {b.l}×{b.w}×{b.h} 在任何允许朝向下都无法通过 "
                          f"{'/'.join(stop_access[b.stop_seq])} 门",
            })
    if unsatisfiable:
        raise HTTPException(409, {
            "detail": "存在无法满足的站点：货物无法通过该站可用的门",
            "unsatisfiable_stops": unsatisfiable,
            "objective": OBJECTIVE_TEXT,
        })

    result = solve_positions(v, boxes, plan.allow_stacking,
                             doors=doors if stops else None,
                             stop_access=stop_access if stops else None)
    if result["status"] not in ("OPTIMAL", "FEASIBLE"):
        raise HTTPException(409, {
            "detail": f"无可行解（{result['status']}）。可能是锁定摆放导致轴荷/空间冲突，"
                      "请检查锁定件或解除部分锁定。",
            "status": result["status"],
            "objective": OBJECTIVE_TEXT,
        })

    # 用求解结果替换未锁定摆放
    for pi in plan.plan_items:
        b = box_spec(pi)
        if b.placed and b.locked:
            continue
        x, y, z, o = result["placements"][b.key]
        p = pi.placement
        if p is None:
            p = models.Placement(plan_item_id=pi.id)
            pi.placement = p
            db.add(p)
        p.x, p.y, p.z, p.orientation = x, y, z, o
        p.locked = False
        p.source = "solver"
    db.commit()
    db.expire_all()
    state = build_state(db, load_plan(db, plan_id))
    state["solve_status"] = result["status"]
    state["objective"] = OBJECTIVE_TEXT
    if stops:
        state["stop_report"] = [
            {
                "seq": s["seq"],
                "name": s["name"],
                "cancelled": bool(s.get("cancelled")),
                "boxes": sum(1 for b in boxes if b.stop_seq == s["seq"]),
                "satisfiable": True,
            }
            for s in stops
        ]
    return state


@app.post("/api/plans/{plan_id}/clear-unlocked")
def clear_unlocked(plan_id: int, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, plan_id)
    for pi in plan.plan_items:
        if pi.placement is not None and not pi.placement.locked:
            db.delete(pi.placement)
    db.commit()
    db.expire_all()
    return build_state(db, load_plan(db, plan_id))


# ---------- 导出 ----------

@app.get("/api/plans/{plan_id}/export.csv")
def export_csv(plan_id: int, db: Session = Depends(get_db)):
    state = build_state(db, _get_plan_or_404(db, plan_id))
    csv_text = build_csv(state)
    return Response(
        content="﻿" + csv_text,  # BOM 便于 Excel 打开
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="plan_{plan_id}_moment_table.csv"'},
    )


@app.get("/api/plans/{plan_id}/export.json")
def export_json(plan_id: int, db: Session = Depends(get_db)):
    return build_state(db, _get_plan_or_404(db, plan_id))


# 若前端已构建（frontend/dist），由后端直接托管，单进程即可运行整套系统
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="spa")
