# SSE 长连接跨页面保持 + 思考时间动态指示器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户切换页面/会话时 SSE 连接不中断，界面显示动态思考时间+旋转指示器

**Architecture:** KeepAlive 缓存 ChatView 阻止 unmount + chat.store 层管理 SSE 生命周期（activeStreamingSessionId + thinkingTimer）+ ChatView 模板层状态条 UI

**Tech Stack:** Vue 3 + Pinia + Tailwind CSS + TypeScript

---

### Task 1: chat.store.ts — 新增 SSE 生命周期状态与方法

**Files:**
- Modify: `frontend/src/stores/chat.store.ts`

- [ ] **Step 1: 在第 146 行后新增 ref 状态变量**

在 `trustPollInFlight` 之后、`ragSpaces` 之前插入：

```typescript
const activeStreamingSessionId = ref<string | null>(null);
const thinkingStartedAt = ref<number | null>(null);
const thinkingElapsed = ref(0);
let _thinkingTimer: ReturnType<typeof setInterval> | null = null;
```

- [ ] **Step 2: 在第 276 行 `stopTrustPolling` 函数之后，新增 `startThinkingTimer` 和 `stopThinkingTimer` 函数**

```typescript
function startThinkingTimer() {
  if (_thinkingTimer != null) return;
  thinkingStartedAt.value = Date.now();
  thinkingElapsed.value = 0;
  _thinkingTimer = setInterval(() => {
    thinkingElapsed.value = Math.floor((Date.now() - (thinkingStartedAt.value || Date.now())) / 1000);
  }, 1000);
}

function stopThinkingTimer() {
  if (_thinkingTimer != null) {
    clearInterval(_thinkingTimer);
    _thinkingTimer = null;
  }
  thinkingStartedAt.value = null;
  thinkingElapsed.value = 0;
}
```

- [ ] **Step 3: 修改 `stopStreamForIdle` 函数（第 292 行），追加清理新状态**

在现有 `stopStreamForIdle` 函数体末尾（`finishActiveSend()` 之后）追加：

```typescript
  activeStreamingSessionId.value = null;
  stopThinkingTimer();
```

- [ ] **Step 4: 修改 `selectSession` 函数（第 492 行），改为条件性杀 SSE**

将第 496 行的无条件 `stopStreamForIdle();` 替换为：

```typescript
if (session.value?.id && session.value.id !== sessionId && session.value.id !== activeStreamingSessionId.value) {
  stopStreamForIdle();
}
```

- [ ] **Step 5: 修改 `createNewSession` 函数（第 482 行），删除无条件 `stopStreamForIdle`**

删除第 483 行的 `stopStreamForIdle();`

- [ ] **Step 6: 修改 `ensureStream` 函数（第 841 行），建立 SSE 时设置会话追踪和计时器**

在 `ensureStream` 函数内部，`eventSource.value = source;` 一行之后，`streamPromise` 闭包内的 `source.onerror` 赋值块之后，插入：

```typescript
        activeStreamingSessionId.value = sessionId;
        startThinkingTimer();
```

（实际位置：紧接 `eventSource.value = source;` 之后，仍在 `streamPromise` 闭包内部）

- [ ] **Step 7: 修改 `finalizeStreaming` 函数（第 300 行），追加计时器清理**

在 `finalizeStreaming` 函数体末尾追加：

```typescript
  activeStreamingSessionId.value = null;
  stopThinkingTimer();
```

- [ ] **Step 8: 新增 `cancelActiveStream` 函数（放在 `stopStream` 函数之前，约第 877 行）**

```typescript
function cancelActiveStream() {
  stopStreamForIdle();
}
```

- [ ] **Step 9: 修改 return 导出块（第 882 行），加入新状态和方法**

在 `deleteSession,` 和 `stopStream,` 之间插入：

```typescript
    activeStreamingSessionId,
    thinkingStartedAt,
    thinkingElapsed,
    cancelActiveStream,
```

- [ ] **Step 10: 提交**

```bash
git add frontend/src/stores/chat.store.ts
git commit -m "feat: add SSE lifecycle persistence with thinking timer in chat store"
```

---

### Task 2: ChatView.vue — 思考状态栏 UI + 移除 onBeforeUnmount SSE 断连

**Files:**
- Modify: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: 替换 `streamStatusText` computed（第 66-72 行）为新的状态栏计算属性**

删除：
```typescript
const streamStatusText = computed(() => {
  if (!chatStore.loading) return "";
  if (chatStore.streamPhase === "connecting") return "正在建立连接...";
  if (chatStore.streamPhase === "streaming") return "智能体处理中...";
  if (chatStore.streamPhase === "closing") return "正在整理回复...";
  return "智能体处理中...";
});
```

