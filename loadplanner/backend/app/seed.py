"""演示数据：培训要求的验证样例。

- 样例A：体积能容纳但前轴超限（重型机组被人为锁定在车厢最前部）
- 样例B：偏心货箱（宽体设备贴一侧，横向偏移超限）
- 样例C：禁止倒置（仪器柜被锁定为侧放朝向）
- 样例D：底板承压超限（钢锭箱面压超限）
- 样例E：未知重量（不得按 0 处理，求解被拒绝）
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def _vehicle() -> models.Vehicle:
    return models.Vehicle(
        name="训练用车 4.2m 厢式货车",
        cargo_l=4200, cargo_w=2100, cargo_h=2200,
        front_axle_x=500, rear_axle_x=3300,
        tare_front_kg=1800, tare_rear_kg=1200,
        max_front_axle_kg=3200, max_rear_axle_kg=6000,
        max_payload_kg=3000,
        floor_rating_kg_m2=2000,
        max_lateral_offset_mm=250,
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
]


def _make_plan(db: Session, name: str, vehicle_id: int, items: dict[str, models.Item],
               spec: list[tuple[str, int]], locked: list[tuple[str, int, int, int, int, int]]):
    """spec: [(item_name, qty)]；locked: [(item_name, copy, x, y, z, orientation)]"""
    plan = models.Plan(name=name, vehicle_id=vehicle_id, allow_stacking=False)
    db.add(plan)
    db.flush()
    locked_map = {(n, c): (x, y, z, o) for n, c, x, y, z, o in locked}
    for item_name, qty in spec:
        for copy in range(1, qty + 1):
            it = items[item_name]
            pi = models.PlanItem(plan_id=plan.id, item_id=it.id, copy_index=copy,
                                 label=f"{it.name} #{copy}")
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
    v = _vehicle()
    db.add(v)
    db.flush()
    items = {}
    for spec in ITEMS:
        it = models.Item(**spec)
        db.add(it)
        db.flush()
        items[it.name] = it

    _make_plan(db, "样例A：体积能容纳但前轴超限", v.id, items,
               [("重型机组", 1), ("纸箱", 4)],
               [("重型机组", 1, 0, 650, 0, 0)])
    _make_plan(db, "样例B：偏心货箱横向超限", v.id, items,
               [("宽体设备", 1), ("纸箱", 2)],
               [("宽体设备", 1, 1000, 0, 0, 0)])
    _make_plan(db, "样例C：禁止倒置的仪器柜被侧放", v.id, items,
               [("精密仪器柜", 1), ("纸箱", 3)],
               [("精密仪器柜", 1, 500, 150, 0, 2)])
    _make_plan(db, "样例D：底板承压超限", v.id, items,
               [("钢锭箱", 1), ("纸箱", 2)],
               [("钢锭箱", 1, 2000, 800, 0, 0)])
    _make_plan(db, "样例E：未知重量不得按零处理", v.id, items,
               [("待称重件", 1), ("纸箱", 1)], [])
    db.commit()
