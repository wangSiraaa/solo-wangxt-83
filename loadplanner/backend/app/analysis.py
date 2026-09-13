"""把 ORM 对象装配成领域对象，计算完整方案状态（违规 + 力矩表 + 质心）。"""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from . import models
from .domain import BoxSpec, VehicleSpec, dims_for
from .physics import moment_table
from .validation import validate


def vehicle_spec(v: models.Vehicle) -> VehicleSpec:
    return VehicleSpec(
        cargo_l=v.cargo_l, cargo_w=v.cargo_w, cargo_h=v.cargo_h,
        front_axle_x=v.front_axle_x, rear_axle_x=v.rear_axle_x,
        tare_front_kg=v.tare_front_kg, tare_rear_kg=v.tare_rear_kg,
        max_front_axle_kg=v.max_front_axle_kg, max_rear_axle_kg=v.max_rear_axle_kg,
        max_payload_kg=v.max_payload_kg,
        floor_rating_kg_m2=v.floor_rating_kg_m2,
        max_lateral_offset_mm=v.max_lateral_offset_mm,
    )


def box_spec(pi: models.PlanItem) -> BoxSpec:
    it = pi.item
    p = pi.placement
    return BoxSpec(
        key=f"pi-{pi.id}",
        label=pi.label,
        l=it.l, w=it.w, h=it.h,
        weight_kg=it.weight_kg,
        no_flip=it.no_flip,
        can_rotate_yaw=it.can_rotate_yaw,
        stackable=it.stackable,
        max_top_load_kg=it.max_top_load_kg,
        placed=p is not None,
        x=p.x if p else 0,
        y=p.y if p else 0,
        z=p.z if p else 0,
        orientation=p.orientation if p else 0,
        locked=bool(p and p.locked),
        source=p.source if p else "manual",
    )


def load_plan(db: Session, plan_id: int) -> models.Plan | None:
    return (
        db.query(models.Plan)
        .options(
            joinedload(models.Plan.vehicle),
            joinedload(models.Plan.plan_items)
            .joinedload(models.PlanItem.item),
            joinedload(models.Plan.plan_items)
            .joinedload(models.PlanItem.placement),
        )
        .filter(models.Plan.id == plan_id)
        .first()
    )


def build_state(db: Session, plan: models.Plan) -> dict:
    v = vehicle_spec(plan.vehicle)
    boxes = [box_spec(pi) for pi in plan.plan_items]
    violations = validate(v, boxes, plan.allow_stacking)
    mt = moment_table(v, boxes)

    rows = []
    for pi, b in zip(plan.plan_items, boxes):
        row = {
            "plan_item_id": pi.id,
            "key": b.key,
            "label": b.label,
            "item": {
                "id": pi.item.id,
                "name": pi.item.name,
                "l": pi.item.l, "w": pi.item.w, "h": pi.item.h,
                "weight_kg": pi.item.weight_kg,
                "no_flip": pi.item.no_flip,
                "can_rotate_yaw": pi.item.can_rotate_yaw,
                "stackable": pi.item.stackable,
                "max_top_load_kg": pi.item.max_top_load_kg,
                "color": pi.item.color,
            },
            "placement": None,
        }
        if b.placed:
            dx, dy, dz = dims_for(b.l, b.w, b.h, b.orientation)
            row["placement"] = {
                "id": pi.placement.id,
                "x": b.x, "y": b.y, "z": b.z,
                "orientation": b.orientation,
                "dx": dx, "dy": dy, "dz": dz,
                "locked": b.locked,
                "source": b.source,
            }
        rows.append(row)

    return {
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "vehicle_id": plan.vehicle_id,
            "allow_stacking": plan.allow_stacking,
        },
        "vehicle": {
            "id": plan.vehicle.id,
            "name": plan.vehicle.name,
            "cargo_l": v.cargo_l, "cargo_w": v.cargo_w, "cargo_h": v.cargo_h,
            "front_axle_x": v.front_axle_x, "rear_axle_x": v.rear_axle_x,
            "tare_front_kg": v.tare_front_kg, "tare_rear_kg": v.tare_rear_kg,
            "max_front_axle_kg": v.max_front_axle_kg,
            "max_rear_axle_kg": v.max_rear_axle_kg,
            "max_payload_kg": v.max_payload_kg,
            "floor_rating_kg_m2": v.floor_rating_kg_m2,
            "max_lateral_offset_mm": v.max_lateral_offset_mm,
        },
        "rows": rows,
        "analysis": {
            "complete": mt["complete"],
            "cg": None if mt["totals"]["cg_x_mm"] is None else {
                "x": mt["totals"]["cg_x_mm"],
                "y": mt["totals"]["cg_y_mm"],
                "z": mt["totals"]["cg_z_mm"],
            },
            "axle": mt["axle"],
            "lateral": mt["lateral"],
            "known_weight_kg": mt["totals"]["known_weight_kg"],
            "violations": violations,
        },
        "moment_table": mt,
    }
