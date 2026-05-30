# 论文查非 6 个增强引擎轻量化部署与强制可用方案

> 适用分支：`new_tgg`  
> 适用目标：将论文查非增强能力部署为“轻量、可复现、可排查、不可静默降级”的运行时体系。  
> 核心选择：**模型资产存放在项目根目录 `.runtime/paper-assets/`，容器内统一挂载到 `/opt/piap-paper-assets`。**

---

## 1. 目标与约束

本方案要满足以下目标：

1. 6 个增强引擎必须真正参与论文查非流程。
2. 不能出现“某个引擎失败后返回空结果、继续生成报告”的静默降级。
3. 模型资产存放在项目根目录，便于本地开发、多人部署、排查文件是否存在。
4. 避免把大模型误提交到 Git。
5. 避免模型目录进入 Docker build context，导致构建极慢。
6. 后端和 celery-worker 共用同一份模型资产。
7. 第一次初始化之后，后续启动不重复下载模型。
8. 每次启动或任务运行前都能明确检查：哪些引擎可用、哪些不可用、为什么不可用。

---

## 2. 当前代码中的关键事实

当前仓库已经具备论文查非增强基础，但存在几个需要修复的点：

### 2.1 当前模型默认路径

下载脚本默认使用：

```text
/opt/piap-paper-assets
```

其中：

```text
/opt/piap-paper-assets/macro_correct/token
/opt/piap-paper-assets/macro_correct/punct
```

分别存放 token 纠错模型和 punct 标点模型。

当前后端运行时也按如下路径读取模型：

```text
PIAP_PAPER_CHECK_PYCORRECTOR_MODEL_DIR=/opt/piap-paper-assets/macro_correct/token
PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG=/opt/piap-paper-assets/macro_correct/token/csc.config
PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG=/opt/piap-paper-assets/macro_correct/punct/sl.config
```

所以本方案保持容器内路径不变，只改变宿主机实际存储位置。

---

### 2.2 当前 Dockerfile 的问题

当前 Dockerfile 在镜像构建阶段执行：

```dockerfile
RUN PYTHONPATH=. python scripts/download_paper_review_assets.py --base-dir /opt/piap-paper-assets
RUN PYTHONPATH=. python scripts/prewarm_paper_review_engines.py --vale-bin /usr/local/bin/vale
```

问题是：

```text
构建镜像 = 下载模型 + 预热模型
```

这会导致：

1. 构建慢。
2. 构建阶段依赖外网。
3. Hugging Face 访问失败会导致镜像无法构建。
4. 每个人本地构建都要重复面对模型下载问题。
5. 构建失败原因混杂：到底是代码依赖失败、模型下载失败、还是模型预热失败，不容易判断。

因此应改为：

```text
镜像构建阶段：只安装 Python 依赖和 Vale CLI
运行初始化阶段：下载模型到项目根目录 .runtime/paper-assets/
启动健康检查阶段：强制检查 6 个增强引擎是否可用
```

---

### 2.3 当前不符合“不降级不兜底”的逻辑

当前有几类静默降级行为需要移除：

#### 1. DOCX/PDF 增强解析失败后 fallback 到普通解析

当前逻辑类似：

```python
try:
    return parse_pdf_enhanced(content)
except Exception:
    return parse_pdf_bytes(content)
```

以及：

```python
try:
    return parse_docx_enhanced(content)
except Exception:
    return parse_docx_bytes(content)
```

这会导致增强解析失败后，系统仍然继续跑，只是能力变弱。

这不符合要求。

---

#### 2. LanguageTool 失败后返回空列表

当前逻辑中，LanguageTool 请求失败后可能直接：

```python
return []
```

这会导致用户以为没有语言问题，实际是 LanguageTool 没有起作用。

---

#### 3. pycorrector 超时或失败后返回空列表

当前逻辑中，pycorrector 超时或异常后可能：

```python
return []
```

这同样属于静默降级。

---

#### 4. macro-correct 只要 token 或 punct 任一成功就继续

如果 token 检测器失败、punct 检测器成功，系统仍然继续运行。

