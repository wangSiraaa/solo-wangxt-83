"""多站点线路测试：走廊阻挡、逐站仿真、取消站点、倒箱优化。"""
import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain import BoxSpec, VehicleSpec
from app.main import app
from app.route import corridor_blockers, extraction_plan, simulate_route, vehicle_doors
from app.seed import seed

VEH_B = VehicleSpec(
    cargo_l=4200, cargo_w=2100, cargo_h=2200,
    front_axle_x=500, rear_axle_x=3300,
    tare_front_kg=1800, tare_rear_kg=1500,
    max_front_axle_kg=3200, max_rear_axle_kg=2800,
    max_payload_kg=2500, floor_rating_kg_m2=2000, max_lateral_offset_mm=250,
    rear_door_w=2000, rear_door_h=1900,
)


def mk(key, x, y, z, l, w, h, weight, stop=None, stackable=False, max_top=None):
    return BoxSpec(key=key, label=key, l=l, w=w, h=h, weight_kg=weight,
                   no_flip=False, can_rotate_yaw=True, stackable=stackable,
                   max_top_load_kg=max_top, placed=True, x=x, y=y, z=z,
                   orientation=0, stop_seq=stop)


STOPS3 = [{"seq": 1, "name": "S1", "access": ["rear"], "cancelled": False},
          {"seq": 2, "name": "S2", "access": ["rear"], "cancelled": False},
          {"seq": 3, "name": "S3", "access": ["rear"], "cancelled": False}]


# ---------- 走廊阻挡 ----------

def test_corridor_blockers_rear():
    target = mk("t", 1000, 700, 0, 600, 600, 600, 200, stop=1)
    behind = mk("b1", 2000, 600, 0, 800, 800, 800, 300, stop=2)
    beside = mk("b2", 2000, 1500, 0, 800, 500, 800, 300, stop=2)  # y 不相交
    front = mk("b3", 0, 700, 0, 500, 600, 600, 100, stop=2)        # 在目标前方
    bl = corridor_blockers(target, [behind, beside, front], "rear")
    assert [b.key for b in bl] == ["b1"]


def test_box_on_top_is_blocker():
    target = mk("t", 1000, 500, 0, 1000, 1000, 500, 300, stop=1, stackable=True)
    top = mk("top", 1200, 700, 500, 400, 400, 400, 60, stop=2)
    bl = corridor_blockers(target, [top], "rear")
    assert [b.key for b in bl] == ["top"]


def test_extraction_side_door_alignment():
    v = VehicleSpec(**{**VEH_B.__dict__, "side_door_x": 1000, "side_door_w": 1000,
                       "side_door_h": 1500})
    doors = vehicle_doors(v)
    aligned = mk("t", 1100, 500, 0, 600, 600, 600, 100, stop=1)
    plan = extraction_plan(aligned, [], doors, ["side"])
    assert plan is not None and plan["door"] == "side"
    misaligned = mk("t", 3000, 500, 0, 600, 600, 600, 100, stop=1)
    assert extraction_plan(misaligned, [], doors, ["side"]) is None
    too_wide = mk("t", 1100, 500, 0, 1200, 600, 600, 100, stop=1)
    assert extraction_plan(too_wide, [], doors, ["side"]) is None


# ---------- 逐站仿真 ----------

def test_route_rear_axle_overload_after_first_unload():
    boxes = [
        mk("heavy", 0, 550, 0, 800, 1000, 800, 1200, stop=1),
        mk("mid", 3100, 0, 0, 1000, 800, 700, 700, stop=2),
        mk("tail", 3100, 900, 0, 800, 1000, 600, 500, stop=3),
    ]
    r = simulate_route(VEH_B, boxes, STOPS3, allow_stacking=False)
    assert r["stages"][0]["valid"] is True            # 初始合规
    s1 = r["stages"][1]
    assert "REAR_AXLE_EXCEEDED" in {v["code"] for v in s1["violations"]}
    assert s1["valid"] is False
    assert r["valid"] is False                        # 中间失败 → 整程无效


def test_route_support_removed_early():
    boxes = [
        mk("bottom", 1500, 500, 0, 1000, 1000, 500, 300, stop=1,
           stackable=True, max_top=200),
        mk("top", 1800, 800, 500, 400, 400, 400, 60, stop=2),
    ]
    stops = STOPS3[:2]
    r = simulate_route(VEH_B, boxes, stops, allow_stacking=True)
    assert r["stages"][0]["valid"] is True
    s1 = r["stages"][1]
    assert "SUPPORT_VIOLATION" in {v["code"] for v in s1["violations"]}
    assert r["valid"] is False


def test_route_cancelled_stop_keeps_cargo():
    boxes = [
        mk("tool", 0, 1500, 0, 400, 500, 400, 100, stop=1),
        mk("taildev", 2500, 550, 0, 1200, 1000, 900, 1450, stop=2),
        mk("front", 0, 650, 0, 600, 800, 500, 900, stop=3),
    ]
    ok = simulate_route(VEH_B, boxes, STOPS3, allow_stacking=False)
    assert ok["valid"] is True
    cancelled = [dict(s, cancelled=(s["seq"] == 2)) for s in STOPS3]
    bad = simulate_route(VEH_B, boxes, cancelled, allow_stacking=False)
    assert bad["stages"][2]["cancelled"] is True
    final = bad["stages"][3]
    assert "taildev" in final["remaining"]            # 取消站点货物保留
    assert "REAR_AXLE_EXCEEDED" in {v["code"] for v in final["violations"]}
    assert bad["valid"] is False


