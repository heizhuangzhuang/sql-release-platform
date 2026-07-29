# 业务规则

## 目录

- SQL 选项清单
- 生成脚本约定
- 上传与清理
- 远程执行和日志
- 执行结果判断
- 环境配置
- MD5 规则

## SQL 选项清单

每个 SQL 文件都是独立执行项。SQL 文件位于远程目标目录根目录，不能再拼接数据库名称子目录。

| Key | 页面标题/SQL 文件 | 数据库用户 | 数据库 | 当前日志 |
| --- | --- | --- | --- | --- |
| `batchetl1_tmp` | `db_pbatchetl001db_1_tmp.sql` | `outbound` | `pbatchetl001db` | `batchetl01_tmp_execute_sql.txt` |
| `batchetl2_tmp` | `db_pbatchetl001db_2_tmp.sql` | `outbound` | `pbatchetl001db` | `batchetl02_tmp_execute_sql.txt` |
| `data1_tmp` | `db_pdata001db_1_tmp.sql` | `outbound` | `pdata001db` | `data01_tmp_execute_sql.txt` |
| `pmigrel88` | `db_pmigrel00ldb_88.sql` | 当前环境 `db_user` | `pmighis001db` | `pmigrel00ldb88_execute_sql.txt` |
| `pmigrel98` | `db_pmigrel00ldb_98.sql` | 当前环境 `db_user` | `pmighis001db` | `pmigrel00ldb98_execute_sql.txt` |
| `batchetl1` | `db_pbatchetl001db_1.sql` | `outbound` | `pbatchetl001db` | `batchetl01_execute_sql.txt` |
| `batchetl2` | `db_pbatchetl001db_2.sql` | `outbound` | `pbatchetl001db` | `batchetl02_execute_sql.txt` |
| `batchetl3` | `db_pbatchetl001db_3.sql` | `outbound` | `pbatchetl001db` | `batchetl03_execute_sql.txt` |
| `batchetl4` | `db_pbatchetl001db_4.sql` | `outbound` | `pbatchetl001db` | `batchetl04_execute_sql.txt` |
| `data` | `db_pdata001db.sql` | `outbound` | `pdata001db` | `data_execute_sql.txt` |
| `other` | `db_pother001db.sql` | `outbound` | `pother001db` | `otherexecute_sql.txt` |
| `pub` | `db_ppub001db.sql` | `outbound` | `ppub001db` | `pubexecute_sql.txt` |
| `history` | `db_phist001db.sql` | `outbound` | `phist001db` | `histexecute_sql.txt` |
| `grant` | `db_pgrant001db.sql` | `outbound` | `pgrant001db` | `grant_execute_sql.txt` |
| `install01` | `db_pinstall001db.sql` | `outbound` | `pinstall001db` | `install01execute_sql.txt` |
| `install02` | `db_pinstall002db.sql` | `outbound` | `pinstall002db` | `install02execute_sql.txt` |
| `mainnf` | `db_pmainnf001db.sql` | `appdb` | `pmainnf001db` | `mainnf001dbexecute_sql.txt` |
| `test` | 测试命令，不读取 SQL | 无 | 无 | `测试脚本log` |

SQL 项统一使用 `/pgsoft/pg14.7/bin/psql -h localhost -p 5432`，并通过 `&>> ./log/<文件名>` 同时记录标准输出和错误输出。

例外：`pmigrel88` 和 `pmigrel98` 使用当前环境的 `db_host`、`db_port`、`db_user`、`db_password` 连接远程数据库 `pmighis001db`。密码通过命令级 `PGPASSWORD` 传入，不得写入系统日志或操作日志，脚本预览中必须显示为 `******`。两个 SQL 必须使用独立日志。

除非明确调整产品执行顺序，否则保持 `SCRIPT_ORDER`：

```text
batchetl1_tmp, batchetl2_tmp, data1_tmp, pmigrel88, pmigrel98,
batchetl1, batchetl2, batchetl3, batchetl4,
data, other, pub, history, grant, install01, install02, mainnf, test
```

每个环境可以保存最多 30 个自定义常规 SQL。每项包含唯一 ID、根目录 SQL 文件名、远程 PG 地址和端口、目标数据库、PG 账户、PG 密码和独立日志文件名。脚本使用命令级 `PGPASSWORD` 连接配置的远程 PG，在内置常规 SQL 之后、测试选项之前按保存顺序写入。密码不得写入系统日志或操作日志，脚本预览必须脱敏为 `******`。SQL 文件名和日志文件名不能与内置项或同环境其他自定义项重复；SQL 必须以 `.sql` 结尾，日志必须以 `.txt` 结尾，并且都不能包含目录路径。

