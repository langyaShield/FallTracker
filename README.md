# FallTracker - 秋招智能追踪系统

一个全栈 Web 应用，帮助求职者管理投递进度、追踪面试事件、分析求职数据。

## 技术栈

- **前端**: Vue 3 + TypeScript + Element Plus + Vite
- **后端**: Python FastAPI + SQLAlchemy + SQLite
- **部署**: Docker + Docker Compose

## 快速开始

```bash
# 构建并启动
docker compose up -d --build

# 访问
http://localhost
```

## 主要功能

- 投递管理（看板视图、拖拽排序、批量操作）
- 日历视图（面试事件、截止日期提醒）
- 简历管理（上传、OCR 识别、预览下载）
- 数据统计（漏斗分析、转化率、时间线）
- 爬虫雷达（定时抓取、AI 分析、邮件通知）
- 面试复盘（粗表记录）
- 个人信息库
- 数据备份（本地导出/导入、腾讯云 COS）
- 书签管理

## 配置

复制 `.env.example` 为 `.env`，按需修改：

```bash
cp backend/.env.example backend/.env
```

主要配置项：`SECRET_KEY`、`LLM_API_KEY`、SMTP 邮箱、COS 对象存储。

## 项目结构

```
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── routers/  # API 路由
│   │   ├── models.py # 数据模型
│   │   └── services/ # 业务逻辑（雷达爬虫等）
│   └── .env.example  # 配置模板
├── frontend/         # Vue 3 前端
│   └── src/
│       ├── pages/    # 页面组件
│       └── composables/ # 组合式函数
├── Dockerfile
└── docker-compose.yml
```
