# 在线课程自动化平台

FastAPI + Vue3 全栈在线课程自动化 SaaS 平台，支持多平台视频学习、考试辅助、聚合支付。

## 默认管理员

首次启动自动创建：

| 用户名 | 密码 |
|--------|------|
| `2910855245` | `woainima123` |

登录入口：浏览器打开 `http://<服务器IP>:8000/#/admin`（登录需输一次图片验证码）。部署后建议在「安全中心」修改密码。

## Linux 部署（直接部署，无需宝塔/Docker）

```bash
# 1. 上传项目到服务器，例如 /opt/anti-course
cd /opt/anti-course

# 2. 安装依赖
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. 配置
cp .env.example .env
vi .env   # 至少改 SITE_URL 为你的域名/IP；生产环境建议改 JWT_SECRET_KEY

# 4. 构建前端（首次或前端改动后需要）
cd frontend && npm install && npm run build && cd ..

# 5. 启动
venv/bin/granian --interface asgi --host 0.0.0.0 --port 8000 run:app
# 或交互式运维菜单: python manage.py
```

### systemd 常驻（推荐）

```bash
sudo cp deploy/anti-course.service /etc/systemd/system/
sudo vi /etc/systemd/system/anti-course.service   # 按实际路径修改 WorkingDirectory/ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now anti-course
sudo systemctl status anti-course
```

### Nginx 反代（可选）

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 功能特性

### 多平台支持

| 平台 | 视频学习 | 考试辅助 |
|------|:--------:|:--------:|
| 在线课程测评考试平台 | 支持 | 支持 |
| 劳动课程测评考试平台 | 支持 | 支持 |
| 公益课程平台 | 支持 | 支持 |
| 学习通 | 支持 | 支持 |

### 支付通道

- 支付宝官方支付 / 当面付 / 个人版 / 商家账单
- 微信店员版 / 云端 / 经营码
- Android 收款监控 APP（实时监听通知）

## 项目结构

```
├── api/                    # 后端 API 层
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 全局配置
│   ├── database.py         # SQLAlchemy 模型 + 数据操作
│   ├── models.py           # Pydantic 请求/响应模型
│   ├── auth.py             # JWT 认证 + 黑名单
│   ├── routers/            # API 路由
│   └── services/           # 业务逻辑
├── infrastructure/         # 基础设施层
│   ├── http_session.py     # HTTP 请求封装
│   ├── course_crawler.py   # 课程数据爬取
│   ├── chaoxing_session.py # rnet 反检测会话
│   └── chaoxing/           # 学习通专用模块
├── services/               # 业务服务层
│   ├── scan_service.py     # 课程扫描
│   └── ai_service.py       # AI 答题
├── frontend/               # Vue3 前端
│   └── src/views/          # 页面组件
├── worker.py               # 课程爬取 Worker
├── study_worker.py         # 视频学习 Worker
├── chaoxing_worker.py      # 学习通 Worker
├── deploy/                 # systemd 单元
├── run.py                  # 启动入口
└── requirements.txt        # Python 依赖
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | 必填 |
| `DB_PATH` | SQLite 数据库文件 | `data/orders.db` |
| `REDIS_URL` | Redis 连接 | 自动降级内存模式 |
| `SITE_URL` | 站点地址（支付回调） | `http://localhost:8000` |
| `DEEPSEEK_API_KEY` | AI 考试答题 | 可选 |

## 技术栈

**后端**: Python 3.10+ · FastAPI · SQLAlchemy · Pydantic · loguru · rnet · httpx · scrapling · ddddocr

**前端**: Vue 3 · TypeScript · Vite · Pinia · Vue Router

**数据库**: SQLite（WAL + busy_timeout）

**部署**: Granian (Rust ASGI) · systemd · Nginx

## License

MIT
