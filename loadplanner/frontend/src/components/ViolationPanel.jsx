import React from "react";

const CODE_NAMES = {
  UNKNOWN_WEIGHT: "重量未知",
  UNPLACED_ITEM: "未摆放",
  OUT_OF_BOUNDS: "越界",
  OVERLAP: "相交",
  ORIENTATION_VIOLATION: "朝向违规",
  SUPPORT_VIOLATION: "支撑不足",
  TOP_LOAD_EXCEEDED: "顶面承压超限",
  FLOOR_BEARING_EXCEEDED: "底板承压超限",
  PAYLOAD_EXCEEDED: "总载重超限",
  FRONT_AXLE_EXCEEDED: "前轴超限",
  REAR_AXLE_EXCEEDED: "后轴超限",
  LATERAL_OFFSET_EXCEEDED: "横向偏心超限",
};

export default function ViolationPanel({ violations, onFocus }) {
  const errors = violations.filter((v) => v.severity === "error");
  const warns = violations.filter((v) => v.severity !== "error");
  return (
    <div className="violation-panel">
      <h3>
        违规检查{" "}
        <span className={errors.length ? "count bad" : "count ok"}>
          {errors.length ? `${errors.length} 项错误` : "无错误"}
        </span>
      </h3>
      {errors.map((v, i) => (
        <div key={i} className="violation error" onClick={() => onFocus(v.keys)}>
          <span className="vcode">{CODE_NAMES[v.code] || v.code}</span>
          <span className="vmsg">{v.message}</span>
        </div>
      ))}
      {warns.map((v, i) => (
        <div key={`w${i}`} className="violation warn" onClick={() => onFocus(v.keys)}>
          <span className="vcode">{CODE_NAMES[v.code] || v.code}</span>
          <span className="vmsg">{v.message}</span>
        </div>
      ))}
    </div>
  );
}
