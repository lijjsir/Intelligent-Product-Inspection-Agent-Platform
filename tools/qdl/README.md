# 独立缺陷检测与 QDL 图文匹配

从项目根目录运行，无需启动平台后端、数据库或前端。Python 3.10+ 即可使用默认 HTTP 推理和规则匹配；运行电脑不加载大模型，不需要 PyTorch/CUDA。

## 配置模型服务

将 `config.example.json` 复制为同目录的 `config.local.json`，把 `base_url` 改为运行电脑可访问的模型服务地址。模型默认为 `qwen3.5:9b-q8_0`。本机专用配置、检测输出和缓存不会提交或进入部署包。

优先级：命令行 `--base-url` / `--model` > 环境变量 `QDL_BASE_URL` / `QDL_MODEL` > `config.local.json` > 默认本机地址。
需要密钥时通过环境变量 `QDL_API_KEY` 提供。内网请求默认绕过系统网络代理；需要代理时设置 `QDL_USE_PROXY=1`。

## 检测图片

```sh
python scripts/detect_defects.py --image /data/images/sample.png
python scripts/detect_defects.py --image-dir /data/images --limit 10
```

Windows 示例：`python scripts/detect_defects.py --image "C:/data/待检测图片.png"`。
入口默认返回 JSON 缺陷结果，并将每次运行保存到独立的 `tools/qdl/results/defects-*.jsonl` 和相邻的 `*_metrics.json`，不覆盖之前的默认输出。

结果包含有无缺陷、缺陷类别、位置描述、证据、模型置信度及框坐标。`bbox` 使用原算法定义：0–1000 的 `[x1,y1,x2,y2]`，与平台的 0–1 `[x,y,w,h]` 不同。
模型可能给出不正确的判断或定位，准确率需要独立标注集评测；没有标签时分类指标为 `null`。

需要明确输出位置或产品类型时：

```sh
python scripts/detect_defects.py --image /data/images/sample.png --category bottle --output tools/qdl/results/bottle.jsonl
```

产品类型必须由 `--category` 显式提供，不从文件夹名称推断，避免把 `scratch`、`good` 等数据集目录标签泄露给模型。
`--prompt-mode evidence-first` 可切换为短证据与 Yes/No 输出。
`--data labels.jsonl` 可使用原包的标注评测流程；真实标签不进入模型提示词。
显式指定 `--output` 会写入该文件；需要续跑时用同一个输入、排序和输出文件并加 `--resume`。

## QDL 图文匹配

```sh
python tools/qdl/run_qdl.py --input tools/qdl/examples/pairs.jsonl --output tools/qdl/results/qdl_audit.jsonl
python tools/qdl/run_qdl.py --input tools/qdl/examples/pairs.jsonl --output tools/qdl/results/qdl_review.jsonl --review --max-candidates 16
```

QDL 输入是独立文字描述与图像检测结果的结构化字段，不直接读取图片，也不替代第一步检测。
JSONL 样例见 `examples/pairs.jsonl`。图像侧可整理自预测结果的 `prediction` 字段；文字侧应来自独立记录，不能复制同一个预测凑成两侧。

默认使用原包的规则、本体和词项相似度；`--review` 会逐候选边调用已部署模型，并要求 JSON Schema 输出。批量使用前先小规模计时。`--embed-model` 只接受已有本地 sentence-transformers 模型目录，在 CPU 加载，不自动下载；该模式需自行安装 `sentence-transformers`。

输出保留 `split`。审计字段 `llm_review_used`、`embedding_backend`、`fallback_used`、`fallback_reasons` 标明实际模式；模型审查失败时原算法可能回退到规则。匹配分数与模型自报置信度均不是校准概率。

## 文件与测试

- `predict.py`：独立推理和评测，保留显式 Ollama 原生/Transformers 可选后端。
- `qdl_core/`：原匹配、本体、数据构建和研究代码；高级 Transformers/RAG 流程需要另配依赖、权重和数据。
- `rebuildcode/`：原证据输出协议。
- `run_qdl.py`：独立图文审计入口。

API 模式不加载 LoRA adapter；需要时选择已部署的微调模型，或使用另配环境的 Transformers 后端。本目录没有配置真实微调训练，也没有接入平台页面或任务调度。

在项目根目录执行测试：

```sh
python -m pytest -q -c tools/qdl/pytest.ini tools/qdl
```

原包部分测试需要 Pillow，可执行 `python -m pip install -r tools/qdl/requirements-inference.txt`；默认 HTTP 推理和规则审计仅依赖标准库。
