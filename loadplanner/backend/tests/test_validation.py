"""校验器单元测试：每类违规都要定位到具体对象。"""
from app.domain import BoxSpec, VehicleSpec
from app.validation import validate

VEH = VehicleSpec(
    cargo_l=4200, cargo_w=2100, cargo_h=2200,
    front_axle_x=500, rear_axle_x=3300,
    tare_front_kg=1800, tare_rear_kg=1200,
    max_front_axle_kg=3200, max_rear_axle_kg=6000,
    max_payload_kg=3000, floor_rating_kg_m2=2000, max_lateral_offset_mm=250,
)


def mk(key, x=0, y=0, z=0, o=0, weight=100, l=500, w=500, h=500,
       no_flip=False, stackable=False, max_top=None, placed=True):
    return BoxSpec(key=key, label=key, l=l, w=w, h=h, weight_kg=weight,
                   no_flip=no_flip, can_rotate_yaw=True, stackable=stackable,
                   max_top_load_kg=max_top, placed=placed, x=x, y=y, z=z, orientation=o)


def codes(violations):
    return {v["code"] for v in violations}


def test_out_of_bounds_located():
    vs = validate(VEH, [mk("a", x=4000)], allow_stacking=False)
    oob = [v for v in vs if v["code"] == "OUT_OF_BOUNDS"]
    assert oob and oob[0]["keys"] == ["a"]


def test_overlap_locates_both():
    vs = validate(VEH, [mk("a", x=0), mk("b", x=250)], allow_stacking=False)
    ov = [v for v in vs if v["code"] == "OVERLAP"]
    assert ov and set(ov[0]["keys"]) == {"a", "b"}


def test_touching_faces_not_overlap():
    vs = validate(VEH, [mk("a", x=0), mk("b", x=500)], allow_stacking=False)
    assert "OVERLAP" not in codes(vs)


def test_unknown_weight_never_zero():
    vs = validate(VEH, [mk("a", weight=None)], allow_stacking=False)
    assert "UNKNOWN_WEIGHT" in codes(vs)
    # 重量未知时不得给出轴荷判定（轴荷结论无效而不是按 0 通过）
    assert "FRONT_AXLE_EXCEEDED" not in codes(vs)
    assert "REAR_AXLE_EXCEEDED" not in codes(vs)


def test_orientation_violation_no_flip():
    # 高 1800 的柜子被侧放（朝向 2 → dz=500）
    vs = validate(VEH, [mk("a", o=2, l=800, w=600, h=1800, no_flip=True)],
                  allow_stacking=False)
    assert "ORIENTATION_VIOLATION" in codes(vs)


def test_front_axle_overload_located():
    # 1500kg 锁定在 x=0（质心 600mm）：前轴 1800+1446=3246 > 3200
    heavy = mk("heavy", x=0, weight=1500, l=1200, w=800, h=800)
    vs = validate(VEH, [heavy], allow_stacking=False)
    fa = [v for v in vs if v["code"] == "FRONT_AXLE_EXCEEDED"]
    assert fa and "heavy" in fa[0]["keys"]


def test_lateral_offset_located():
    wide = mk("wide", x=1000, y=0, weight=900, l=1600, w=1200, h=900)
    vs = validate(VEH, [wide], allow_stacking=False)
    assert "LATERAL_OFFSET_EXCEEDED" in codes(vs)


def test_floor_bearing_located():
    steel = mk("steel", x=2000, y=800, weight=400, l=400, w=400, h=400)
    vs = validate(VEH, [steel], allow_stacking=False)
    fb = [v for v in vs if v["code"] == "FLOOR_BEARING_EXCEEDED"]
    assert fb and fb[0]["keys"] == ["steel"]


def test_support_violation_when_floating():
    top = mk("top", z=500)
    vs = validate(VEH, [top], allow_stacking=False)
    assert "SUPPORT_VIOLATION" in codes(vs)


def test_stacking_rules():
    bottom = mk("bottom", z=0, stackable=True, max_top=50)
    top = mk("top", z=500, weight=80)
    vs = validate(VEH, [bottom, top], allow_stacking=True)
    assert "TOP_LOAD_EXCEEDED" in codes(vs)

    top_ok = mk("top", z=500, weight=40)
    vs2 = validate(VEH, [bottom, top_ok], allow_stacking=True)
    assert "SUPPORT_VIOLATION" not in codes(vs2)
    assert "TOP_LOAD_EXCEEDED" not in codes(vs2)

    not_stackable = mk("bottom", z=0, stackable=False)
    vs3 = validate(VEH, [not_stackable, top_ok], allow_stacking=True)
    assert "SUPPORT_VIOLATION" in codes(vs3)


def test_payload_exceeded():
    boxes = [mk(f"b{i}", x=i * 500, weight=1200) for i in range(3)]
    vs = validate(VEH, boxes, allow_stacking=False)
    assert "PAYLOAD_EXCEEDED" in codes(vs)


def test_clean_plan_has_no_errors():
    b = mk("a", x=1500, y=800, weight=500)
    vs = validate(VEH, [b], allow_stacking=False)
    assert [v for v in vs if v["severity"] == "error"] == []