但你的目标是 6 个增强引擎都必须起作用，所以 token 和 punct 应该分别作为必需能力检查，任何一个失败都应阻断任务。

---

#### 5. disabled 被当作 ok

当前部分 runtime 诊断中，如果某个引擎配置为 disabled，可能被视为 ok。

这适合“可选增强”，但不适合“6 个增强引擎必须起作用”的场景。

在严格论文查非模式下：

```text
disabled = failure
```

---

## 3. 本方案定义的 6 个增强引擎

为了既符合当前代码结构，又便于部署和健康检查，本方案将 6 个增强引擎定义为：

| 编号 | 引擎 | 主要依赖 | 作用 | 失败处理 |
|---|---|---|---|---|
| E1 | 增强文档解析引擎 | `python-docx`、`lxml`、`PyMuPDF` | DOCX/PDF 结构、样式、字体、字号、页边距、页眉页脚、PDF 坐标布局解析 | 直接失败，不 fallback |
| E2 | pycorrector / MacBERT 纠错引擎 | `pycorrector` + 本地 MacBERT 模型 | 中文错别字检测 | 直接失败 |
| E3 | macro-correct token 引擎 | `macro-correct` + `csc.config` | 中文词级/字级纠错 | 直接失败 |
| E4 | macro-correct punct 引擎 | `macro-correct` + `sl.config` | 中文标点检测 | 直接失败 |
| E5 | LanguageTool 语言校对引擎 | LanguageTool sidecar | 语言、拼写、标点、语法提示 | 直接失败 |
| E6 | Vale 写作规范引擎 | Vale CLI + `.vale.ini` | 写作风格、单位空格、主观表达、规则化文本规范 | 直接失败 |

> 注意：E1 内部同时覆盖 DOCX 与 PDF。  
> 对 DOCX 任务，必须检查 `python-docx + lxml`。  
> 对 PDF 任务，必须检查 `PyMuPDF`。  
> 如果要同时允许 docx/pdf 都作为论文查非输入，则启动时建议三者都检查。

---

## 4. 推荐根目录资产路径

宿主机项目根目录：

```text
.runtime/paper-assets/
```

容器内统一路径：

```text
/opt/piap-paper-assets
```

完整目录结构：

```text
Intelligent-Product-Inspection-Agent-Platform/
├── .runtime/
│   └── paper-assets/
│       ├── manifest.json
│       └── macro_correct/
│           ├── token/
│           │   ├── config.json
│           │   ├── csc.config
│           │   ├── pytorch_model.bin
│           │   ├── tokenizer.json
│           │   ├── tokenizer_config.json
│           │   ├── special_tokens_map.json
│           │   └── vocab.txt
│           └── punct/
│               ├── config.json
│               ├── sl.config
│               ├── pytorch_model.bin
│               ├── tokenizer_config.json
│               ├── special_tokens_map.json
│               ├── idx2pun.json
│               └── vocab.txt
├── backend/
├── frontend/
├── docker-compose.yml
├── .gitignore
└── .dockerignore
```

---

## 5. 为什么可以放项目根目录

放项目根目录的优势是：

1. 本地开发者能直接看到模型是否下载成功。
2. 别人电脑部署时，不需要理解 Docker volume 的真实存储路径。
3. 迁移项目时，只要复制 `.runtime/paper-assets` 即可迁移模型资产。
4. 排查路径问题更容易。
5. 与当前代码的 `/opt/piap-paper-assets` 读取路径兼容，只需要 volume 映射。

但必须避免三个问题：

```text
问题 1：误提交模型到 Git
问题 2：Docker build context 变大
问题 3：模型版本与代码版本不一致
```

本方案分别用：

```text
.gitignore
.dockerignore
manifest.json + verify 脚本
```

解决。

---

## 6. 必须修改 `.gitignore`

在项目根目录 `.gitignore` 增加：

```gitignore
# Local runtime assets for paper review engines
.runtime/
!.runtime/.gitkeep

# Large model artifacts must never be committed
**/pytorch_model.bin
**/*.safetensors
**/*.ckpt
**/*.pt
**/*.onnx
**/*.bin
```

