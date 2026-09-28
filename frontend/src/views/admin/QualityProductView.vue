<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus, RefreshRight } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useQualityReferenceStore } from "@/stores/quality-reference.store";
import type { ProductCategoryV4, QualityProduct } from "@/types/quality-risk.types";

const refs = useQualityReferenceStore();
const loading = ref(false);
const drawer = ref(false);
const mode = ref<"category" | "product">("category");
const editingId = ref("");
const identifiers = ref<Array<{ identifier_type: string; identifier_value: string }>>([]);
const categoryForm = reactive({ code: "", name: "", parent_id: "", description: "", is_active: true });
const productForm = reactive({ category_id: "", name: "", model: "", brand: "", manufacturer_enterprise_id: "", attributesText: "{}", is_active: true });

const title = computed(() => `${editingId.value ? "编辑" : "新增"}${mode.value === "category" ? "产品类别" : "具体产品 / 型号"}`);

async function load() {
  loading.value = true;
  try { await refs.loadProducts(true); } finally { loading.value = false; }
}
function reset() { editingId.value=""; identifiers.value=[]; Object.assign(categoryForm,{code:"",name:"",parent_id:"",description:"",is_active:true}); Object.assign(productForm,{category_id:refs.categories[0]?.id||"",name:"",model:"",brand:"",manufacturer_enterprise_id:"",attributesText:"{}",is_active:true}); }
function create(kind:"category"|"product") { reset(); mode.value=kind; drawer.value=true; }
function editCategory(row:ProductCategoryV4){ reset(); mode.value="category"; editingId.value=row.id; Object.assign(categoryForm,{code:row.code,name:row.name,parent_id:row.parent_id||"",description:row.description||"",is_active:row.is_active}); drawer.value=true; }
function editProduct(row:QualityProduct){ reset(); mode.value="product"; editingId.value=row.id; identifiers.value=row.identifiers.map(x=>({identifier_type:x.identifier_type,identifier_value:x.identifier_value})); Object.assign(productForm,{category_id:row.category_id,name:row.name,model:row.model||"",brand:row.brand||"",manufacturer_enterprise_id:row.manufacturer_enterprise_id||"",attributesText:JSON.stringify(row.attributes||{},null,2),is_active:row.is_active}); drawer.value=true; }
function addIdentifier(){ identifiers.value.push({identifier_type:"model_code",identifier_value:""}); }
async function save(){
  if(mode.value==="category"){
    if(!categoryForm.code.trim()||!categoryForm.name.trim()){ElMessage.warning("请填写类别编码和名称");return;}
    const payload={...categoryForm,parent_id:categoryForm.parent_id||null};
    if(editingId.value) await qualityRiskApi.updateCategory(editingId.value,payload); else await qualityRiskApi.createCategory(payload);
  }else{
    if(!productForm.category_id||!productForm.name.trim()){ElMessage.warning("请选择类别并填写产品名称");return;}
    let attributes={}; try{attributes=JSON.parse(productForm.attributesText||"{}");}catch{ElMessage.warning("扩展属性必须是JSON对象");return;}
    const payload={category_id:productForm.category_id,name:productForm.name,model:productForm.model||null,brand:productForm.brand||null,manufacturer_enterprise_id:productForm.manufacturer_enterprise_id||null,attributes,identifiers:identifiers.value.filter(x=>x.identifier_value.trim()),is_active:productForm.is_active};
    if(editingId.value) await qualityRiskApi.updateProduct(editingId.value,payload); else await qualityRiskApi.createProduct(payload);
  }
  refs.invalidate("products"); drawer.value=false; ElMessage.success("产品主数据已保存"); await load();
}
onMounted(load);
</script>
<template>
  <main class="product-page">
    <header class="product-hero"><div><p>QUALITY PRODUCT REFERENCE</p><h1>产品类别与具体产品</h1><span>以产品类别支撑广域风险分析；品牌、型号和外部SKU只在来源明确时补充。</span></div><div><el-button :icon="RefreshRight" @click="load">刷新</el-button><el-button :icon="Plus" @click="create('category')">新增类别</el-button><el-button type="primary" :icon="Plus" @click="create('product')">新增具体产品</el-button></div></header>
    <el-alert type="info" :closable="false" title="生产批次和单件序列号不属于产品主数据；它们只随投诉、报告、抽查或实物样品按来源记录。" />
    <div class="catalog-grid" v-loading="loading">
      <section><header><small>01 / CATEGORY</small><h2>产品类别</h2></header><el-table :data="refs.categories" @row-dblclick="editCategory"><el-table-column prop="code" label="编码" width="130"/><el-table-column prop="name" label="类别" min-width="180"/><el-table-column label="状态" width="90"><template #default="{row}"><el-tag :type="row.is_active?'success':'info'">{{row.is_active?'启用':'停用'}}</el-tag></template></el-table-column><el-table-column width="80"><template #default="{row}"><el-button link @click="editCategory(row)">编辑</el-button></template></el-table-column></el-table></section>
      <section><header><small>02 / PRODUCT</small><h2>具体产品 / 型号</h2></header><el-table :data="refs.products" @row-dblclick="editProduct"><el-table-column prop="category_name" label="类别" min-width="130"/><el-table-column label="产品" min-width="220"><template #default="{row}"><strong>{{row.name}}</strong><span class="subline">{{[row.brand,row.model].filter(Boolean).join(' · ')||'未提供品牌或型号'}}</span></template></el-table-column><el-table-column label="外部标识" min-width="160"><template #default="{row}">{{row.identifiers.map((x:any)=>x.identifier_value).join('、')||'无'}}</template></el-table-column><el-table-column width="80"><template #default="{row}"><el-button link @click="editProduct(row)">编辑</el-button></template></el-table-column></el-table></section>
    </div>
    <el-drawer v-model="drawer" :title="title" size="min(600px,96vw)" :close-on-click-modal="false">
      <el-form v-if="mode==='category'" label-position="top"><el-form-item label="类别编码" required><el-input v-model="categoryForm.code" :disabled="!!editingId"/></el-form-item><el-form-item label="类别名称" required><el-input v-model="categoryForm.name"/></el-form-item><el-form-item label="上级类别"><el-select v-model="categoryForm.parent_id" clearable><el-option v-for="item in refs.categories.filter(x=>x.id!==editingId)" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item><el-form-item label="说明"><el-input v-model="categoryForm.description" type="textarea" :rows="3"/></el-form-item><el-switch v-model="categoryForm.is_active" active-text="启用" inactive-text="停用"/></el-form>
      <el-form v-else label-position="top"><el-form-item label="产品类别" required><el-select v-model="productForm.category_id"><el-option v-for="item in refs.categories" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item><el-form-item label="产品名称" required><el-input v-model="productForm.name"/></el-form-item><div class="form-grid"><el-form-item label="品牌（选填）"><el-input v-model="productForm.brand"/></el-form-item><el-form-item label="型号（选填）"><el-input v-model="productForm.model"/></el-form-item></div><el-form-item label="扩展属性"><el-input v-model="productForm.attributesText" type="textarea" :rows="4"/></el-form-item><div class="identifier-head"><strong>外部标识（选填）</strong><el-button size="small" @click="addIdentifier">添加</el-button></div><div v-for="(item,index) in identifiers" :key="index" class="identifier-row"><el-select v-model="item.identifier_type"><el-option label="型号代码" value="model_code"/><el-option label="来源SKU" value="sku"/><el-option label="条码" value="barcode"/><el-option label="来源产品编号" value="source_product_id"/></el-select><el-input v-model="item.identifier_value"/><el-button text type="danger" @click="identifiers.splice(index,1)">移除</el-button></div><el-switch v-model="productForm.is_active" active-text="启用" inactive-text="停用"/></el-form>
      <template #footer><el-button @click="drawer=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-drawer>
  </main>
