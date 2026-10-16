<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { Search, Close, ChatLineRound, Document } from '@element-plus/icons-vue';
import { chatApi } from '@/api/chat.api';
import type { ChatSearchItem, ChatSearchKind } from '@/types/chat.types';
import { formatServerDateTime } from '@/utils/date-time';

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value:boolean]; select: [item:ChatSearchItem] }>();
const query = ref('');
const kind = ref<ChatSearchKind>('all');
const input = ref<HTMLInputElement>();
const items = ref<ChatSearchItem[]>([]);
const total = ref(0);
const hasMore = ref(false);
const busy = ref(false);
const error = ref('');
const selected = ref(0);
const tabs: {kind:ChatSearchKind; label:string}[] = [{kind:'all',label:'全部'},{kind:'chat',label:'对话'},{kind:'image',label:'图片'},{kind:'file',label:'文档'}];
let timer: ReturnType<typeof setTimeout> | undefined;
let version = 0;

function segments(text: string) {
  const needle = query.value.trim().toLowerCase();
  if (!needle) return [{text,match:false}];
  const parts: {text:string;match:boolean}[] = [];
  let start = 0;
  for (let position=text.toLowerCase().indexOf(needle); position>=0; position=text.toLowerCase().indexOf(needle,start)) {
    parts.push({text:text.slice(start,position),match:false},{text:text.slice(position,position+needle.length),match:true});
    start=position+needle.length;
  }
  parts.push({text:text.slice(start),match:false});
  return parts;
}
async function search(more = false) {
  if (!props.modelValue) return;
  const current = ++version;
  busy.value=true; error.value='';
  const offset = more ? items.value.length : 0;
  if (!more) { items.value=[]; total.value=0; hasMore.value=false; selected.value=0; }
  try {
    const {data}=await chatApi.searchSessions(query.value.trim(),kind.value,offset);
    if (current!==version || !props.modelValue) return;
    items.value=more ? [...items.value,...data.data.items] : data.data.items;
    total.value=data.data.total; hasMore.value=data.data.has_more;
  } catch { if(current===version) error.value='搜索暂不可用，请重试'; }
  finally { if(current===version) busy.value=false; }
}
function schedule() {
  version++;
  if (timer) clearTimeout(timer);
  if (!props.modelValue) return;
  busy.value=true; items.value=[]; total.value=0; hasMore.value=false; error.value='';
  timer=setTimeout(()=>void search(),250);
}
function clear() { query.value=''; void nextTick(()=>input.value?.focus()); }
function choose(item: ChatSearchItem) {
  const focus = Boolean(query.value.trim()) || kind.value==='image' || kind.value==='file';
  emit('update:modelValue',false);
  emit('select',{...item,message_seq:focus ? item.message_seq : null});
}
function move(amount:number) { selected.value=Math.max(0,Math.min(items.value.length-1,selected.value+amount)); }
function image(item: ChatSearchItem) { return item.attachments?.find(att=>att.kind==='image' && /^(https?:\/\/|\/(?!\/)|data:image\/)/.test(att.url || '')); }
watch([query,kind],schedule);
watch(()=>props.modelValue,(open)=> { if(open) { void search(); } else { version++; busy.value=false; if(timer)clearTimeout(timer); } });
onBeforeUnmount(()=> { version++; if(timer)clearTimeout(timer); });
</script>

<template>
  <el-dialog :model-value="modelValue" title="搜索对话" :show-close="false" width="min(94vw, 760px)" top="10vh" class="conversation-search-dialog" append-to-body @update:model-value="emit('update:modelValue',$event)" @opened="input?.focus()">
    <template #header>
      <div class="search-dialog-heading">
        <Search aria-hidden="true" />
        <input ref="input" v-model="query" maxlength="200" placeholder="搜索标题、对话内容或附件名称" aria-label="搜索标题、对话内容或附件名称" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="items[selected] && choose(items[selected])" />
        <button v-if="query" class="search-clear" @click="clear">清除</button>
        <button class="search-close" aria-label="关闭对话搜索" @click="emit('update:modelValue',false)"><Close /></button>
      </div>
      <nav class="search-kind-tabs" aria-label="搜索分类"><button v-for="tab in tabs" :key="tab.kind" :aria-pressed="kind===tab.kind" :class="{active:kind===tab.kind}" @click="kind=tab.kind">{{ tab.label }}</button></nav>
    </template>
    <div class="search-results" :aria-busy="busy">
      <div class="search-status">{{ query.trim() ? `匹配对话${total ? ` · ${total}` : ''}` : '最近对话' }}<span>仅搜索本人对话</span></div>
      <p v-if="busy && !items.length" class="search-empty">正在搜索…</p>
      <div v-else-if="error" class="search-empty">{{ error }} <button @click="search()">重试</button></div>
      <p v-else-if="!items.length" class="search-empty">{{ query.trim() ? '没有找到匹配的对话，试试其他关键词' : '还没有历史对话' }}</p>
      <button v-for="(item,index) in items" :key="item.id" class="search-result" :class="{active:index===selected}" @mouseenter="selected=index" @click="choose(item)">
        <ChatLineRound class="search-result-icon" aria-hidden="true" />
        <span class="search-result-copy"><strong><template v-for="(part,i) in segments(item.title || '新对话')" :key="i"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></strong><span class="search-snippet"><template v-for="(part,i) in segments(item.snippet)" :key="i"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span></span>
        <img v-if="image(item)" class="search-result-thumbnail" :src="image(item)?.url" alt="" />
        <span v-else-if="item.attachments?.length" class="search-result-document"><Document aria-hidden="true" /></span>
        <time>{{ formatServerDateTime(item.last_message_at || item.created_at).slice(0,10) }}</time>
      </button>
      <button v-if="hasMore" class="search-more" :disabled="busy" @click="search(true)">{{ busy ? '加载中…' : '加载更多' }}</button>
    </div>
  </el-dialog>
