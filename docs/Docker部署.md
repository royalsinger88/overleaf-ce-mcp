# overleaf-ce-mcp Docker 部署指南

本指南用于把 `overleaf-ce-mcp` 作为容器运行。

## 1. 前提

- 服务器已安装 Docker（建议 24+）。
- 你有可用的 CE 地址（例如 `http://129.150.32.65:17880`）。
- 已准备认证文件：`/root/.olauth`。

## 2. 构建镜像

默认构建（不安装 LaTeX，本地编译工具不可用，但上传/同步可用）：

```bash
cd /root/overleaf-ce-mcp
docker build -t overleaf-ce-mcp:latest .
```

需要容器内 `latexmk`（镜像更大）：

```bash
cd /root/overleaf-ce-mcp
docker build --build-arg INSTALL_LATEX=1 -t overleaf-ce-mcp:latex .
```

## 3. 直接运行

```bash
docker run --rm -it \
  -v /root/overleaf-workspace:/workspace \
  -v /root/.olauth:/root/.olauth \
  -w /workspace \
  overleaf-ce-mcp:latest
```

说明：
- 容器入口命令是 `overleaf-ce-mcp`（MCP stdio 服务）。
- 默认模板目录已在镜像内设置为：`/opt/overleaf-ce-mcp/overleaf_ce_mcp/templates`。
- 若要额外启用 Semantic Scholar，可追加：`-e S2_API_KEY="your_semantic_scholar_key"`。

## 4. 使用 compose 运行

项目已内置 `docker-compose.yml`：

```bash
cd /root/overleaf-ce-mcp
docker compose up --build
```

若你的环境未启用 `docker compose` 子命令，可改用：

```bash
cd /root/overleaf-ce-mcp
docker-compose up --build
```

后台运行：

```bash
cd /root/overleaf-ce-mcp
docker compose up -d --build
```

或：

```bash
cd /root/overleaf-ce-mcp
docker-compose up -d --build
```

停止：

```bash
cd /root/overleaf-ce-mcp
docker compose down
```

或：

```bash
cd /root/overleaf-ce-mcp
docker-compose down
```

## 5. 容器内自检

如果你需要在容器内临时执行 Python 检查：

```bash
docker run --rm -it \
  -v /root/overleaf-workspace:/workspace \
  -v /root/.olauth:/root/.olauth \
  -w /workspace \
  --entrypoint python \
  overleaf-ce-mcp:latest \
  -c "from overleaf_ce_mcp.server import _collect_env_status; print(_collect_env_status())"
```

## 6. 常见问题

1. 容器里看不到认证
- 检查是否挂载了 `-v /root/.olauth:/root/.olauth`。
- 检查文件格式是否为 pickle 且包含 `cookie` 字段。

2. 需要本地编译但 `latexmk` 不可用
- 用 `INSTALL_LATEX=1` 重新构建。

3. Semantic Scholar 检索经常 429
- 默认 `source=all` 已不依赖 Semantic Scholar，可直接使用。
- 若你必须用 Semantic Scholar，再给容器注入 `S2_API_KEY`。

4. 同步时误传了 workspace 根目录
- 当前版本已内置路径收敛护栏：`project_name` 命中同名子目录时自动收敛。

5. replace 无法删除深层文件
- 当前版本已修复多级路径删除逻辑。

6. 如何在容器流程里接入“深度研究报告”
- 先用 `generate_deep_research_prompt` 生成提示词。
- 在 GPT 网页版得到报告后，保存到挂载目录（如 `/workspace/test/deep-research-report.md`）。
- 再调用 `ingest_deep_research_report`，并把 `save_bib_path` 指到项目目录（如 `/workspace/test/references.bib.draft`）。
