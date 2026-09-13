# 装载试算培训系统（Load Planner）

运输工程培训用的可视化装载试算工具：关注**重量与重心**，而不只是"货箱能不能塞进车厢"。

- **React + Three.js**：车厢、箱体、总质心、前后轴与横向允许走廊的三维展示
- **FastAPI + OR-Tools (CP-SAT)**：候选位置求解，轴荷/横向约束直接内化在模型里
- **PostgreSQL**：保存箱体尺寸、重量、朝向约束与方案（测试用 SQLite，部署默认 PostgreSQL）

## 模型边界（重要）

- 仅限**刚性矩形货箱**、轴对齐摆放（6 种朝向）；
- 支撑条件：底板支撑，可选堆叠（上层必须被可堆叠箱体完整支撑，顶面承压受限）；
- **简化静态轴荷**：刚性车体 + 前后两轴静力平衡，不做悬架/侧倾/制动动态分析；
- 横向只校核总质心偏移，不替代侧倾稳定性校核；
- **不连接实际运输调度，不替代安全鉴定**，仅用于教学试算。

## 业务规则

- 越界、相交、承压超限（底板面压 / 顶面堆压）、轴荷超限、横向偏心、朝向违规，**全部定位到具体对象**（违规条目携带货物 key，前端点击可高亮）；
- **未知重量绝不按 0 处理**：存在未知重量时轴荷/质心结论标记为无效，求解接口直接拒绝（422），补录重量后方可计算；
- 人工摆放可**锁定**，求解器只计算剩余部分；锁定导致无可行解时返回 409 并说明；
- 导出**逐件位置 + 力矩核对表**（CSV/JSON），可手工复核每件对前轴的力臂与力矩，而非只看三维动画。

## 快速开始

### 方式一：Docker（PostgreSQL + 后端）

```bash
cp .env.example .env              # 填入本机 PostgreSQL 用户、口令与 DATABASE_URL
docker compose up --build        # API 在 :8000，自动建表并灌入演示样例
```

`.env` 只保存本机连接信息，已被忽略；不要把真实口令提交到仓库。

### 方式二：本地开发

```bash
# 后端（默认连 PostgreSQL；无数据库时可用 SQLite 体验）
cd backend
pip install -r requirements.txt
DATABASE_URL="sqlite+pysqlite:///./demo.db" uvicorn app.main:app --reload

# 前端（另开终端）
cd frontend
npm install
npm run dev                    # :5173，代理 /api 到 :8000
```

前端 `npm run build` 之后，后端会在 `:8000` 直接托管页面，单进程即可运行。

### 运行测试

```bash
cd backend && python -m pytest -q     # 31 个测试：物理/校验/求解器/端到端 API
```

## 内置验证样例

| 样例 | 现象 | 教学点 |
|---|---|---|
| A 体积能容纳但前轴超限 | 1500 kg 机组锁定在车厢最前部，前轴 3246 kg > 3200 kg | 杠杆效应：质心越靠前，前轴反力越大；锁定状态下求解返回 409（纸箱全放车尾也救不回），解锁后重排合规 |
| B 偏心货箱 | 宽体设备贴一侧，横向偏移 -450 mm 超出 ±250 mm | 总质心横向约束 |
| C 禁止倒置 | 仪器柜被锁定为侧放朝向 | 朝向约束校验；求解器只选保持竖直的朝向 |
| D 底板承压超限 | 400 kg 钢锭箱面压 2500 kg/m² > 2000 | 承压超限定位到具体箱体 |
| E 未知重量 | 待称重件未补录 | 轴荷结论判无效 + 求解 422，补录后可解 |

## API 摘要

```
GET/POST  /api/vehicles                 车辆（车厢尺寸、轴位、轴荷限值、面压额定）
GET/POST  /api/items                    箱体（尺寸、重量可空、朝向/堆叠约束）
PATCH     /api/items/{id}               补录重量等
GET/POST  /api/plans                    方案
GET       /api/plans/{id}               完整状态：摆放 + 违规 + 质心/轴荷 + 力矩表
POST      /api/plans/{id}/placements    人工摆放并锁定（upsert）
DELETE    /api/placements/{id}          移除摆放（交还求解器）
POST      /api/plans/{id}/solve         求解剩余部分（保留锁定件）
POST      /api/plans/{id}/clear-unlocked
GET       /api/plans/{id}/export.csv    力矩核对表（含轴荷核算与违规清单）
GET       /api/plans/{id}/export.json
```

## 坐标与单位约定

- 长度 mm、重量 kg；x 从车厢前壁指向车尾，y 从左壁向右，z 从底板向上；
- 朝向编码 0–5：`正放 / 正放转90° / 侧放 / 侧放转90° / 立放 / 立放转90°`；
- 轴荷：`前轴 = 空车前轴 + W·(x后轴 − x质心)/轴距`，后轴同理；质心在前轴之前时前轴反力大于货重。

## 目录结构

```
backend/
  app/domain.py      领域模型、朝向编码、AABB 相交
  app/physics.py     质心、双轴轴荷、逐件力矩表
  app/validation.py  逐对象定位的违规校验
  app/solver.py      OR-Tools CP-SAT 求解（轴荷/横向约束内化）
  app/analysis.py    ORM → 领域对象装配、方案状态
  app/main.py        FastAPI 端点
  app/seed.py        五个演示样例
  tests/             31 个测试
frontend/
  src/components/Scene3D.jsx        车厢/箱体/质心/轴 三维视图
  src/components/ItemPanel.jsx      货物清单与人工摆放锁定
  src/components/ViolationPanel.jsx 违规列表（点击定位）
  src/components/MomentTable.jsx    力矩核对表与轴荷条
```