说明：

1. `.runtime/` 整体忽略，避免模型进入 Git。
2. 如果想保留目录结构，可以只提交 `.runtime/.gitkeep`。
3. 再额外忽略常见大模型文件，防止有人把模型放到其他路径后误提交。

可选：

```bash
mkdir -p .runtime
touch .runtime/.gitkeep
```

---

## 7. 必须修改 `.dockerignore`

在项目根目录 `.dockerignore` 增加：

```dockerignore
# Local runtime assets should not enter docker build context
.runtime/
runtime/
runtime_*/
runtime-*/

# Large model artifacts
**/pytorch_model.bin
**/*.safetensors
**/*.ckpt
**/*.pt
**/*.onnx
**/*.bin
```

原因：

即使 `.gitignore` 忽略了模型，Docker build 仍然可能把 `.runtime/` 发送到 build context。

如果 `.dockerignore` 不排除，执行：

```bash
docker compose build
```

时，大模型文件会被一起打包发送给 Docker daemon，导致构建极慢。

---

## 8. Dockerfile 改造

### 8.1 删除构建阶段模型下载和预热

从 `backend/Dockerfile` 删除：

```dockerfile
RUN PYTHONPATH=. python scripts/download_paper_review_assets.py --base-dir /opt/piap-paper-assets
RUN PYTHONPATH=. python scripts/prewarm_paper_review_engines.py --vale-bin /usr/local/bin/vale
```

保留：

1. Python 依赖安装。
2. Vale CLI 安装。
3. 字体安装。
4. 后端代码复制。

推荐结构：

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIAP_PAPER_CHECK_PYCORRECTOR_ENTRYPOINT=macbert_local \
    PIAP_PAPER_CHECK_PYCORRECTOR_MODEL_DIR=/opt/piap-paper-assets/macro_correct/token \
    PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG=/opt/piap-paper-assets/macro_correct/token/csc.config \
    PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG=/opt/piap-paper-assets/macro_correct/punct/sl.config \
    PIAP_PAPER_CHECK_VALE_BIN=/usr/local/bin/vale

WORKDIR /app/backend

ARG VALE_VERSION=3.13.0

