"""物理模型单元测试：质心、轴荷、力矩表。"""
from app.domain import BoxSpec, VehicleSpec
from app.physics import axle_loads, cargo_cg, moment_table

VEH = VehicleSpec(
    cargo_l=4200, cargo_w=2100, cargo_h=2200,
    front_axle_x=500, rear_axle_x=3300,
    tare_front_kg=1800, tare_rear_kg=1200,
    max_front_axle_kg=3200, max_rear_axle_kg=6000,
    max_payload_kg=3000, floor_rating_kg_m2=2000, max_lateral_offset_mm=250,
)


def box(key, x, weight, l=1000, w=1000, h=1000):
    return BoxSpec(key=key, label=key, l=l, w=w, h=h, weight_kg=weight,
                   no_flip=False, can_rotate_yaw=True, stackable=False,
                   max_top_load_kg=None, placed=True, x=x, y=500, z=0, orientation=0)


def test_cg_weighted_average():
    cg = cargo_cg([box("a", 0, 100), box("b", 1000, 300)])
    # x 质心: (100*500 + 300*1500) / 400 = 1250
    assert abs(cg[0] - 1250) < 1e-6


def test_axle_loads_split_by_lever_rule():
    # 1000 kg 位于 x=1900（两轴中点）→ 货物均分到两轴
    loads = axle_loads(VEH, 1000, 1900)
    assert abs(loads["cargo_front"] - 500) < 1e-6
    assert abs(loads["cargo_rear"] - 500) < 1e-6
    assert abs(loads["front"] - 2300) < 1e-6
    assert abs(loads["rear"] - 1700) < 1e-6


def test_load_ahead_of_front_axle_amplifies_front():
    # 质心在前轴之前 → 前轴反力大于货物重量（杠杆效应）
    loads = axle_loads(VEH, 1500, 0)
    assert loads["cargo_front"] > 1500
    assert loads["cargo_rear"] < 0


def test_moment_table_marks_unknown_weight_incomplete():
    boxes = [box("a", 0, 100),
             BoxSpec(key="m", label="m", l=500, w=500, h=500, weight_kg=None,
                     no_flip=False, can_rotate_yaw=True, stackable=False,
                     max_top_load_kg=None, placed=True, x=2000, y=0, z=0)]
    mt = moment_table(VEH, boxes)
    assert mt["complete"] is False
    unknown_row = [r for r in mt["rows"] if r["key"] == "m"][0]
    assert unknown_row["weight_kg"] is None
    assert unknown_row["moment_kg_m"] is None  # 未知重量不产生力矩行数值，但绝不按 0 计入合计
    # 合计只含已知 100kg
    assert mt["totals"]["known_weight_kg"] == 100


def test_moment_arm_against_front_axle():
    mt = moment_table(VEH, [box("a", 0, 100)])
    row = mt["rows"][0]
    # 质心 x=500，前轴 x=500 → 力臂 0
    assert row["arm_front_axle_mm"] == 0
    assert row["moment_kg_m"] == 0
