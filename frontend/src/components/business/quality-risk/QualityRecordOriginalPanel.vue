<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { extractApiErrorMessage } from "@/api/http";
import { qualityRiskApi } from "@/api/quality-risk.api";
import type { QualityAttachment, QualitySourceRecord } from "@/types/quality-risk.types";
import { isPdfAttachment, readSourceText, safeSourceUrl } from "@/utils/quality-source-reading";

const props = defineProps<{ record: QualitySourceRecord; attachments: QualityAttachment[]; initialAttachmentId?: string; targetPage?: number; pageRequestKey?: number }>();
const emit = defineEmits<{ download: [file: QualityAttachment] }>();
const selectedId = ref("");
const originalUrl = ref("");
const text = ref("");
const loading = ref(false);
const error = ref("");
const readingBody = ref<HTMLElement>();
const findText = ref('');
const findMessage = ref('');
const matchedParagraph = ref(-1);
let epoch = 0;
const textLimit = 2 * 1024 * 1024;
const activeFile = computed(() => props.attachments.find(file => file.id === selectedId.value));
function fileKind(file?: QualityAttachment): "pdf" | "image" | "text" | "other" {
  if (!file) return "other";
  const mime = (file.mime_type || "").split(";")[0]?.toLowerCase() || "";
  if (isPdfAttachment(file)) return "pdf";
  if (["image/png", "image/jpeg", "image/webp", "image/gif"].includes(mime)) return "image";
  if (mime === "text/plain" || /\.(txt|csv|json)$/i.test(file.file_name)) return "text";
  return "other";
}
const kind = computed(() => fileKind(activeFile.value));
const pdfSource = computed(() => originalUrl.value + (props.targetPage && Number.isInteger(props.targetPage) && props.targetPage > 0 ? `#page=${props.targetPage}&view=FitH&navpanes=0` : '#view=FitH&navpanes=0'));
const sourceUrl = computed(() => safeSourceUrl(props.record.provenance));
const sourceDomain = computed(() => sourceUrl.value ? new URL(sourceUrl.value).hostname : "");
const sourceIsPdf = computed(() => sourceUrl.value && /\.pdf$/i.test(new URL(sourceUrl.value).pathname));
const reading = computed(() => readSourceText(text.value, !!sourceUrl.value && !sourceIsPdf.value));
const canPreview = computed(() => activeFile.value && kind.value !== "other" && !(kind.value === "text" && activeFile.value.size_bytes > textLimit));
function clearPreview() {
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
  originalUrl.value = "";
  text.value = "";
  findText.value = ''; findMessage.value = ''; matchedParagraph.value = -1;
}
async function findInText() {
  const term = findText.value.trim().toLocaleLowerCase();
  if (!term) { matchedParagraph.value = -1; findMessage.value = ''; return; }
  const hits = reading.value.paragraphs.flatMap((paragraph, index) => paragraph.toLocaleLowerCase().includes(term) ? [index] : []);
  const next = hits.find(index => index > matchedParagraph.value) ?? hits[0];
  matchedParagraph.value = next ?? -1;
  findMessage.value = hits.length ? `找到 ${hits.length} 段相关内容` : '未找到相关内容';
  await nextTick();
  const body = readingBody.value;
  const target = body?.querySelector<HTMLElement>('[data-reading-match="true"]');
  if (body && target) body.scrollTop += target.getBoundingClientRect().top - body.getBoundingClientRect().top - 12;
}
async function loadOriginal() {
  const current = ++epoch;
  clearPreview();
  error.value = "";
  loading.value = false;
  const file = activeFile.value;
  const format = kind.value;
  if (!file || !canPreview.value) return;
  loading.value = true;
  try {
    // Use the authenticated download endpoint, never a public storage URL.
    const response = await qualityRiskApi.downloadAttachment(file.id);
    if (current !== epoch) return;
    const blob = response.data as unknown as Blob;
    if (format === "text") {
      if (blob.size > textLimit) throw new Error("文字附件较大，请下载后核对。");
      const content = await blob.text();
      if (current !== epoch) return;
      text.value = content;
      originalUrl.value = URL.createObjectURL(new Blob([blob], { type: 'text/plain;charset=utf-8' }));
    } else {
      // Keep PDFs as PDFs even if the download response uses octet-stream.
      const safeType = format === "pdf" ? "application/pdf" : file.mime_type;
      originalUrl.value = URL.createObjectURL(new Blob([blob], { type: safeType }));
    }
  } catch (failure) {
    if (current === epoch)
      error.value = failure instanceof Error && failure.message === "文字附件较大，请下载后核对。"
        ? failure.message : extractApiErrorMessage(failure, "原件未能加载，请重试或下载附件核对。");
  } finally {
    if (current === epoch) loading.value = false;
  }
}
watch(() => [props.record.id, props.initialAttachmentId, ...props.attachments.map(file => file.id)], () => {
  selectedId.value = (props.attachments.find(file => file.id === props.initialAttachmentId)
    || props.attachments.find(file => fileKind(file) === "pdf")
    || props.attachments.find(file => fileKind(file) === "image")
    || props.attachments.find(file => fileKind(file) === "text")
    || props.attachments[0])?.id || "";
}, { immediate: true });
watch(() => [props.record.id, activeFile.value?.id], loadOriginal, { immediate: true });
onBeforeUnmount(() => { ++epoch; clearPreview(); });
</script>

