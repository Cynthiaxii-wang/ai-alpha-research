# AI Alpha Research Web

Next.js App Router 网站。保留 Overview、AI Value Chain、Signal Monitor、Factor Lab、AI 需求兑现链及公司详情。各模块沿用 `/#signals` 等 hash 地址。

## 本地开发

使用 Node.js 22 和 npm。从项目根目录：

```bash
npm ci --prefix web
npm run dev
```

访问 http://localhost:3000。在 `web/` 内也可直接执行 `npm run dev`。

```bash
# 项目根目录：验证生产构建并启动
npm run build
npm run start
```

## 目录

```text
web/
  app/layout.jsx          文档、元信息和全局样式
  app/page.jsx            首页入口
  src/App.jsx             客户端看板和 hash 导航
  src/DemandChain.jsx      需求兑现链组件
  src/styles.css          原有视觉样式
  public/data/dashboard.json  Python 导出的研究快照
  public/favicon.svg
  next.config.mjs         standalone 构建配置
  scripts/start.mjs       补齐静态资源并启动 standalone 服务
  Dockerfile
```

Python 的 `src/`、`scripts/`、`config/`、`data/` 保留在项目根目录。网站构建不执行数据采集，也不需要 Python 或提供商 API 密钥。

## Vercel

将项目推送到 Git 仓库后导入 Vercel：

- Root Directory：`web`
- Framework Preset：`Next.js`
- Node.js：22.x
- Install Command：`npm ci`
- Build Command：`npm run build`
- Output Directory：使用 Next.js 默认值，不填写 `dist` 或 `out`
- Environment Variables：当前网站无需配置；根目录 `.env` 仅供本地 Python 采集使用

每次更新 `public/data/dashboard.json` 后重新部署。当前应用没有登录系统；需要内部访问时，应在托管平台或反向代理配置访问控制。

## Node.js / Docker

普通 Node.js 主机：在 `web/` 执行 `npm ci`、`npm run build`、`npm run start`，通过进程管理器运行并配置 HTTPS 反向代理。启动脚本自动将 `public/` 和 `.next/static/` 复制到 standalone 目录，可通过 `PORT` 和 `HOSTNAME` 环境变量调整监听地址（默认 `0.0.0.0:3000`）。

Docker 在项目根目录构建，构建上下文必须为 `web/`：

```bash
docker build -t ai-alpha-research ./web
docker run --rm -p 3000:3000 --name ai-alpha-research ai-alpha-research
```

镜像使用非 root 用户，包含 standalone 服务、静态资源和研究 JSON。无需挂载项目根目录或 `.env`。

如手动搬运 standalone 产物，需要同时复制 `web/public` 到产物中的 `public`，以及 `web/.next/static` 到产物中的 `.next/static`，再运行 `node server.js`。Dockerfile 已包含这些步骤。

## 数据更新与发布范围

在项目根目录使用原有 Python 环境生成快照：

```bash
python3 scripts/export_web_data.py
npm run build
```

部署内容是生成时的快照；托管网站不会自动运行本地每日采集任务。更新后需重建并重新部署。所有 `public/` 文件均可被访问者下载。

项目已有 `scripts/audit_public_release.py` 将研究数据标记为 `blocked_for_public_redistribution`，记录了 Massive 数据及工作簿来源数据的公开展示授权要求。技术部署配置已就绪，但该迁移不改变既有数据发布状态；公开发布前需完成原有审核，或换用允许公开展示的数据。

Next.js 官方参考：[部署](https://nextjs.org/docs/app/getting-started/deploying)、[standalone 输出](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)。
