# 运维手册

## 目录

- 运行环境
- 第一次启动
- 日常启动
- 运行时文件
- 日志规范
- 常见故障
- 验证与发布

## 运行环境

支持 Linux 或 macOS。最低目标 Python 版本为 3.8.2，并需要 `pip`、到 SSH 目标的网络访问能力和现代浏览器。远程 Linux 服务器需要 SSH/SFTP、Bash，以及 SQL 执行所需的 PostgreSQL `psql`。

依赖包括 FastAPI、Uvicorn、Paramiko、python-multipart、Jinja2 和 python-dotenv。升级固定版本前必须重新确认 Python 3.8 支持情况。

## 第一次启动

在项目目录执行：

```bash
chmod +x start.sh start_uvicorn.sh
./start.sh
```

`start.sh` 会创建 `.venv`、安装固定依赖，并监听 `0.0.0.0:8000`。

使用已有 Python 环境时执行：

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

使用用户目录中的 Uvicorn：

```bash
UVICORN_BIN=/home/your_user/.local/bin/uvicorn RELOAD= ./start_uvicorn.sh
```

`--reload` 只用于开发，稳定运行时关闭自动重载。

## 运行时文件

以下文件由运行时生成，禁止提交或打入公开模板：

- `.env`
- `profiles.json`
- `md5_settings.json`
- `runtime_logs/`
- `.venv/`
- `__pycache__/`

`.env.example`、`profiles.example.json` 和 `md5_settings.example.json` 只用于展示安全数据结构。

## 日志规范

技术生命周期、HTTP 请求、SSH、命令和异常记录到 `runtime_logs/app.log`。简洁的用户操作、成功状态和中文字段记录到 `runtime_logs/operations.log`。两个日志都按照 `LOG_MAX_BYTES` 和 `LOG_BACKUP_COUNT` 自动滚动。

日志要包含足够的非敏感排查信息：

- HTTP 方法和路径
- 操作名称和耗时
- 环境名称、主机、端口和用户
- 远程目录和脚本名称
- 选中的 SQL key
- 安全引用后的命令和退出码
- 上传、删除、扫描或查询数量
- 非预期异常堆栈

不得记录 SSH 密码或敏感文件完整内容。

## 常见故障

### 页面打不开

检查 8000 端口是否监听、启动输出和 `runtime_logs/app.log`。确认进程从项目目录启动，否则可能找不到 Jinja2 模板。

### SSH 连接失败

使用页面“测试连接”。检查主机、端口、用户、密码、防火墙和远程 SSH 服务。系统明确不支持 SSH_KEY_PATH。

### 手工 SSH 能执行，页面不能执行

对比日志里的非交互命令和手工命令。检查工作目录、脚本名称、文件权限、PATH、PostgreSQL 环境变量和 `/pgsoft/pg14.7/bin/psql`。继续查看退出码、错误输出和当前远程日志。

### 点击生成脚本没有效果

确认至少选择一个与 `SCRIPT_BLOCKS` 对应的 key，检查 `/generate` 返回，再检查 `/script-preview`。确认当前环境的脚本名称和远程目录。Shell 中的 `%` 曾经被 Python `%` 格式化误判，包含日期格式时使用 `.format()` 或正确转义百分号。

### 远程日志乱码

以字节读取，优先尝试 UTF-8，再尝试常见中文编码，替换字符只作为最后兜底。不要直接使用 Web 服务器系统默认编码。

### 浏览器选择目录没有绝对路径

这是浏览器安全限制，不是后端故障。输入框中已有手工绝对路径时保留它；浏览器目录句柄通常只能提供目录名称。

## 验证与发布

完成修改前执行：

```bash
python3 -m py_compile main.py config.py logging_setup.py
python3 /Skill目录/scripts/audit_project.py --project /项目目录
```

然后验证受影响页面和接口。远程写操作只能针对用户明确选择的安全环境执行；没有实际执行时必须说明。

提交代码或同步模板前：

1. 检查 `git status` 和暂存差异。
2. 搜索即将提交的密码和用户绝对路径。
3. 确认运行 JSON、`.env`、日志、缓存和无关临时文件未被提交。
4. 保持提交范围单一，不强推、不覆盖远程历史。
