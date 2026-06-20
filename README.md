# FallTracker

秋招投递追踪与管理平台 — 帮助你高效管理求职投递、面试日程、简历和职位雷达的一站式工具。

![status](https://img.shields.io/badge/status-running-brightgreen) ![docker](https://img.shields.io/badge/docker-ready-blue) ![stack](https://img.shields.io/badge/Vue3%20%2B%20FastAPI-success)

---

## 功能概览

### 核心功能

- **投递管理** — 记录每一条投递（公司、岗位、状态、标签、截止日期），关联简历和面试事件
- **面试日历** — 日历视图集中查看所有面试与截止日期，支持 ICS 导出订阅
- **面试复盘** — 记录面试笔记，LLM 辅助生成结构化 Q&A 和反思总结
- **简历管理** — 上传 PDF / Word (.docx) / 图片简历，自动 OCR 提取文本并支持全文搜索；支持批量删除、重新 OCR、文件替换、下载
- **职位雷达** — 配置爬虫定时抓取招聘网站，LLM 智能分析匹配结果，邮件 + 站内通知；支持招聘网站模板一键创建、向导式配置、常见邮箱预设
- **数据统计** — 核心KPI（总投递/回复率/面试率/Offer率/待跟进）、投递趋势折线图、转化漏斗图、面试类型与轮次统计、公司进展排名与停留天数预警
- **用户设置** — 自定义 LLM API（DeepSeek 等）、邮件 SMTP 配置、腾讯云 COS 云端备份配置

### 秋招增强功能

- **CSV 批量导入** — 上传 CSV 文件一次导入数十条投递，支持中英文表头自动映射，预览确认后导入
- **CSV 数据导出** — 一键导出投递数据为 CSV 文件，方便分享给导师或存档
- **看板搜索 + 多维筛选** — 关键词搜索、状态筛选、标签过滤、排序，100+ 投递时快速定位
- **批量操作** — 多选卡片批量更新状态、添加/移除标签、批量删除
- **截止日期智能预警** — 首页紧急 deadline 看板（三级紧急度着色 + 倒计时），看板卡片紧急度标识
- **面试/截止双重提醒** — 面试 24h 提醒 + 截止 48h 提醒，站内通知 + 日历告警

### 数据备份

- **本地导出/导入** — 一键导出全量数据（投递、面试、简历、爬虫、通知等 8 张表）为 JSON 文件，支持覆盖导入
- **腾讯云 COS 云端备份** — 配置 COS 参数后可一键上传备份到云端，从云端列出备份文件并选择恢复
- **COS 自动备份** — 可配置自动备份间隔（1h/2h/4h/6h/12h/24h/48h/7d），系统按设定间隔自动上传备份到 COS，文件名区分自动备份与手动备份
- **ID 重映射** — 导入时自动处理所有外键关联（resume_id、delivery_id、config_id），保证关系链不断

### 管理员功能

- **用户管理** — 管理员查看所有注册用户基础信息（用户名、注册时间、投递数、简历数），不含密码和隐私数据
- **用户禁用/启用** — 对选定账户进行禁用或取消禁用，禁用后用户无法访问系统
- **邀请码注册控制** — 管理员生成一次性邀请码，新用户注册必须填写有效邀请码，控制平台注册人数
- **过期邀请码自动清理** — 系统每小时自动删除已过期的邀请码，管理员也可在后台手动触发清理

### 通知与提醒

- **站内通知中心** — 雷达命中、爬虫失败、面试提醒、截止提醒统一收件，未读数实时显示
- **ICS 日历导出** — 一键导出 RFC 5545 标准 .ics 文件，导入 Google Calendar / Outlook
- **邮件通知** — 爬虫命中目标时自动发送邮件到指定邮箱
- **修改密码** — 用户可在侧边栏点击用户名进入修改密码页面，支持旧密码验证

### 安全特性

- **敏感信息加密** — LLM API Key、SMTP 密码、COS SecretId/SecretKey 使用 Fernet (AES-128-CBC) 加密存储
- **邀请码注册** — 注册必须填写有效邀请码，防止无限注册
- **用户禁用** — 管理员可禁用恶意用户，禁用后 API 返回 403
- **API 速率限制** — 登录 10 次/分钟、注册 5 次/分钟，防止暴力破解
- **CORS 安全** — 通配符 origin 时自动禁用 credentials
- **强制密钥检查** — 使用默认 SECRET_KEY 时直接阻止应用启动
- **LLM Prompt 注入防护** — 用户输入截断 + 特殊字符转义，防止 prompt injection
- **SSRF 防护** — 爬虫禁止访问内网地址和私有 IP 段
- **SQL 注入防护** — sort_by 白名单、LIKE 通配符转义、column_type 正则校验
- **邀请码行级锁** — 防止并发注册重复使用同一邀请码

---

## 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| Python 3.12 | 运行时 |
| FastAPI | Web 框架 |
| SQLAlchemy 2.x | ORM |
| SQLite | 数据库 |
| APScheduler | 后台任务调度 |
| slowapi | API 速率限制 |
| cryptography (Fernet) | 敏感字段加密 |
| PyMuPDF + Tesseract OCR + python-docx | 简历文本提取 |
| python-jose + passlib (bcrypt 4.x) | JWT 认证 & 密码加密 |
| httpx + BeautifulSoup4 | 爬虫 HTTP 请求 & HTML 解析 |
| cos-python-sdk-v5 | 腾讯云 COS 对象存储 |
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
| ECharts + vue-echarts | 数据可视化图表 |

### 部署

| 技术 | 用途 |
|------|------|
| Docker (多阶段构建) | 容器化 |
| Docker Compose | 服务编排 |
| Uvicorn (2 workers) | ASGI 服务器 |
| GitHub Actions | CI/CD 自动化 |

---

## 项目结构

```
FallTracker/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI（pytest + vue-tsc + build）
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 应用入口、路由注册、异常处理、SPA 静态服务
│   │   ├── config.py              # 环境变量配置
│   │   ├── database.py            # 数据库引擎 & 会话
│   │   ├── models.py              # SQLAlchemy 数据模型（11 张表）
│   │   ├── schemas.py             # Pydantic 请求/响应模型
│   │   ├── auth.py                # JWT 令牌 & 密码工具 & 管理员鉴权 & 禁用检查
│   │   ├── crypto.py              # Fernet 加密工具（敏感字段加解密）
│   │   ├── ratelimit.py           # slowapi 速率限制实例
│   │   ├── ocr.py                 # OCR 文本提取（PDF / 图片 / .docx）
│   │   ├── routers/
│   │   │   ├── auth.py            # 注册（邀请码校验）/ 登录 / 当前用户
│   │   │   ├── deliveries.py      # 投递 CRUD + 筛选搜索 + 批量操作 + CSV 导入导出
│   │   │   ├── events.py          # 面试事件 CRUD + ICS 导出
│   │   │   ├── resumes.py         # 简历上传 / OCR / 搜索 / 预览 / 批量删除 / 重新OCR / 下载
│   │   │   ├── reviews.py         # 面试复盘 CRUD
│   │   │   ├── radar.py           # 爬虫配置 / 执行 / 结果 / 模板列表
│   │   │   ├── statistics.py      # 统计数据（总览 / 漏斗 / 转化率 / 趋势 / 公司进展 / 面试统计）
│   │   │   ├── settings.py        # 用户设置（LLM / SMTP / COS，含加密）
│   │   │   ├── backup.py          # 数据备份（本地导出导入 + COS 云端上传恢复 + 自动备份调度）
│   │   │   ├── admin.py           # 管理员接口（用户管理 + 邀请码管理）
│   │   │   └── notifications.py   # 站内通知 CRUD + 批量删除
│   │   └── services/
│   │       ├── notification_service.py  # 通知业务逻辑（独立 service 层）
│   │       └── radar/
│   │           ├── fetcher.py     # HTTP 抓取 / 重试 / HTML 解析 / SSRF 防护
│   │           ├── llm.py         # LLM 分析（含加密字段解密）
│   │           ├── email.py       # SMTP 通知（含加密字段解密，支持 SSL 端口 465）
│   │           ├── engine.py      # 单次执行编排 + 触发站内通知
│   │           └── scheduler.py   # APScheduler 调度 + 面试提醒 + 截止预警
│   ├── spiders/                   # 爬虫配置模板（BOSS直聘、51job、拉勾、猎聘）
│   ├── tests/                     # pytest 测试套件
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                     # 本地开发启动脚本
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── DashboardPage.vue  # 看板（搜索筛选 + 批量操作 + 导入导出 + deadline 标识）
│   │   │   ├── HomePage.vue       # 首页（KPI + 紧急 deadline 预警 + 即将到来的面试）
│   │   │   ├── DeliveryDetailPage.vue  # 投递详情 + 事件时间线
│   │   │   ├── CalendarPage.vue   # 面试日历 + ICS 导出
│   │   │   ├── RadarPage.vue      # 职位雷达（模板快速创建 + 向导式配置 + 运行记录 + 邮箱预设）
│   │   │   ├── ResumesPage.vue    # 简历管理 + OCR + 全文搜索 + 批量操作 + 文件替换
│   │   │   ├── ReviewsPage.vue    # 面试复盘 + LLM 生成
│   │   │   ├── StatisticsPage.vue # 数据统计（KPI + 趋势折线图 + 漏斗图 + 面试统计 + 公司进展）
│   │   │   ├── AdminPage.vue      # 管理员界面（用户管理 + 邀请码管理 + 过期清理）
│   │   │   ├── SettingsPage.vue   # 用户设置（LLM / 邮箱 / 数据备份 / COS 云端备份）
│   │   │   └── ChangePasswordPage.vue  # 修改密码
│   │   ├── components/
│   │   │   ├── PageHeader.vue     # 公共页头组件
│   │   │   ├── NotificationCenter.vue  # 站内通知中心（铃铛 + 未读角标）
│   │   │   ├── BatchImportDialog.vue   # CSV 批量导入对话框
│   │   │   ├── EChartsWrap.vue         # ECharts 轻量封装组件（按需引入 + 自动 resize）
│   │   │   └── radar/
│   │   │       └── RadarEmailSettings.vue  # 邮箱配置（常见邮箱预设 + 授权码引导）
│   │   ├── composables/           # 组合式函数（useTheme 等）
│   │   ├── stores/auth.ts         # Pinia 认证状态（含 401 全局拦截 + is_admin）
│   │   └── lib/                   # 工具函数（api / error / format / constants）
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── scripts/
│   ├── deploy.sh                  # Docker 部署脚本
│   └── ...                        # WSL2 部署脚本
├── Dockerfile                     # 多阶段构建（前端构建 + 后端运行）
├── docker-compose.yml             # 容器编排（1GB 内存限制）
└── .gitignore
```

---

## 数据模型

| 模型 | 说明 |
|------|------|
| `User` | 用户账户（bcrypt 密码哈希、管理员标识、禁用状态） |
| `InviteCode` | 邀请码（一次性使用、过期时间、使用者记录） |
| `Delivery` | 投递记录（公司、岗位、状态、标签、截止日期、JD 描述） |
| `InterviewEvent` | 面试事件（轮次、时间、时长、地点、会议链接、面试官） |
| `Resume` | 简历（文件路径、文件大小、文件类型、OCR 文本、OCR 状态与进度） |
| `Review` | 面试复盘（原始笔记、结构化 Q&A、标签、反思） |
| `Notification` | 站内通知（类型、标题、正文、是否已读） |
| `CrawlerConfig` | 爬虫配置（URL、CSS 选择器、间隔、目标描述、邮件通知） |
| `CrawlerResult` | 爬虫执行结果（原始文本、LLM 分析、是否命中、邮件状态） |
| `UserSettings` | 用户设置（LLM API、SMTP 邮件、COS 云端备份，敏感字段加密存储） |

投递状态流转：`待投递 → 已投递 → 笔试中 → 面试中 → 已Offer / 已终止`

---

## API 路由

所有接口前缀为 `/api`，需要 JWT 认证（注册/登录除外）。

| 模块 | 前缀 | 主要端点 |
|------|------|----------|
| auth | `/api/auth` | 注册（邀请码校验）、登录、获取当前用户、修改密码 |
| deliveries | `/api/deliveries` | CRUD + 搜索筛选 + 批量状态/标签/删除 + CSV 导入/导出 + 截止查询 |
| events | `/api/events` | 面试事件 CRUD + `GET /export.ics` 日历导出 |
| resumes | `/api/resumes` | 上传、OCR、搜索、预览、重命名、文件替换、批量删除、重新OCR、下载 |
| reviews | `/api/reviews` | CRUD + LLM 生成结构化 Q&A |
| radar | `/api/radar` | 爬虫配置管理、手动执行、结果查询、模板列表 |
| statistics | `/api/statistics` | 总览KPI、漏斗、转化率、趋势、公司进展、面试统计 |
| settings | `/api/settings` | LLM 配置 + SMTP 邮件配置 + COS 云端备份配置（加密存储） |
| backup | `/api/backup` | 本地导出/导入 + COS 云端上传/恢复/列表 |
| admin | `/api/admin` | 用户列表/禁用/启用 + 邀请码生成/列表（仅管理员） |
| notifications | `/api/notifications` | 列表、未读数、标记已读、删除、批量清空 |

### deliveries 端点详情

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/deliveries` | 列表（支持 search/status/tag/sort 筛选参数） |
| `POST` | `/deliveries` | 创建投递 |
| `GET` | `/deliveries/upcoming-deadlines` | 未来 N 天截止的投递 |
| `POST` | `/deliveries/import/preview` | CSV 预览（上传文件） |
| `POST` | `/deliveries/import` | CSV 正式导入 |
| `GET` | `/deliveries/export` | 导出 CSV（支持按状态筛选） |
| `PUT` | `/deliveries/batch/status` | 批量更新状态 |
| `PUT` | `/deliveries/batch/tags` | 批量添加/移除标签 |
| `DELETE` | `/deliveries/batch` | 批量删除 |
| `GET/PUT/DELETE` | `/deliveries/{id}` | 单条 CRUD |

### backup 端点详情

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/backup/export` | 导出全量数据为 JSON 文件下载 |
| `POST` | `/backup/import` | 上传 JSON 文件恢复数据（覆盖模式：先清空再导入） |
| `POST` | `/backup/upload-to-cos` | 导出并上传到腾讯云 COS（手动备份，文件名含 `_manual_`） |
| `GET` | `/backup/cos-list` | 列出 COS 上的备份文件（含自动/手动类型标识） |
| `POST` | `/backup/restore-from-cos` | 从 COS 下载备份并恢复数据（覆盖模式） |
| `POST` | `/backup/cos-delete` | 删除 COS 上的指定备份文件 |
| `POST` | `/backup/cos-rename` | 重命名 COS 上的备份文件 |

### admin 端点详情

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/admin/users` | 获取所有用户列表（含投递数/简历数统计） |
| `POST` | `/admin/users/{id}/disable` | 禁用用户 |
| `POST` | `/admin/users/{id}/enable` | 取消禁用用户 |
| `POST` | `/admin/invite-codes` | 批量生成邀请码 |
| `GET` | `/admin/invite-codes` | 获取所有邀请码列表 |
| `DELETE` | `/admin/invite-codes/expired` | 清理所有已过期的邀请码 |

健康检查：`GET /health`
OpenAPI 文档：`GET /docs`（Swagger UI）

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 22+ & npm/pnpm
- Tesseract OCR（用于简历 OCR 功能）
- Docker（推荐）或本地 Python + Node 环境

### 本地开发

**1. 后端**

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入配置（SECRET_KEY 必须修改）
pip install -r requirements.txt
python run.py
```

后端运行在 `http://127.0.0.1:8000`。

**2. 前端**

```bash
cd frontend
npm install
npm run dev
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

### WSL2 + Windows Docker 部署

适用于 Windows 11 + WSL2 + Docker Desktop 的开发环境：

```powershell
# 1. 构建镜像
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_build.sh

# 2. 启动容器
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_run.sh

# 3. 查看状态
wsl -d Ubuntu-22.04 -e bash scripts/wsl_docker_inspect.sh
```

访问 http://localhost:8000/

### 设置管理员

首个管理员需手动在数据库设置：

```sql
UPDATE users SET is_admin = 1 WHERE username = '你的管理员用户名';
```

---

## 环境变量

### 后端（`backend/.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///./falltracker.db` | 数据库连接 |
| `SECRET_KEY` | `change-me-to-a-random-secret-key` | JWT 签名密钥（**必须修改，否则阻止启动**） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token 过期时间（分钟，默认 7 天） |
| `CORS_ORIGINS` | `*` | 允许的 CORS 源 |
| `LLM_API_KEY` | 空 | LLM API 密钥 |
| `LLM_API_BASE` | `https://api.deepseek.com/v1` | LLM API 地址 |
| `LLM_MODEL` | `deepseek-chat` | LLM 模型名称 |

---

## 爬虫配置模板

`backend/spiders/` 目录下提供主流招聘网站的爬虫配置模板：

- `boss-zhipin.json` — BOSS 直聘
- `51job.json` — 前程无忧
- `lagou.json` — 拉勾网
- `liepin.json` — 猎聘网
- `sample-template.json` — 通用模板

雷达触发链路：
- **命中** → 写结果 → 发邮件 → 站内通知
- **失败** → 写结果 → 站内通知
- **面试 24h 内** → 定时扫描 → 站内通知
- **截止 48h 内** → 定时扫描 → 站内通知

---

## 测试

```bash
# 后端测试
cd backend
pip install pytest
pytest tests/ -v

# 前端构建检查
cd frontend
npm run build
```

CI 由 GitHub Actions 自动运行：后端 pytest + 前端 TypeScript 检查 + 构建验证。

---

## License

MIT
