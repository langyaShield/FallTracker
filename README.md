# FallTracker

秋招投递追踪与管理平台 —— 帮助你高效管理求职投递、面试日程、简历和职位雷达的一站式工具。

![status](https://img.shields.io/badge/status-running-brightgreen) ![docker](https://img.shields.io/badge/docker-ready-blue) ![stack](https://img.shields.io/badge/Vue3%20%2B%20FastAPI-success)

---

## 目录

- [功能概览](#功能概览)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [数据模型](#数据模型)
- [API 路由](#api-路由)
- [前端页面](#前端页面)
- [快速开始](#快速开始)
  - [本地开发](#本地开发)
  - [Docker 部署（推荐）](#docker-部署推荐)
  - [WSL2 + Windows Docker 部署](#wsl2--windows-docker-部署)
- [环境变量](#环境变量)
- [爬虫配置模板](#爬虫配置模板)
- [近期重构与新增功能](#近期重构与新增功能)
- [辅助脚本](#辅助脚本)
- [License](#license)

---

## 功能概览

### 核心功能

- **投递管理** — 记录每一条投递（公司、岗位、状态、标签、截止日期），关联简历和面试事件
- **面试日历** — 日历视图集中查看所有面试与截止日期，支持 ICS 导出订阅
- **面试复盘** — 记录面试笔记，LLM 辅助生成结构化 Q&A 和反思总结
- **简历管理** — 上传 PDF / Word (.docx) / 图片简历，自动 OCR 提取文本并支持全文搜索
- **职位雷达** — 配置爬虫定时抓取招聘网站，LLM 智能分析匹配结果，邮件 + 站内通知
- **数据统计** — 投递状态分布、时间线等多维度统计分析
- **用户设置** — 自定义 LLM API（DeepSeek 等）和邮件 SMTP 配置

### 增强功能（本轮新增）

- **🔔 站内通知中心** — 雷达命中、爬虫失败、面试 24h 提醒统一收件，未读数实时显示
- **📅 ICS 日历导出** — 一键导出 RFC 5545 标准的 .ics 文件，可导入 Google Calendar / Outlook
- **⏰ 面试前 24h 提醒** — 日历页顶部告警 + 通知中心推送，提前 10 分钟准备
- **📄 简历 .docx 支持** — 原生支持 Microsoft Word 简历（python-docx 解析）
- **📊 面试失败/复盘分级提示** — HomePage 错误消息按严重度分级（error/warning）

---

## 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| Python 3.12 | 运行时 |
| FastAPI | Web 框架 |
| SQLAlchemy 2.x | ORM |
| SQLite | 数据库 |
| PyMuPDF + Tesseract OCR + python-docx | 简历文本提取 |
| python-jose + passlib (bcrypt 4.x) | JWT 认证 & 密码加密（72 字节兼容） |
| httpx + BeautifulSoup4 | 爬虫 HTTP 请求 & HTML 解析 |
| Pydantic Settings | 环境变量管理 |

### 前端

| 技术 | 用途 |
|------|------|
| Vue 3 + `<script setup>` | UI 框架 |
| TypeScript | 类型安全 |
| Vite 5 | 构建工具 |
| Element Plus | UI 组件库 |
| Tailwind CSS | 原子化样式 |
| Pinia | 状态管理 |
| Vue Router | 路由 |
| Axios | HTTP 客户端（含 401 全局拦截） |
| Lucide Icons | 图标库 |

### 部署

| 技术 | 用途 |
|------|------|
| Docker (多阶段构建) | 容器化 |
| Docker Compose | 服务编排 |
| Uvicorn (2 workers) | ASGI 服务器 |
| FastAPI StaticFiles | 同进程托管前端 SPA |

---

## 项目结构

```
FallTracker/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口、路由注册、异常处理、SPA 静态服务
│   │   ├── config.py            # 环境变量配置
│   │   ├── database.py          # 数据库引擎 & 会话
│   │   ├── models.py            # SQLAlchemy 数据模型（11 张表）
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── auth.py              # JWT 令牌 & 密码工具（含 72 字节截断）
│   │   ├── ocr.py               # OCR 文本提取（PDF / 图片 / .docx）
│   │   ├── routers/
│   │   │   ├── auth.py          # 注册 / 登录 / 当前用户
│   │   │   ├── deliveries.py    # 投递记录 CRUD（带 limit/offset 分页）
│   │   │   ├── events.py        # 面试事件 CRUD + ICS 导出
│   │   │   ├── resumes.py       # 简历上传 / OCR / 搜索
│   │   │   ├── reviews.py       # 面试复盘 CRUD
│   │   │   ├── radar.py         # 爬虫配置 / 执行 / 结果（薄路由层）
│   │   │   ├── statistics.py    # 统计数据
│   │   │   ├── settings.py      # 用户设置
│   │   │   └── notifications.py # ⭐ 站内通知 CRUD
│   │   └── services/
│   │       └── radar/           # ⭐ B-1 拆分后的雷达服务
│   │           ├── __init__.py  # re-export 兼容旧调用
│   │           ├── fetcher.py   # HTTP 抓取 / 重试 / HTML 解析
│   │           ├── llm.py       # LLM 分析 + pre-fetch settings
│   │           ├── email.py     # SMTP 通知
│   │           ├── engine.py    # 单次执行编排 + 触发站内通知
│   │           └── scheduler.py # APScheduler 后台调度 + 面试提醒 tick
│   ├── spiders/                 # 爬虫配置模板（BOSS直聘、51job、拉勾、猎聘）
│   ├── data/                    # SQLite 数据库（容器内 /app/backend/data/）
│   ├── uploads/                 # 上传的简历文件
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                   # 本地开发启动脚本
├── frontend/
│   ├── src/
│   │   ├── pages/               # 页面组件
│   │   ├── layouts/             # 布局组件（含 NotificationCenter 集成）
│   │   ├── components/
│   │   │   ├── PageHeader.vue   # ⭐ 公共页头组件
│   │   │   ├── NotificationCenter.vue # ⭐ 站内通知中心
│   │   │   └── radar/
│   │   │       └── RadarEmailSettings.vue # ⭐ 雷达页邮箱 Tab
│   │   ├── composables/         # 组合式函数（useTheme 等）
│   │   ├── stores/
│   │   │   └── auth.ts          # ⭐ 含 401 全局拦截 + HMR dispose 守卫
│   │   ├── router/
│   │   └── lib/                 # 工具函数（错误提取、常量映射等）
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── scripts/
│   ├── deploy.sh                # Docker 部署脚本
│   ├── kill_old_backend.sh      # 清理旧容器
│   ├── wsl_docker_check.sh      # ⭐ WSL 中检查 Docker
│   ├── wsl_docker_build.sh      # ⭐ WSL 中构建镜像
│   ├── wsl_docker_run.sh        # ⭐ WSL 中启动容器
│   ├── wsl_docker_inspect.sh    # ⭐ WSL 中查看容器状态
│   ├── fix_calendar_wsl.sh      # ⭐ 修复 WSL 文件缓存问题
│   └── test_health.ps1          # ⭐ 主机端健康检查
├── Dockerfile                   # 多阶段构建（前端构建 + 后端运行）
├── docker-compose.yml           # 容器编排（适配 2GB 内存服务器）
├── linkup.md                    # ⭐ 完整的多 Agent 协作记录
└── .gitignore
```

---

## 数据模型

| 模型 | 说明 | 状态 |
|------|------|------|
| `User` | 用户账户（bcrypt 密码哈希） | ✅ |
| `Delivery` | 投递记录（公司、岗位、状态、标签、截止日期） | ✅ |
| `InterviewEvent` | 面试事件（轮次、时间、时长、地点、会议链接） | ✅ |
| `Resume` | 简历（文件路径、OCR 文本、OCR 状态与进度） | ✅ |
| `Review` | 面试复盘（原始笔记、结构化 Q&A、标签、反思） | ✅ |
| **`Notification`** | **⭐ 站内通知（类型、标题、正文、是否已读、关联资源）** | ✅ |
| `RadarJob` | 雷达抓取的职位（来源、公司、岗位、链接、MD5 去重） | ⚠️ 死模型 |
| `RadarFilter` | 用户雷达过滤标签 | ⚠️ 死模型 |
| `CrawlerConfig` | 爬虫配置（URL、CSS 选择器、间隔、目标描述、邮件通知） | ✅ |
| `CrawlerResult` | 爬虫执行结果（原始文本、LLM 分析、是否命中、邮件状态） | ✅ |
| `UserSettings` | 用户设置（LLM API、SMTP 邮件配置） | ✅ |

> 标记 ⚠️ 死模型已在 `models.py` 加 `DEPRECATED` 注释，等待 T2-3（启用 RadarJob / RadarFilter）激活。

---

## API 路由

所有接口前缀为 `/api`，需要 JWT 认证（注册/登录除外）。

| 路由模块 | 端点前缀 | 功能 |
|----------|----------|------|
| auth | `/api/auth` | 注册、登录、获取当前用户 |
| deliveries | `/api/deliveries` | 投递记录增删改查（带分页） |
| **events** | `/api/events` | 面试事件 CRUD + **`GET /export.ics`** 导出 |
| resumes | `/api/resumes` | 简历上传、OCR（PDF/图片/.docx）、搜索、预览 |
| reviews | `/api/reviews` | 面试复盘增删改查 |
| radar | `/api/radar` | 爬虫配置管理、手动执行、结果查询 |
| statistics | `/api/statistics` | 统计数据查询 |
| settings | `/api/settings` | 用户 LLM / 邮件设置 |
| **notifications** | **`/api/notifications`** | ⭐ **站内通知：列表 / 未读数 / 标记已读 / 删除** |

健康检查：`GET /health`（返回 `{"status":"ok"}`）
OpenAPI 文档：`GET /docs`（Swagger UI）

---

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | LoginPage | 用户登录 |
| `/register` | RegisterPage | 用户注册 |
| `/dashboard` | DashboardPage | 仪表盘（默认首页） |
| `/delivery/:id` | DeliveryDetailPage | 投递详情 |
| `/calendar` | CalendarPage | 面试日历（24h 提醒 + ICS 导出） |
| `/radar` | RadarPage | 职位雷达（Tab 拆分：基本 / 邮箱） |
| `/resumes` | ResumesPage | 简历管理（PDF + Word + 图片） |
| `/reviews` | ReviewsPage | 面试复盘 |
| `/statistics` | StatisticsPage | 数据统计 |
| `/settings` | SettingsPage | 用户设置 |

全局组件：
- 顶部铃铛 + 通知中心 [NotificationCenter.vue](file://./frontend/src/components/NotificationCenter.vue)（sidebar footer 集成）
- 公共页头 [PageHeader.vue](file://./frontend/src/components/PageHeader.vue)（消除 7 页面重复 CSS）

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 22+ & pnpm
- Tesseract OCR（用于简历 OCR 功能）
- Docker（推荐）或本地 Python + Node 环境

### 本地开发

**1. 后端**

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入配置
pip install -r requirements.txt
python run.py
```

后端运行在 `http://127.0.0.1:8000`。

**2. 前端**

```bash
cd frontend
pnpm install
pnpm dev
```

前端运行在 `http://localhost:5173`，API 请求自动代理到后端。

### Docker 部署（推荐）

```bash
# 一键部署
bash scripts/deploy.sh

# 或手动操作
docker compose build --pull
docker compose up -d
```

部署后访问 `http://YOUR_SERVER_IP`，健康检查 `http://YOUR_SERVER_IP/health`。

常用命令：

```bash
docker compose logs -f     # 查看日志
docker compose ps          # 查看状态
docker compose down        # 停止服务
docker compose restart     # 重启服务
```

### WSL2 + Windows Docker 部署

> 适用于本机为 Windows 11 + WSL2 + Docker Desktop 的开发场景。**避开了 Windows 文件锁问题**（NTFS + SQLite WAL 在 pytest 时会卡住）。

**前置**：Docker Desktop 已安装并启动；WSL2 启用 Ubuntu 发行版。

**一键流程**：

```powershell
# 1. 构建镜像（在 WSL 中调 Windows 的 Docker Desktop）
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_build.sh

# 2. 启动容器
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_run.sh

# 3. 查看状态
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_inspect.sh
```

**手动启动**（如需自定义）：

```bash
wsl -d Ubuntu-22.04
export DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
export PATH="$(dirname "$DOCKER_BIN"):$PATH"

# 将 <your-workspace-path> 替换为你的项目所在路径
# 例：cd /mnt/c/Users/<你的用户名>/Desktop/test/FallTracker
cd <your-workspace-path>/FallTracker

docker build -t falltracker:latest -f Dockerfile .
docker run -d --name falltracker -p 8000:8000 \
  -e JWT_SECRET="dev-secret-please-change" \
  falltracker:latest
```

**访问**：打开浏览器 → **http://localhost:8000/**

> 容器中 FastAPI 进程直接托管前端 SPA（无需 nginx），**单端口 8000** 同时提供 API + 前端。

**已知坑**：
- WSL 对 Windows 文件系统 `/mnt/c/...` 有缓存，编辑文件后用 `touch` 强制刷新元数据
- 容器内 SQLite 默认不持久化（数据存 `/app/backend/data/`），需 `-v` 挂载才持久

---

## 环境变量

### 后端（`backend/.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///./falltracker.db` | 数据库连接 |
| `SECRET_KEY` | `change-me-to-a-random-secret-key` | JWT 签名密钥（**生产环境务必修改**） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token 过期时间（分钟，默认 7 天） |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接（预留） |
| `LLM_API_KEY` | 空 | LLM API 密钥 |
| `LLM_API_BASE` | `https://api.deepseek.com/v1` | LLM API 地址 |
| `LLM_MODEL` | `deepseek-chat` | LLM 模型名称 |

### 前端

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE` | API 基础路径（默认 `/api`） |

---

## 爬虫配置模板

`backend/spiders/` 目录下提供了主流招聘网站的爬虫配置模板：

- `boss-zhipin.json` — BOSS 直聘
- `51job.json` — 前程无忧
- `lagou.json` — 拉勾网
- `liepin.json` — 猎聘网
- `sample-template.json` — 通用模板
- `regex-example.json` — 正则提取示例

雷达触发链路：
- **命中** → 写 `CrawlerResult` → 发邮件 → **写站内通知** ⭐
- **失败** → 写 `CrawlerResult` → **写站内通知**（error 级别）⭐
- **面试 24h 内** → scheduler 扫描 → **写站内通知**（warning 级别）⭐

---

## 近期重构与新增功能

详细协作记录见 [linkup.md](file://./linkup.md)（仅内部协作留存，不随仓库上传）。

### 多 Agent 协作成果（5 轮迭代 + 1 轮部署验证）

| Agent | 职责 | 关键产出 |
|-------|------|----------|
| 前端优化者 | 迭代前端代码 | 22 项整改 + 2 个 T1 新功能 + 4 个 Bug 修复 |
| 后端优化者 | 迭代后端代码 | 14 项整改 + B-1 radar.py 拆分（614→173 行）+ ICS 导出 |
| 批判者 | 找茬 / 验收 | 22 项整改 100% 验收通过 |
| 协调者 | 协调三方 | 进度跟踪、虚假完成检测、流程纠正 |
| 需求分析者 | 挖掘需求 | 7 个 Bug + 14 个功能需求（T1/T2/T3 分级） |
| **部署工程师** ⭐ | **容器化验证** | **Dockerfile 修复 + WSL2 部署链路** |

### 第 1-5 轮：22 项代码整改

**前端 8 项**：F-1 错误提示优化、F-2 PageHeader 公共组件、F-3 useTheme 拆分、F-4 RadarPage Tab 拆分、F-5 `wasDragged` ref 化、F-6 `main.ts` 拆分、F-7 fetchUpcoming 改用后端 Query、F-8 401 拦截模块守卫

**后端 13 项**：B-1 radar.py 拆分 5 子模块、B-2 settings 集中管理、B-3 LLM settings 预取、B-4 `_fetch_page` 拆子函数、B-5 inspect API、B-6 DeclarativeBase、B-7 models 注释、B-8 reviews.py import 集中、B-9 logger 守卫、B-10 bcrypt 72 字节、B-11 全局异常处理、B-12 5 处 `except: pass` 修复、B-13 投递分页

### 第 6 轮：T1 需求 + Bug 修复

- **T1-2 站内通知中心**（4 后端端点 + 1 前端组件 + 3 触发源）
- **T1-3 ICS 日历导出**（RFC 5545 完整实现 + Blob 下载）
- **N-BUG-5** 日历 24h 面试提醒
- **N-BUG-6** 简历支持 .docx
- **N-BUG-7** HomePage 错误分级提示

### 第 7 轮：Docker 化与 WSL2 部署

- 删除 3 个无依赖的 vitest 测试文件（避免 vue-tsc 阻塞）
- 修复 `CalendarPage.vue` 4 处 TypeScript 错误（vue-tsc 抓到）
- Dockerfile 多阶段构建验证（前端构建 + 后端运行，单端口 8000）
- WSL2 + Windows Docker 部署脚本（4 个 shell 脚本 + 1 个 PowerShell 脚本）

---

## 辅助脚本

| 脚本 | 用途 |
|------|------|
| `scripts/deploy.sh` | 通用 Docker 部署 |
| `scripts/kill_old_backend.sh` | 清理旧容器 |
| `scripts/wsl_docker_check.sh` | WSL 中检查 Docker 可用性 |
| `scripts/wsl_docker_build.sh` | WSL 中构建 `falltracker:latest` |
| `scripts/wsl_docker_run.sh` | WSL 中启动容器（内部存储） |
| `scripts/wsl_docker_inspect.sh` | WSL 中查看容器 / dist / OpenAPI |
| `scripts/fix_calendar_wsl.sh` | 修复 WSL 文件缓存导致的内容滞后 |
| `scripts/test_health.ps1` | 主机端 HTTP 200/401 路径验证 |

---

## License

MIT