<template>
  <section class="record-original-panel" :class="{'pdf-original-panel':kind === 'pdf'}" aria-label="原件与出处对照">
    <header><h3>{{ kind === 'pdf' ? 'PDF 原件' : kind === 'text' && sourceUrl && !sourceIsPdf ? '网页正文与出处' : '原始附件与出处' }}</h3><span>与资料记录对照</span></header>
    <div v-if="sourceUrl && kind !== 'pdf'" class="original-source">
      <div><strong>{{ sourceIsPdf ? '来源原件' : '来源网页' }}</strong><span>{{ sourceDomain }}</span></div>
      <a :href="sourceUrl" target="_blank" rel="noopener noreferrer">{{ sourceIsPdf ? '打开来源 PDF' : '打开来源网页' }} ↗</a>
    </div>
    <div v-if="attachments.length" class="original-controls">
      <label v-if="attachments.length > 1">选择附件
        <el-select v-model="selectedId" aria-label="选择对照附件">
          <el-option v-for="file in attachments" :key="file.id" :value="file.id" :label="file.file_name" />
        </el-select>
      </label>
      <p v-else class="original-file-name">{{ activeFile?.file_name }}</p>
      <div class="original-file-actions">
        <a v-if="originalUrl" :href="originalUrl" target="_blank" rel="noopener noreferrer">新窗口查看原件</a>
        <el-button v-else disabled :loading="loading">新窗口查看原件</el-button>
        <el-button v-if="activeFile" link type="primary" @click="emit('download', activeFile)">下载附件</el-button>
        <a v-if="kind === 'pdf' && sourceUrl" :href="sourceUrl" target="_blank" rel="noopener noreferrer">来源链接 ↗</a>
      </div>
    </div>
    <el-skeleton v-if="loading" :rows="7" animated class="original-loading" />
    <div v-else-if="error" class="original-feedback" role="alert">
      <p>{{ error }}</p><el-button @click="loadOriginal">重试原件</el-button>
    </div>
    <template v-else-if="originalUrl && kind !== 'text'">
      <template v-if="kind === 'pdf'">
        <iframe :key="pageRequestKey || 0" :src="pdfSource" title="资料原始PDF（连续阅读）" class="original-pdf-frame" />
      </template>
      <a v-else :href="originalUrl" target="_blank" rel="noopener noreferrer" class="original-image"><img :src="originalUrl" :alt="activeFile?.file_name || '资料图片原件'"></a>
      <p class="original-help">{{ kind === 'pdf' ? '整份 PDF 连续滚动，使用阅读器工具栏缩放；也可在新窗口查看。' : '点击图片可在新窗口查看原件。' }}</p>
    </template>
    <div v-else-if="activeFile && kind === 'text' && canPreview" class="original-text-wrap">
      <div v-if="sourceUrl" class="web-source-notice">{{ attachments.some(isPdfAttachment) ? '当前查看文字附件，可切换到 PDF 原件核对。' : sourceIsPdf ? '当前为文字附件，可通过来源链接打开完整 PDF。' : '本条为网页资料，没有 PDF 附件。可打开来源网页核对。' }}</div>
      <p class="original-help">{{ reading.cleaned ? '正文阅读排版 · 收起网页导航与元信息，未校改数字和结论' : '文字附件 · 按保存内容显示' }}</p>
      <form class="original-text-search" @submit.prevent="findInText"><label for="original-text-find">查找正文</label><input id="original-text-find" v-model="findText" placeholder="输入关键词" @input="matchedParagraph = -1"><el-button native-type="submit" size="small">查找</el-button><span role="status">{{ findMessage }}</span></form>
      <article ref="readingBody" class="original-text" aria-label="原文正文阅读"><h4 v-if="reading.title">{{ reading.title }}</h4><p v-for="(paragraph, index) in reading.paragraphs" :key="index" :data-reading-match="index === matchedParagraph">{{ paragraph || '（空白文字附件）' }}</p></article>
      <details v-if="reading.cleaned" class="original-raw-copy"><summary>查看文字副本原始排版</summary><pre>{{ text }}</pre></details>
    </div>
    <p v-else class="original-feedback">{{ activeFile ? '此附件格式或大小不适合在线预览，请下载核对。' : sourceUrl ? '当前没有可预览附件，可打开来源页面核对；网页资料不一定有 PDF。' : '本条资料未提供可查看的原件附件或来源链接。' }}</p>
  </section>
