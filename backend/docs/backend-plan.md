# 后端实现计划与验收口径

本文件把课程考核方案当作唯一验收标准，把 GitHub 参考项目只当作领域拆分和数据一致性参考。参考项目中的预约、审批、邮件、推荐、评论和 7 天借期不属于本课程后端范围；本项目固定使用 Python、SQLite、30 天借期和每天 0.10 元罚款。

## 架构

```text
React 前台
    │ JSON / REST
FastAPI 路由（认证、图书、读者、借阅、文件、统计）
    │
领域服务（规则、权限、日期和金额计算）
    │
Repository 查询（不在仓储层提交事务）
    │
SQLAlchemy 2 + SQLite
```

每个写入用例由服务层取得 `BEGIN IMMEDIATE` 写锁、完成校验、更新关联表并一次提交。借书把借阅记录和可借库存放在同一事务中；还书把归还状态、罚款和库存恢复放在同一事务中。SQLite 连接开启外键、WAL 和 busy timeout。

## 数据表

| 表 | 用途 | 关键约束 |
| --- | --- | --- |
| `users` | 管理员和读者账号 | 学号唯一；停用账号不能登录；借阅上限非负 |
| `books` | 图书目录和库存 | ISBN、图书编号唯一；可借数不超过总数；删除采用停用 |
| `loans` | 借阅生命周期 | `BORROWED` 必须没有归还日期；`RETURNED` 必须有归还日期；借期不少于 30 天 |

`backend/database/schema.sql` 是提交用的 SQL 结构文件；`scripts/init_db.py` 通过 ORM 幂等创建同一结构。

## API 交付顺序

1. `auth`：管理员 `admin` 和读者学号登录，JWT 每次请求重新查询账号状态。
2. `books`：按书名、作者、ISBN、分类和图书编号查询；管理员完成增删改。
3. `readers`：管理员增改和注销；有未归还借阅的读者不能注销。
4. `loans`：借阅前检查库存、借阅上限和逾期记录；还书前提供罚款预览；返回凭单数据。
5. `files`：管理员导入图书 CSV，整批校验后一次提交；导出图书、读者和借阅 CSV。
6. `dashboard`：统计在馆图书、库存、读者、借阅、逾期和未缴罚款；管理员分析接口补充借还趋势、分类馆藏、热门图书和逾期区间。

## 课程考核映射

| 考核点 | 后端证据 |
| --- | --- |
| 菜单/页面展示 | FastAPI `/docs`、前台页面调用的 REST 路由 |
| 增、删、改、查 | books/readers 路由和对应测试 |
| 文件读写 | `/api/v1/files`、`data/seed_*.csv`、`database/schema.sql` |
| 功能整合 | 借阅事务、库存更新、罚款预览和 dashboard 统计 |
| 正常启动 | `scripts/init_db.py`、应用 lifespan 自动建表、README 启动命令 |
| 异常处理 | 稳定错误码、权限检查、字段校验、重复 ISBN、库存和状态冲突 |

前端页面对应关系：

| 前端页面 | 主要接口 | 可录制的操作证据 |
| --- | --- | --- |
| 管理总览 | `/dashboard/stats`、`/loans` | 菜单、指标卡、最近借阅、快捷入口 |
| 图书管理/目录 | `/books`、`/books/{id}` | 新增、修改、停用、按字段查询、库存状态 |
| 读者管理 | `/readers` | 创建、修改、注销、借阅上限和状态 |
| 借还书工作台 | `/loans`、`/loans/borrow`、`return-preview`、`return`、`fine/pay` | 借阅、归还预览、库存恢复、罚款登记 |
| 数据分析 | `/dashboard/stats`、`/dashboard/analytics` | 7/30/90 天趋势、分类、热门书、逾期分布 |
| 导入导出 | `/files/*` | 文件选择、前几行读取预览、整批导入结果、下载文件 |

报告中按考核方案逐项截取 `/docs`、CRUD 请求和响应、CSV 导入前后文件、读文件结果、借阅凭单和测试结果即可形成代码与效果证据。考核方案中出现的 “Trea” 按原文保留，具体软件名称以教师实际要求为准。

## 交付前检查

```text
/opt/miniconda3/envs/pytorch_env/bin/python -m pytest -q backend/tests
/opt/miniconda3/envs/pytorch_env/bin/python -m compileall -q backend/app backend/scripts
```

初始化演示库时使用 `scripts.seed --as-of YYYY-MM-DD`。脚本写入 1 个管理员、8 名读者、15 本图书和 12 条借阅记录，重复执行会跳过已有数据，不清空真实数据。
