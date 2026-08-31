《人工智能导论》图书管理系统

后端代码、数据库结构、初始化数据和完整运行说明位于 backend/README.txt。
后端启动：

    cd backend
    /opt/miniconda3/envs/pytorch_env/bin/python -m pip install -r requirements.txt
    /opt/miniconda3/envs/pytorch_env/bin/python -m scripts.init_db
    /opt/miniconda3/envs/pytorch_env/bin/python -m scripts.seed --as-of 2026-08-31
    /opt/miniconda3/envs/pytorch_env/bin/python -m uvicorn app.main:app --reload --port 8000

测试：

    /opt/miniconda3/envs/pytorch_env/bin/python -m pytest -q backend/tests

课程提交所需的技术报告、演示材料和 React 前台应与 backend 目录一起打包；
前端运行、演示账号、GitHub Pages 和评分证据清单见 frontend/README.md。
后端 API 契约和按评分点拆分的实施计划见 backend/docs/。

前端本地演示：

    cd frontend
    pnpm install
    pnpm dev

默认页面使用静态演示数据；复制 frontend/.env.example 为 frontend/.env.local
并将 VITE_DATA_MODE 改为 live 后，执行 pnpm dev:live 可连接本地 FastAPI。
