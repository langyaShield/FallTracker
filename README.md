# FallTracker

秋招投递追踪与管理平台 —— 帮助你高效管理求职投递、面试日程、简历和职位雷达的一站式工具。

## 功能概览

- **投递管理** — 记录每一条投递（公司、岗位、状态、标签、截止日期），关联简历和面试事件
- **面试日历** — 以日历视图集中查看所有面试安排，支持轮次、地点、会议链接等详情
- **面试复盘** — 记录面试笔记，LLM 辅助生成结构化 Q&A 和反思总结
- **简历管理** — 上传 PDF / 图片简历，自动 OCR 提取文本并支持全文搜索
- **职位雷达** — 配置爬虫定时抓取招聘网站，LLM 智能分析匹配结果，邮件通知
- **数据统计** — 投递状态分布、时间线等多维度统计分析
- **用户设置** — 自定义 LLM API（DeepSeek 等）和邮件 SMTP 配置

## 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| Python 3.12 | 运行时 |
| FastAPI | Web 框架 |
| SQLAlchemy 2.x | ORM |
| SQLite | 数据库 |
| PyMuPDF + Tesseract OCR | 简历文本提取 |
| python-jose + passlib | JWT 认证 & 密码加密 |
| httpx + BeautifulSoup4 | 爬虫 HTTP 请求 & HTML 解析 |
| Pydantic Settings | 环境变量管理 |

### 前端

| 技术 | 用途 |
|------|------|
| Vue 3 | UI 框架 |
| TypeScript | 类型安全 |
| Vite 5 | 构建工具 |
| Element Plus | UI 组件库 |
| Tailwind CSS | 原子化样式 |
| Pinia | 状态管理 |
| Vue Router | 路由 |
| Axios | HTTP 客户端 |
| Lucide Icons | 图标库 |

### 部署

| 技术 | 用途 |
|------|------|
| Docker (多阶段构建) | 容器化 |
| Docker Compose | 服务编排 |
| Uvicorn | ASGI 服务器 |

## 项目结构

```
FallTracker/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口、路由注册、SPA 静态服务
│   │   ├── config.py            # 环境变量配置
│   │   ├── database.py          # 数据库引擎 & 会话
│   │   ├── models.py            # SQLAlchemy 数据模型
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── auth.py              # JWT 令牌 & 密码工具
│   │   ├── ocr.py               # OCR 文本提取（PDF / 图片）
│   │   └── routers/
│   │       ├── auth.py          # 注册 / 登录 / 当前用户
│   │       ├── deliveries.py    # 投递记录 CRUD
│   │       ├── events.py        # 面试事件 CRUD
│   │       ├── resumes.py       # 简历上传 / OCR / 搜索
│   │       ├── reviews.py       # 面试复盘 CRUD
│   │       ├── radar.py         # 爬虫配置 / 执行 / 结果
│   │       ├── statistics.py    # 统计数据
│   │       └── settings.py      # 用户设置
│   ├── spiders/                  # 爬虫配置模板（BOSS直聘、51job、拉勾、猎聘）
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                   # 本地开发启动脚本
├── frontend/
│   ├── src/
│   │   ├── pages/               # 页面组件
│   │   ├── layouts/             # 布局组件
│   │   ├── components/          # 通用组件
│   │   ├── composables/         # 组合式函数（主题切换等）
│   │   ├── stores/              # Pinia 状态管理
│   │   ├── router/              # 路由配置
│   │   └── lib/                 # 工具函数
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── scripts/
│   ├── deploy.sh                # Docker 部署脚本
│   └── kill_old_backend.sh      # 清理旧容器
├── Dockerfile                   # 多阶段构建（前端构建 + 后端运行）
├── docker-compose.yml           # 容器编排（适配 2GB 内存服务器）
└── .gitignore
```

## 数据模型

| 模型 | 说明 |
|------|------|
| `User` | 用户账户 |
| `Delivery` | 投递记录（公司、岗位、状态、标签、截止日期） |
| `InterviewEvent` | 面试事件（轮次、时间、时长、地点、会议链接） |
| `Resume` | 简历（文件路径、OCR 文本、OCR 状态与进度） |
| `Review` | 面试复盘（原始笔记、结构化 Q&A、标签、反思） |
| `RadarJob` | 雷达抓取的职位（来源、公司、岗位、链接、MD5 去重） |
| `RadarFilter` | 用户雷达过滤标签 |
| `CrawlerConfig` | 爬虫配置（URL、CSS 选择器、间隔、目标描述、邮件通知） |
| `CrawlerResult` | 爬虫执行结果（原始文本、LLM 分析、是否命中、邮件状态） |
| `UserSettings` | 用户设置（LLM API、SMTP 邮件配置） |

## API 路由

所有接口前缀为 `/api`，需要 JWT 认证（注册/登录除外）。

| 路由模块 | 端点前缀 | 功能 |
|----------|----------|------|
| auth | `/api/auth` | 注册、登录、获取当前用户 |
| deliveries | `/api/deliveries` | 投递记录增删改查 |
| events | `/api/events` | 面试事件增删改查 |
| resumes | `/api/resumes` | 简历上传、OCR 处理、搜索、预览 |
| reviews | `/api/reviews` | 面试复盘增删改查 |
| radar | `/api/radar` | 爬虫配置管理、手动执行、结果查询 |
| statistics | `/api/statistics` | 统计数据查询 |
| settings | `/api/settings` | 用户 LLM / 邮件设置 |

健康检查：`GET /health`

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | LoginPage | 用户登录 |
| `/register` | RegisterPage | 用户注册 |
| `/dashboard` | DashboardPage | 仪表盘（默认首页） |
| `/delivery/:id` | DeliveryDetailPage | 投递详情 |
| `/calendar` | CalendarPage | 面试日历 |
| `/radar` | RadarPage | 职位雷达 |
| `/resumes` | ResumesPage | 简历管理 |
| `/reviews` | ReviewsPage | 面试复盘 |
| `/statistics` | StatisticsPage | 数据统计 |
| `/settings` | SettingsPage | 用户设置 |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 22+ & pnpm
- Tesseract OCR（用于简历 OCR 功能）

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

### Docker 部署

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

## 爬虫配置模板

`backend/spiders/` 目录下提供了主流招聘网站的爬虫配置模板：

- `boss-zhipin.json` — BOSS 直聘
- `51job.json` — 前程无忧
- `lagou.json` — 拉勾网
- `liepin.json` — 猎聘网
- `sample-template.json` — 通用模板
- `regex-example.json` — 正则提取示例

## License

MIT
