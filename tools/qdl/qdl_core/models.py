"""
models.py - 模型加载 + LLM/VLM 推理封装
========================================
职责：
  - StructuredPipelineModels：封装流水线所需的三类模型
      · VLM（Qwen3-VL，必需）
      · 句向量模型（BGE，缺依赖时优雅降级）
      · FAISS 索引（MVTec 知识库，缺依赖时优雅降级）
  - _llm_text_inference：纯文本 LLM 推理（查询理解 / 结构化生成 / CoT）
  - _vlm_image_inference：图文 VLM 推理（图像侧 JSON / 视觉候选）

依赖：utils（常量 + 模块别名） / transformers / qwen_vl_utils / torch
"""

from utils import *
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, GenerationConfig
from qwen_vl_utils import process_vision_info


# =====================================================
# 1. 模型加载器（VLM + SentenceTransformer + FAISS）
# =====================================================

class StructuredPipelineModels:
    """封装流水线所需的三类模型：VLM / 句向量模型 / FAISS 索引。"""

    def __init__(self):
        self.processor = None
        self.vlm = None
        self.embedder = None
        self.faiss_index = None
        self.kb_docs: list[dict] = []
        self.kb_dim: int = 0
        self.last_rag_trace: dict = {}
        self._loaded = False

    def load(self):
        """加载全部模型。VLM 必需；句向量+FAISS 缺依赖时优雅降级。"""
        print(f"⏳ 加载 VLM ... (路径: {MODEL_PATH})")
        # 修复：Kaggle 路径含多个 / 会被 HF 误判为 repo_id
        # 加 local_files_only=True 强制走本地路径
        self.processor = AutoProcessor.from_pretrained(
            MODEL_PATH, local_files_only=True,
        )
        self.vlm = Qwen3VLForConditionalGeneration.from_pretrained(
            MODEL_PATH, torch_dtype=torch.float16, device_map="auto",
            local_files_only=True,
        )
        print("✅ VLM 加载完成")
        self._load_kb_and_embedder()
        self._loaded = True

    def _load_kb_and_embedder(self):
        """加载 MVTec 知识库 + 句向量模型 + FAISS 索引。"""
        # QDL candidate scoring uses the embedder independently of RAG. Load it
        # even when the optional knowledge-base files are absent.
        try:
            from sentence_transformers import SentenceTransformer
            print(f"⏳ 加载句向量模型：{EMBED_MODEL_NAME}")
            self.embedder = SentenceTransformer(EMBED_MODEL_NAME, local_files_only=True)
            print("✅ 句向量模型加载完成")
        except ImportError:
            print("⚠️ 缺 sentence-transformers，QDL 将退化为词元相似度")
            self.embedder = None
        except Exception as e:
            print(f"⚠️ 句向量模型加载失败（离线？）：{e}；QDL 将退化为词元相似度")
            self.embedder = None

        if not os.path.exists(KB_JSON_PATH):
            print(f"⚠️  知识库 JSON 不存在：{KB_JSON_PATH}")
            print(f"    请先运行 build_mvtec_kb.py 构建知识库")
            print(f"    流水线将在无 RAG 模式下运行")
            return

        with open(KB_JSON_PATH, encoding="utf-8") as f:
            self.kb_docs = json.load(f)
        print(f"✅ 加载知识库：{len(self.kb_docs)} 条文档")

        if os.path.exists(KB_META_PATH):
            with open(KB_META_PATH, encoding="utf-8") as f:
                meta = json.load(f)
            self.kb_dim = meta.get("dim", 512)

        # 加载 FAISS 索引
        if self.embedder is not None and os.path.exists(KB_FAISS_PATH):
            try:
                import faiss
                print(f"⏳ 加载 FAISS 索引：{KB_FAISS_PATH}")
                self.faiss_index = faiss.read_index(KB_FAISS_PATH)
                print(f"✅ FAISS 索引加载完成（{self.faiss_index.ntotal} 条向量）")
            except ImportError:
                print(f"⚠️  缺 faiss，跳过向量索引加载")
                self.faiss_index = None
        else:
            self.faiss_index = None

    def is_rag_ready(self) -> bool:
        """RAG 是否可用（句向量模型 + FAISS 索引都就绪）。"""
        return self.embedder is not None and self.faiss_index is not None


# =====================================================
# 2. 工具函数：LLM/VLM 推理
# =====================================================

def _llm_text_inference(models: StructuredPipelineModels,
                         prompt: str,
                         max_new_tokens: int = 128) -> str:
    """纯文本 LLM 推理（用于查询理解 / 结构化文本生成 / CoT 推理）。"""
    proc = models.processor
    mdl = models.vlm
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], padding=True, return_tensors="pt").to("cuda")
    with torch.no_grad():
        gen_cfg = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens,
                                   repetition_penalty=1.2)
        gen_ids = mdl.generate(**inputs, generation_config=gen_cfg)
    out = proc.batch_decode(
        [o[len(i):] for i, o in zip(inputs.input_ids, gen_ids)],
        skip_special_tokens=True,
    )[0].strip()
    del inputs, gen_ids
    torch.cuda.empty_cache()
    return out


