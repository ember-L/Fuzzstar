# 团队接入说明（RongXing / FuzzStar2.0）

数据库和后端跑在一台主机上，其他成员从局域网连接。

## 服务器信息（主机机主维护）

| 项目 | 值 |
| --- | --- |
| 主机局域网 IP | `10.216.251.47`（Wi-Fi 变动后以机主最新通知为准） |
| MySQL | `10.216.251.47:3307`，库名 `rongxing`，用户 `rongxing`（注意端口是 **3307**，不是默认 3306） |
| 后端 API | `http://10.216.251.47:8000/api/v1` |
| 管理后台 | `http://10.216.251.47:8000/admin` |

> MySQL 密码请勿写进任何提交的文件，由机主私发。

## 成员端启动步骤（backend/ 目录）

```bash
# 1. 创建虚拟环境并装依赖（Python 3.11+）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 创建本地 .env（不要提交到 git）
cp .env.example .env   # 或 Windows: copy .env.example .env
```

`.env` 需要修改的项：

```ini
DATABASE_URL=mysql+pymysql://rongxing:<密码>@10.216.251.47:3307/rongxing?charset=utf8mb4
JWT_SECRET=<任意≥32字节随机串，各成员可不同>
ADMIN_EMAILS=admin@rongxing.app
```

```bash
# 3. 启动后端（成员本机调试用 127.0.0.1 即可）
.venv\Scripts\python.exe -m uvicorn app.main:create_dev_app --factory --host 127.0.0.1 --port 8000
```

数据库表结构由主机机主负责迁移；成员一般**不需要**跑 alembic。

## 主机机主操作

```bash
# 启动后端（监听所有网卡，供局域网访问）
.venv\Scripts\python.exe -m uvicorn app.main:create_dev_app --factory --host 0.0.0.0 --port 8000

# 创建/重置管理员账户（无需邮箱验证）
.venv\Scripts\python.exe -m scripts.create_admin --email admin@rongxing.app --password <密码>

# 本地演示模式（独立 SQLite 演示库 + 演示数据）
.venv\Scripts\python.exe -m scripts.run_admin_demo --host 0.0.0.0 --port 8000
```

## 管理员登录说明

- 管理后台账号 = `ADMIN_EMAILS` 里登记的邮箱 + 对应密码
- **管理员登录不需要邮箱验证**：登录接口对 `ADMIN_EMAILS` 白名单内的邮箱跳过验证检查；`scripts/create_admin.py` 也会直接把邮箱标记为已验证
- 验证方式：机主在数据库所在机器运行上面的 `create_admin` 命令即可
- 安全提示：ADMIN_EMAILS 白名单就是权限边界，请勿把陌生人的邮箱加进去

## 常见问题

- **连不上数据库**：确认主机和你在同一局域网（或主机 IP 未变化），主机防火墙 3307/8000 入站规则已放行
- **后端启动报 JWT_SECRET 错误**：`.env` 里的 JWT_SECRET 至少 32 字节
- **登录提示"请先验证邮箱"**：普通用户账号仍需邮箱验证；管理员账号若出现此提示，说明该邮箱不在 ADMIN_EMAILS 里
- **主机 Wi-Fi 切换后**：IP 可能变化，机主需重新通知大家更新 DATABASE_URL 和 API 地址
