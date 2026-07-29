# SQL 发布执行台

一个基于 FastAPI 的轻量级 Web 工具，用来把本地 SQL 目录上传到远程 Linux 服务器，按页面选择生成固定名称的执行脚本，并通过 SSH 远程执行脚本、查看执行日志。

项目主要面向个人或小团队内部使用，不包含登录鉴权，请不要直接暴露到公网。

## 功能特性

- 支持上传本地目录内所有文件到远程服务器目录，远程同名文件会被覆盖。
- 支持多环境配置，例如 `T2`、`Sit1`、`zsc`，页面可切换当前环境。
- 支持生成固定脚本名，默认 `224.sh`。
- 支持按 SQL 类型多选生成脚本，例如临时 SQL、data、pub、history、grant、install、mainnf、测试脚本等。
- 支持远程执行脚本，并在页面展示远程 `log` 目录中的日志文件。
- 支持日志历史备份，历史日志默认在远程 `log/history` 下。
- 支持查看远端目录内容、刷新远端目录、清除远端目录，但会保留 `log` 目录。
- 支持远程目录 MD5 文件清单统计。
- 支持本地目录 MD5 文件清单统计。
- 后台有中文系统日志和操作日志，方便运维排查。

## 技术栈

- Python 3.8+
- FastAPI
- Uvicorn
- Paramiko SSH/SFTP
- Jinja2 模板

## 目录结构

```text
.
├── main.py                     # FastAPI 入口，包含页面路由、上传、生成脚本、执行脚本、日志、MD5 接口
├── config.py                   # 多环境配置读写逻辑
├── logging_setup.py            # 系统日志和操作日志配置
├── storage_utils.py            # JSON 原子写入和配置文件安全读取
├── requirements.txt            # Python 依赖
├── requirements-dev.txt        # 可选的代码规范检查依赖
├── pyproject.toml              # Python 3.8 与 Ruff 代码规范
├── start.sh                    # Linux 一键启动脚本，自动创建虚拟环境并安装依赖
├── start_uvicorn.sh            # 使用指定 uvicorn 路径启动的脚本
├── templates/
│   ├── index.html              # SQL 发布执行台页面
│   ├── md5.html                # MD5 首页
│   ├── md5_local.html          # 本地目录 MD5 页面
│   └── md5_remote.html         # 远程服务器 MD5 页面
├── tests/                      # 不连接远程服务器的核心与页面契约测试
├── .env.example                # 环境变量示例，不要填写真实密码提交
├── profiles.example.json       # 多环境配置示例，不要填写真实密码提交
└── md5_settings.example.json   # MD5 配置示例
```

## 快速启动

### 1. 准备 Python 环境

项目已按 Python 3.8 兼容方式编写。建议使用 Python 3.8 或更高版本。

```bash
python3 --version
```

### 2. 安装并启动

```bash
cd /path/to/project
chmod +x start.sh
./start.sh
```

启动成功后访问：

```text
http://127.0.0.1:8000/
```

如果部署在 Linux 服务器并希望局域网访问，可以使用服务器 IP 加端口访问：

```text
http://服务器IP:8000/
```

## 手动启动方式