COPY backend/requirements.txt ./requirements.txt

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl fonts-wqy-microhei wget && \
    curl -fsSL "https://github.com/vale-cli/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" -o /tmp/vale.tar.gz && \
    tar -xzf /tmp/vale.tar.gz -C /tmp vale && \
    install -m 0755 /tmp/vale /usr/local/bin/vale && \
    rm -f /tmp/vale /tmp/vale.tar.gz && \
    rm -rf /var/lib/apt/lists/* && \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY backend/ ./

EXPOSE 8000
```

---

## 9. requirements.txt 必须补充 PyMuPDF

当前 PDF 增强解析使用：

```python
import fitz
```

`fitz` 来自 `PyMuPDF`。

因此 `backend/requirements.txt` 增加：

```txt
PyMuPDF>=1.24.0
```

建议保留：

```txt
pypdf>=5.4.0
```

但在严格论文查非路径中，PDF 不允许增强解析失败后回退到 pypdf。

`pypdf` 可以保留给其他轻量文本提取场景，但不能作为论文查非增强路径的 fallback。

---

## 10. 新增 paper-assets-init 服务

在 `docker-compose.yml` 中增加一次性初始化服务：

```yaml
  paper-assets-init:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: piap-paper-assets-init
    working_dir: /app/backend
    command: >
      sh -c "PYTHONPATH=. python scripts/download_paper_review_assets.py
      --base-dir /opt/piap-paper-assets
      && PYTHONPATH=. python scripts/verify_paper_review_assets.py
      --base-dir /opt/piap-paper-assets"
    volumes:
      - ./.runtime/paper-assets:/opt/piap-paper-assets
    profiles:
      - paper-check
```

解释：

1. 宿主机路径是项目根目录下的 `.runtime/paper-assets`。
2. 容器内路径仍是 `/opt/piap-paper-assets`。
3. 初始化完成后，backend 和 celery-worker 只读挂载同一目录。
4. 初始化服务只负责资产准备，不负责启动后端。

---

## 11. backend 挂载根目录模型资产

在 `backend` 服务中增加：

```yaml
    volumes:
      - ./backend:/app/backend
      - ./.runtime/paper-assets:/opt/piap-paper-assets:ro
```

并增加依赖：

```yaml
    depends_on:
      paper-assets-init:
        condition: service_completed_successfully
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
      qdrant:
        condition: service_started
      languagetool:
        condition: service_healthy
```

环境变量保持：

```yaml
      PIAP_PAPER_CHECK_LANGUAGETOOL_URL: http://languagetool:8010
      PIAP_PAPER_CHECK_VALE_BIN: /usr/local/bin/vale
      PIAP_PAPER_CHECK_PYCORRECTOR_ENTRYPOINT: macbert_local
      PIAP_PAPER_CHECK_PYCORRECTOR_MODEL_DIR: /opt/piap-paper-assets/macro_correct/token
      PIAP_PAPER_CHECK_MACRO_CORRECT_TOKEN_CONFIG: /opt/piap-paper-assets/macro_correct/token/csc.config
      PIAP_PAPER_CHECK_MACRO_CORRECT_PUNCT_CONFIG: /opt/piap-paper-assets/macro_correct/punct/sl.config
      PIAP_PAPER_CHECK_STRICT_STARTUP: "true"
      PIAP_PAPER_CHECK_DISABLE_FALLBACK: "true"
```

---

## 12. celery-worker 也必须挂载同一份资产

如果论文查非任务可能在 worker 中执行，则 worker 必须挂载同一目录：

```yaml
  celery-worker:
    volumes:
      - ./backend:/app/backend
      - ./.runtime/paper-assets:/opt/piap-paper-assets:ro
    depends_on:
      paper-assets-init:
        condition: service_completed_successfully
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
      qdrant:
        condition: service_started
      languagetool:
        condition: service_healthy
```

否则会出现：

```text
backend 健康
worker 执行任务时找不到模型
```

这类问题非常隐蔽，必须避免。

---

## 13. LanguageTool 保持 sidecar

LanguageTool 是 Java 服务，不建议塞进 Python 后端镜像。

保留独立容器：

```yaml
  languagetool:
    image: erikvl87/languagetool:latest
    container_name: piap-languagetool
    environment:
      Java_Xms: 256m
      Java_Xmx: 512m
    ports:
      - "127.0.0.1:8081:8010"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8010/v2/languages"]
      interval: 10s
      timeout: 5s
      retries: 10
```

这是轻量且合理的方式：

```text
Python 后端镜像：代码、Python 依赖、Vale CLI
LanguageTool 容器：Java 语言校对服务
项目根目录 .runtime/paper-assets：本地模型资产
```

---

## 14. 新增 manifest.json 机制

模型放在项目根目录后，必须防止：

```text
代码升级了，但 .runtime/paper-assets 仍然是旧模型
```

建议下载完成后生成：

```text
.runtime/paper-assets/manifest.json
```

示例：

```json
{
  "asset_version": "paper-check-assets-v1",
  "created_by": "download_paper_review_assets.py",
  "base_dir": "/opt/piap-paper-assets",
  "repos": {
    "token": {
      "repo_id": "Macropodus/macbert4mdcspell_v2",
      "target": "macro_correct/token",
      "required_files": [
        "config.json",
        "csc.config",
        "pytorch_model.bin",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt"
      ]
    },
    "punct": {
      "repo_id": "Macropodus/bert4sl_punct_zh_public",
      "target": "macro_correct/punct",
      "required_files": [
        "config.json",
        "idx2pun.json",
        "pytorch_model.bin",
        "sl.config",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.txt"
      ]
    }
  }
}
```

更严格时应固定 Hugging Face revision：

```python
snapshot_download(
    repo_id=repo_id,
    revision="固定 commit sha",
    local_dir=str(target_dir),
    allow_patterns=files,
    local_dir_use_symlinks=False,
)
```

---

## 15. 新增 verify_paper_review_assets.py

新增脚本：

```text
backend/scripts/verify_paper_review_assets.py
```

用途：

1. 检查 token 模型文件是否完整。
2. 检查 punct 模型文件是否完整。
3. 检查关键配置文件是否存在。
4. 检查 `pytorch_model.bin` 是否非空。
5. 检查 manifest 是否存在。
6. 失败时直接退出非 0 状态。

示例代码：

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOKEN_FILES = [
    "config.json",
    "csc.config",
    "pytorch_model.bin",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
]

PUNCT_FILES = [
    "config.json",
    "idx2pun.json",
    "pytorch_model.bin",
    "sl.config",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="/opt/piap-paper-assets")
    args = parser.parse_args()

    base = Path(args.base_dir)
    errors: list[str] = []

    _check_dir(base / "macro_correct" / "token", TOKEN_FILES, errors)
    _check_dir(base / "macro_correct" / "punct", PUNCT_FILES, errors)

    manifest = base / "manifest.json"
    if not manifest.exists():
        errors.append(f"missing manifest: {manifest}")
    else:
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid manifest.json: {exc}")

    if errors:
        for item in errors:
            print(f"[paper-assets] {item}")
        return 1

    print(f"[paper-assets] ready: {base}")
    return 0


def _check_dir(path: Path, files: list[str], errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"missing dir: {path}")
        return

    for name in files:
        file_path = path / name
        if not file_path.exists():
            errors.append(f"missing file: {file_path}")
            continue

        if name in {"pytorch_model.bin", "vocab.txt"} and file_path.stat().st_size <= 0:
            errors.append(f"empty file: {file_path}")


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 16. 修改 download_paper_review_assets.py：生成 manifest

在下载脚本末尾增加 manifest 生成逻辑：

```python
def _write_manifest(base_dir: Path) -> None:
    manifest = {
        "asset_version": "paper-check-assets-v1",
        "created_by": "download_paper_review_assets.py",
        "base_dir": str(base_dir),
        "repos": {
            "token": {
                "repo_id": TOKEN_REPO,
                "target": "macro_correct/token",
                "required_files": TOKEN_FILES,
            },
            "punct": {
                "repo_id": PUNCT_REPO,
                "target": "macro_correct/punct",
                "required_files": PUNCT_FILES,
            },
        },
    }
    (base_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

在 `main()` 中：

```python
_write_manifest(base_dir)
```

---

## 17. 严格健康检查服务改造

当前 runtime 诊断应改造成“严格模式”。

建议新增配置：

```python
paper_check_strict_startup: bool = True
paper_check_disable_fallback: bool = True
```

并将引擎状态拆得更细：

```python
ENGINE_NAMES = (
    "enhanced_parser",
    "pycorrector",
    "macro_correct_token",
    "macro_correct_punct",
    "languagetool",
    "vale",
)
```

返回结构建议：

```json
{
  "ok": true,
  "status": "healthy",
  "strict": true,
  "engines_used": [
    "enhanced_parser",
    "pycorrector",
    "macro_correct_token",
    "macro_correct_punct",
    "languagetool",
    "vale"
  ],
  "engine_status": [
    {"name": "enhanced_parser", "ok": true, "detail": "python-docx/lxml/PyMuPDF installed"},
    {"name": "pycorrector", "ok": true, "detail": "pycorrector.MacBertCorrector.macbert_correct"},
    {"name": "macro_correct_token", "ok": true, "detail": "MacroCSC4Token.func_csc_token_batch"},
    {"name": "macro_correct_punct", "ok": true, "detail": "MacroCSC4Punct.func_csc_punct_batch"},
    {"name": "languagetool", "ok": true, "detail": "http://languagetool:8010"},
    {"name": "vale", "ok": true, "detail": "vale version ..."}
  ]
}
```

---

## 18. disabled 不能算 ok

严格模式下，所有增强引擎都必须启用。

错误示例：

```python
if not settings.paper_check_pycorrector_enabled:
    return {"name": "pycorrector", "ok": True, "detail": "disabled by config"}
```

应改成：

```python
if not settings.paper_check_pycorrector_enabled:
    return {"name": "pycorrector", "ok": False, "detail": "disabled but required in strict mode"}
```

macro-correct、LanguageTool、Vale 同理。

---

## 19. 启动时强校验

当前启动时如果 runtime 不健康，只记录 warning，不阻断启动。

严格模式应改为：

```python
async def log_paper_review_runtime_status() -> None:
    from app.services.paper_review_runtime_service import PaperReviewRuntimeService
    from app.core.config import settings

    result = await PaperReviewRuntimeService.diagnose()

    if result.get("ok"):
        logger.info("paper review runtime ready engines=%s", result.get("engines_used"))
        return

    if settings.paper_check_strict_startup:
        raise RuntimeError(f"paper review runtime not ready: {result.get('engine_status')}")

    logger.warning("paper review runtime not ready details=%s", result.get("engine_status"))
```

效果：

```text
6 个增强引擎全部可用：后端正常启动
任意一个不可用：后端启动失败
```

这比任务运行到一半才发现问题更合理。

---

## 20. 任务执行前也要 assert_ready

只在启动时检查还不够，因为运行期间 LanguageTool 容器可能挂掉，或者模型目录被误删。

在论文查非任务入口处执行：

```python
PaperReviewRuntimeService.assert_ready()
```

建议在 `check_paper_format()` 的 docx/pdf 路径开始处做：

```python
runtime_status = PaperReviewRuntimeService.diagnose_sync()
if not runtime_status.get("ok"):
    detail = "; ".join(
        f"{item['name']}: {item.get('detail') or 'unavailable'}"
        for item in runtime_status.get("engine_status", [])
        if not item.get("ok")
    )
    raise PaperReviewDependencyError(f"论文查非增强引擎未就绪：{detail}")
```

不要返回：

```python
{
  "score": 0,
  "issues": [],
  "limitations": ["论文检测环境未就绪，已终止 docx 增强校验。"]
}
```

因为这对用户来说仍然像是一次“有结果”的检查。

严格模式应该直接失败。

---

## 21. 移除 DOCX/PDF 增强解析 fallback

修改 `backend/agent/tools/file_parsers.py`。

严格模式下建议：

```python
def parse_file_content(file_name: str, content: bytes) -> dict:
    suffix = Path(file_name).suffix.lower()

    if suffix == ".pdf":
        from agent.tools.paper_pdf_parser import parse_pdf_enhanced
        return parse_pdf_enhanced(content)

    if suffix == ".docx":
        from agent.tools.paper_docx_parser import parse_docx_enhanced
        return parse_docx_enhanced(content)

    if suffix == ".tex":
        return parse_tex_bytes(content)

    raise ValueError("论文查非仅支持 docx、pdf、tex，且增强解析失败不得降级。")
```

如果仍想保留普通解析给其他非论文场景使用，可以拆成两个入口：

```python
parse_file_content()
parse_paper_review_file_content_strict()
```

论文查非只调用严格入口。

---

## 22. PDF 增强解析必须可用

`paper_pdf_parser.py` 使用：

```python
import fitz
```

因此必须安装：

```txt
PyMuPDF>=1.24.0
```

并在 runtime 诊断中增加：

```python
_check_import("fitz", "PyMuPDF")
```

如果是 PDF 文件，`fitz` 不可用就直接失败。

---

## 23. DOCX 增强解析必须可用

DOCX 增强解析依赖：

```text
python-docx
lxml
```

建议 runtime 中检查：

```python
_check_import("docx", "python-docx")
_check_import("lxml", "lxml")
```

且增强解析失败不能 fallback 到基础 `parse_docx_bytes()`。

---

## 24. pycorrector 失败必须抛错

当前 pycorrector 超时或异常时不应返回空结果。

建议修改：

```python
except PycorrectorUnavailableError as exc:
    raise PaperReviewDependencyError(f"pycorrector 不可用：{exc}") from exc
except asyncio.TimeoutError as exc:
    raise PaperReviewDependencyError(f"pycorrector 超时：{timeout_sec}s") from exc
except Exception as exc:
    raise PaperReviewDependencyError(f"pycorrector 执行失败：{exc}") from exc
```

---

## 25. macro-correct token 和 punct 必须都成功

建议修改：

```python
if token_results is None:
    raise PaperReviewDependencyError(f"macro-correct token 不可用：{token_error or 'no result'}")

if punct_results is None:
    raise PaperReviewDependencyError(f"macro-correct punct 不可用：{punct_error or 'no result'}")
```

不要只在两个都失败时才报错。

---

## 26. LanguageTool 失败必须抛错

建议修改：

```python
except Exception as exc:
    raise PaperReviewDependencyError(f"LanguageTool 不可用或执行失败：{exc}") from exc
```

不要：

```python
return []
```

---

## 27. Vale 失败必须抛错

Vale 当前已经对非 0/1 返回码抛出 `PaperReviewDependencyError`，这是正确方向。

还需要保证：

1. Vale 可执行文件存在。
2. `.vale.ini` 存在。
3. 规则目录存在。
4. `subprocess.run()` 超时也抛错，而不是被吞掉。

---

## 28. DOCX 和 PDF 都应进入文本增强引擎

当前文本增强引擎集中在 `_run_docx_text_engines()`。

建议改名：

```python
def _run_required_text_engines(parsed: dict[str, Any], *, file_name: str) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    issues.extend(_check_text_norms(parsed))
    issues.extend(_check_pycorrector(parsed))
    issues.extend(_check_macro_correct(parsed))
    issues.extend(_check_language_tool(parsed, file_name=file_name))
    issues.extend(_check_vale(parsed))
    return issues
```

DOCX：

```python
if document_type == "docx":
    issues.extend(_check_docx_structure(parsed))
    issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
    issues.extend(_check_docx_style(parsed))
    issues.extend(_check_front_matter_rules(parsed, template=template, document_type=document_type))
    issues.extend(_check_toc_rules(parsed, template=template))
    issues.extend(_check_heading_rules(parsed))
    issues.extend(_check_figure_table_rules(parsed))
    issues.extend(_check_formula_rules(parsed))
    issues.extend(_check_reference_rules(parsed))
    issues.extend(_check_word_artifact_rules(parsed))
    issues.extend(_run_required_text_engines(parsed, file_name=file_name))
```

PDF：

```python
elif document_type == "pdf":
    issues.extend(_check_pdf_structure(parsed))
    issues.extend(_check_text_norms(parsed))
    issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
    issues.extend(_check_front_matter_rules(parsed, template=template, document_type=document_type))
    issues.extend(_check_heading_rules(parsed))
    issues.extend(_check_figure_table_rules(parsed))
    issues.extend(_check_formula_rules(parsed))
    issues.extend(_check_reference_rules(parsed))
    issues.extend(_run_required_text_engines(parsed, file_name=file_name))
```

这样 PDF 也能得到：

```text
pycorrector
macro-correct token
macro-correct punct
LanguageTool
Vale
```

的增强检查。

---

## 29. 推荐启动命令

首次启动：

```bash
docker compose --profile paper-check up -d \
  mysql redis minio qdrant languagetool paper-assets-init backend frontend
```

如果任务由 celery 执行：

```bash
docker compose --profile paper-check up -d \
  mysql redis minio qdrant languagetool paper-assets-init backend celery-worker frontend
```

后续启动：

```bash
docker compose --profile paper-check up -d backend celery-worker frontend
```

如果模型资产已经存在且 manifest 校验通过，`paper-assets-init` 不会重复下载。

---

## 30. 推荐排查命令

查看模型目录：

```bash
ls -lah .runtime/paper-assets
ls -lah .runtime/paper-assets/macro_correct/token
ls -lah .runtime/paper-assets/macro_correct/punct
```

检查 manifest：

```bash
cat .runtime/paper-assets/manifest.json
```

容器内验证：

```bash
docker compose exec backend ls -lah /opt/piap-paper-assets
docker compose exec backend ls -lah /opt/piap-paper-assets/macro_correct/token
docker compose exec backend ls -lah /opt/piap-paper-assets/macro_correct/punct
```

检查 Vale：

```bash
docker compose exec backend vale --version
```

检查 LanguageTool：

```bash
curl http://127.0.0.1:8081/v2/languages
```

执行 runtime 诊断：

```bash
docker compose exec backend python - <<'PY'
from app.services.paper_review_runtime_service import PaperReviewRuntimeService
print(PaperReviewRuntimeService.diagnose_sync())
PY
```

---

## 31. 验收标准

一个合理的验收标准应包括：

### 31.1 资产验收

```text
.runtime/paper-assets/manifest.json 存在
.runtime/paper-assets/macro_correct/token/csc.config 存在
.runtime/paper-assets/macro_correct/token/pytorch_model.bin 存在且非空
.runtime/paper-assets/macro_correct/punct/sl.config 存在
.runtime/paper-assets/macro_correct/punct/pytorch_model.bin 存在且非空
```

---

### 31.2 引擎验收

runtime health 返回：

```text
enhanced_parser ok=true
pycorrector ok=true
macro_correct_token ok=true
macro_correct_punct ok=true
languagetool ok=true
vale ok=true
```

任一失败时，后端启动失败或论文查非任务失败。

---

### 31.3 不降级验收

人为破坏以下任一项，应导致任务失败，而不是返回空 issues：

```text
删除 .runtime/paper-assets/macro_correct/token/csc.config
停止 languagetool 容器
改错 PIAP_PAPER_CHECK_VALE_BIN
卸载或移除 PyMuPDF
设置 PIAP_PAPER_CHECK_PYCORRECTOR_ENABLED=false
删除 punct/sl.config
```

预期行为：

```text
任务失败
返回明确错误
指出具体哪个增强引擎不可用
不生成“正常检查报告”
```

---

## 32. 最小改造清单

### 必改文件

```text
.gitignore
.dockerignore
docker-compose.yml
backend/Dockerfile
backend/requirements.txt
backend/scripts/download_paper_review_assets.py
backend/scripts/verify_paper_review_assets.py
backend/app/core/config.py
backend/app/core/events.py
backend/app/services/paper_review_runtime_service.py
backend/agent/tools/file_parsers.py
backend/agent/tools/paper_format_checker.py
```

---

### 建议新增文件

```text
backend/scripts/verify_paper_review_assets.py
docs/PAPER_REVIEW_6_ENGINE_STRICT_DEPLOYMENT.md
```

---

## 33. 最终推荐架构

```text
项目根目录
├── .runtime/paper-assets/        # 模型资产，本地可见，不提交 Git，不进入 Docker build context
├── backend/                      # 后端代码
├── frontend/                     # 前端代码
└── docker-compose.yml

Docker Compose
├── paper-assets-init             # 一次性下载/校验模型资产
├── backend                       # FastAPI + Python 引擎 + Vale CLI
├── celery-worker                 # 可选，异步任务执行
├── languagetool                  # Java sidecar
├── mysql                         # 业务数据
├── redis                         # Celery / cache
├── minio                         # 模板、文件、对象存储
└── qdrant                        # 模板条款 / RAG 向量检索
```

核心原则：

```text
模型不进镜像
模型不进 Git
模型不进 Docker build context
模型在项目根目录可见
容器内路径保持 /opt/piap-paper-assets
backend 和 worker 只读挂载同一份模型
所有增强引擎强制健康检查
任何增强引擎失败都直接失败
不 fallback
不 return []
不 disabled-as-ok
```

---

## 34. 一句话总结

最推荐的实现是：

```text
项目根目录 .runtime/paper-assets 存模型
docker-compose 用 paper-assets-init 初始化
backend/worker 只读挂载 /opt/piap-paper-assets
LanguageTool 独立 sidecar
Vale 内置后端镜像
PyMuPDF 补入 requirements
DOCX/PDF 增强解析失败不 fallback
pycorrector、macro-correct、LanguageTool、Vale 失败直接抛错
启动时和任务前都做强健康检查
```

这样可以在保持部署轻量的同时，确保 6 个增强引擎真正起作用，而不是悄悄失效后继续生成不可靠的论文查非报告。
