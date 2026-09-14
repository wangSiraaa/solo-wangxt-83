"""多站点线路：门与可接近方向、走廊阻挡（倒箱）分析、逐站卸载仿真。

简化假设（培训用）：
- 尾门在 x=cargo_l 截面，侧门在 y=cargo_w 一侧的 [side_door_x, +side_door_w] 区间；
- 卸货只能沿直线滑出：尾门沿 +x，侧门沿 +y，**不允许穿透其他箱体**；
- 压在目标箱上方的箱体必须先移除，计入阻挡；
- 侧门要求箱体纵向区间完全对正门口（不允许先纵向挪动再横移）；
- 搬移次数 = 阻挡箱体的数量（每箱计一次倒箱，不递归计算阻挡的阻挡）。
"""
from __future__ import annotations

from .domain import BoxSpec, VehicleSpec
from .physics import moment_table
from .validation import ERROR, validate


def vehicle_doors(v: VehicleSpec) -> list[dict]:
    """车辆实际具备的门。尾门缺省与车厢同截面。"""
    doors = [{
        "kind": "rear",
        "w": v.rear_door_w if v.rear_door_w is not None else v.cargo_w,
        "h": v.rear_door_h if v.rear_door_h is not None else v.cargo_h,
    }]
    if v.side_door_w is not None:
        doors.append({
            "kind": "side",
            "x": v.side_door_x or 0.0,
            "w": v.side_door_w,
            "h": v.side_door_h if v.side_door_h is not None else v.cargo_h,
        })
    return doors


def fits_orientation(dims: tuple[int, int, int], door: dict) -> bool:
    """某朝向 (dx,dy,dz) 的截面能否通过门（不考虑位置）。"""
    dx, dy, dz = dims
    if door["kind"] == "rear":
        return dy <= door["w"] and dz <= door["h"]
    return dx <= door["w"] and dz <= door["h"]


def _overlap(a1: float, a2: float, b1: float, b2: float) -> bool:
    return a1 < b2 and b1 < a2


def corridor_blockers(box: BoxSpec, others: list[BoxSpec], door_kind: str) -> list[BoxSpec]:
    """沿指定方向滑出时，位于抽出走廊内或压在上方、必须先搬移的箱体。"""
    x, y, z, dx, dy, dz = box.aabb()
    blockers = []
    for o in others:
        if o is box:
            continue
        ox, oy, oz, odx, ody, odz = o.aabb()
        # 压在上方：必须先移除
        if oz >= z + dz and _overlap(x, x + dx, ox, ox + odx) and _overlap(y, y + dy, oy, oy + ody):
            blockers.append(o)
            continue
        if door_kind == "rear":
            # 走廊：(x+dx .. 车尾) × 箱截面
            if ox + odx > x + dx and _overlap(y, y + dy, oy, oy + ody) \
                    and _overlap(z, z + dz, oz, oz + odz):
                blockers.append(o)
        else:  # side：走廊 (y+dy .. 侧墙) × 箱截面
            if oy + ody > y + dy and _overlap(x, x + dx, ox, ox + odx) \
                    and _overlap(z, z + dz, oz, oz + odz):
                blockers.append(o)
    return blockers


def extraction_plan(box: BoxSpec, others: list[BoxSpec], doors: list[dict],
                    access: list[str]) -> dict | None:
    """可选方向中搬移次数最小的抽出方案；没有任何门可用时返回 None。"""
    best = None
    for d in doors:
        if d["kind"] not in access:
            continue
        dx, dy, dz = box.dims()
        if not fits_orientation((dx, dy, dz), d):
            continue
        if d["kind"] == "side" and not (d["x"] <= box.x and box.x + dx <= d["x"] + d["w"]):
            continue  # 侧门要求纵向对正门口
        bl = corridor_blockers(box, others, d["kind"])
        if best is None or len(bl) < len(best["blockers"]):
            best = {"door": d["kind"], "blockers": bl}
    return best


def _stage_snapshot(vehicle: VehicleSpec, current: list[BoxSpec],
                    allow_stacking: bool) -> tuple[list[dict], dict]:
    vs = validate(vehicle, current, allow_stacking)
    mt = moment_table(vehicle, current)
    return vs, mt


def simulate_route(vehicle: VehicleSpec, boxes: list[BoxSpec], stops: list[dict],
                   allow_stacking: bool) -> dict:
    """从同一清单（当前摆放 + 站点定义）确定性重放全程。

    任一中间状态存在 error 级违规 → 该阶段 invalid → 整程 invalid。
    """
    doors = vehicle_doors(vehicle)
    stages = []

    def make_stage(seq, name, current, unloaded, moves, extra_violations, cancelled=False):
        vs, mt = _stage_snapshot(vehicle, current, allow_stacking)
        vs = extra_violations + vs
        valid = not any(v["severity"] == ERROR for v in vs)
        return {
            "seq": seq,
            "name": name,
            "cancelled": cancelled,
            "unloaded": [b.key for b in unloaded],
            "unloaded_labels": [b.label for b in unloaded],
            "moves": moves,
            "remaining": [b.key for b in current],
            "violations": vs,
            "cg": None if mt["totals"]["cg_x_mm"] is None else {
                "x": mt["totals"]["cg_x_mm"],
                "y": mt["totals"]["cg_y_mm"],
                "z": mt["totals"]["cg_z_mm"],
            },
            "axle": mt["axle"],
            "valid": valid,
        }

    current = list(boxes)
    stages.append(make_stage(0, "初始装载", current, [], [], []))

    for stop in sorted(stops, key=lambda s: s["seq"]):
        seq = stop["seq"]
        if stop.get("cancelled"):
            # 站点取消：货物保留在车上，状态不变，但仍记录阶段以便重放
            stages.append(make_stage(seq, f"{stop['name']}（已取消，货物保留）",
                                     current, [], [], [], cancelled=True))
            continue
        unload = [b for b in current if b.stop_seq == seq]
        moves = []
        access_violations = []
        for b in unload:
            others = [o for o in current if o is not b]
            plan = extraction_plan(b, others, doors, stop.get("access", ["rear"]))
            if plan is None:
                access_violations.append({
                    "code": "NO_ACCESS",
                    "severity": ERROR,
                    "message": f"「{b.label}」在「{stop['name']}」无可接近方向"
                               "（门尺寸不符或纵向未对正侧门）",
                    "keys": [b.key],
                    "details": {},
                })
            else:
                moves.append({
                    "key": b.key,
                    "label": b.label,
                    "door": plan["door"],
                    "blockers": [{"key": o.key, "label": o.label} for o in plan["blockers"]],
                    "count": len(plan["blockers"]),
                })
        current = [b for b in current if b.stop_seq != seq]
        stages.append(make_stage(seq, f"{stop['name']} 卸货后", current, unload,
                                 moves, access_violations))

    return {
        "valid": all(s["valid"] for s in stages),
        "total_moves": sum(m["count"] for s in stages for m in s["moves"]),
        "stages": stages,
    }