def _vlm_image_inference(models: StructuredPipelineModels,
                          img_path: str,
                          prompt: str,
                          max_new_tokens: int = 256) -> str:
    """图文 VLM 推理（用于图像侧 JSON 生成）。

    回退到 0-shot 单图版本（与 /kaggle/input/models/emilylisa/qwen3-vl-lora-merged 对齐）。
    """
    proc = models.processor
    mdl = models.vlm
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": img_path},
            {"type": "text",  "text": prompt},
        ],
    }]
    text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = proc(
        text=[text], images=image_inputs, videos=video_inputs,
        padding=True, return_tensors="pt",
    ).to("cuda")
    with torch.no_grad():
        gen_cfg = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens,
                                   repetition_penalty=1.2)
        gen_ids = mdl.generate(**inputs, generation_config=gen_cfg)
    out = proc.batch_decode(
        [o[len(i):] for i, o in zip(inputs.input_ids, gen_ids)],
        skip_special_tokens=True,
    )[0].strip()
    del inputs, gen_ids
    torch.cuda.empty_cache()
    return out


# =====================================================
# 3. Batch 推理函数（v2.6 加速 3：LLM/VLM batch 化）
# =====================================================

def _llm_text_inference_batch(models: StructuredPipelineModels,
                               prompts: list,
                               max_new_tokens: int = 128,
                               batch_size: int = 4) -> list:
    """
    批量纯文本 LLM 推理。
    把 N 个 prompt 分成 ceil(N/batch_size) 个 batch，每个 batch 一次 generate()。

    返回 list[str]，长度 = len(prompts)。
    """
    proc = models.processor
    mdl = models.vlm
    results = []

    for i in range(0, len(prompts), batch_size):
        batch_prompts = prompts[i:i + batch_size]

        # 为每个 prompt 构造 messages
        texts = []
        for p in batch_prompts:
            msgs = [{"role": "user", "content": [{"type": "text", "text": p}]}]
            t = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            texts.append(t)

        inputs = proc(text=texts, padding=True, return_tensors="pt").to("cuda")

        with torch.no_grad():
            gen_cfg = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens,
                                   repetition_penalty=1.2)
            gen_ids = mdl.generate(**inputs, generation_config=gen_cfg)

        outs = proc.batch_decode(
            [o[len(inp):] for inp, o in zip(inputs.input_ids, gen_ids)],
            skip_special_tokens=True,
        )
        results.extend([o.strip() for o in outs])

        del inputs, gen_ids
        torch.cuda.empty_cache()

    return results


def _vlm_image_inference_batch(models: StructuredPipelineModels,
                                img_paths: list,
                                prompts: list,
                                max_new_tokens: int = 256,
                                batch_size: int = 2) -> list:
    """
    批量图文 VLM 推理（单图模式）。
    把 N 个 (img_path, prompt) 分成 batch，每个 batch 一次 generate()。

    返回 list[str]，长度 = len(img_paths)。
    """
    proc = models.processor
    mdl = models.vlm
    results = []

    for i in range(0, len(img_paths), batch_size):
        batch_imgs = img_paths[i:i + batch_size]
        batch_prompts = prompts[i:i + batch_size]

        texts = []
        all_image_inputs = []
        for img_path, prompt in zip(batch_imgs, batch_prompts):
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": img_path},
                    {"type": "text", "text": prompt},
                ],
            }]
            t = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            texts.append(t)
            image_inputs, _ = process_vision_info(messages)
            if image_inputs:
                all_image_inputs.extend(image_inputs)

        inputs = proc(
            text=texts, images=all_image_inputs if all_image_inputs else None,
            padding=True, return_tensors="pt",
        ).to("cuda")

        with torch.no_grad():
            gen_cfg = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens,
                                   repetition_penalty=1.2)
            gen_ids = mdl.generate(**inputs, generation_config=gen_cfg)

        outs = proc.batch_decode(
            [o[len(inp):] for inp, o in zip(inputs.input_ids, gen_ids)],
            skip_special_tokens=True,
        )
        results.extend([o.strip() for o in outs])

        del inputs, gen_ids
        torch.cuda.empty_cache()

    return results


def _vlm_image_inference_batch_dual(models: StructuredPipelineModels,
                                     ref_img_paths: list,
                                     test_img_paths: list,
                                     prompts: list,
                                     max_new_tokens: int = 256,
                                     batch_size: int = 2) -> list:
    """
    批量图文 VLM 推理（1-shot 双图模式）。
    每个样本有 2 张图：[参考图, 测试图]。
    batch_size 指样本数（每个样本 2 张图，实际 batch = batch_size * 2 张图）。

    返回 list[str]，长度 = len(test_img_paths)。
    """
    proc = models.processor
    mdl = models.vlm
    results = []
    n = len(test_img_paths)

    for i in range(0, n, batch_size):
        batch_refs = ref_img_paths[i:i + batch_size]
        batch_tests = test_img_paths[i:i + batch_size]
        batch_prompts = prompts[i:i + batch_size]

        texts = []
        all_image_inputs = []
        for ref_path, test_path, prompt in zip(batch_refs, batch_tests, batch_prompts):
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": ref_path},   # 第 1 张：参考图
                    {"type": "image", "image": test_path},   # 第 2 张：测试图
                    {"type": "text", "text": prompt},
                ],
            }]
            t = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            texts.append(t)
            image_inputs, _ = process_vision_info(messages)
            if image_inputs:
                all_image_inputs.extend(image_inputs)

        inputs = proc(
            text=texts, images=all_image_inputs if all_image_inputs else None,
            padding=True, return_tensors="pt",
        ).to("cuda")

        with torch.no_grad():
            gen_cfg = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens,
                                   repetition_penalty=1.2)
            gen_ids = mdl.generate(**inputs, generation_config=gen_cfg)

        outs = proc.batch_decode(
            [o[len(inp):] for inp, o in zip(inputs.input_ids, gen_ids)],
            skip_special_tokens=True,
        )
        results.extend([o.strip() for o in outs])

        del inputs, gen_ids
        torch.cuda.empty_cache()

    return results
