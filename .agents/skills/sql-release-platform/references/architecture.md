# 系统架构

## 目录

- 运行结构
- 源码职责
- 配置与状态
- 请求流程
- 接口清单
- 兼容性约束

## 运行结构

系统由一个 FastAPI 进程运行，使用 Jinja2 输出服务端页面，页面交互由原生 JavaScript 完成。后端通过 Paramiko 的 SSH/SFTP 连接 Linux 服务器。该工具定位为个人运维工具，当前不引入数据库、任务队列、前端打包工具和登录鉴权。

可以把 `main.py` 类比成 Java Web 中合并后的 Controller 与 Service；把 `config.py` 类比成配置 VO 和配置服务；把 `storage_utils.py` 类比成 Repository 的安全持久化基础设施；把 `logging_setup.py` 类比成日志基础设施。

## 源码职责

| 路径 | 职责 |
| --- | --- |
| `main.py` | FastAPI 应用、接口、SSH/SFTP、脚本生成、远程日志、本地及远程 MD5 |
| `config.py` | `ConnectionProfile`、应用配置、JSON 环境配置持久化、旧 `.env` 迁移 |
| `logging_setup.py` | 系统滚动日志、操作审计日志、日志尾部读取 |
| `storage_utils.py` | JSON 配置校验、权限收紧、临时文件与原子替换 |
| `templates/index.html` | SQL 发布执行台、弹窗、上传、环境、脚本和日志页面逻辑 |
| `templates/md5.html` | MD5 功能入口页 |
| `templates/md5_local.html` | 本地路径保存、浏览器目录授权、本地 MD5 计算和展示 |
| `templates/md5_remote.html` | 独立远程连接、多路径、后缀过滤和远程 MD5 展示 |
| `profiles.json` | 运行时 SSH 环境配置，包含明文密码，禁止提交 |
| `md5_settings.json` | 本地/远程 MD5 路径和远程连接配置，禁止提交 |
| `runtime_logs/app.log` | 技术运行日志 |
| `runtime_logs/operations.log` | 中文操作审计日志 |
| `requirements.txt` | 兼容 Python 3.8 的固定依赖版本 |
| `start.sh` | 创建虚拟环境、安装依赖并监听 `0.0.0.0:8000` |
| `start_uvicorn.sh` | 使用已有 Uvicorn 启动，支持环境变量覆盖 |
| `tests/` | 不连接 SSH 的配置、脚本、MD5 和页面结构回归测试 |

## 配置与状态

发布执行台环境保存在 `profiles.json`：

```text
active -> 当前环境名称
profiles[] -> name、ssh_host、ssh_port、ssh_user、ssh_password、
              remote_dir、script_name、default_local_dir、
              db_host、db_port、db_user、db_password、custom_sql_options[]
custom_sql_options[] -> id、sql_file、pg_host、pg_port、database、
                        db_user、db_password、log_file
```

MD5 配置独立保存在 `md5_settings.json`：

```text
remote -> connection、paths、suffixes、paths_by_profile（兼容旧数据）
local  -> paths、suffixes
```

`.env` 只用于旧配置迁移、默认初始化和应用级日志设置。SSH 连接配置优先在页面中维护。

## 请求流程

发布操作遵循以下流程：

```text
浏览器操作
  -> FastAPI 接口
  -> 当前 ConnectionProfile
  -> SSH/SFTP 连接
  -> 远程文件或 Shell 命令
  -> 中文系统日志和操作日志
  -> JSON 返回结果
  -> 页面状态区域和弹窗
```

“生成脚本”和“执行脚本”是两个独立操作。生成操作把配置名称对应的脚本写入远程目录并设置权限；执行操作始终使用当前环境的 `remote_dir` 和 `script_name`。

## 接口清单

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/` | SQL 发布执行台 |
| GET | `/md5` | MD5 入口页 |
| GET | `/md5/local` | 本地 MD5 页面 |
| GET | `/md5/remote` | 远程 MD5 页面 |
| GET/POST | `/md5-local-settings` | 读取/保存本地 MD5 配置 |
| GET | `/md5-defaults` | 读取远程 MD5 默认配置 |
| POST | `/md5-remote-settings` | 保存远程 MD5 配置 |
| POST | `/md5-local-scan` | 扫描手工本地路径和浏览器授权文件 |
| POST | `/md5-scan` | 通过 SSH 执行远程 MD5 扫描 |
| GET/POST | `/config-profiles` | 查询/保存发布环境 |
| POST | `/config-profiles/active` | 切换当前环境 |
| DELETE | `/config-profiles/{name}` | 删除环境，至少保留一个 |
| POST | `/connection-test` | 测试当前环境 SSH 连接 |
| POST | `/custom-sql-options` | 给当前环境新增自定义常规 SQL |
| DELETE | `/custom-sql-options/{option_id}` | 删除当前环境的自定义常规 SQL |
| GET | `/remote-summary` | 统计并展示远程根目录内容 |
| GET | `/system-logs` | 读取 `app.log` 或 `operations.log` 尾部 |
| POST | `/upload` | 递归上传所选目录中的内容 |
| POST | `/clear-dir` | 清理远程目录但保留 `log` |
| POST | `/generate` | 生成当前环境配置的 Shell 脚本 |
| POST | `/run` | 执行当前环境配置的 Shell 脚本 |
| GET | `/logs?scope=current|history` | 查询当前或历史远程日志 |
| GET | `/script-preview` | 查询脚本内容和最近修改时间 |

## 兼容性约束

- 目标版本是 Python 3.8.2。
- 使用 `typing.List`、`typing.Dict`、`typing.Optional`，不要使用高版本类型语法。
- 固定依赖版本必须继续支持 Python 3.8。
- 页面使用原生 HTML/CSS/JavaScript，未经用户确认不要引入 Node 构建流程。
- 所有文件保持 UTF-8，并保留中文远程日志的多编码兼容处理。
- 启动脚本先进入项目目录，避免从其他目录启动时找不到模板和配置。
