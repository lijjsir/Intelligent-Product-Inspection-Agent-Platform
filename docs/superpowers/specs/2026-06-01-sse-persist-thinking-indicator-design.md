# SSE 长连接跨页面保持 + 思考时间动态指示器

> 日期：2026-06-01
> 分支：`new_tgg`
> 涉及：前端 SSE 生命周期、KeepAlive 路由缓存、智能体处理状态 UI

## 1. 问题

1. 用户提交论文查非任务后，ChatView 显示"智能体处理中..."，一段时间后不再更新
2. 切换到其他页面（或其他聊天会话）后，`onBeforeUnmount` 触发 `stopStream()`，SSE EventSource 被关闭，后端继续处理但前端永远收不到结果
3. `selectSession()` 切换会话时也无条件调用 `stopStreamForIdle()`，杀死活跃 SSE
4. 没有思考时间动态显示，用户不知道等了多久

## 2. 改动范围

### 2.1 chat.store.ts — SSE 生命周期改造

**新增状态**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `activeStreamingSessionId` | `string \| null` | 当前持有活跃 SSE 连接的会话 ID |
| `thinkingStartedAt` | `number \| null` | 思考开始时间戳 (ms) |
| `thinkingElapsed` | `number` | 已过秒数，1s 定时器驱动 |
| `_thinkingTimer` | `ReturnType\<typeof setInterval\> \| null` | 计时器句柄 |

**新增方法**：

- `startThinkingTimer()` — 记录 `thinkingStartedAt = Date.now()`，启动 1s 间隔更新 `thinkingElapsed`
- `stopThinkingTimer()` — 清除 interval，重置上述三个状态
- `cancelActiveStream()` — 用户主动取消：杀 SSE + 停计时器 + 清理 activeStreamingSessionId

**修改现有方法**：

- `selectSession(sessionId)` — 仅当 `sessionId !== activeStreamingSessionId` 时不杀 SSE（不调用 `stopStreamForIdle`）
- `createNewSession()` — 同上，创建新会话不杀活跃 SSE
- `finalizeStreaming()` — 保持不变，`message_final` / `run_failed` 到达时正常关闭 SSE
- `ensureStream()` — 建立 SSE 时设置 `activeStreamingSessionId`，启动 `startThinkingTimer()`

**清理时机**（唯一杀 SSE 的场景）：

1. `message_final` / `run_failed` 到达（已有 `finalizeStreaming`）
2. 用户显式取消（`cancelActiveStream()`）
3. `window.beforeunload`（防标签页关闭泄漏）

### 2.2 ChatView.vue — 思考状态栏 + 计时器

**移除**：

- 第 710 行 `onBeforeUnmount(() => { chatStore.stopStream(); disposeTaskStreams(); })`
- 第 66-72 行 `streamStatusText` computed

**新增**：消息列表上方窄状态栏（高度 36px），三要素：

1. **旋转指示器** — 16px 细环，`border-top-color: teal-600`，`animation: spin 0.8s linear infinite`
2. **阶段文案** — 根据 `streamPhase` 切换：`正在建立连接...` / `智能体分析中...` / `正在整理结果...`
3. **计时器** — 从 `thinkingElapsed` 计算，`<1m` 显示秒，`<1h` 显示 `XmXXs`，`>=1h` 显示 `XhXXm`

```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
.thinking-spinner {
  width: 16px; height: 16px;
  border: 2px solid #e4e4e7;
  border-top-color: #0d9488;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
```

状态条出现/消失使用 `opacity + max-height` 过渡，避免 layout shift。

**新增生命周期**：

```typescript
onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload);
});
onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
  // 不再调用 stopStream，由 KeepAlive 保持连接
});
```

### 2.3 AppLayout.vue — KeepAlive 缓存 ChatView

[AppLayout.vue:108](frontend/src/layouts/AppLayout.vue#L108)：

```diff
- <RouterView />
+ <RouterView v-slot="{ Component }">
+   <KeepAlive :include="['ChatView']">
+     <component :is="Component" />
+   </KeepAlive>
+ </RouterView>
```

ChatView 的 SFC 文件名自动推导组件名为 `ChatView`，与 `include` 匹配。仅 ChatView 被缓存，其他页面正常卸载。

## 3. 关键约束

- 只有一个活跃智能体处理任务（用户确认）
- 用户可切到其他会话或其他页面，处理不中断
- SSE 在 `message_final` / `run_failed` / 显式取消 / 关标签页 四种情况下才断开
- 思考时间在 store 中由 setInterval 驱动，1s 精度，不依赖 SSE 事件
- 状态栏仅在有活跃流时显示，`loading === false` 时消失

## 4. 不变更的部分

- SSE 端点、StreamToken、EventSource 底层机制不变
- fallbackPolling 机制保留（SSE 建立失败时的兜底）
- 任务级 SSE (`task.store.ts`) 不受影响
- 会议室 SSE (`meeting.store.ts`) 不受影响
