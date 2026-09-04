# Campus Library 前端

这是图书管理系统的 React + TypeScript + Vite 前端。页面采用 Google Workspace / Material 3 的轻量视觉语言：Google Sans Flex、Noto Sans SC、蓝色主操作、圆角容器、清晰的状态标签和移动端抽屉导航。登录页展示 `202314109方昕哲制作 · 20260831` 的淡色斜向制作水印；登录后页面会在内容背景显示当前账号的低透明度斜向水印，打印凭单时自动隐藏。

## 两种运行模式

默认是静态演示模式，数据在浏览器内存中生成，刷新页面会恢复成一组固定的课程演示数据。它不需要启动后端，适合 GitHub Pages、演示视频和课程报告截图。

```bash
cd frontend
pnpm install
pnpm dev
```

演示账号：

* 管理员：`admin` / `admin123`
* 读者：`DEMO-S001` / `demo123`

连接本地 FastAPI 时复制 `.env.example` 为 `.env.local`，将模式改为 `live`：

```dotenv
VITE_DATA_MODE=live
VITE_API_ORIGIN=http://127.0.0.1:8000
VITE_API_BASE=/api/v1
VITE_BASE_PATH=/
```

然后执行 `pnpm dev:live`。Vite 开发服务器会把 `/api` 和 `/health` 转发到 `VITE_API_ORIGIN`；生产构建由 `VITE_API_BASE` 决定请求前缀。

## 构建与检查

```bash
pnpm build
pnpm build:live
pnpm exec tsc --noEmit
pnpm test
```

生产包位于 `dist/`。应用使用 `HashRouter`，静态服务器不需要额外配置 history fallback。

## 页面和课程证据

管理员页面覆盖总览、图书 CRUD、读者 CRUD、借阅/归还/罚款、数据分析和 CSV 导入导出；读者页面覆盖图书检索、详情借阅、我的借阅和个人资料。后台分析接口提供可选 7/30/90 天趋势、分类馆藏、热门图书和逾期分布。

建议录制以下证据：登录页、图书新增/编辑/停用、关键词查询、读者创建、管理员办理借阅、归还预览和库存恢复、CSV 导入前后、CSV 导出文件、数据分析页和打印凭单。报告中的 Trea 安装/配置截图应使用实际操作截图，不由程序伪造。

## GitHub Pages

仓库根目录的 `.github/workflows/pages.yml` 会在推送默认分支后构建 `frontend` 的演示包并发布到 GitHub Pages。工作流将 `VITE_BASE_PATH` 设置为 `/<repository-name>/`；如果使用用户/组织根站点，可在工作流中改为 `/`。Pages 版本只包含演示数据，真实 SQLite 写入仍由本地 FastAPI 提供。