</template>

<style scoped>
.search-dialog-heading { display:flex; align-items:center; gap:13px; padding:3px 6px 21px; }
.search-dialog-heading>svg { width:21px; height:21px; color:#8c9bad; flex:none; }
.search-dialog-heading input { min-width:0; flex:1; border:0; outline:none; font:inherit; font-size:18px; color:#2c3c50; background:transparent; }
.search-dialog-heading input::placeholder { font-size:14px; color:#95a1b2; }
.search-dialog-heading button { flex:none; border:0; background:transparent; color:#7b8797; cursor:pointer; }
.search-clear { font:inherit; font-size:12px; padding:7px 13px; border-right:1px solid #e7ebf1 !important; }
.search-close { display:grid; place-items:center; padding:5px; border-radius:6px; }
.search-close svg { width:19px; height:19px; }
.search-close:hover { background:#f0f3f7; }
.search-kind-tabs { display:flex; gap:9px; }
.search-kind-tabs button { border:0; border-radius:20px; background:transparent; font:inherit; font-size:13px; color:#7a899c; padding:8px 15px; cursor:pointer; }
.search-kind-tabs button.active { background:#eef3f9; color:#34485f; }
.search-results { max-height:55vh; overflow-y:auto; padding:9px 0; }
.search-status { display:flex; justify-content:space-between; font-size:11px; color:#93a0b0; padding:1px 14px 12px; }
.search-status span { font-size:10px; }
.search-result { width:100%; display:flex; align-items:center; gap:16px; text-align:left; border:0; border-radius:12px; padding:15px 14px; background:transparent; cursor:pointer; color:#34475e; font:inherit; }
.search-result.active { background:#f2f5f8; }
.search-result-icon { width:21px; height:21px; flex:none; color:#738499; }
.search-result-copy { display:flex; flex-direction:column; gap:7px; min-width:0; flex:1; }
.search-result-copy strong { font-size:14px; font-weight:500; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.search-snippet { font-size:12px; color:#8b98aa; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.search-result mark { background:transparent; color:#2b6cba; font-weight:600; }
.search-result time { flex:none; color:#9da7b4; font-size:10px; }
.search-result-thumbnail,.search-result-document { width:42px; height:42px; flex:none; border:1px solid #e0e6ee; border-radius:8px; object-fit:cover; background:#fff; }
.search-result-document { display:grid; place-items:center; color:#94a3b7; }
.search-result-document svg { width:21px; height:21px; }
.search-empty { text-align:center; padding:55px 12px; font-size:13px; color:#8c9caf; }
.search-empty button,.search-more { border:0; background:transparent; color:#537da9; cursor:pointer; font:inherit; }
.search-more { display:block; margin:12px auto 5px; font-size:12px; }
button:focus-visible { outline:2px solid #9dc0e9; outline-offset:1px; }
@media(max-width:700px) { .search-result { gap:10px; padding-inline:10px; } .search-result time { display:none; } .search-kind-tabs { gap:2px; } .search-kind-tabs button { padding-inline:13px; } .search-dialog-heading { gap:8px; } .search-dialog-heading>svg { display:none; } .search-dialog-heading input::placeholder { font-size:12px; } .search-clear { padding-inline:8px; } }
</style>
<style>
.conversation-search-dialog.el-dialog { padding:22px 18px 12px; border-radius:18px; box-shadow:0 20px 70px #13213b30; }
.conversation-search-dialog .el-dialog__header { padding:0 4px 16px; margin:0; border-bottom:1px solid #e8edf3; }
.conversation-search-dialog .el-dialog__body { padding:12px 0 0; }
</style>
