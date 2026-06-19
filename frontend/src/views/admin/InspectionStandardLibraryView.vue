<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { DocumentChecked, FolderOpened, Plus, RefreshRight, Search, UploadFilled } from "@element-plus/icons-vue";
import { ragSpaceApi } from "@/api/rag-space.api";
import { useInspectionStandardStore } from "@/stores/inspection_standard.store";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  StandardDocumentChunkItem,
  StandardDocumentItem,
  StandardRetrieveHit,
} from "@/types/governance.types";
import type { RagSpace } from "@/types/rag-space.types";

const store = useInspectionStandardStore();
const ragSpaces = ref<RagSpace[]>([]);
const drawerOpen = ref(false);
const detailOpen = ref(false);
const saving = ref(false);
const retrieveLoading = ref(false);
const editingId = ref("");
const currentLibrary = ref<InspectionStandardLibraryItem | null>(null);
const retrieveHits = ref<StandardRetrieveHit[]>([]);

// Chunk drill-down state
const chunkDrawerOpen = ref(false);
const currentDocumentForChunks = ref<StandardDocumentItem | null>(null);

// Document editing state
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
  productCategory: "",
  importStatus: "",
  standardStatus: "",
  keyword: "",
});

const form = reactive<InspectionStandardPayload>({
  name: "",
  product_family: "",
  domain: "",
  product_category: "",
  standard_status: "现行",
  rag_space_ids: [],
  qdrant_collection: "",
  pdf_root_dir: "standard/current",
  file_glob: "*.pdf",
  chunk_strategy: "heading_then_size",
  import_mode: "scan_and_index",
  auto_reindex: false,
  description: "",
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
      [item.name, item.domain, item.product_category, item.pdf_root_dir, item.description]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    return (
      keywordMatched &&
      (!filters.domain || item.domain === filters.domain) &&
      (!filters.productCategory || item.product_category === filters.productCategory) &&
      (!filters.importStatus || item.import_status === filters.importStatus) &&
      (!filters.standardStatus || item.standard_status === filters.standardStatus)
    );
  }),
);

const domains = computed(() => Array.from(new Set(store.items.map((item) => item.domain).filter(Boolean))).sort());
const productCategories = computed(() =>
  Array.from(new Set(store.items.map((item) => item.product_category).filter(Boolean))).sort(),
);

