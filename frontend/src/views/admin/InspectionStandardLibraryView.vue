<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { DocumentChecked, FolderOpened, MoreFilled, Plus, RefreshRight, Search, UploadFilled } from "@element-plus/icons-vue";
import { productMasterApi } from "@/api/product-master.api";
import { useInspectionStandardStore } from "@/stores/inspection_standard.store";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import { formatCodeName } from "@/utils/master-data-labels";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  ProductLine,
  ProductSku,
  StandardDocumentItem,
  StandardRetrieveHit,
} from "@/types/governance.types";

const store = useInspectionStandardStore();
const inspectionSpecStore = useInspectionSpecStore();

const drawerOpen = ref(false);
const detailOpen = ref(false);
const saving = ref(false);
const retrieveLoading = ref(false);
const editingId = ref("");
const currentLibrary = ref<InspectionStandardLibraryItem | null>(null);
const retrieveHits = ref<StandardRetrieveHit[]>([]);

const uploadFiles = ref<File[]>([]);
const uploading = ref(false);
const uploadDialogOpen = ref(false);
const uploadTargetId = ref("");

const chunkDrawerOpen = ref(false);
const currentDocumentForChunks = ref<StandardDocumentItem | null>(null);
const productLines = ref<ProductLine[]>([]);
const productSkus = ref<ProductSku[]>([]);

const editingDocumentId = ref("");
const docForm = reactive({
  standard_no: "",
  standard_name: "",
  domain: "",
  product_category: "",
  standard_level: "",
  standard_status: "",
});

const filters = reactive({
  domain: "",
  importStatus: "",
  keyword: "",
});

const form = reactive<InspectionStandardPayload>({
  name: "",
  product_family: "",
  inspection_spec_id: "",
  applicable_product_line_ids: [],
  applicable_product_sku_ids: [],
  domain: "",
  standard_status: "现行",
  chunk_strategy: "heading_then_size",
  is_active: true,
});

const retrieveForm = reactive({
  query: "陶瓷杯口沿裂纹是否合格",
  domain: "",
  productCategory: "",
  topK: 8,
});

const filteredItems = computed(() =>
  store.items.filter((item) => {
    const keyword = filters.keyword.trim().toLowerCase();
    const keywordMatched =
      !keyword ||
      [item.name, item.domain, item.description, item.spec_code, item.spec_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    return (
      keywordMatched &&
      (!filters.domain || item.domain === filters.domain) &&
      (!filters.importStatus || item.import_status === filters.importStatus)
    );
  }),
);

const domains = computed(() => Array.from(new Set(store.items.map((item) => item.domain).filter(Boolean))).sort());
const availableSpecs = computed(() => inspectionSpecStore.items.filter((item) => item.is_active));
const availableSkusForForm = computed(() =>
  productSkus.value.filter((item) => (form.applicable_product_line_ids || []).includes(item.product_line_id)),
);
const selectedSpec = computed(() => availableSpecs.value.find((item) => item.id === form.inspection_spec_id) || null);

function resetForm() {
  editingId.value = "";
  Object.assign(form, {
    name: "",
    product_family: "",
    inspection_spec_id: "",
    applicable_product_line_ids: [],
    applicable_product_sku_ids: [],
    domain: "",
    standard_status: "现行",
    chunk_strategy: "heading_then_size",
    is_active: true,
  });
}

function statusLabel(status: string) {
  return (
    {
      not_scanned: "未扫描",
      scanned: "已扫描",
      pending: "待导入",
      indexing: "导入中",
      completed: "已完成",
      partial_failed: "部分失败",
      failed: "失败",
    }[status] || status || "未扫描"
  );
}

function statusType(status: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "partial_failed") return "danger";
  if (status === "indexing" || status === "pending") return "warning";
  return "info";
}

async function loadProductMasterOptions() {
  const { data } = await productMasterApi.catalog(false);
  productLines.value = data.data.product_lines;
  productSkus.value = data.data.product_skus;
}