## 生成脚本约定

所有选中项写入同一个当前环境脚本，默认名称为 `224.sh`。脚本开头必须包含：

```bash
#!/usr/bin/env bash
set -e
mkdir -p ./log ./log/history
```

每个选中项按照以下顺序生成：

1. 输出 `echo "执行<title>"`。
2. 如果当前日志存在，把它移动到 `./log/history/<原文件名>_YYYYMMDD_HHMMSS`。
3. 执行对应命令并生成新的当前日志。

测试选项必须创建 `./log/测试脚本log`，内容必须是 `测试通过啦！！` 并带换行。脚本要先创建 `log`，确保空目录第一次执行也成功。

脚本通过 SFTP 使用 UTF-8 写入，然后远程执行 `chmod +x`。预览和执行都必须读取环境中的 `script_name`，不能在代码中写死 `224.sh`。

## 上传与清理

上传本地所选目录内部的全部文件和子目录。去掉浏览器提供的最外层目录名称，只把目录内容放入 `remote_dir`。自动创建缺失的远程子目录。同名文件直接覆盖，无关文件保持不变。

上传前突出显示待上传数量；完成后返回真实成功数量，并弹窗提示成功或失败。

上传成功后必须清空浏览器目录选择，并把“当前选择文件数（待上传）”重置为 `0`；上传失败时保留原选择和数量，方便用户直接重试。用户重新选择目录后，再展示新目录的待上传文件数。

清理前必须弹窗展示当前环境和完整远程路径。递归删除远程目录内容，但保留顶层 `log` 目录，因此 `log/history`、当前日志和历史日志都会保留。完成后展示删除条目数量。

## 远程执行和日志

执行命令必须等价于：

```text
cd <安全引用后的 remote_dir> && bash <安全引用后的 ./script_name>
```

返回命令和退出码用于排查。Shell 退出码非 0 时接口返回失败。系统日志使用中文记录环境、路径、命令和退出码，但绝不记录密码。

当前日志读取 `log` 中全部普通文件，历史日志读取 `log/history` 中全部普通文件，按修改时间从新到旧排序。读取字节时优先 UTF-8，再尝试常见中文编码，最后才使用替换字符。页面通过两个标签页区分当前和历史日志，历史日志不能混入当前状态判断。

## 执行结果判断

读取当前日志最后一行非空、去除首尾空白后的内容：

- 转成大写后等于 `COMMENT`：成功。
- 其他所有情况：失败，包括 `ROLLBACK`、空日志、读取失败和输出不完整。

成功/失败标签紧跟日志文件名。每个日志卡片标题使用不同颜色，方便同时查看多个数据库。除非用户明确要求，不对历史日志应用成功失败判断。

## 环境配置

支持 `T2`、`Sit1`、`zsc` 等自定义环境名。保存 SSH 主机、端口、用户、明文密码、远程目录、脚本名称、默认本地目录，迁移数据库主机、端口、用户和明文密码，以及当前环境的自定义常规 SQL。页面支持分别显示/隐藏两个密码。连接成功显示绿色，失败显示红色。

上传、清理、生成、执行、远程目录、脚本预览和当前/历史日志统一使用当前活动环境。远程 MD5 配置保持独立，但可以首次从发布环境初始化。

## MD5 规则

支持 `.sql,.txt` 等后缀过滤；后缀为空表示统计全部文件。用户保存的路径刷新后继续存在，只有删除并重新保存后才移除。

远程 MD5：

- 独立保存 SSH 连接和多个路径。
- 单次最多统计 20 个路径。
- 通过 SSH 递归计算符合后缀文件的 MD5、大小、路径和可取得的创建/变更时间。
- 结果按照配置路径分组。

本地 MD5：

- 支持多个路径输入行。
- 支持绝对手工路径，由运行 FastAPI 的机器读取。
- 支持浏览器目录授权，由浏览器文件句柄读取。
- 选择目录只读取并计算 MD5，不上传、不复制文件。
- 浏览器无法可靠提供完整绝对路径，页面不能虚假展示绝对路径。
- 输入框已有绝对路径时，浏览器选择目录不能把它覆盖掉。
- 结果按照路径分组，不同路径标题使用不同颜色。
- 文件表格区域大约展示 10 行，更多内容通过滚动查看。
- 统计完成后支持在页面切换按文件路径、文件大小或文件时间排序。
- 文件大小支持“大到小”和“小到大”，文件时间支持“新到旧”和“旧到新”。
- 多个路径分组分别排序，不能把不同路径的文件混在一起。