</template>
<style scoped>
.product-page{min-height:100%;padding:22px;background:linear-gradient(180deg,#f3f9fc,#fbfcfd);color:#142f43}.product-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:16px;padding:28px 30px;border:1px solid #b8d8e8;border-radius:18px;background:linear-gradient(125deg,#e7f5fb,#fff 65%,#eef9f5)}.product-hero p,section small{margin:0 0 8px;color:#0a6b91;font:700 11px ui-monospace,monospace;letter-spacing:.14em}.product-hero h1{margin:0;font-size:36px;letter-spacing:-.035em}.product-hero span{display:block;margin-top:10px;color:#587183}.product-hero>div:last-child{display:flex;gap:8px;flex-wrap:wrap}.el-alert{margin-bottom:16px}.catalog-grid{display:grid;grid-template-columns:minmax(340px,.7fr) minmax(520px,1.3fr);gap:18px}.catalog-grid section{overflow:hidden;padding:18px;border:1px solid #d8e5ec;border-radius:16px;background:#fff;box-shadow:0 12px 30px rgba(25,65,90,.06)}section header{margin-bottom:14px}h2{margin:0;font-size:22px}.subline{display:block;margin-top:3px;color:#758a99;font-size:12px}.el-select{width:100%}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.identifier-head{display:flex;align-items:center;justify-content:space-between;margin:18px 0 8px}.identifier-row{display:grid;grid-template-columns:150px 1fr auto;gap:8px;margin-bottom:8px}@media(max-width:980px){.catalog-grid{grid-template-columns:1fr}.product-hero{align-items:flex-start;flex-direction:column}}@media(max-width:600px){.product-page{padding:12px}.product-hero{padding:20px 16px}.product-hero>div:last-child{width:100%}.product-hero :deep(.el-button){flex:1;min-height:44px;margin-left:0}.form-grid,.identifier-row{grid-template-columns:1fr}}
</style>
