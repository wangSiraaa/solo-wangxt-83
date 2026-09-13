from typing import Optional

from pydantic import BaseModel, Field


class VehicleIn(BaseModel):
    name: str
    cargo_l: int = Field(gt=0)
    cargo_w: int = Field(gt=0)
    cargo_h: int = Field(gt=0)
    front_axle_x: float
    rear_axle_x: float
    tare_front_kg: float = 0
    tare_rear_kg: float = 0
    max_front_axle_kg: float
    max_rear_axle_kg: float
    max_payload_kg: float
    floor_rating_kg_m2: float = 1500
    max_lateral_offset_mm: float = 250


class VehicleOut(VehicleIn):
    id: int

    class Config:
        from_attributes = True


class ItemIn(BaseModel):
    name: str
    l: int = Field(gt=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    weight_kg: Optional[float] = None  # None = 未知，禁止按 0 处理
    no_flip: bool = False
    can_rotate_yaw: bool = True
    stackable: bool = False
    max_top_load_kg: Optional[float] = None
    color: str = "#4f8ef7"


class ItemPatch(BaseModel):
    name: Optional[str] = None
    weight_kg: Optional[float] = None
    no_flip: Optional[bool] = None
    can_rotate_yaw: Optional[bool] = None
    stackable: Optional[bool] = None
    max_top_load_kg: Optional[float] = None
    color: Optional[str] = None


class ItemOut(ItemIn):
    id: int

    class Config:
        from_attributes = True


class PlanItemIn(BaseModel):
    item_id: int
    quantity: int = Field(default=1, ge=1, le=50)


class PlanIn(BaseModel):
    name: str
    vehicle_id: int
    allow_stacking: bool = False
    items: list[PlanItemIn] = []


class PlanOut(BaseModel):
    id: int
    name: str
    vehicle_id: int
    allow_stacking: bool
    item_count: int


class PlacementIn(BaseModel):
    plan_item_id: int
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    z: int = Field(ge=0)
    orientation: int = Field(ge=0, le=5)
