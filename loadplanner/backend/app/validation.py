"""违规校验：每条违规都定位到具体对象（plan_item 的 key 列表）。

违规代码：
- UNKNOWN_WEIGHT          重量未知（禁止按 0 处理，轴荷结果判为无效）
- UNPLACED_ITEM           尚未摆放（提示级）
- OUT_OF_BOUNDS           越出车厢
- OVERLAP                 两件相交
- ORIENTATION_VIOLATION   朝向违反禁止倒置/禁止偏航约束
- SUPPORT_VIOLATION       悬空、支撑不完整、下方箱体不可堆叠，或方案未启用堆叠
- TOP_LOAD_EXCEEDED       下方箱体顶面承压超限
- FLOOR_BEARING_EXCEEDED  底板面承压超限
- PAYLOAD_EXCEEDED        总载重超限
- FRONT_AXLE_EXCEEDED     前轴荷超限
- REAR_AXLE_EXCEEDED      后轴荷超限
- LATERAL_OFFSET_EXCEEDED 总质心横向偏移超限
"""
from __future__ import annotations

from .domain import BoxSpec, VehicleSpec, aabb_overlap, allowed_codes
from .physics import axle_loads, cargo_cg

ERROR = "error"
WARN = "warn"


def _v(code, message, keys, severity=ERROR, details=None):
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "keys": list(keys),
        "details": details or {},
    }


