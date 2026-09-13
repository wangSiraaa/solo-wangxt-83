"""求解器测试：可行性、锁定保留、轴荷约束内生化、禁止倒置。"""
from app.domain import BoxSpec, VehicleSpec, aabb_overlap
from app.solver import solve_positions
from app.validation import validate

VEH = VehicleSpec(
    cargo_l=4200, cargo_w=2100, cargo_h=2200,
    front_axle_x=500, rear_axle_x=3300,
    tare_front_kg=1800, tare_rear_kg=1200,
    max_front_axle_kg=3200, max_rear_axle_kg=6000,
    max_payload_kg=3000, floor_rating_kg_m2=2000, max_lateral_offset_mm=250,
)


def mk(key, weight, l, w, h, no_flip=False, stackable=False, max_top=None,
       placed=False, x=0, y=0, z=0, o=0, locked=False):
    return BoxSpec(key=key, label=key, l=l, w=w, h=h, weight_kg=weight,
                   no_flip=no_flip, can_rotate_yaw=True, stackable=stackable,
                   max_top_load_kg=max_top, placed=placed, x=x, y=y, z=z,
                   orientation=o, locked=locked)


def apply(boxes, result):
    for b in boxes:
        x, y, z, o = result["placements"][b.key]
        b.x, b.y, b.z, b.orientation, b.placed = x, y, z, o, True
    return boxes


def test_solver_packs_and_respects_axle_limits():
    # 样例A 解锁版：1500kg 重件 + 4 纸箱，全部交给求解器
    boxes = [mk("heavy", 1500, 1200, 800, 800, no_flip=True)] + \
            [mk(f"c{i}", 25, 600, 400, 400) for i in range(4)]
    res = solve_positions(VEH, boxes, allow_stacking=False)
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    apply(boxes, res)
    placed = {b.key: b for b in boxes}
    # 重件质心必须后移到 x>=850 附近（前轴约束内化为模型约束）
    assert placed["heavy"].center()[0] >= 840
    errors = [v for v in validate(VEH, boxes, False) if v["severity"] == "error"]
    assert errors == []


def test_locked_placement_is_kept_and_rest_computed():
    locked = mk("fixed", 200, 800, 600, 400, placed=True, x=0, y=0, z=0, o=0, locked=True)
    boxes = [locked, mk("f1", 100, 500, 500, 500), mk("f2", 100, 500, 500, 500)]
    res = solve_positions(VEH, boxes, allow_stacking=False)
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    assert res["placements"]["fixed"] == (0, 0, 0, 0)
    apply(boxes, res)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not aabb_overlap(boxes[i].aabb(), boxes[j].aabb())


def test_infeasible_when_locked_heavy_at_front():
    # 样例A 锁定版：重件锁定在 x=0，纸箱全部推到最后也无法救回前轴 → 不可行
    locked = mk("heavy", 1500, 1200, 800, 800, placed=True, x=0, y=650, z=0, o=0, locked=True)
    boxes = [locked] + [mk(f"c{i}", 25, 600, 400, 400) for i in range(4)]
    res = solve_positions(VEH, boxes, allow_stacking=False)
    assert res["status"] == "INFEASIBLE"


def test_no_flip_kept_upright():
    boxes = [mk("cab", 400, 800, 600, 1800, no_flip=True),
             mk("c1", 25, 600, 400, 400)]
    res = solve_positions(VEH, boxes, allow_stacking=False)
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    _, _, _, o = res["placements"]["cab"]
    assert o in (0, 1)  # 高度方向保持竖直


def test_lateral_constraint_centers_wide_box():
    boxes = [mk("wide", 900, 1600, 1200, 900)]
    res = solve_positions(VEH, boxes, allow_stacking=False)
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    apply(boxes, res)
    y_cg = boxes[0].center()[1]
    assert abs(y_cg - 1050) <= 250


def test_stacking_support_and_top_load():
    bottom = mk("bottom", 500, 1000, 1000, 500, stackable=True, max_top=100)
    light = mk("light", 60, 400, 400, 400)
    heavy = mk("heavy", 300, 400, 400, 400)
    boxes = [bottom, light, heavy]
    res = solve_positions(VEH, boxes, allow_stacking=True)
    assert res["status"] in ("OPTIMAL", "FEASIBLE")
    apply(boxes, res)
    errors = [v for v in validate(VEH, boxes, True) if v["severity"] == "error"]
    assert errors == []
