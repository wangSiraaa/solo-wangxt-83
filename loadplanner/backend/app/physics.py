"""简化静力学：总质心、双轴轴荷、逐件力矩核对表。

模型假设（培训用，不替代安全鉴定）：
- 车辆简化为刚性体，仅前/后两根轴承担载荷；
- 货物重量通过静力平衡分配到两轴：
    R_front = W * (x_rear - x_cg) / (x_rear - x_front)
    R_rear  = W * (x_cg - x_front) / (x_rear - x_front)
  质心在前轴之前时前轴反力会大于货物重量（杠杆效应）；
- 轴荷 = 空车轴荷（tare）+ 货物反力；
- 横向只校核总质心相对车厢中心线的偏移，不做侧倾稳定性分析。
"""
from __future__ import annotations

from typing import Optional

from .domain import BoxSpec, VehicleSpec


def cargo_cg(boxes: list[BoxSpec]) -> Optional[tuple[float, float, float]]:
    """已摆放且重量已知部分的质心。无已知重量件时返回 None。"""
    known = [b for b in boxes if b.placed and b.weight_kg is not None]
    total = sum(b.weight_kg for b in known)
    if not known or total <= 0:
        return None
    cx = sum(b.weight_kg * b.center()[0] for b in known) / total
    cy = sum(b.weight_kg * b.center()[1] for b in known) / total
    cz = sum(b.weight_kg * b.center()[2] for b in known) / total
    return (cx, cy, cz)


def axle_loads(vehicle: VehicleSpec, total_w: float, x_cg: float) -> dict:
    """由货物总重与纵向质心位置求前后轴荷（含空车轴荷）。"""
    wb = vehicle.wheelbase
    r_front = total_w * (vehicle.rear_axle_x - x_cg) / wb
    r_rear = total_w * (x_cg - vehicle.front_axle_x) / wb
    front = vehicle.tare_front_kg + r_front
    rear = vehicle.tare_rear_kg + r_rear
    return {
        "cargo_front": r_front,
        "cargo_rear": r_rear,
        "front": front,
        "rear": rear,
        "front_limit": vehicle.max_front_axle_kg,
        "rear_limit": vehicle.max_rear_axle_kg,
        "front_margin": vehicle.max_front_axle_kg - front,
        "rear_margin": vehicle.max_rear_axle_kg - rear,
        "front_ok": front <= vehicle.max_front_axle_kg + 1e-6,
        "rear_ok": rear <= vehicle.max_rear_axle_kg + 1e-6,
    }


def moment_table(vehicle: VehicleSpec, boxes: list[BoxSpec]) -> dict:
    """逐件力矩核对表（对前轴取矩）+ 汇总行。

    重量未知的件保留行但力矩记为 None，并标记 complete=False —— 绝不按 0 计入。
    """
    rows = []
    for b in boxes:
        if not b.placed:
            continue
        cx, cy, _ = b.center()
        arm = cx - vehicle.front_axle_x
        y_off = cy - vehicle.cargo_w / 2
        if b.weight_kg is None:
            moment = None
            lat_moment = None
        else:
            moment = b.weight_kg * arm / 1000.0          # kg·m
            lat_moment = b.weight_kg * y_off / 1000.0    # kg·m
        rows.append({
            "key": b.key,
            "label": b.label,
            "weight_kg": b.weight_kg,
            "x_mm": b.x, "y_mm": b.y, "z_mm": b.z,
            "orientation": b.orientation,
            "x_center_mm": round(cx, 1),
            "arm_front_axle_mm": round(arm, 1),
            "moment_kg_m": None if moment is None else round(moment, 2),
            "y_offset_mm": round(y_off, 1),
            "lateral_moment_kg_m": None if lat_moment is None else round(lat_moment, 2),
        })

    known = [r for r in rows if r["weight_kg"] is not None]
    complete = len(known) == len(rows) and all(b.placed for b in boxes)
    total_w = sum(r["weight_kg"] for r in known)
    total_moment = sum(r["moment_kg_m"] for r in known)

    cg = cargo_cg(boxes)
    axle = None
    lateral = None
    if cg is not None and total_w > 0:
        axle = axle_loads(vehicle, total_w, cg[0])
        lateral = {
            "offset_mm": round(cg[1] - vehicle.cargo_w / 2, 1),
            "limit_mm": vehicle.max_lateral_offset_mm,
            "ok": abs(cg[1] - vehicle.cargo_w / 2) <= vehicle.max_lateral_offset_mm + 1e-6,
        }

    return {
        "rows": rows,
        "complete": complete,
        "totals": {
            "known_weight_kg": round(total_w, 2),
            "known_moment_kg_m": round(total_moment, 2),
            "cg_x_mm": None if cg is None else round(cg[0], 1),
            "cg_y_mm": None if cg is None else round(cg[1], 1),
            "cg_z_mm": None if cg is None else round(cg[2], 1),
        },
        "axle": axle,
        "lateral": lateral,
    }