async function loadAll() {
  await Promise.all([
    store.fetchAll(),
    inspectionSpecStore.fetchAll(),
    loadProductMasterOptions(),
  ]);
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(item: InspectionStandardLibraryItem) {
  editingId.value = item.id;
  Object.assign(form, {
    name: item.name,
    product_family: item.product_family || "",
    inspection_spec_id: item.inspection_spec_id || "",
    applicable_product_line_ids: [...(item.applicable_product_line_ids || [])],
    applicable_product_sku_ids: [...(item.applicable_product_sku_ids || [])],
    domain: item.domain || "",
    standard_status: item.standard_status || "现行",
    chunk_strategy: item.chunk_strategy || "heading_then_size",
    is_active: item.is_active,
  });
  drawerOpen.value = true;
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写检测标准名称");
    return;
  }
  if (!String(form.inspection_spec_id || "").trim()) {
    ElMessage.warning("请先绑定质检门槛");
    return;
  }
  if (!String(form.product_family || "").trim()) {
    ElMessage.warning("请填写产品族");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      ...form,
      spec_code: selectedSpec.value?.spec_code || form.spec_code || null,
    };
    if (editingId.value) {
      await store.updateOne(editingId.value, payload);
      ElMessage.success("检测标准已更新");
    } else {
      await store.createOne(payload);
      ElMessage.success("检测标准已创建");
    }
    drawerOpen.value = false;
  } finally {
    saving.value = false;
  }
}