替换为：
```typescript
const thinkingPhaseText = computed(() => {
  if (chatStore.streamPhase === "connecting") return "正在建立连接...";
  if (chatStore.streamPhase === "streaming") return "智能体分析中...";
  if (chatStore.streamPhase === "closing") return "正在整理结果...";
  return "处理中...";
});

const thinkingElapsedText = computed(() => {
  const s = chatStore.thinkingElapsed;
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (s < 3600) return `${m}m${rem.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h${(m % 60).toString().padStart(2, "0")}m`;
});
```

- [ ] **Step 2: 修改 `streamingPlaceholder` 函数（第 414-420 行）中的引用**

将第 419 行：
```typescript
return streamStatusText.value || "智能体处理中...";
```
改为：
```typescript
return thinkingPhaseText.value || "智能体处理中...";
```

- [ ] **Step 3: 替换模板中的状态条（第 1008-1020 行）**

将：
```html
        <div v-if="streamStatusText" class="stream-status">
          <span>{{ streamStatusText }}</span>
          <el-button
            v-if="chatStore.canCancelResponse"
            size="small"
            type="danger"
            link
            :icon="CircleClose"
            @click="interruptCurrentResponse()"
          >
            中断回答
          </el-button>
        </div>
```

替换为：
```html
        <div v-if="chatStore.loading" class="thinking-bar">
          <span class="thinking-spinner"></span>
          <span class="thinking-phase">{{ thinkingPhaseText }}</span>
          <span class="thinking-timer">{{ thinkingElapsedText }}</span>
          <el-button
            v-if="chatStore.canCancelResponse"
            size="small"
            type="danger"
            link
            :icon="CircleClose"
            class="thinking-cancel-btn"
            @click="interruptCurrentResponse()"
          >
            中断
          </el-button>
        </div>
```

- [ ] **Step 4: 替换 CSS（第 1380-1391 行的 `.stream-status` 样式块）**

将：
```css
.stream-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 2px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
```

替换为：
```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
.thinking-bar {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 14px;
  border-radius: 999px;
  background: #f0fdfa;
  border: 1px solid #ccfbf1;
  color: #0f766e;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 6px;
  transition: opacity 0.3s ease-out-quint;
}
.thinking-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #ccfbf1;
  border-top-color: #0d9488;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
.thinking-timer {
  font-variant-numeric: tabular-nums;
  color: #5eead4;
  margin-left: 2px;
}
.thinking-cancel-btn {
  margin-left: 4px;
}
```

- [ ] **Step 5: 替换 `onBeforeUnmount`（第 710 行），移除 `stopStream` 调用的直接卸载断连**

将：
```typescript
onBeforeUnmount(() => { chatStore.stopStream(); disposeTaskStreams(); });
```

替换为：
```typescript
function handleBeforeUnload() {
  chatStore.stopStream();
  disposeTaskStreams();
}
onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload);
});
onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
  // 不再调用 stopStream — SSE 由 KeepAlive 保持
  disposeTaskStreams();
});
```

注意：需要将 `onBeforeUnmount` 的 import（第 4 行）保持不变，因为仍在组件中使用。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat: add thinking timer status bar with spinner, remove SSE teardown on unmount"
```

---

### Task 3: AppLayout.vue — KeepAlive 缓存 ChatView

**Files:**
- Modify: `frontend/src/layouts/AppLayout.vue`

- [ ] **Step 1: 将第 108 行的 `<RouterView />` 替换为 KeepAlive 包装版本**

将：
```vue
        <RouterView />
```

替换为：
```vue
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="['ChatView']">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
```

- [ ] **Step 2: 验证 ChatView 的 SFC 文件名匹配 `include` 名称**

`ChatView.vue` 的 SFC `defineOptions` 未显式设置 name，Vue 3 + Vite 自动从文件名推导为 `ChatView`，与 `include: ['ChatView']` 匹配。无需额外改动。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/layouts/AppLayout.vue
git commit -m "feat: wrap ChatView in KeepAlive to persist SSE across page navigation"
```

---

### Task 4: 验证与收尾

- [ ] **Step 1: TypeScript 编译检查**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1
```
预期：无新增类型错误。

- [ ] **Step 2: 检查 ChatView.vue 中不再使用 `streamStatusText` 的残留引用**

```bash
cd frontend && npx grep -n "streamStatusText" src/views/ChatView.vue
```
预期：无匹配（已全部替换）。

- [ ] **Step 3: 检查 `stopStream` 调用点仅剩 beforeunload 场景**

确认 ChatView.vue 中只有 `handleBeforeUnload` 调用 `chatStore.stopStream()`。

- [ ] **Step 4: 验证 KeepAlive 不破坏其他路由**

打开应用，切换至非 ChatView 页面（Dashboard、Tasks 等），确认页面正常加载和卸载，无内存泄漏或重复渲染。

- [ ] **Step 5: 端到端验证**

1. 在聊天页发送一条需要较长时间处理的请求（如上传 docx 论文查非）
2. 观察状态条显示旋转指示器 + 动态思考时间
3. 切换到其他页面等待 30 秒，再切回聊天页
4. 确认：SSE 连接未中断，状态条仍在，计时器递增，最终收到完整结果
5. 切换到其他会话，确认原会话的活跃 SSE 不受影响
6. 关闭浏览器标签页，确认 SSE 被清理

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "chore: verify SSE persistence and thinking indicator"
```
