# AI4DB Research Teams Tracker

LLM + Database 方向（NL2SQL / Data Agents）学者与团队追踪系统。

## Quick Start

```bash
# 安装依赖
pip install -r scripts/requirements.txt

# 生成 Dashboard
cd scripts && python build_dashboard.py && cd ..

# 浏览器打开
open dashboard.html
```

## 功能

- **5 Tab Dashboard**：世界地图 / 机构分布 / 研究方向 / 申请看板 / 完整表格
- **结构化数据**：`data/researchers.json` 存储所有学者信息，支持筛选、排序、导出
- **CLI 工具**：交互式添加/更新学者条目

## 管理学者数据

```bash
# 添加新学者
cd scripts && python add_researcher.py

# 更新已有条目（如添加联系记录、更新申请状态）
cd scripts && python add_researcher.py --update uid-001

# 重新生成 Dashboard
cd scripts && python build_dashboard.py
```

## 离线使用

```bash
cd scripts && python build_dashboard.py --offline
```

生成的 `dashboard.html` 为自包含单文件，可直接分享。

## 数据结构

- `data/researchers.json` — 学者数据（核心）
- `data/institutions.json` — 机构信息（QS排名、经纬度）
- `data/schema.md` — 字段说明
- `data/researchers.csv` — 自动导出的 CSV（每次 build 时生成）