async function removeItem(item: InspectionStandardLibraryItem) {
  await ElMessageBox.confirm(`将删除检测标准“${item.name}”及其关联文档。`, "删除检测标准", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await store.removeOne(item.id);
  ElMessage.success("检测标准已删除");
}

async function indexLibrary(item: InspectionStandardLibraryItem, reindex = false) {
  const result = await store.indexOne(item.id, reindex);
  const action = reindex ? "重建索引" : "批量导入";
  ElMessage.success(`${action}完成，生成 ${result.chunk_count} 个 chunk`);
  if (currentLibrary.value?.id === item.id) await store.fetchDocuments(item.id);
}

function openUploadDialog(item: InspectionStandardLibraryItem) {
  uploadTargetId.value = item.id;
  uploadFiles.value = [];
  uploadDialogOpen.value = true;
}

function openUploadForCurrent() {
  if (currentLibrary.value) openUploadDialog(currentLibrary.value);
}

async function doUpload() {
  if (!uploadFiles.value.length) {
    ElMessage.warning("请选择 PDF 文件");
    return;
  }
  uploading.value = true;
  try {
    const result = await store.uploadOne(uploadTargetId.value, uploadFiles.value);
    ElMessage.success(`已上传 ${result.uploaded_count} 个文件，成功索引 ${result.indexed_count} 个`);
    uploadDialogOpen.value = false;
    if (currentLibrary.value?.id === uploadTargetId.value) await store.fetchDocuments(uploadTargetId.value);
  } finally {
    uploading.value = false;
  }
}

function handleRemoveUploadFile(index: number) {
  uploadFiles.value.splice(index, 1);
}

async function openDocuments(item: InspectionStandardLibraryItem) {
  currentLibrary.value = item;
  retrieveForm.domain = item.domain || "";
  retrieveForm.productCategory = item.product_family || "";
  detailOpen.value = true;
  retrieveHits.value = [];
  store.docPage = 1;
  await store.fetchDocuments(item.id);
}

async function retrieveStandards() {
  retrieveLoading.value = true;
  try {
    const result = await store.retrieve({
      query: retrieveForm.query,
      domain: retrieveForm.domain || null,
      product_category: retrieveForm.productCategory || null,
      top_k: retrieveForm.topK,
      only_active: true,
    });
    retrieveHits.value = result.hits;
    if (!result.hits.length) ElMessage.info("未召回标准条款");
  } finally {
    retrieveLoading.value = false;
  }
}

async function openChunks(doc: StandardDocumentItem) {
  currentDocumentForChunks.value = doc;
  chunkDrawerOpen.value = true;
  await store.fetchChunks(doc.id);
}

function startEditDocument(doc: StandardDocumentItem) {
  currentDocumentForChunks.value = doc;
  editingDocumentId.value = doc.id;
  Object.assign(docForm, {
    standard_no: doc.standard_no,
    standard_name: doc.standard_name,
    domain: doc.domain,
    product_category: doc.product_category || "",
    standard_level: doc.standard_level,
    standard_status: doc.standard_status,
  });
}

function cancelEditDocument() {
  editingDocumentId.value = "";
}

async function saveDocument(doc: StandardDocumentItem) {
  await store.updateDocument(doc.id, { ...docForm });
  editingDocumentId.value = "";
  ElMessage.success("文档已更新");
}

async function removeDocument(doc: StandardDocumentItem) {
  await ElMessageBox.confirm(`将删除标准文档“${doc.standard_no}”及其全部 chunk。`, "删除文档", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await store.removeDocument(doc.id);
  ElMessage.success("文档已删除");
}

function documentStatusType(row: StandardDocumentItem) {
  return statusType(row.import_status);
}

function onPageChange(newPage: number) {
  store.setPage(newPage);
}

function onDocPageChange(newPage: number) {
  if (currentLibrary.value) store.setDocPage(newPage, currentLibrary.value.id);
}

watch(
  () => form.applicable_product_line_ids,
  (lineIds) => {
    const allowedSkuIds = new Set(
      productSkus.value
        .filter((item) => (lineIds || []).includes(item.product_line_id))
        .map((item) => item.id),
    );
    form.applicable_product_sku_ids = (form.applicable_product_sku_ids || []).filter((item) => allowedSkuIds.has(item));
  },
);

watch(
  () => form.inspection_spec_id,
  () => {
    form.spec_code = selectedSpec.value?.spec_code || null;
  },
);

onMounted(loadAll);
</script>

<template>
  <div class="standard-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">Standards Library</p>
        <h2>检测标准库</h2>
        <p>管理标准文档、适用范围和质检门槛绑定。任务创建时只选检测标准，门槛在这里维护。</p>
      </div>
      <div class="heading-actions">
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建标准库</el-button>
      </div>
    </section>

    <section class="metric-strip">
      <div class="metric-item">
        <span>标准库</span>
        <strong>{{ store.metrics.libraries }}</strong>
      </div>
      <div class="metric-item">
        <span>PDF 文档</span>
        <strong>{{ store.metrics.pdfs }}</strong>
      </div>
      <div class="metric-item">
        <span>已索引 Chunk</span>
        <strong>{{ store.metrics.chunks }}</strong>
      </div>
      <div class="metric-item">
        <span>异常库</span>
        <strong>{{ store.metrics.failed }}</strong>
      </div>
    </section>

    <section class="toolbar">
      <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索名称、门槛编码、说明" class="keyword" />
      <el-select v-model="filters.domain" clearable placeholder="领域" class="filter-select">
        <el-option v-for="domain in domains" :key="domain" :label="domain" :value="domain" />
      </el-select>
      <el-select v-model="filters.importStatus" clearable placeholder="导入状态" class="filter-select">
        <el-option label="未扫描" value="not_scanned" />
        <el-option label="已扫描" value="scanned" />
        <el-option label="待导入" value="pending" />
        <el-option label="导入中" value="indexing" />
        <el-option label="已完成" value="completed" />
        <el-option label="部分失败" value="partial_failed" />
        <el-option label="失败" value="failed" />
      </el-select>
    </section>

    <section class="table-surface">
      <el-table :data="filteredItems" v-loading="store.loading" row-key="id">
        <el-table-column label="检测标准" min-width="220">
          <template #default="{ row }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span>{{ row.domain || "未设领域" }} · {{ row.product_family || "未设产品族" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="质检门槛" min-width="180">
          <template #default="{ row }">
            <el-tag :type="row.has_quality_threshold ? 'success' : 'warning'" effect="plain">
              {{ row.has_quality_threshold ? (row.spec_code || row.spec_name || "已绑定") : "未绑定门槛" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="domain" label="领域" width="120" />
        <el-table-column label="RAG 空间" min-width="190">
          <template #default="{ row }">
            <div class="tag-line">
              <el-tag v-for="space in row.rag_spaces" :key="space.id" effect="plain">{{ space.name }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="PDF / 文档 / Chunk" width="160">
          <template #default="{ row }">{{ row.pdf_count }} / {{ row.document_count }} / {{ row.chunk_count }}</template>
        </el-table-column>
        <el-table-column label="导入状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.import_status)">{{ statusLabel(row.import_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近索引" width="180">
          <template #default="{ row }">{{ row.last_indexed_at || row.last_scanned_at || "未执行" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link :icon="FolderOpened" @click="openDocuments(row)">文档</el-button>
            <el-button link type="primary" :icon="UploadFilled" @click="openUploadDialog(row)">上传</el-button>
            <el-dropdown
              trigger="click"
              @command="
                (cmd: string) => {
                  if (cmd === 'reindex') indexLibrary(row, true);
                  else if (cmd === 'edit') openEdit(row);
                  else if (cmd === 'delete') removeItem(row);
                }
              "
            >
              <el-button link :icon="MoreFilled">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="reindex">重建索引</el-dropdown-item>
                  <el-dropdown-item command="edit">编辑</el-dropdown-item>
                  <el-dropdown-item command="delete" style="color: var(--el-color-danger)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-row">
        <el-pagination
          v-model:current-page="store.page"
          v-model:page-size="store.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="store.total"
          layout="total, sizes, prev, pager, next"
          @size-change="store.setSize($event)"
          @current-change="onPageChange"
        />
      </div>
    </section>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑检测标准' : '新建检测标准'" size="560px">
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="检测标准名称" required>
          <el-input v-model="form.name" placeholder="如：陶瓷产品检测标准" />
          <div class="form-hint">会自动创建同名 RAG 空间。任务创建时用户只选择检测标准。</div>
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="绑定质检门槛" required>
            <el-select v-model="form.inspection_spec_id" filterable clearable placeholder="选择质检门槛">
              <el-option
                v-for="spec in availableSpecs"
                :key="spec.id"
                :label="`${spec.spec_code} · ${spec.name}`"
                :value="spec.id"
              />
            </el-select>
            <div v-if="selectedSpec" class="threshold-summary">
              <span>编码 {{ selectedSpec.spec_code }}</span>
              <span>图片 {{ selectedSpec.required_image_count }}</span>
              <span>视角 {{ selectedSpec.required_views?.join("、") || "未设置" }}</span>
              <span>置信 {{ selectedSpec.ai_gate_confidence_threshold }}</span>
              <span>证据 {{ selectedSpec.ai_gate_evidence_threshold }}</span>
              <span>追溯 {{ selectedSpec.ai_gate_traceability_threshold }}</span>
              <span>{{ selectedSpec.auto_pass_enabled ? "自动放行开启" : "自动放行关闭" }}</span>
            </div>
          </el-form-item>
          <el-form-item label="产品族" required>
            <el-input v-model="form.product_family" placeholder="如：screw / bottle / tile" />
          </el-form-item>
          <el-form-item label="领域">
            <el-select v-model="form.domain" allow-create filterable clearable default-first-option placeholder="选择或输入领域">
              <el-option label="日用陶瓷" value="日用陶瓷" />
              <el-option label="包装印刷" value="包装印刷" />
              <el-option label="包装材料" value="包装材料" />
              <el-option label="纺织服装" value="纺织服装" />
              <el-option label="家具木制品" value="家具木制品" />
              <el-option label="通用质检" value="通用质检" />
            </el-select>
          </el-form-item>
          <el-form-item label="标准状态">
            <el-select v-model="form.standard_status">
              <el-option label="现行" value="现行" />
              <el-option label="即将实施" value="即将实施" />
              <el-option label="被代替" value="被代替" />
              <el-option label="废止" value="废止" />
            </el-select>
          </el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="适用产品线">
            <el-select v-model="form.applicable_product_line_ids" multiple filterable clearable placeholder="不选则默认不限">
              <el-option v-for="line in productLines" :key="line.id" :label="formatCodeName(line)" :value="line.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="适用 SKU">
            <el-select v-model="form.applicable_product_sku_ids" multiple filterable clearable placeholder="优先按 SKU 精确适配">
              <el-option v-for="sku in availableSkusForForm" :key="sku.id" :label="formatCodeName(sku)" :value="sku.id" />
            </el-select>
          </el-form-item>
        </div>
        <el-collapse v-if="editingId">
          <el-collapse-item title="高级设置">
            <div class="form-grid">
              <el-form-item label="Chunk 策略">
                <el-select v-model="form.chunk_strategy">
                  <el-option label="标题优先，长度兜底" value="heading_then_size" />
                  <el-option label="按页码" value="page" />
                  <el-option label="固定长度" value="fixed_size" />
                </el-select>
              </el-form-item>
              <el-form-item label="启用状态">
                <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
              </el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          {{ editingId ? "保存" : "创建检测标准" }}
        </el-button>
      </template>
    </el-drawer>

    <el-dialog v-model="uploadDialogOpen" title="上传 PDF 文件" width="520px">
      <el-upload
        drag
        multiple
        :auto-upload="false"
        :on-change="(_file: any, _files: any) => (uploadFiles = _files.map((f: any) => f.raw))"
        accept=".pdf"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将 PDF 文件拖到此处，或<em>点击选择</em></div>
        <template #tip>
          <div class="upload-tip">支持多文件上传，上传后自动解析并建立索引</div>
        </template>
      </el-upload>
      <div v-if="uploadFiles.length" class="upload-file-list">
        <el-tag v-for="(f, i) in uploadFiles" :key="i" closable @close="handleRemoveUploadFile(i)">
          {{ f.name }}
        </el-tag>
      </div>

      <template #footer>
        <el-button @click="uploadDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">
          上传并索引（{{ uploadFiles.length }} 个文件）
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailOpen" :title="currentLibrary?.name || '标准库文档'" size="760px">
      <div class="detail-stack">
        <section class="detail-toolbar">
          <el-button :icon="RefreshRight" @click="currentLibrary && store.fetchDocuments(currentLibrary.id)">刷新文档</el-button>
          <el-button :icon="UploadFilled" type="primary" @click="openUploadForCurrent">上传 PDF</el-button>
        </section>

        <el-table :data="store.documents" v-loading="store.documentLoading" row-key="id" max-height="320">
          <el-table-column label="标准文档" min-width="220">
            <template #default="{ row }">
              <div class="primary-cell">
                <strong>{{ row.standard_no }}</strong>
                <span>{{ row.standard_name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="file_name" label="文件名" min-width="180" />
          <el-table-column label="页 / Chunk" width="110">
            <template #default="{ row }">{{ row.page_count || 0 }} / {{ row.chunk_count }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="documentStatusType(row)">{{ statusLabel(row.import_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link @click="openChunks(row)">Chunks</el-button>
              <el-button link @click="startEditDocument(row)">编辑</el-button>
              <el-button link type="danger" @click="removeDocument(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="editingDocumentId" class="inline-edit-card">
          <el-form label-position="top" class="form-grid-3">
            <el-form-item label="标准号">
              <el-input v-model="docForm.standard_no" />
            </el-form-item>
            <el-form-item label="标准名称">
              <el-input v-model="docForm.standard_name" />
            </el-form-item>
            <el-form-item label="领域">
              <el-input v-model="docForm.domain" />
            </el-form-item>
            <el-form-item label="产品类别">
              <el-input v-model="docForm.product_category" />
            </el-form-item>
            <el-form-item label="标准级别">
              <el-select v-model="docForm.standard_level">
                <el-option label="GB" value="GB" />
                <el-option label="GB/T" value="GB/T" />
                <el-option label="GB/Z" value="GB/Z" />
              </el-select>
            </el-form-item>
            <el-form-item label="标准状态">
              <el-select v-model="docForm.standard_status">
                <el-option label="现行" value="现行" />
                <el-option label="即将实施" value="即将实施" />
                <el-option label="被代替" value="被代替" />
                <el-option label="废止" value="废止" />
              </el-select>
            </el-form-item>
          </el-form>
          <div class="inline-edit-actions">
            <el-button @click="cancelEditDocument">取消</el-button>
            <el-button type="primary" @click="currentDocumentForChunks && saveDocument(currentDocumentForChunks)">保存</el-button>
          </div>
        </div>

        <div class="pagination-row">
          <el-pagination
            v-model:current-page="store.docPage"
            :page-size="store.docSize"
            :total="store.docTotal"
            layout="total, prev, pager, next"
            small
            @current-change="onDocPageChange"
          />
        </div>

        <section class="retrieve-panel">
          <div class="retrieve-grid">
            <el-input v-model="retrieveForm.query" :prefix-icon="Search" placeholder="输入标准检索问题" />
            <el-input v-model="retrieveForm.domain" placeholder="领域" />
            <el-input v-model="retrieveForm.productCategory" placeholder="产品类别" />
            <el-input-number v-model="retrieveForm.topK" :min="1" :max="20" controls-position="right" />
            <el-button type="primary" :icon="DocumentChecked" :loading="retrieveLoading" @click="retrieveStandards">测试检索</el-button>
          </div>
          <div v-if="retrieveHits.length" class="hit-list">
            <article v-for="hit in retrieveHits" :key="hit.id" class="hit-item">
              <header>
                <strong>{{ hit.standard_no || hit.source }}</strong>
                <el-tag effect="plain">score {{ hit.score.toFixed(3) }}</el-tag>
              </header>
              <p>{{ hit.quote }}</p>
              <footer>{{ hit.standard_name }} · 第{{ hit.page_number || "-" }}页 · 第{{ hit.chunk_index || "-" }}段</footer>
            </article>
          </div>
        </section>
      </div>
    </el-drawer>

    <el-drawer v-model="chunkDrawerOpen" :title="`${currentDocumentForChunks?.standard_no || ''} Chunks`" size="800px">
      <div class="detail-stack">
        <div v-if="currentDocumentForChunks" class="primary-cell" style="margin-bottom: 12px">
          <strong>{{ currentDocumentForChunks.standard_no }}</strong>
          <span>{{ currentDocumentForChunks.standard_name }} · {{ currentDocumentForChunks.file_name }}</span>
        </div>
        <el-table :data="store.chunks" v-loading="store.chunkLoading" row-key="id" max-height="520">
          <el-table-column label="#" width="60">
            <template #default="{ row }">{{ row.chunk_index }}</template>
          </el-table-column>
          <el-table-column prop="section_title" label="章节" width="200" />
          <el-table-column label="页码" width="80">
            <template #default="{ row }">{{ row.page_from || "-" }}</template>
          </el-table-column>
          <el-table-column label="文本预览" min-width="300">
            <template #default="{ row }">{{ (row.chunk_text || "").slice(0, 200) }}{{ (row.chunk_text || "").length > 200 ? "..." : "" }}</template>
          </el-table-column>
          <el-table-column label="Token" width="80">
            <template #default="{ row }">{{ row.token_count || 0 }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.standard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-heading,
.toolbar,
.table-surface,
.retrieve-panel {
  border: 1px solid oklch(90% 0.01 250);
  border-radius: 8px;
  background: oklch(99% 0.004 250);
}

.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  padding: 18px 20px;
}

.eyebrow {
  margin: 0 0 4px;
  color: oklch(45% 0.04 250);
  font-size: 12px;
  font-weight: 700;
}

.page-heading h2 {
  margin: 0;
  color: oklch(22% 0.018 250);
  font-size: 22px;
  font-weight: 700;
}

.page-heading p:last-child {
  margin: 6px 0 0;
  color: oklch(46% 0.018 250);
}

.heading-actions,
.toolbar,
.tag-line,
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid oklch(90% 0.01 250);
  border-radius: 8px;
  overflow: hidden;
  background: oklch(98.5% 0.005 250);
}

.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 54px;
  padding: 12px 16px;
  border-right: 1px solid oklch(90% 0.01 250);
}

.metric-item:last-child {
  border-right: 0;
}

.metric-item span {
  color: oklch(46% 0.018 250);
  font-size: 13px;
}

.metric-item strong {
  color: oklch(24% 0.02 250);
  font-size: 22px;
}

.toolbar {
  padding: 12px;
}

.keyword {
  width: 320px;
}

.filter-select {
  width: 180px;
}

.table-surface {
  padding: 8px 12px 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 4px;
}

.primary-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.primary-cell strong {
  color: oklch(24% 0.02 250);
}

.primary-cell span {
  color: oklch(52% 0.018 250);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.drawer-form,
.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.form-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: oklch(55% 0.02 250);
}

.threshold-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.threshold-summary span {
  padding: 2px 7px;
  border: 1px solid oklch(86% 0.018 250);
  border-radius: 6px;
  background: oklch(98% 0.006 250);
  color: oklch(39% 0.024 250);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.inline-edit-card {
  border: 1px solid oklch(90% 0.01 250);
  border-radius: 8px;
  padding: 14px;
  background: oklch(100% 0.003 250);
}

.inline-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}

.detail-toolbar {
  justify-content: flex-end;
}

.retrieve-panel {
  padding: 14px;
}

.retrieve-grid {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) minmax(120px, 1fr) minmax(120px, 1fr) 96px auto;
  gap: 10px;
  align-items: center;
}

.upload-icon {
  font-size: 2.5rem;
  color: oklch(55% 0.04 250);
}

.upload-text {
  margin-top: 8px;
  font-size: 14px;
  color: oklch(46% 0.018 250);
}

.upload-text em {
  color: var(--el-color-primary);
  font-style: normal;
}

.upload-tip {
  font-size: 12px;
  color: oklch(55% 0.02 250);
}

.upload-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.hit-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.hit-item {
  border: 1px solid oklch(90% 0.01 250);
  border-radius: 8px;
  padding: 12px;
  background: oklch(100% 0.003 250);
}

.hit-item header,
.hit-item footer {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.hit-item p {
  margin: 8px 0;
  color: oklch(34% 0.02 250);
  line-height: 1.6;
}

.hit-item footer {
  color: oklch(52% 0.018 250);
  font-size: 12px;
}

@media (max-width: 960px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-strip,
  .form-grid,
  .form-grid-3,
  .retrieve-grid {
    grid-template-columns: 1fr;
  }

  .metric-item {
    border-right: 0;
    border-bottom: 1px solid oklch(90% 0.01 250);
  }

  .metric-item:last-child {
    border-bottom: 0;
  }

  .keyword,
  .filter-select {
    width: 100%;
  }
}
</style>
