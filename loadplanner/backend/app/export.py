"""力矩核对表导出（CSV / JSON）。"""
from __future__ import annotations

import csv
import io

from .domain import ORIENTATION_NAMES

HEADER = [
    "标签", "重量kg", "x_mm", "y_mm", "z_mm", "朝向",
    "质心x_mm", "力臂mm(对前轴)", "力矩kg·m", "横向偏心mm", "横向力矩kg·m",
]


def build_csv(state: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    v = state["vehicle"]
    a = state["analysis"]
    mt = state["moment_table"]

    w.writerow([f"装载力矩核对表 - {state['plan']['name']}"])
    w.writerow([f"车辆: {v['name']}",
                f"前轴x={v['front_axle_x']:.0f}mm", f"后轴x={v['rear_axle_x']:.0f}mm",
                f"前轴限值={v['max_front_axle_kg']:.0f}kg", f"后轴限值={v['max_rear_axle_kg']:.0f}kg"])
    if not a["complete"]:
        w.writerow(["警告: 存在未知重量或未摆放的箱体，以下汇总仅覆盖已知部分，不能作为最终依据"])
    w.writerow([])
    w.writerow(HEADER)
    for r in mt["rows"]:
        w.writerow([
            r["label"],
            "未知" if r["weight_kg"] is None else r["weight_kg"],
            r["x_mm"], r["y_mm"], r["z_mm"],
            ORIENTATION_NAMES.get(r["orientation"], r["orientation"]),
            r["x_center_mm"], r["arm_front_axle_mm"],
            "" if r["moment_kg_m"] is None else r["moment_kg_m"],
            r["y_offset_mm"],
            "" if r["lateral_moment_kg_m"] is None else r["lateral_moment_kg_m"],
        ])
    w.writerow([])
    t = mt["totals"]
    w.writerow(["合计(已知重量部分)", t["known_weight_kg"], "", "", "", "",
                t["cg_x_mm"] or "", "", t["known_moment_kg_m"], t["cg_y_mm"] or "", ""])
    if mt["axle"]:
        ax = mt["axle"]
        w.writerow([])
        w.writerow(["轴荷核算", "数值kg", "限值kg", "裕量kg", "判定"])
        w.writerow(["前轴(含空车)", round(ax["front"], 1), ax["front_limit"],
                    round(ax["front_margin"], 1), "OK" if ax["front_ok"] else "超限"])
        w.writerow(["后轴(含空车)", round(ax["rear"], 1), ax["rear_limit"],
                    round(ax["rear_margin"], 1), "OK" if ax["rear_ok"] else "超限"])
    if mt["lateral"]:
        la = mt["lateral"]
        w.writerow(["横向偏移mm", la["offset_mm"], f"±{la['limit_mm']:.0f}", "",
                    "OK" if la["ok"] else "超限"])
    w.writerow([])
    w.writerow(["违规项", len([x for x in a["violations"] if x["severity"] == "error"])])
    for viol in a["violations"]:
        w.writerow([viol["severity"], viol["code"], viol["message"]])
    return buf.getvalue()