```bash
cd /path/to/project
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

开发调试时可使用自动重载：

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 配置说明

页面右侧“环境配置”可维护多个远程服务器配置。

主要字段：

- `配置名称`：自定义环境名，例如 `T2`、`Sit1`。
- `SSH_HOST`：远程服务器 IP 或域名。
- `SSH_PORT`：SSH 端口，默认 `22`。
- `SSH_USER`：SSH 用户名。
- `SSH_PASSWORD`：SSH 密码，页面支持显示明文。
- `REMOTE_DIR`：远程服务器上传和执行目录，例如 `/opt/upload`。
- `脚本名称`：默认 `224.sh`。
- `默认本地目录`：选择目录时的参考路径，也可以手动重新选择。
- `数据库 IP / 主机名`、`数据库端口`、`数据库用户`、`数据库密码`：仅供两个远程迁移 SQL 使用；原有 SQL 仍连接远程 Linux 本机数据库。

配置会保存到本地 `profiles.json`。该文件包含密码，已在 `.gitignore` 中排除，不应提交到 GitHub。
系统使用临时文件加原子替换保存运行配置，并把配置文件权限设置为仅当前系统用户可读写，降低并发保存或进程中断导致 JSON 损坏的风险。

如果首次启动没有 `profiles.json`，系统会尝试读取 `.env` 初始化一个 `default` 环境。可以参考 `.env.example`。

## SQL 发布流程

1. 在页面选择当前环境。
2. 点击“测试连接”，确认能连通远程服务器。
3. 在“上传目录”区域选择本地目录并上传。
4. 在“生成脚本”区域勾选需要执行的 SQL 类型。
5. 点击“生成 SQL 脚本”，系统会在远程目录生成 `224.sh`。
6. 展开脚本内容，确认无误。
7. 点击“执行脚本”，远程执行 `bash 224.sh`。
8. 在“日志内容”区域查看当前日志和历史备份日志。

远程迁移 SQL `db_pmigrel00ldb_88.sql` 和 `db_pmigrel00ldb_98.sql` 都连接数据库 `pmighis001db`，数据库连接取自当前环境配置，并分别写入独立日志。

“常规 SQL”支持为当前环境新增自定义项。填写根目录 SQL 文件名、远程 PG 地址和端口、目标数据库、PG 账户、PG 密码和独立日志文件名后即可长期保存、勾选生成或删除。每个环境最多配置 30 个，密码不会写入系统日志，脚本预览会显示为 `******`。

## 日志成功/失败判断

页面会读取每个日志文件最后一行非空内容。

- 最后一行是 `COMMENT`，并且不是 `ROLLBACK`，显示成功。
- 其他场景显示失败。

该判断逻辑只用于页面提示，最终结果仍建议结合完整日志确认。

## 远程目录清理规则

点击“清除目录”会弹窗确认当前环境和远程路径。

清理时会删除远程目录下除 `log` 目录外的文件和子目录。

`log` 目录、当前日志和 `log/history` 历史备份会保留。

## MD5 文件清单

页面入口：

```text
http://127.0.0.1:8000/md5
```

支持两类清单：

- 本地目录 MD5：可选择本地目录，也可手动输入本地路径。
- 远程服务器 MD5：复用远程连接配置，可添加多个远程路径。

可以通过文件后缀过滤，例如：

```text
.sql,.txt
```

MD5 配置会保存到本地 `md5_settings.json`。该文件可能包含本机路径，已在 `.gitignore` 中排除。

## 本地质量检查

以下检查不会建立 SSH 连接、上传文件或执行 SQL：

```bash
python3 -m py_compile main.py config.py logging_setup.py storage_utils.py
python3 -m unittest discover -s tests -v
python3 .agents/skills/sql-release-platform/scripts/audit_project.py --project .
```

需要执行统一代码规范检查时：

```bash
python3 -m pip install -r requirements-dev.txt
ruff check .
ruff format --check main.py config.py logging_setup.py storage_utils.py tests
```

测试覆盖配置保存与切换、远程 PG 脚本生成、密码脱敏、日志名称、MD5 配置，以及关键页面 ID 和接口绑定。

## 安全提醒

- 本工具默认不带登录鉴权，只适合内网或本机使用。
- 不要把 `.env`、`profiles.json`、`md5_settings.json` 上传到 GitHub。
- 不要在示例配置中填写真实服务器密码。
- 如果需要公网访问，建议先增加登录鉴权、HTTPS、IP 白名单和操作审计。

## 常见问题

### 页面提示 SSH 连接失败

请检查：

- 服务器 IP 是否正确。
- SSH 端口是否开放。
- 用户名和密码是否正确。
- 当前机器是否能访问目标服务器。

### 上传失败

请检查：

- 当前环境的 `REMOTE_DIR` 是否存在或是否有权限创建。
- SSH 用户是否有远程目录写权限。
- 本地选择的是目录，不是单个文件。

### 手动执行脚本成功，页面执行失败

请检查：

- 页面当前环境是否切换正确。
- 页面配置的脚本名称是否和远程脚本一致。
- 后台操作日志中打印的执行命令、远程目录、脚本路径是否正确。

## GitHub 提交建议

建议提交这些文件：

```text
main.py
config.py
logging_setup.py
storage_utils.py
requirements.txt
requirements-dev.txt
pyproject.toml
start.sh
start_uvicorn.sh
templates/
tests/
README.md
.gitignore
.env.example
profiles.example.json
md5_settings.example.json
```

不要提交这些文件：

```text
.env
profiles.json
md5_settings.json
runtime_logs/
.venv/
__pycache__/
```
