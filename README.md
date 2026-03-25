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
- **自动化发现**：可按天扫描 OpenAlex 中的 arXiv / 顶会论文，自动把 QS100 学校里的新团队或新论文补回仓库，不再局限于 `data/institutions.json` 里已经存在的学校

## 管理学者数据

```bash
# 添加新学者
cd scripts && python add_researcher.py

# 更新已有条目（如添加联系记录、更新申请状态）
cd scripts && python add_researcher.py --update uid-001

# 重新生成 Dashboard
cd scripts && python build_dashboard.py
```

## 每日自动化

仓库已经可以接一个 GitHub Actions 定时流程：

- 每天扫描近几天的 OpenAlex 论文结果，重点看 AI4DB 相关关键词
- 只自动加入 QS 排名 `<= 100` 的大学；如果学校还没出现在 `data/institutions.json`，脚本会保留一个可读的 `institution_display_name`，并用生成的 key 写进 `data/researchers.json`
- 对已存在的研究者，只补充缺失的 `notable_papers`
- 生成新的 `data/researchers.json`、`data/researchers.csv` 和 `dashboard.html` 后自动 push

本地试跑：

```bash
cd scripts
python discover_research_teams.py --dry-run
python discover_research_teams.py --apply
python build_dashboard.py
```

如果某个学校不在 QS<100 的范围内，脚本会跳过，不会自动入库。

## 离线使用

```bash
cd scripts && python build_dashboard.py --offline
```

生成的 `dashboard.html` 为自包含单文件，可直接分享。

## 线上部署

仓库已经补了 GitHub Pages 的部署 workflow。只要把 GitHub Pages 的 Source 设成 `GitHub Actions`，后续每次 `main` 分支有更新时，都会自动重建并发布网站。

线上页面会用 `dashboard.html` 生成对应的 `index.html`，因此可以直接作为静态站点访问。

## 数据结构

- `data/researchers.json` — 学者数据（核心）
- `data/institutions.json` — 机构信息（QS排名、经纬度）
- `data/qs_rankings.json` — QS 2026 排名缓存，自动发现时用它判断是否满足 `QS <= 100`
- `data/schema.md` — 字段说明
- `data/researchers.csv` — 自动导出的 CSV（每次 build 时生成）