def validate(vehicle: VehicleSpec, boxes: list[BoxSpec], allow_stacking: bool) -> list[dict]:
    violations: list[dict] = []
    placed = [b for b in boxes if b.placed]

    # 1) 重量未知：绝不按 0 处理
    for b in boxes:
        if b.weight_kg is None:
            violations.append(_v(
                "UNKNOWN_WEIGHT",
                f"「{b.label}」重量未知：轴荷/质心结果无效，请先补录重量（不得按 0 计）",
                [b.key],
            ))

    # 2) 未摆放提示
    for b in boxes:
        if not b.placed:
            violations.append(_v("UNPLACED_ITEM", f"「{b.label}」尚未摆放", [b.key], WARN))

    # 3) 逐件：越界 / 朝向 / 底板承压
    for b in placed:
        dx, dy, dz = b.dims()
        if b.x < 0 or b.y < 0 or b.z < 0 or \
                b.x + dx > vehicle.cargo_l or b.y + dy > vehicle.cargo_w or b.z + dz > vehicle.cargo_h:
            violations.append(_v(
                "OUT_OF_BOUNDS",
                f"「{b.label}」越出车厢（占用 x[{b.x},{b.x + dx}] y[{b.y},{b.y + dy}] z[{b.z},{b.z + dz}]，"
                f"车厢 {vehicle.cargo_l}×{vehicle.cargo_w}×{vehicle.cargo_h}）",
                [b.key],
            ))
        if b.orientation not in allowed_codes(b.no_flip, b.can_rotate_yaw):
            reason = "禁止倒置/侧倒" if b.no_flip else "禁止偏航旋转"
            violations.append(_v(
                "ORIENTATION_VIOLATION",
                f"「{b.label}」朝向 {b.orientation} 违反约束（{reason}）",
                [b.key],
            ))
        if b.weight_kg is not None and b.z == 0:
            area_m2 = dx * dy / 1e6
            pressure = b.weight_kg / area_m2
            if pressure > vehicle.floor_rating_kg_m2:
                violations.append(_v(
                    "FLOOR_BEARING_EXCEEDED",
                    f"「{b.label}」底板承压 {pressure:.0f} kg/m² 超过额定 {vehicle.floor_rating_kg_m2:.0f} kg/m²",
                    [b.key],
                    details={"pressure": round(pressure, 1), "limit": vehicle.floor_rating_kg_m2},
                ))

    # 4) 两两相交
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if aabb_overlap(placed[i].aabb(), placed[j].aabb()):
                violations.append(_v(
                    "OVERLAP",
                    f"「{placed[i].label}」与「{placed[j].label}」相交",
                    [placed[i].key, placed[j].key],
                ))

    # 5) 支撑与堆叠承压
    for b in placed:
        if b.z == 0:
            continue
        if not allow_stacking:
            violations.append(_v(
                "SUPPORT_VIOLATION",
                f"「{b.label}」悬空（z={b.z}），且本方案未启用堆叠",
                [b.key],
            ))
            continue
        bx, by, bdx, bdy = b.x, b.y, *b.dims()[:2]
        supporters = []
        for s in placed:
            if s is b:
                continue
            sdx, sdy, sdz = s.dims()
            top = s.z + sdz
            if top != b.z:
                continue
            if s.x <= bx and bx + bdx <= s.x + sdx and s.y <= by and by + bdy <= s.y + sdy:
                supporters.append(s)
        if not supporters:
            violations.append(_v(
                "SUPPORT_VIOLATION",
                f"「{b.label}」悬空或未被完整支撑（z={b.z}）",
                [b.key],
            ))
        else:
            for s in supporters:
                if not s.stackable:
                    violations.append(_v(
                        "SUPPORT_VIOLATION",
                        f"「{b.label}」压在不可堆叠的「{s.label}」上",
                        [b.key, s.key],
                    ))

    for s in placed:
        if s.max_top_load_kg is None:
            continue
        sdx, sdy, sdz = s.dims()
        top = s.z + sdz
        load = 0.0
        riders = []
        for b in placed:
            if b is s or b.weight_kg is None:
                continue
            bx, by, bdx, bdy = b.x, b.y, *b.dims()[:2]
            if b.z == top and s.x <= bx and bx + bdx <= s.x + sdx and s.y <= by and by + bdy <= s.y + sdy:
                load += b.weight_kg
                riders.append(b.key)
        if load > s.max_top_load_kg:
            violations.append(_v(
                "TOP_LOAD_EXCEEDED",
                f"「{s.label}」顶面承压 {load:.0f} kg 超过上限 {s.max_top_load_kg:.0f} kg",
                [s.key] + riders,
                details={"load": load, "limit": s.max_top_load_kg},
            ))

    # 6) 总载重（仅重量全部已知时判定；未知重量不得按 0 计）
    if all(b.weight_kg is not None for b in boxes):
        total = sum(b.weight_kg for b in boxes)
        if total > vehicle.max_payload_kg:
            violations.append(_v(
                "PAYLOAD_EXCEEDED",
                f"总载重 {total:.0f} kg 超过额定 {vehicle.max_payload_kg:.0f} kg",
                [b.key for b in boxes],
                details={"total": total, "limit": vehicle.max_payload_kg},
            ))

    # 7) 轴荷与横向偏移：对已摆放且重量已知的部分即时判定。
    # 若还有未摆放件，结论仅对应当前状态（消息中注明），但已出现的超限必须报告。
    placed_known = [b for b in placed if b.weight_kg is not None]
    if placed_known and len(placed_known) == len(placed):
        unplaced_note = ""
        n_unplaced = sum(1 for b in boxes if not b.placed)
        if n_unplaced:
            unplaced_note = f"（另有 {n_unplaced} 件未摆放，最终判定以全部装载为准）"
        total = sum(b.weight_kg for b in placed_known)
        cg = cargo_cg(placed_known)
        loads = axle_loads(vehicle, total, cg[0])
        keys = [b.key for b in placed_known]
        if not loads["front_ok"]:
            violations.append(_v(
                "FRONT_AXLE_EXCEEDED",
                f"前轴荷 {loads['front']:.0f} kg 超过限值 {loads['front_limit']:.0f} kg"
                f"（超出 {-loads['front_margin']:.0f} kg，已装货物质心 x={cg[0]:.0f} mm）{unplaced_note}",
                keys,
                details={"front": round(loads["front"], 1), "limit": loads["front_limit"]},
            ))
        if not loads["rear_ok"]:
            violations.append(_v(
                "REAR_AXLE_EXCEEDED",
                f"后轴荷 {loads['rear']:.0f} kg 超过限值 {loads['rear_limit']:.0f} kg"
                f"（超出 {-loads['rear_margin']:.0f} kg，已装货物质心 x={cg[0]:.0f} mm）{unplaced_note}",
                keys,
                details={"rear": round(loads["rear"], 1), "limit": loads["rear_limit"]},
            ))
        off = cg[1] - vehicle.cargo_w / 2
        if abs(off) > vehicle.max_lateral_offset_mm:
            violations.append(_v(
                "LATERAL_OFFSET_EXCEEDED",
                f"已装货物总质心横向偏移 {off:+.0f} mm 超过允许 ±{vehicle.max_lateral_offset_mm:.0f} mm{unplaced_note}",
                keys,
                details={"offset": round(off, 1), "limit": vehicle.max_lateral_offset_mm},
            ))

    return violations