function resetForm() {
  editingId.value = "";
  Object.assign(form, {
    name: "",
    product_family: "",
    domain: "",
    product_category: "",
    standard_status: "现行",
    rag_space_ids: [],
    qdrant_collection: "",
    pdf_root_dir: "standard/current",
    file_glob: "*.pdf",
    chunk_strategy: "heading_then_size",
    import_mode: "scan_and_index",
    auto_reindex: false,
    description: "",
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

function isActionLoading(action: string, id: string) {
  return store.actionLoading === `${action}:${id}`;
}

async function loadAll() {
  const [{ data: spaces }] = await Promise.all([ragSpaceApi.list(500), store.fetchAll()]);
  ragSpaces.value = spaces.data;
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(item: InspectionStandardLibraryItem) {
  editingId.value = item.id;
  Object.assign(form, {
    name: item.name,
    product_family: item.product_family,
    domain: item.domain || "",
    product_category: item.product_category || "",
    standard_status: item.standard_status || "现行",
    rag_space_ids: [...item.rag_space_ids],
    qdrant_collection: item.qdrant_collection || "",
    pdf_root_dir: item.pdf_root_dir || "standard/current",
    file_glob: item.file_glob || "*.pdf",
    chunk_strategy: item.chunk_strategy || "heading_then_size",
    import_mode: "scan_and_index",
    auto_reindex: item.auto_reindex,
    description: item.description || "",
    is_active: item.is_active,
  });
  drawerOpen.value = true;
}

async function submit({ scanAfterSave = false } = {}) {
  saving.value = true;
  try {
    const payload = {
      ...form,
      product_family: form.product_family || form.product_category || form.domain || form.name,
    };
    const saved = editingId.value ? await store.updateOne(editingId.value, payload) : await store.createOne(payload);
    if (scanAfterSave) {
      await store.scanOne(saved.id);
      ElMessage.success("标准库已保存并完成 PDF 扫描");
    } else {
      ElMessage.success(editingId.value ? "标准库已更新" : "标准库已创建");
    }
    drawerOpen.value = false;
  } finally {
    saving.value = false;
  }
}

async function removeItem(item: InspectionStandardLibraryItem) {
  await ElMessageBox.confirm(`将删除"${item.name}"，标准文档记录也将不再出现在列表中。`, "删除标准库", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await store.removeOne(item.id);
  ElMessage.success("标准库已删除");
}

async function scanLibrary(item: InspectionStandardLibraryItem) {
  const result = await store.scanOne(item.id);
  ElMessage.success(`扫描完成：${result.scanned_count} 个 PDF`);
  if (currentLibrary.value?.id === item.id) await store.fetchDocuments(item.id);
}

async function indexLibrary(item: InspectionStandardLibraryItem, reindex = false) {
  const result = await store.indexOne(item.id, reindex);
  const action = reindex ? "重建索引" : "批量导入";
  ElMessage.success(`${action}完成：${result.chunk_count} 个 chunk，失败 ${result.failed_count} 个`);
  if (currentLibrary.value?.id === item.id) await store.fetchDocuments(item.id);
}

async function openDocuments(item: InspectionStandardLibraryItem) {
  currentLibrary.value = item;
  retrieveForm.domain = item.domain || "";
  retrieveForm.productCategory = item.product_category || "";
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

// Chunk drill-down
async function openChunks(doc: StandardDocumentItem) {
  currentDocumentForChunks.value = doc;
  chunkDrawerOpen.value = true;
  await store.fetchChunks(doc.id);
}

// Document editing
function startEditDocument(doc: StandardDocumentItem) {
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
  await ElMessageBox.confirm(`将删除标准文档"${doc.standard_no}"及其所有 chunk 记录。`, "删除文档", {
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

onMounted(loadAll);
</script>

<template>
  <div class="standard-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">Standards Library</p>
        <h2>检测标准库</h2>
        <p>管理国家标准 PDF、标准元数据和 RAG 索引。</p>
      </div>
      <div class="heading-actions">
        <el-button :icon="RefreshRight" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增标准库</el-button>
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
        <span>已索引 chunk</span>
        <strong>{{ store.metrics.chunks }}</strong>
      </div>
      <div class="metric-item">
        <span>异常库</span>
        <strong>{{ store.metrics.failed }}</strong>
      </div>
    </section>

    <section class="toolbar">
      <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索名称、目录、说明" class="keyword" />
      <el-select v-model="filters.domain" clearable placeholder="领域" class="filter-select">
        <el-option v-for="domain in domains" :key="domain" :label="domain" :value="domain" />
      </el-select>
      <el-select v-model="filters.productCategory" clearable placeholder="产品类别" class="filter-select">
        <el-option v-for="category in productCategories" :key="category" :label="category" :value="category" />
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
      <el-select v-model="filters.standardStatus" clearable placeholder="标准状态" class="filter-select">
        <el-option label="现行" value="现行" />
        <el-option label="即将实施" value="即将实施" />
        <el-option label="被代替" value="被代替" />
        <el-option label="废止" value="废止" />
      </el-select>
    </section>

    <section class="table-surface">
      <el-table :data="filteredItems" v-loading="store.loading" row-key="id">
        <el-table-column label="标准库" min-width="220">
          <template #default="{ row }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span>{{ row.pdf_root_dir || "未配置 PDF 目录" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="domain" label="领域" width="120" />
        <el-table-column prop="product_category" label="产品类别" width="140" />
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
        <el-table-column label="操作" width="360" fixed="right">
          <template #default="{ row }">
            <el-button link :icon="FolderOpened" @click="openDocuments(row)">文档</el-button>
            <el-button link :loading="isActionLoading('scan', row.id)" @click="scanLibrary(row)">扫描</el-button>
            <el-button link type="primary" :loading="isActionLoading('index', row.id)" @click="indexLibrary(row)">导入</el-button>
            <el-button link type="warning" :loading="isActionLoading('reindex', row.id)" @click="indexLibrary(row, true)">重建</el-button>
            <el-button link @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="removeItem(row)">删除</el-button>
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

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑标准库' : '新增标准库'" size="680px">
      <el-form label-position="top" class="drawer-form">
        <el-form-item label="标准库名称">
          <el-input v-model="form.name" placeholder="如：陶瓷产品标准库" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="领域">
            <el-select v-model="form.domain" allow-create filterable default-first-option placeholder="选择或输入领域">
              <el-option label="日用陶瓷" value="日用陶瓷" />
              <el-option label="包装印刷" value="包装印刷" />
              <el-option label="包装材料" value="包装材料" />
              <el-option label="纺织服装" value="纺织服装" />
              <el-option label="家具木制品" value="家具木制品" />
              <el-option label="通用质检" value="通用质检" />
            </el-select>
          </el-form-item>
          <el-form-item label="产品类别">
            <el-input v-model="form.product_category" placeholder="如：日用瓷器、针织T恤衫" />
          </el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="标准状态">
            <el-select v-model="form.standard_status">
              <el-option label="现行" value="现行" />
              <el-option label="即将实施" value="即将实施" />
              <el-option label="被代替" value="被代替" />
              <el-option label="废止" value="废止" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
          </el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="导入模式">
            <el-select v-model="form.import_mode">
              <el-option label="仅绑定空间" value="bind_only" />
              <el-option label="扫描目录" value="scan_only" />
              <el-option label="扫描并索引" value="scan_and_index" />
            </el-select>
          </el-form-item>
          <el-form-item label="自动重建索引">
            <el-switch v-model="form.auto_reindex" active-text="开启" inactive-text="关闭" />
          </el-form-item>
        </div>
        <el-form-item label="关联 RAG 空间">
          <el-select v-model="form.rag_space_ids" multiple filterable placeholder="选择一个或多个知识库空间" class="full-width">
            <el-option v-for="space in ragSpaces" :key="space.id" :label="space.name" :value="space.id" />
          </el-select>
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="PDF 根目录">
            <el-input v-model="form.pdf_root_dir" placeholder="standard/current/ceramic" />
          </el-form-item>
          <el-form-item label="文件匹配规则">
            <el-input v-model="form.file_glob" placeholder="*.pdf" />
          </el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="Chunk 策略">
            <el-select v-model="form.chunk_strategy">
              <el-option label="标题优先，长度兜底" value="heading_then_size" />
              <el-option label="按页码" value="page" />
              <el-option label="固定长度" value="fixed_size" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="Qdrant collection">
          <el-input v-model="form.qdrant_collection" placeholder="默认使用系统配置 collection" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="记录该标准库覆盖的国家标准范围" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button :loading="saving" @click="submit()">保存</el-button>
        <el-button type="primary" :loading="saving" @click="submit({ scanAfterSave: true })">保存并扫描 PDF</el-button>
      </template>
    </el-drawer>

    <el-drawer v-model="detailOpen" :title="currentLibrary?.name || '标准库文档'" size="760px">
      <div class="detail-stack">
        <section class="detail-toolbar">
          <el-button :icon="RefreshRight" @click="currentLibrary && store.fetchDocuments(currentLibrary.id)">刷新文档</el-button>
          <el-button :icon="UploadFilled" type="primary" @click="currentLibrary && indexLibrary(currentLibrary)">批量导入</el-button>
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

        <!-- Inline document edit row -->
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
            <el-button type="primary" @click="saveDocument(currentDocumentForChunks!)">保存</el-button>
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

    <!-- Chunk drill-down drawer -->
    <el-drawer v-model="chunkDrawerOpen" :title="currentDocumentForChunks?.standard_no + ' Chunks'" size="800px">
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
            <template #default="{ row }">{{ (row.chunk_text || "").slice(0, 200) }}{{ (row.chunk_text || "").length > 200 ? "…" : "" }}</template>
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

.full-width {
  width: 100%;
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