</template>

<style scoped>
.record-original-panel{min-width:0;border:1px solid #dce4ec;border-radius:8px;background:#f8fafc;overflow:hidden;position:sticky;top:0;align-self:start}
header{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:16px;background:white;border-bottom:1px solid #dce4ec}
h3{font-size:15px;margin:0}header span{font-size:12px;color:#607386}
.original-source{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:14px 16px;padding:12px;background:#eef6f6;border-radius:6px;font-size:12px}
.original-source strong,.original-source span{display:block}.original-source span{margin-top:4px;color:#607386;overflow-wrap:anywhere}
a{color:#245de5;text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:underline}a:focus-visible{outline:2px solid #245de5;outline-offset:3px}
.original-controls{padding:0 16px 14px;font-size:13px}.original-controls label{display:grid;gap:6px}.original-file-name{overflow-wrap:anywhere;margin:0}
.original-file-actions{display:flex;align-items:center;flex-wrap:wrap;gap:16px;margin-top:10px}
.original-pdf-frame{display:block;width:100%;height:72vh;min-height:460px;border:0;background:#525659}
.pdf-original-panel>header{padding:12px 16px}.pdf-original-panel .original-controls{padding:10px 16px}.pdf-original-panel .original-file-name{font-size:12px}.pdf-original-panel .original-file-actions{margin-top:6px}
.original-page-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 16px;background:white;border-block:1px solid #dce4ec;font-size:12px;color:#607386}
.original-page-canvas{min-height:180px;max-height:65vh;overflow:auto;background:#e8edf3;padding:14px}.original-page-canvas img{display:block;width:100%;height:auto}.original-page-canvas a{display:block}
.original-image{display:block;max-height:70vh;overflow:auto;background:#e8edf3;padding:12px}.original-image img{display:block;max-width:100%;height:auto;margin:auto}
.original-text-wrap{padding:0 16px 16px}.original-text{font-family:inherit;font-size:13px;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere;max-height:65vh;overflow:auto;margin:0;padding:14px;background:#fff;border:1px solid #dce4ec;border-radius:5px}
.original-text{position:relative}.original-text h4{font-size:16px;line-height:1.7;margin:0 0 18px}.original-text p{margin:0 0 14px}.original-text p:last-child{margin-bottom:0}.original-text p[data-reading-match="true"]{background:#fff2c9;outline:2px solid #ead69c;outline-offset:3px}
.web-source-notice{font-size:12px;line-height:1.8;color:#526c7c;background:#edf3f7;border-radius:5px;padding:10px;margin-bottom:10px}
.original-text-search{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:12px;margin:12px 0}.original-text-search input{min-width:100px;flex:1;border:1px solid #dce4ec;border-radius:4px;padding:7px 9px;max-width:100%}.original-text-search span{font-size:11px;color:#607386}
.original-raw-copy{font-size:12px;margin-top:14px;color:#607386}.original-raw-copy summary{cursor:pointer;padding:9px 0}.original-raw-copy pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;line-height:1.8;font-family:inherit}
.original-help{color:#607386;font-size:12px;line-height:1.7;padding:0 16px}.original-text-wrap .original-help{padding:0}
.original-feedback{font-size:13px;line-height:1.8;margin:16px;color:#607386}.original-loading{padding:16px}
@media(max-width:980px){.record-original-panel{position:static}.original-page-canvas{max-height:58vh}}
@media(max-width:650px){header,.original-source{align-items:flex-start;flex-direction:column}.original-file-actions a,.original-source>a{min-height:36px;display:inline-flex;align-items:center}}
</style>
