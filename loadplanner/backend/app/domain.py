"""领域模型与几何基础。

约定：
- 单位：长度 mm，重量 kg。
- 坐标系：x 从车厢前壁指向车尾，y 从车厢左壁指向右壁，z 从底板向上。
- 朝向编码 0..5 表示刚性矩形箱体的 6 种轴对齐摆放方式。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# 朝向编码 -> (l,w,h) 中哪一维落到 (dx,dy,dz)
ORIENTATION_PERM = {
    0: (0, 1, 2),  # (l,w,h) 正放
    1: (1, 0, 2),  # (w,l,h) 正放·偏航90°
    2: (1, 2, 0),  # (w,h,l) 侧放
    3: (2, 1, 0),  # (h,w,l) 侧放·偏航90°
    4: (0, 2, 1),  # (l,h,w) 立放
    5: (2, 0, 1),  # (h,l,w) 立放·偏航90°
}

ORIENTATION_NAMES = {
    0: "正放",
    1: "正放·转90°",
    2: "侧放",
    3: "侧放·转90°",
    4: "立放",
    5: "立放·转90°",
}


def dims_for(l: int, w: int, h: int, code: int) -> tuple[int, int, int]:
    """返回某朝向下箱体的 (dx, dy, dz)。"""
    p = ORIENTATION_PERM[code]
    dims = (l, w, h)
    return dims[p[0]], dims[p[1]], dims[p[2]]


def allowed_codes(no_flip: bool, can_rotate_yaw: bool) -> list[int]:
    """根据约束过滤可用朝向。

    no_flip=True 禁止倒置/侧倒：原始高度方向必须保持竖直（仅剩 0/1）。
    can_rotate_yaw=False 禁止绕竖直轴转动（只保留偶数编码）。
    """
    codes = list(range(6))
    if no_flip:
        codes = [c for c in codes if ORIENTATION_PERM[c][2] == 2]
    if not can_rotate_yaw:
        codes = [c for c in codes if c % 2 == 0]
    return codes or [0]


def aabb_overlap(a: tuple, b: tuple) -> bool:
    """两个轴对齐盒 (x,y,z,dx,dy,dz) 是否相交（贴面不算相交）。"""
    ax, ay, az, adx, ady, adz = a
    bx, by, bz, bdx, bdy, bdz = b
    return (
        ax < bx + bdx and bx < ax + adx
        and ay < by + bdy and by < ay + ady
        and az < bz + bdz and bz < az + adz
    )


@dataclass
class VehicleSpec:
    cargo_l: int
    cargo_w: int
    cargo_h: int
    front_axle_x: float        # 前轴中心到车厢前壁的距离 mm
    rear_axle_x: float         # 后轴中心到车厢前壁的距离 mm
    tare_front_kg: float       # 空车前轴荷
    tare_rear_kg: float        # 空车后轴荷
    max_front_axle_kg: float
    max_rear_axle_kg: float
    max_payload_kg: float
    floor_rating_kg_m2: float  # 底板面承压上限 kg/m²
    max_lateral_offset_mm: float  # 允许的总质心横向偏移
    # 门：尾门默认与车厢同截面；侧门在 y=cargo_w 一侧，None 表示无侧门
    rear_door_w: Optional[float] = None
    rear_door_h: Optional[float] = None
    side_door_x: Optional[float] = None   # 侧门起点（距前壁）
    side_door_w: Optional[float] = None   # 侧门纵向宽度
    side_door_h: Optional[float] = None

    @property
    def wheelbase(self) -> float:
        return self.rear_axle_x - self.front_axle_x


@dataclass
class BoxSpec:
    """方案中的一件货（可能已摆放，可能未摆放）。"""
    key: str                    # 业务键，如 "pi-17"（plan_item id）
    label: str
    l: int
    w: int
    h: int
    weight_kg: Optional[float]  # None = 重量未知，绝不能按 0 处理
    no_flip: bool
    can_rotate_yaw: bool
    stackable: bool
    max_top_load_kg: Optional[float]
    placed: bool = False
    x: int = 0
    y: int = 0
    z: int = 0
    orientation: int = 0
    locked: bool = False
    source: str = "manual"      # manual | solver
    stop_seq: Optional[int] = None  # 卸货站点序号；None = 随车不卸

    def dims(self) -> tuple[int, int, int]:
        return dims_for(self.l, self.w, self.h, self.orientation)

    def aabb(self) -> tuple:
        dx, dy, dz = self.dims()
        return (self.x, self.y, self.z, dx, dy, dz)

    def center(self) -> tuple[float, float, float]:
        dx, dy, dz = self.dims()
        return (self.x + dx / 2, self.y + dy / 2, self.z + dz / 2)
