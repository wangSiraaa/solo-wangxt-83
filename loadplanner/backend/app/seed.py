"""演示数据：培训要求的验证样例。

基础样例（训练车A）：
- 样例A：体积能容纳但前轴超限（重型机组被人为锁定在车厢最前部）
- 样例B：偏心货箱（宽体设备贴一侧，横向偏移超限）
- 样例C：禁止倒置（仪器柜被锁定为侧放朝向）
- 样例D：底板承压超限（钢锭箱面压超限）
- 样例E：未知重量（不得按 0 处理，求解被拒绝）

多站点线路样例（训练车B，后轴限值 2800 kg）：
- 样例F：重货先卸 → 卸完后轴偏载（初始合规，中途失效）
- 样例G：下层支撑被提前取走 → 上层悬空
- 样例H：站点临时取消 → 货物保留，末段后轴超限
- 样例I：先卸货物被后卸货物堵住 → 倒箱 2 次；解锁重排后 0 次
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def _vehicle_a() -> models.Vehicle:
    return models.Vehicle(
        name="训练用车A 4.2m 厢式货车",
        cargo_l=4200, cargo_w=2100, cargo_h=2200,
        front_axle_x=500, rear_axle_x=3300,
        tare_front_kg=1800, tare_rear_kg=1200,
        max_front_axle_kg=3200, max_rear_axle_kg=6000,
        max_payload_kg=3000,
        floor_rating_kg_m2=2000,
        max_lateral_offset_mm=250,
    )


def _vehicle_b() -> models.Vehicle:
    return models.Vehicle(
        name="训练用车B 4.2m 轻型厢车（后轴限值紧）",
        cargo_l=4200, cargo_w=2100, cargo_h=2200,
        front_axle_x=500, rear_axle_x=3300,
        tare_front_kg=1800, tare_rear_kg=1500,
        max_front_axle_kg=3200, max_rear_axle_kg=2800,
        max_payload_kg=2500,
        floor_rating_kg_m2=2000,
        max_lateral_offset_mm=250,
        rear_door_w=2000, rear_door_h=1900,
    )


ITEMS = [
    dict(name="重型机组", l=1200, w=800, h=800, weight_kg=1500,
         no_flip=True, can_rotate_yaw=True, stackable=False, color="#e67e22"),
    dict(name="纸箱", l=600, w=400, h=400, weight_kg=25,
         no_flip=False, can_rotate_yaw=True, stackable=True, max_top_load_kg=100,
         color="#f1c40f"),
    dict(name="宽体设备", l=1600, w=1200, h=900, weight_kg=900,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#9b59b6"),
    dict(name="精密仪器柜", l=800, w=600, h=1800, weight_kg=400,
         no_flip=True, can_rotate_yaw=True, stackable=False, color="#2ecc71"),
    dict(name="钢锭箱", l=400, w=400, h=400, weight_kg=400,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#7f8c8d"),
    dict(name="待称重件", l=500, w=500, h=500, weight_kg=None,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#e74c3c"),
    # 多站点线路样例货物
    dict(name="前部重件", l=800, w=1000, h=800, weight_kg=1200,
         no_flip=True, can_rotate_yaw=True, stackable=False, color="#c0392b"),
    dict(name="中部设备B", l=1000, w=800, h=700, weight_kg=700,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#16a085"),
    dict(name="尾部纸箱", l=800, w=1000, h=600, weight_kg=500,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#d4ac0d"),
    dict(name="底箱", l=1000, w=1000, h=500, weight_kg=300,
         no_flip=False, can_rotate_yaw=True, stackable=True, max_top_load_kg=200,
         color="#8e44ad"),
    dict(name="顶箱", l=400, w=400, h=400, weight_kg=60,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#f39c12"),
    dict(name="随车工具箱", l=400, w=500, h=400, weight_kg=100,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#95a5a6"),
    dict(name="尾部设备", l=1200, w=1000, h=900, weight_kg=1450,
         no_flip=True, can_rotate_yaw=True, stackable=False, color="#c0392b"),
    dict(name="前部配重箱", l=600, w=800, h=500, weight_kg=900,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#2c3e50"),
    dict(name="周转箱A", l=600, w=600, h=600, weight_kg=200,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#1abc9c"),
    dict(name="周转箱B", l=800, w=800, h=800, weight_kg=300,
         no_flip=False, can_rotate_yaw=True, stackable=False, color="#3498db"),
]


def _make_plan(db: Session, name: str, vehicle_id: int, items: dict[str, models.Item],
               spec: list[tuple[str, int]], locked: list[tuple],
               allow_stacking: bool = False,
               stops: list[dict] | None = None,
               assignments: dict[tuple[str, int], int] | None = None):
    """spec: [(item_name, qty)]；locked: [(item_name, copy, x, y, z, orientation)]；
    assignments: {(item_name, copy): stop_seq}"""
    plan = models.Plan(name=name, vehicle_id=vehicle_id,
                       allow_stacking=allow_stacking, stops_json=stops or [])
    db.add(plan)
    db.flush()
    locked_map = {(n, c): (x, y, z, o) for n, c, x, y, z, o in locked}
    assignments = assignments or {}
    for item_name, qty in spec:
        for copy in range(1, qty + 1):
            it = items[item_name]
            pi = models.PlanItem(
                plan_id=plan.id, item_id=it.id, copy_index=copy,
                label=f"{it.name} #{copy}",
                stop_seq=assignments.get((item_name, copy)),
            )
            db.add(pi)
            db.flush()
            key = (item_name, copy)
            if key in locked_map:
                x, y, z, o = locked_map[key]
                db.add(models.Placement(plan_item_id=pi.id, x=x, y=y, z=z,
                                        orientation=o, locked=True, source="manual"))
    return plan


def seed(db: Session) -> None:
    if db.query(models.Vehicle).count() > 0:
        return
    va = _vehicle_a()
    vb = _vehicle_b()
    db.add_all([va, vb])
    db.flush()
    items = {}
    for spec in ITEMS:
        it = models.Item(**spec)
        db.add(it)
        db.flush()
        items[it.name] = it

    # ---- 基础样例（车辆A）----
    _make_plan(db, "样例A：体积能容纳但前轴超限", va.id, items,
               [("重型机组", 1), ("纸箱", 4)],
               [("重型机组", 1, 0, 650, 0, 0)])
    _make_plan(db, "样例B：偏心货箱横向超限", va.id, items,
               [("宽体设备", 1), ("纸箱", 2)],
               [("宽体设备", 1, 1000, 0, 0, 0)])
    _make_plan(db, "样例C：禁止倒置的仪器柜被侧放", va.id, items,
               [("精密仪器柜", 1), ("纸箱", 3)],
               [("精密仪器柜", 1, 500, 150, 0, 2)])
    _make_plan(db, "样例D：底板承压超限", va.id, items,
               [("钢锭箱", 1), ("纸箱", 2)],
               [("钢锭箱", 1, 2000, 800, 0, 0)])
    _make_plan(db, "样例E：未知重量不得按零处理", va.id, items,
               [("待称重件", 1), ("纸箱", 1)], [])

    # ---- 多站点线路样例（车辆B）----
    stops3 = [
        {"seq": 1, "name": "站点1", "access": ["rear"], "cancelled": False},
        {"seq": 2, "name": "站点2", "access": ["rear"], "cancelled": False},
        {"seq": 3, "name": "站点3", "access": ["rear"], "cancelled": False},
    ]
    # F：重货先卸 → 卸完后轴偏载。初始：前2932/后2768 合规；站点1卸完后轴 2811>2800
    _make_plan(db, "样例F：重货先卸后轴偏载", vb.id, items,
               [("前部重件", 1), ("中部设备B", 1), ("尾部纸箱", 1)],
               [("前部重件", 1, 0, 550, 0, 0),
                ("中部设备B", 1, 3100, 0, 0, 0),
                ("尾部纸箱", 1, 3100, 900, 0, 0)],
               stops=stops3,
               assignments={("前部重件", 1): 1, ("中部设备B", 1): 2, ("尾部纸箱", 1): 3})
    # G：下层支撑被提前取走 → 站点1后顶箱悬空
    _make_plan(db, "样例G：下层支撑被提前取走", vb.id, items,
               [("底箱", 1), ("顶箱", 1)],
               [("底箱", 1, 1500, 500, 0, 0),
                ("顶箱", 1, 1800, 800, 500, 0)],
               allow_stacking=True,
               stops=[{"seq": 1, "name": "站点1", "access": ["rear"], "cancelled": False},
                      {"seq": 2, "name": "站点2", "access": ["rear"], "cancelled": False}],
               assignments={("底箱", 1): 1, ("顶箱", 1): 2})
    # H：站点2 取消 → 尾部设备保留到末段，后轴 2846>2800
    _make_plan(db, "样例H：站点临时取消", vb.id, items,
               [("随车工具箱", 1), ("尾部设备", 1), ("前部配重箱", 1)],
               [("随车工具箱", 1, 0, 1500, 0, 0),
                ("尾部设备", 1, 2500, 550, 0, 0),
                ("前部配重箱", 1, 0, 650, 0, 0)],
               stops=stops3,
               assignments={("随车工具箱", 1): 1, ("尾部设备", 1): 2,
                            ("前部配重箱", 1): 3})
    # I：周转箱A（先卸）被两个周转箱B 堵在车厢深处 → 倒箱 2 次
    _make_plan(db, "样例I：先卸货物被堵需倒箱", vb.id, items,
               [("周转箱A", 1), ("周转箱B", 2)],
               [("周转箱A", 1, 1000, 700, 0, 0),
                ("周转箱B", 1, 2000, 600, 0, 0),
                ("周转箱B", 2, 3000, 600, 0, 0)],
               stops=stops3,
               assignments={("周转箱A", 1): 1, ("周转箱B", 1): 2, ("周转箱B", 2): 3})
    db.commit()
