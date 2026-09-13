"""端到端 API 测试：五个演示样例 + 锁定/求解/导出流程。"""
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.seed import seed
from app.db import SessionLocal


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


def error_codes(state):
    return {v["code"] for v in state["analysis"]["violations"] if v["severity"] == "error"}


def test_seed_plans_exist(client):
    plans = plans_by_name(client)
    assert any("样例A" in n for n in plans)
    assert any("样例E" in n for n in plans)


def test_scenario_a_front_axle_overloaded_then_solved(client):
    pid = plans_by_name(client)["样例A：体积能容纳但前轴超限"]["id"]
    state = client.get(f"/api/plans/{pid}").json()
    assert "FRONT_AXLE_EXCEEDED" in error_codes(state)
    # 违规定位到重型机组
    viol = [v for v in state["analysis"]["violations"] if v["code"] == "FRONT_AXLE_EXCEEDED"][0]
    heavy_key = [r["key"] for r in state["rows"] if "重型机组" in r["label"]][0]
    assert heavy_key in viol["keys"]

    # 重件被锁定在最前部时，剩余纸箱怎么摆都救不回前轴 → 409
    r = client.post(f"/api/plans/{pid}/solve")
    assert r.status_code == 409

    # 解除锁定（删除人工摆放）后求解 → 前轴合规
    heavy_row = [r for r in state["rows"] if "重型机组" in r["label"]][0]
    r = client.delete(f"/api/placements/{heavy_row['placement']['id']}")
    assert r.status_code == 200

    r = client.post(f"/api/plans/{pid}/solve")
    assert r.status_code == 200
    solved = r.json()
    assert solved["solve_status"] in ("OPTIMAL", "FEASIBLE")
    assert error_codes(solved) == set()
    # 力矩核对表完整且前轴裕量非负
    assert solved["moment_table"]["complete"] is True
    assert solved["analysis"]["axle"]["front_margin"] >= 0


def test_scenario_b_lateral_offset(client):
    pid = plans_by_name(client)["样例B：偏心货箱横向超限"]["id"]
    state = client.get(f"/api/plans/{pid}").json()
    assert "LATERAL_OFFSET_EXCEEDED" in error_codes(state)
    # 解锁后重排，横向回到限值内
    wide = [r for r in state["rows"] if "宽体设备" in r["label"]][0]
    client.delete(f"/api/placements/{wide['placement']['id']}")
    solved = client.post(f"/api/plans/{pid}/solve").json()
    assert abs(solved["analysis"]["lateral"]["offset_mm"]) <= 250


def test_scenario_c_no_flip(client):
    pid = plans_by_name(client)["样例C：禁止倒置的仪器柜被侧放"]["id"]
    state = client.get(f"/api/plans/{pid}").json()
    assert "ORIENTATION_VIOLATION" in error_codes(state)
    cab = [r for r in state["rows"] if "精密仪器柜" in r["label"]][0]
    client.delete(f"/api/placements/{cab['placement']['id']}")
    solved = client.post(f"/api/plans/{pid}/solve").json()
    cab_after = [r for r in solved["rows"] if "精密仪器柜" in r["label"]][0]
    assert cab_after["placement"]["orientation"] in (0, 1)


def test_scenario_d_floor_bearing(client):
    pid = plans_by_name(client)["样例D：底板承压超限"]["id"]
    state = client.get(f"/api/plans/{pid}").json()
    assert "FLOOR_BEARING_EXCEEDED" in error_codes(state)
    viol = [v for v in state["analysis"]["violations"]
            if v["code"] == "FLOOR_BEARING_EXCEEDED"][0]
    steel_key = [r["key"] for r in state["rows"] if "钢锭箱" in r["label"]][0]
    assert viol["keys"] == [steel_key]


def test_scenario_e_unknown_weight_blocks_solve(client):
    pid = plans_by_name(client)["样例E：未知重量不得按零处理"]["id"]
    state = client.get(f"/api/plans/{pid}").json()
    assert "UNKNOWN_WEIGHT" in error_codes(state)
    assert state["analysis"]["complete"] is False
    r = client.post(f"/api/plans/{pid}/solve")
    assert r.status_code == 422
    assert "未知重量" in str(r.json()["detail"])

    # 补录重量后可以求解
    items = client.get("/api/items").json()
    mystery = [i for i in items if i["name"] == "待称重件"][0]
    client.patch(f"/api/items/{mystery['id']}", json={"weight_kg": 120})
    r = client.post(f"/api/plans/{pid}/solve")
    assert r.status_code == 200
    assert error_codes(r.json()) == set()


def test_manual_lock_then_solve_keeps_position(client):
    pid = plans_by_name(client)["样例E：未知重量不得按零处理"]["id"]
    items = client.get("/api/items").json()
    mystery = [i for i in items if i["name"] == "待称重件"][0]
    client.patch(f"/api/items/{mystery['id']}", json={"weight_kg": 120})

    state = client.get(f"/api/plans/{pid}").json()
    carton = [r for r in state["rows"] if "纸箱" in r["label"]][0]
    # 人工锁定纸箱在 (3000, 800, 0)
    r = client.post(f"/api/plans/{pid}/placements", json={
        "plan_item_id": carton["plan_item_id"], "x": 3000, "y": 800, "z": 0,
        "orientation": 0,
    })
    assert r.status_code == 200
    solved = client.post(f"/api/plans/{pid}/solve").json()
    carton_after = [r for r in solved["rows"] if "纸箱" in r["label"]][0]
    assert carton_after["placement"]["x"] == 3000
    assert carton_after["placement"]["locked"] is True
    assert error_codes(solved) == set()


def test_export_csv_contains_moment_table(client):
    pid = plans_by_name(client)["样例A：体积能容纳但前轴超限"]["id"]
    r = client.get(f"/api/plans/{pid}/export.csv")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "力矩核对表" in text
    assert "力臂mm(对前轴)" in text
    assert "重型机组" in text
    assert "前轴(含空车)" in text
