from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    cargo_l: Mapped[int] = mapped_column(Integer)   # mm
    cargo_w: Mapped[int] = mapped_column(Integer)
    cargo_h: Mapped[int] = mapped_column(Integer)
    front_axle_x: Mapped[float] = mapped_column(Float)  # mm，距前壁
    rear_axle_x: Mapped[float] = mapped_column(Float)
    tare_front_kg: Mapped[float] = mapped_column(Float)
    tare_rear_kg: Mapped[float] = mapped_column(Float)
    max_front_axle_kg: Mapped[float] = mapped_column(Float)
    max_rear_axle_kg: Mapped[float] = mapped_column(Float)
    max_payload_kg: Mapped[float] = mapped_column(Float)
    floor_rating_kg_m2: Mapped[float] = mapped_column(Float, default=1500.0)
    max_lateral_offset_mm: Mapped[float] = mapped_column(Float, default=250.0)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    l: Mapped[int] = mapped_column(Integer)  # mm
    w: Mapped[int] = mapped_column(Integer)
    h: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)  # None=未知
    no_flip: Mapped[bool] = mapped_column(Boolean, default=False)          # 禁止倒置
    can_rotate_yaw: Mapped[bool] = mapped_column(Boolean, default=True)
    stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    max_top_load_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="#4f8ef7")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    allow_stacking: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    vehicle: Mapped[Vehicle] = relationship()
    plan_items: Mapped[list["PlanItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanItem(Base):
    """方案中的一件货（同种箱体多件时逐件一行）。"""
    __tablename__ = "plan_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    copy_index: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str] = mapped_column(String(200))

    plan: Mapped[Plan] = relationship(back_populates="plan_items")
    item: Mapped[Item] = relationship()
    placement: Mapped["Placement | None"] = relationship(
        back_populates="plan_item", cascade="all, delete-orphan", uselist=False
    )


class Placement(Base):
    """一件货的摆放。locked=True 表示人工锁定，求解器不得改动。"""
    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_item_id: Mapped[int] = mapped_column(ForeignKey("plan_items.id"), unique=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    z: Mapped[int] = mapped_column(Integer)
    orientation: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|solver
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    plan_item: Mapped[PlanItem] = relationship(back_populates="placement")
