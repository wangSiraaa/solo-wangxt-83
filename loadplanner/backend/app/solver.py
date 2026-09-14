"""OR-Tools CP-SAT 装载求解器。

- 连续位置（mm 整数）+ 6 朝向选择；
- 两两不相交（6 方向分离析取）；
- 轴荷约束直接作为线性约束进入模型（力矩关于位置是线性的），
  因此"体积能装但前轴超限"的解会被直接排除，而不是事后发现；
- 总质心横向偏移约束；
- 可选堆叠：上层箱体必须被某个可堆叠箱体完整支撑，且顶面承压受限；
- 站点感知（多站点线路）：
  * 朝向按卸货站点的可用门截面过滤；
  * 支撑顺序硬约束：先卸的箱体不得支撑后卸/随车的箱体；
  * 后卸货物对先卸货物抽出走廊的阻挡作为软惩罚（减少倒箱）；
- locked=True 的人工摆放被固定，求解器只计算剩余部分；
- 重量未知的箱体在 API 层即被拒绝（422），不会进入本模型。
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from .domain import BoxSpec, VehicleSpec, allowed_codes, dims_for
from .route import fits_orientation

WEIGHT_SCALE = 10  # kg -> 0.1kg，保证力矩约束为整数线性
BLOCK_PENALTY = 4000  # 每一对"后卸货物阻挡先卸货物"的惩罚权重

OBJECTIVE_TEXT = (
    "min 4000·后卸货物阻挡对数 + 16·占用长度 + 4·Σ高度 + Σx "
    "（锁定/固定货物不动；先卸者不被后卸者支撑；朝向受站点门限）"
)


def solve_positions(
    vehicle: VehicleSpec,
    boxes: list[BoxSpec],
    allow_stacking: bool,
    time_limit_s: float = 8.0,
    doors: list[dict] | None = None,
    stop_access: dict[int, list[str]] | None = None,
) -> dict:
    """返回 {"status": str, "placements": {key: (x, y, z, orientation)}}。

    placements 包含全部箱体（locked 的回显其固定值）。
    doors/stop_access 提供时启用站点感知（门截面过滤 + 支撑顺序 + 阻挡惩罚）。
    """
    model = cp_model.CpModel()
    n = len(boxes)
    L, W, H = vehicle.cargo_l, vehicle.cargo_w, vehicle.cargo_h

    def box_codes(b: BoxSpec) -> list[int]:
        codes = allowed_codes(b.no_flip, b.can_rotate_yaw)
        if doors and stop_access and b.stop_seq is not None:
            acc = stop_access.get(b.stop_seq, ["rear"])
            usable = [d for d in doors if d["kind"] in acc]
            codes = [c for c in codes
                     if any(fits_orientation(dims_for(b.l, b.w, b.h, c), d) for d in usable)]
        return codes

    xs, ys, zs = [], [], []
    dxs, dys, dzs = [], [], []

    for i, b in enumerate(boxes):
        codes = box_codes(b)
        if not codes:
            # 没有任何朝向能通过该站点的门：模型必然不可行，由上层预检报告
            bad = model.new_bool_var(f"bad{i}")
            model.add(bad == 1)
            model.add(bad == 0)
            codes = [0]
        ov = {c: model.new_bool_var(f"o{i}_{c}") for c in codes}
        model.add_exactly_one(ov.values())
        dx = sum(ov[c] * dims_for(b.l, b.w, b.h, c)[0] for c in codes)
        dy = sum(ov[c] * dims_for(b.l, b.w, b.h, c)[1] for c in codes)
        dz = sum(ov[c] * dims_for(b.l, b.w, b.h, c)[2] for c in codes)
        x = model.new_int_var(0, L, f"x{i}")
        y = model.new_int_var(0, W, f"y{i}")
        z = model.new_int_var(0, H, f"z{i}")
        model.add(x + dx <= L)
        model.add(y + dy <= W)
        model.add(z + dz <= H)
        if b.placed and b.locked:
            model.add(x == b.x)
            model.add(y == b.y)
            model.add(z == b.z)
            if b.orientation in ov:
                model.add(ov[b.orientation] == 1)
            else:
                # 锁定朝向本身违反约束（或无法通过站点门）：必然不可行
                bad = model.new_bool_var(f"badl{i}")
                model.add(bad == 1)
                model.add(bad == 0)
        xs.append(x); ys.append(y); zs.append(z)
        dxs.append(dx); dys.append(dy); dzs.append(dz)

    # 两两不重叠
    for i in range(n):
        for j in range(i + 1, n):
            sep = [model.new_bool_var(f"s{i}_{j}_{k}") for k in range(6)]
            model.add(xs[i] + dxs[i] <= xs[j]).only_enforce_if(sep[0])
            model.add(xs[j] + dxs[j] <= xs[i]).only_enforce_if(sep[1])
            model.add(ys[i] + dys[i] <= ys[j]).only_enforce_if(sep[2])
            model.add(ys[j] + dys[j] <= ys[i]).only_enforce_if(sep[3])
            model.add(zs[i] + dzs[i] <= zs[j]).only_enforce_if(sep[4])
            model.add(zs[j] + dzs[j] <= zs[i]).only_enforce_if(sep[5])
            model.add_bool_or(sep)

    # 支撑 / 堆叠
    if allow_stacking:
        on = {}
        for i in range(n):
            onfloor = model.new_bool_var(f"floor{i}")
            model.add(zs[i] == 0).only_enforce_if(onfloor)
            model.add(zs[i] >= 1).only_enforce_if(onfloor.negated())
            supporters = []
            for j in range(n):
                if i == j or not boxes[j].stackable:
                    continue
                # 站点顺序硬约束：先卸的 j 不得支撑后卸/随车的 i
                si, sj = boxes[i].stop_seq, boxes[j].stop_seq
                if sj is not None and (si is None or si > sj):
                    continue
                bij = model.new_bool_var(f"on{i}_{j}")
                model.add(zs[i] == zs[j] + dzs[j]).only_enforce_if(bij)
                model.add(xs[i] >= xs[j]).only_enforce_if(bij)
                model.add(xs[i] + dxs[i] <= xs[j] + dxs[j]).only_enforce_if(bij)
                model.add(ys[i] >= ys[j]).only_enforce_if(bij)
                model.add(ys[i] + dys[i] <= ys[j] + dys[j]).only_enforce_if(bij)
                on[(i, j)] = bij
                supporters.append(bij)
            model.add(onfloor + sum(supporters) >= 1)
        for j, b in enumerate(boxes):
            if b.max_top_load_kg is None:
                continue
            load = sum(
                on[(i, j)] * int(round(boxes[i].weight_kg * WEIGHT_SCALE))
                for i in range(n) if (i, j) in on
            )
            model.add(load <= int(round(b.max_top_load_kg * WEIGHT_SCALE)))
    else:
        for i in range(n):
            model.add(zs[i] == 0)

    # 轴荷约束（全部重量已知，API 层已保证）
    # ws 为缩放后的重量（×WEIGHT_SCALE），m2 = Σ w'·(2x+dx) = 2·WEIGHT_SCALE·M，
    # 因此限值项也要乘以 WEIGHT_SCALE 保持量纲一致。
    ws = [int(round(b.weight_kg * WEIGHT_SCALE)) for b in boxes]
    w_tot = sum(ws)
    if w_tot > 0:
        wb = vehicle.wheelbase
        s = WEIGHT_SCALE
        m2 = sum(ws[i] * (2 * xs[i] + dxs[i]) for i in range(n))
        lo2 = 2 * (w_tot * vehicle.rear_axle_x
                   - s * (vehicle.max_front_axle_kg - vehicle.tare_front_kg) * wb)
        hi2 = 2 * (s * (vehicle.max_rear_axle_kg - vehicle.tare_rear_kg) * wb
                   + w_tot * vehicle.front_axle_x)
        hi2 = min(hi2, 2 * w_tot * vehicle.rear_axle_x)  # 前轴不得抬离
        model.add(m2 >= round(lo2))
        model.add(m2 <= round(hi2))
        # 横向：|y_cg - W/2| <= max_lateral_offset
        m2y = sum(ws[i] * (2 * ys[i] + dys[i]) for i in range(n))
        off = vehicle.max_lateral_offset_mm
        model.add(m2y >= round(w_tot * (W - 2 * off)))
        model.add(m2y <= round(w_tot * (W + 2 * off)))

    # 倒箱惩罚：后卸/随车货物 j 阻挡先卸货物 i 的抽出走廊（按站点可用方向）
    block_terms = []
    if allow_stacking:
        # 后卸货物压在先卸货物正上方：取出下方箱体前必须先搬开
        for (above, below), bij in on.items():
            sa, sb = boxes[above].stop_seq, boxes[below].stop_seq
            if sb is not None and sa is not None and sa > sb:
                block_terms.append(bij)
    if doors and stop_access:
        for i in range(n):
            si = boxes[i].stop_seq
            if si is None:
                continue
            acc = stop_access.get(si, ["rear"])
            kinds = {d["kind"] for d in doors if d["kind"] in acc}
            for j in range(n):
                if i == j:
                    continue
                sj = boxes[j].stop_seq
                if sj is not None and sj <= si:
                    continue  # j 不晚于 i 卸货，不会留在车上阻挡
                if "rear" in kinds:
                    # j 在 i 的尾门走廊内：x_j+x 向超出 i 的尾端 且 y、z 相交
                    block_terms.append(
                        _corridor_bool(model, i, j, xs, ys, zs, dxs, dys, dzs, "rear"))
                if "side" in kinds:
                    block_terms.append(
                        _corridor_bool(model, i, j, xs, ys, zs, dxs, dys, dzs, "side"))

    # 目标：先减少倒箱，再缩短占用长度、压低重心、靠前紧凑
    used = model.new_int_var(0, L, "used")
    for i in range(n):
        model.add(used >= xs[i] + dxs[i])
    model.minimize(BLOCK_PENALTY * sum(block_terms) + 16 * used + 4 * sum(zs) + sum(xs))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    status = solver.solve(model)
    name = solver.status_name(status)

    result = {"status": name, "placements": {}}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, b in enumerate(boxes):
            dx = solver.value(dxs[i])
            dy = solver.value(dys[i])
            dz = solver.value(dzs[i])
            orient = next(
                c for c in allowed_codes(b.no_flip, b.can_rotate_yaw)
                if dims_for(b.l, b.w, b.h, c) == (dx, dy, dz)
            )
            result["placements"][b.key] = (
                solver.value(xs[i]), solver.value(ys[i]), solver.value(zs[i]), orient,
            )
    return result


def _corridor_bool(model, i, j, xs, ys, zs, dxs, dys, dzs, kind):
    """返回布尔变量：j 是否处于 i 向 kind 方向抽出的走廊内（会阻挡 i）。"""
    if kind == "rear":
        # 分离条件（任一成立则不阻挡）：j 未越过 i 的尾端 / y 不相交 / z 不相交
        sep = [model.new_bool_var(f"cb{i}_{j}r{k}") for k in range(5)]
        model.add(xs[j] + dxs[j] <= xs[i] + dxs[i]).only_enforce_if(sep[0])
        model.add(ys[i] + dys[i] <= ys[j]).only_enforce_if(sep[1])
        model.add(ys[j] + dys[j] <= ys[i]).only_enforce_if(sep[2])
        model.add(zs[i] + dzs[i] <= zs[j]).only_enforce_if(sep[3])
        model.add(zs[j] + dzs[j] <= zs[i]).only_enforce_if(sep[4])
    else:
        sep = [model.new_bool_var(f"cb{i}_{j}s{k}") for k in range(5)]
        model.add(ys[j] + dys[j] <= ys[i] + dys[i]).only_enforce_if(sep[0])
        model.add(xs[i] + dxs[i] <= xs[j]).only_enforce_if(sep[1])
        model.add(xs[j] + dxs[j] <= xs[i]).only_enforce_if(sep[2])
        model.add(zs[i] + dzs[i] <= zs[j]).only_enforce_if(sep[3])
        model.add(zs[j] + dzs[j] <= zs[i]).only_enforce_if(sep[4])
    block = model.new_bool_var(f"cb{i}_{j}_{kind}")
    model.add_bool_or(sep).only_enforce_if(block.negated())
    model.add_bool_and([s.negated() for s in sep]).only_enforce_if(block)
    return block