def test_route_replay_deterministic():
    boxes = [mk("a", 0, 500, 0, 800, 1000, 800, 500, stop=1),
             mk("b", 3000, 500, 0, 800, 1000, 800, 500, stop=2)]
    r1 = simulate_route(VEH_B, boxes, STOPS3[:2], False)
    r2 = simulate_route(VEH_B, boxes, STOPS3[:2], False)
    assert r1 == r2


# ---------- API 端到端 ----------

@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed(db)
    db.close()
    with TestClient(app) as c:
        yield c


def plans_by_name(client):
    return {p["name"]: p for p in client.get("/api/plans").json()}


def test_api_scenario_f_route_invalid_midway(client):
    pid = plans_by_name(client)["样例F：重货先卸后轴偏载"]["id"]
    r = client.get(f"/api/plans/{pid}/route").json()
    assert r["stages"][0]["valid"] is True
    assert r["stages"][1]["valid"] is False
    assert any(v["code"] == "REAR_AXLE_EXCEEDED" for v in r["stages"][1]["violations"])
    assert r["valid"] is False


def test_api_scenario_g_support_violation(client):
    pid = plans_by_name(client)["样例G：下层支撑被提前取走"]["id"]
    r = client.get(f"/api/plans/{pid}/route").json()
    assert any(v["code"] == "SUPPORT_VIOLATION" for v in r["stages"][1]["violations"])
    assert r["valid"] is False


def test_api_scenario_h_cancel_toggle(client):
    pid = plans_by_name(client)["样例H：站点临时取消"]["id"]
    assert client.get(f"/api/plans/{pid}/route").json()["valid"] is True
    # 取消站点2
    state = client.get(f"/api/plans/{pid}").json()
    stops = [dict(s, cancelled=(s["seq"] == 2)) for s in state["plan"]["stops"]]
    client.patch(f"/api/plans/{pid}/stops", json={"stops": stops, "assignments": {}})
    r = client.get(f"/api/plans/{pid}/route").json()
    assert r["stages"][2]["cancelled"] is True
    assert r["valid"] is False
    # 恢复后重新有效
    stops = [dict(s, cancelled=False) for s in stops]
    client.patch(f"/api/plans/{pid}/stops", json={"stops": stops, "assignments": {}})
    assert client.get(f"/api/plans/{pid}/route").json()["valid"] is True


def test_api_scenario_i_rehandle_count_then_optimized(client):
    pid = plans_by_name(client)["样例I：先卸货物被堵需倒箱"]["id"]
    r = client.get(f"/api/plans/{pid}/route").json()
    s1 = r["stages"][1]
    assert s1["moves"][0]["count"] == 2               # 被两个周转箱B堵住
    assert {b["label"] for b in s1["moves"][0]["blockers"]} == {"周转箱B #1", "周转箱B #2"}
    # 站点2 的 周转箱B#1 又被 周转箱B#2 挡住 → 再倒 1 次
    assert r["stages"][2]["moves"][0]["count"] == 1
    assert r["total_moves"] == 3

    # 解锁周转箱A，让求解器在减少倒箱的目标下重排初始位置
    state = client.get(f"/api/plans/{pid}").json()
    box_a = [x for x in state["rows"] if "周转箱A" in x["label"]][0]
    client.delete(f"/api/placements/{box_a['placement']['id']}")
    solved = client.post(f"/api/plans/{pid}/solve").json()
    assert solved["solve_status"] in ("OPTIMAL", "FEASIBLE")
    assert "objective" in solved and "阻挡" in solved["objective"]
    r2 = client.get(f"/api/plans/{pid}/route").json()
    assert r2["stages"][1]["moves"][0]["count"] == 0  # 倒箱消除
    assert r2["valid"] is True


def test_api_route_requires_full_placement(client):
    pid = plans_by_name(client)["样例A：体积能容纳但前轴超限"]["id"]
    r = client.post(f"/api/plans/{pid}/route".replace("route", "route"))
    # 样例A 有未摆放纸箱 → 409
    resp = client.get(f"/api/plans/{pid}/route")
    assert resp.status_code == 409


def test_api_unsatisfiable_stop_reported(client):
    """侧门宽 700mm，800mm 宽的箱子在该站无法卸出 → 明确报告不可满足站点。"""
    vehicles = client.get("/api/vehicles").json()
    vb = [v for v in vehicles if "用车B" in v["name"]][0]
    items = client.get("/api/items").json()
    box_b = [i for i in items if i["name"] == "周转箱B"][0]  # 800×800×800
    r = client.post("/api/plans", json={
        "name": "侧门不可达测试", "vehicle_id": vb["id"],
        "items": [{"item_id": box_b["id"], "quantity": 1}],
    })
    pid = r.json()["id"]
    state = client.get(f"/api/plans/{pid}").json()
    piid = state["rows"][0]["plan_item_id"]
    client.patch(f"/api/plans/{pid}/stops", json={
        "stops": [{"seq": 1, "name": "仅侧门站", "access": ["side"], "cancelled": False}],
        "assignments": {str(piid): 1},
    })
    # 车辆B 无侧门 → 该站无可接近方向
    resp = client.post(f"/api/plans/{pid}/solve")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["unsatisfiable_stops"]
    assert "objective" in detail
