import React, { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Line, Edges } from "@react-three/drei";

// 坐标映射：业务 (x 前→后, y 左→右, z 上) mm → three (x, z, y) m
const S = 0.001;
const p3 = (x, y, z) => [x * S, z * S, y * S];

function CargoHold({ vehicle }) {
  const { cargo_l: L, cargo_w: W, cargo_h: H } = vehicle;
  return (
    <group>
      {/* 车厢线框 */}
      <mesh position={p3(L / 2, W / 2, H / 2)}>
        <boxGeometry args={[L * S, H * S, W * S]} />
        <meshBasicMaterial color="#8aa0b8" wireframe transparent opacity={0.5} />
      </mesh>
      {/* 底板 */}
      <mesh position={p3(L / 2, W / 2, -2)} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[L * S, W * S]} />
        <meshStandardMaterial color="#2b3442" />
      </mesh>
      <gridHelper
        args={[L * S, 21, "#3d4b61", "#2e3a4c"]}
        position={p3(L / 2, W / 2, 0.5)}
        rotation={[0, 0, 0]}
        scale={[1, 1, W / L]}
      />
      {/* 前壁标记（x=0 为车头方向） */}
      <mesh position={p3(0, W / 2, H / 2)} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[W * S, H * S]} />
        <meshStandardMaterial color="#33465e" transparent opacity={0.35} side={2} />
      </mesh>
    </group>
  );
}

function AxleMarkers({ vehicle }) {
  const { cargo_w: W, cargo_h: H, front_axle_x: fx, rear_axle_x: rx } = vehicle;
  const mk = (ax, color) => (
    <group key={ax}>
      <mesh position={p3(ax, W / 2, H / 2)} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[W * S, H * S]} />
        <meshStandardMaterial color={color} transparent opacity={0.12} side={2} depthWrite={false} />
      </mesh>
      <Line
        points={[p3(ax, 0, 0), p3(ax, W, 0)]}
        color={color}
        lineWidth={3}
      />
    </group>
  );
  return (
    <>
      {mk(fx, "#e74c3c")}
      {mk(rx, "#3498db")}
    </>
  );
}

function CargoBox({ row, violated, selected, onSelect }) {
  const { placement } = row;
  const { x, y, z, dx, dy, dz, locked } = placement;
  const color = violated ? "#e74c3c" : row.item.color;
  return (
    <mesh
      position={p3(x + dx / 2, y + dy / 2, z + dz / 2)}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(row.key);
      }}
    >
      <boxGeometry args={[dx * S, dz * S, dy * S]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={selected ? 0.95 : 0.8}
        emissive={selected ? "#ffffff" : "#000000"}
        emissiveIntensity={selected ? 0.25 : 0}
      />
      <Edges scale={1.002} color={locked ? "#f1c40f" : violated ? "#ff7675" : "#1c2733"} />
    </mesh>
  );
}

function CgMarker({ cg, vehicle }) {
  if (!cg) return null;
  const off = vehicle.max_lateral_offset_mm;
  const { cargo_l: L, cargo_w: W } = vehicle;
  return (
    <group>
      {/* 总质心 */}
      <mesh position={p3(cg.x, cg.y, cg.z)}>
        <sphereGeometry args={[0.09, 24, 24]} />
        <meshStandardMaterial color="#ff2d78" emissive="#ff2d78" emissiveIntensity={0.6} />
      </mesh>
      <Line points={[p3(cg.x, cg.y, 0), p3(cg.x, cg.y, cg.z)]} color="#ff2d78" dashed dashSize={0.08} gapSize={0.05} />
      {/* 横向允许走廊 */}
      <mesh position={p3(L / 2, W / 2, 30)}>
        <boxGeometry args={[L * S, 0.03, 2 * off * S]} />
        <meshBasicMaterial color="#2ecc71" transparent opacity={0.12} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Doors({ vehicle }) {
  const rw = vehicle.rear_door_w ?? vehicle.cargo_w;
  const rh = vehicle.rear_door_h ?? vehicle.cargo_h;
  return (
    <>
      {/* 尾门（x = 车尾） */}
      <mesh position={p3(vehicle.cargo_l, vehicle.cargo_w / 2, rh / 2)} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[rw * S, rh * S]} />
        <meshBasicMaterial color="#2ecc71" transparent opacity={0.18} side={2} depthWrite={false} />
      </mesh>
      {/* 侧门（y = 右侧墙） */}
      {vehicle.side_door_w != null && (
        <mesh position={p3(
          (vehicle.side_door_x ?? 0) + vehicle.side_door_w / 2,
          vehicle.cargo_w,
          (vehicle.side_door_h ?? vehicle.cargo_h) / 2,
        )}>
          <planeGeometry args={[vehicle.side_door_w * S, (vehicle.side_door_h ?? vehicle.cargo_h) * S]} />
          <meshBasicMaterial color="#e67e22" transparent opacity={0.25} side={2} depthWrite={false} />
        </mesh>
      )}
    </>
  );
}

export default function Scene3D({ state, selectedKey, onSelect }) {
  const { vehicle, rows, analysis } = state;
  const violatedKeys = useMemo(() => {
    const s = new Set();
    for (const v of analysis.violations) {
      if (v.severity === "error") v.keys.forEach((k) => s.add(k));
    }
    return s;
  }, [analysis]);

  return (
    <Canvas
      camera={{ position: [7.5, 4.5, 6.5], fov: 45, far: 200 }}
      style={{ background: "#1c2733" }}
    >
      <ambientLight intensity={0.7} />
      <directionalLight position={[6, 10, 4]} intensity={1.1} />
      <CargoHold vehicle={vehicle} />
      <AxleMarkers vehicle={vehicle} />
      <Doors vehicle={vehicle} />
      {rows
        .filter((r) => r.placement)
        .map((r) => (
          <CargoBox
            key={r.key}
            row={r}
            violated={violatedKeys.has(r.key)}
            selected={selectedKey === r.key}
            onSelect={onSelect}
          />
        ))}
      <CgMarker cg={analysis.cg} vehicle={vehicle} />
      <OrbitControls target={p3(vehicle.cargo_l / 2, vehicle.cargo_w / 2, 400)} />
    </Canvas>
  );
}
