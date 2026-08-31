# v1 API 契约

## 范围

API 根路径为 `/api/v1`，当前挂载六个业务域：`auth`、`books`、`readers`、`loans`、`files`、`dashboard`。模块已经注册，具体业务端点按实现计划逐步加入。当前版本不包含预约、推荐或其他未列入范围的功能。

系统端点为 `GET /health`，返回：

```json
{"status": "ok", "database": "configured", "version": "0.1.0"}
```

其中 `database` 表示数据库配置状态；没有数据库配置时为 `not_configured`，数据库模块不可用时为 `unavailable`。

## 字段命名

请求和响应使用 JSON，字段统一使用 `snake_case`。标识字段使用 `id`，时间字段使用 ISO 8601 格式并带时区；金额字段使用整数分或明确的十进制金额，禁止用浮点数表达金额。分页参数使用 `page` 和 `page_size`，列表响应使用 `items`、`total`、`page`、`page_size`。

## HTTP 错误

- `400 Bad Request`：请求格式或业务参数不合法。
- `401 Unauthorized`：缺少或无法验证的身份凭证。
- `403 Forbidden`：身份有效但没有执行操作的权限。
- `404 Not Found`：资源不存在。
- `409 Conflict`：资源状态冲突，例如重复借阅或归还状态不匹配。
- `422 Unprocessable Entity`：请求体字段校验失败（FastAPI 默认校验响应）。
- `500 Internal Server Error`：未预期的服务端错误。

错误响应统一包含 `detail` 对象，其中至少有 `code` 和 `message`；业务错误的
额外字段直接放在该对象中，字段校验错误还会在 `errors` 中保留原始字段位置。

## 借阅与费用规则

借阅期限为 30 天。逾期费用按每天 0.10 元计算，从到期日次日起计费，费用为逾期天数乘以 0.10 元；归还当日不额外计作逾期天数。金额计算使用精确的货币表示，结果保留到分。

## 当前路由

| 方法 | 路径 | 权限 | 作用 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 公开 | 管理员或学号登录 |
| `GET` | `/api/v1/auth/me` | 已登录 | 查看当前账号 |
| `GET/POST` | `/api/v1/books` | 登录/管理员 | 查询或新增图书 |
| `GET/PATCH/DELETE` | `/api/v1/books/{id}` | 登录/管理员 | 查看、修改或停用图书 |
| `GET/POST` | `/api/v1/readers` | 管理员 | 查询或新增读者 |
| `GET/PATCH/DELETE` | `/api/v1/readers/{id}` | 本人/管理员 | 查看、修改或注销读者 |
| `GET` | `/api/v1/loans` | 已登录 | 按借阅号、学号、状态和逾期过滤 |
| `POST` | `/api/v1/loans/borrow` | 已登录 | 使用 `book_id`、`isbn` 或 `book_code` 之一借书 |
| `GET` | `/api/v1/loans/{id}/receipt` | 本人/管理员 | 获取借阅凭单数据 |
| `GET/POST` | `/api/v1/loans/{id}/return-preview`、`return` | 本人/管理员 | 预览并完成还书 |
| `POST` | `/api/v1/loans/{id}/fine/pay` | 管理员 | 登记罚款已缴 |
| `POST/GET` | `/api/v1/files/books/import`、`export` | 管理员 | 图书 CSV 导入和导出 |
| `GET` | `/api/v1/files/readers/export`、`loans/export` | 管理员 | 读者和借阅 CSV 导出 |
| `GET` | `/api/v1/dashboard/stats` | 管理员 | 首页汇总统计 |
| `GET` | `/api/v1/dashboard/analytics?days=7\|30\|90` | 管理员 | 借还趋势、分类馆藏、热门图书和逾期分布 |

借阅请求示例：

```json
{"book_code": "BK000001"}
```

或者：

```json
{"isbn": "978-7-111-12345-6", "reader_id": 12}
```

管理员可提供 `reader_id` 为读者办理借阅；普通读者不能替他人借阅。返回的 `fine_amount` 始终是两位小数的元字符串，例如 `"0.30"`。

分析接口返回 `as_of`、`start_date`、`end_date`，并保证 `daily_trends` 包含窗口内每一天（没有记录的日期返回零）。`popular_books` 按借阅次数降序、图书 id 升序排列；`overdue_buckets` 固定返回 `1–7 天`、`8–30 天`、`31 天以上` 三个区间。`as_of` 可选，仅用于演示和测试的确定性日期。
