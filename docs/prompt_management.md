# Prompt 管理界面改造最佳方案

> 目标：将当前“DSPy 优化工作台”替换为普通 Prompt 管理中心。  
> 核心诉求：展示提示词所在位置、可视化编辑、保留空格/换行/缩进、页面修改后运行时生效、代码中默认提示词变化后页面能同步显示。

---

## 1. 最优结论

推荐采用：

```text
代码默认 Prompt + 数据库覆盖 Prompt + 运行时 Resolver + 扫描同步 + Diff 对比 + 版本回滚
```

不要让网页在生产环境直接修改源码文件。最佳方式是：

```text
代码里保留默认 Prompt
数据库里保存页面修改后的 Prompt 版本
运行时优先读取数据库生效版本
没有数据库覆盖时使用代码默认版本
代码默认 Prompt 改了以后，由扫描器同步到页面
```

最终效果：

```text
开发者改代码 Prompt → 扫描器同步 → 页面显示代码默认 Prompt 变化
用户在页面改 Prompt → 写入数据库版本 → 运行时立即使用新 Prompt
两边都改了 → 页面提示差异和冲突，让用户选择使用哪一版
```

这比“网页直接改源码”更安全、更容易部署、更容易回滚，也更适合服务器环境和多人协作。

---

## 2. 为什么不建议网页直接修改源码

网页直接修改 `.py` / `.ts` 文件会带来几个问题：

1. **部署不稳定**：线上容器里的源码可能是只读的，或者修改后重启丢失。
2. **Git 冲突难处理**：页面改源码不会自动进入 Git 流程，后续拉代码可能覆盖。
3. **权限风险高**：给网页写源码权限，相当于给业务界面开放代码修改权限。
4. **回滚困难**：用户误改后，很难区分是代码变更还是页面变更。
5. **多环境不一致**：本地、测试、生产的 Prompt 会不一致。

所以最佳方案不是“页面直接改代码”，而是：

```text
代码默认值负责初始化和兜底
数据库版本负责线上动态生效
Diff 页面负责告诉用户两边差异
```

如果确实需要把页面改动反写到代码，建议只在开发环境支持“生成补丁 / 创建 PR”，不要在线上直接写源码。

---

## 3. 前端最佳设计

### 3.1 页面定位

页面名称：

```text
Prompt 管理
```

副标题：

```text
集中管理各 Agent 与流程阶段使用的提示词，支持代码默认版本、数据库生效版本、差异对比、发布和回滚。
```

### 3.2 页面布局

推荐三栏结构：

```text
┌─────────────────────────────────────────────────────────────┐
│ 顶部统计：总数 / 当前生效 / 数据库覆盖 / 代码变更 / 待审核     │
├───────────────┬─────────────────────┬───────────────────────┤
│ 左侧位置树     │ 中间 Prompt 列表      │ 右侧编辑与版本详情       │
│               │                     │                       │
│ Chat Agent    │ 普通问答提示词        │ Prompt 名称             │
│ Task Agent    │ RAG 回答提示词        │ 使用位置                │
│ 共享能力       │ 标准比对提示词        │ Monaco 编辑器           │
│               │ 报告生成提示词        │ Diff / 历史 / 发布按钮   │
└───────────────┴─────────────────────┴───────────────────────┘
```

### 3.3 左侧位置树

按“用户能理解的业务位置”组织，不按技术文件名组织。

示例：

```text
Chat Agent
  ├─ 普通问答
  ├─ RAG 回答
  └─ 文件总结

Task Inspection Agent
  ├─ 任务创建
  ├─ 检测项抽取
  ├─ 标准检索决策
  ├─ 标准比对判定
  └─ 报告生成

共享能力
  ├─ 证据合成
  ├─ 引用格式化
  └─ 规则冲突仲裁
```

每个节点都应该有“使用者能看懂的位置说明”，例如：

```text
位置：Task Inspection Agent / 标准比对判定
说明：根据检测值和 RAG 标准证据判断 PASS / FAIL / UNCERTAIN。
代码位置：backend/agent/prompts/inspection_prompts.py
来源：数据库生效版本覆盖代码默认版本
```

### 3.4 中间 Prompt 卡片

每张卡片展示：

```text
名称：标准比对提示词
位置：Task Inspection Agent / 标准比对判定
Prompt Key：inspection.standard_review.system
来源：数据库覆盖
状态：已发布
当前版本：v4
最后更新：2026-xx-xx
```

建议标签：

```text
代码默认       蓝色
数据库覆盖     绿色
代码已变化     橙色
有冲突         红色
草稿           灰色
已发布         绿色
```

### 3.5 右侧编辑器

必须保留所有空格、换行、缩进和首尾空行。推荐使用 Monaco Editor 或 CodeMirror。

编辑器要求：

```text
- 等宽字体
- 行号
- 不自动 trim
- 支持搜索
- 支持只读 / 编辑切换
- 支持代码默认版本与当前生效版本 Diff
- 支持保存草稿、发布、回滚
```

保存时一定不要这样写：

```ts
content: editor.getValue().trim()
```

应该这样：

```ts
content: editor.getValue()
```

否则会破坏 Prompt 的首尾换行和缩进。

### 3.6 右侧详情字段

推荐展示：

```text
Prompt 名称
Prompt Key
业务位置
所属 Agent
所属阶段
代码文件
代码符号
当前来源：代码默认 / 数据库覆盖
当前版本
状态
最后编辑人
最后更新时间
内容 Hash
```

### 3.7 Diff 对比

右侧提供三个 Tab：

```text
编辑
代码默认版本
差异对比
历史版本
```

差异对比包括：

```text
代码默认版本 vs 当前生效版本
当前草稿版本 vs 当前生效版本
代码默认版本 vs 最新草稿版本
```

---

## 4. 后端总体架构

推荐新增四个核心模块：

```text
PromptRegistry    代码中的 Prompt 注册表
PromptScanner     扫描代码默认 Prompt
PromptResolver    运行时解析最终 Prompt
PromptAdminAPI    页面管理接口
```

整体流程：

```text
代码 Prompt 文件
  ↓
PromptScanner 扫描
  ↓
prompt_definitions.code_default_content 更新
  ↓
页面展示代码默认版本

页面编辑 Prompt
  ↓
创建 prompt_versions 草稿
  ↓
发布版本
  ↓
prompt_definitions.active_version_id 指向新版本
  ↓
PromptResolver 运行时优先读取数据库生效版本
```

---

## 5. 代码中的 Prompt 应该怎么组织

不要让长 Prompt 散落在业务代码中。建议统一放到：

```text
backend/agent/prompts/
  chat_prompts.py
  inspection_prompts.py
  shared_prompts.py
```

每个文件只负责声明 Prompt 元信息和默认内容。

示例：

```python
PROMPTS = [
    {
        "key": "chat.rag_answer.system",
        "display_name": "RAG 回答提示词",
        "description": "根据用户问题和检索证据生成可引用回答。",
        "agent_key": "chat",
        "agent_name": "Chat Agent",
        "stage_key": "rag_answer",
        "stage_name": "RAG 回答",
        "usage_location": "Chat Agent / RAG 回答",
        "source_file": "backend/agent/prompts/chat_prompts.py",
        "source_symbol": "chat.rag_answer.system",
        "content": """
你是一个产品质量检测助手。
请基于用户问题和检索到的证据回答。

要求：
1. 不要编造标准。
2. 如果证据不足，请说明无法判断。
3. 输出必须包含引用来源。
""",
    }
]
```

业务代码不要直接 import 这个字符串，而是调用：

```python
prompt = await prompt_resolver.get("chat.rag_answer.system")
```

---

## 6. 数据库设计

### 6.1 prompt_definitions

用于描述一个 Prompt 的稳定身份、使用位置和代码默认内容。

```sql
CREATE TABLE prompt_definitions (
  id BINARY(16) PRIMARY KEY,
  org_id BINARY(16) NOT NULL,

  prompt_key VARCHAR(160) NOT NULL,
  display_name VARCHAR(160) NOT NULL,
  description TEXT NULL,

  agent_key VARCHAR(100) NULL,
  agent_name VARCHAR(100) NULL,
  stage_key VARCHAR(100) NULL,
  stage_name VARCHAR(100) NULL,
  usage_location VARCHAR(255) NULL,

  source_type VARCHAR(32) NOT NULL DEFAULT 'code',
  source_file VARCHAR(255) NULL,
  source_symbol VARCHAR(160) NULL,
  start_line INT NULL,
  end_line INT NULL,

  code_default_content LONGTEXT NULL,
  code_content_hash VARCHAR(64) NULL,

  active_version_id BINARY(16) NULL,

  sync_status VARCHAR(32) NOT NULL DEFAULT 'synced',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,

  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  deleted_at DATETIME NULL,

  UNIQUE KEY uk_org_prompt_key (org_id, prompt_key)
);
```

`sync_status` 建议取值：

```text
synced          代码默认和页面记录一致
code_changed    代码默认内容变化，页面尚未处理
db_override     数据库版本覆盖代码默认版本
conflict        代码和数据库版本都发生变化，需要人工选择
missing_in_code 代码中已找不到该 Prompt
```

### 6.2 prompt_versions

保存页面创建的每个 Prompt 版本。

如果已有 `prompt_versions` 表，可以扩展字段，不必完全重建。

```sql
CREATE TABLE prompt_versions (
  id BINARY(16) PRIMARY KEY,
  org_id BINARY(16) NOT NULL,
  prompt_definition_id BINARY(16) NOT NULL,

  version INT NOT NULL,
  content LONGTEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,

  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  change_summary TEXT NULL,

  created_by BINARY(16) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  deleted_at DATETIME NULL,

  UNIQUE KEY uk_prompt_version (org_id, prompt_definition_id, version)
);
```

`status` 建议取值：

```text
draft       草稿
review      待审核
approved    已发布
deprecated  已废弃
```

### 6.3 prompt_sync_events

记录扫描、同步、冲突、发布等事件。

```sql
CREATE TABLE prompt_sync_events (
  id BINARY(16) PRIMARY KEY,
  org_id BINARY(16) NOT NULL,
  prompt_definition_id BINARY(16) NOT NULL,

  event_type VARCHAR(64) NOT NULL,
  old_hash VARCHAR(64) NULL,
  new_hash VARCHAR(64) NULL,
  message TEXT NULL,

  created_at DATETIME NOT NULL
);
```

`event_type` 示例：

```text
code_scanned
code_changed
db_version_created
version_published
rollback
conflict_detected
missing_in_code
```

---

## 7. 后端接口设计

建议新增独立路由：

```text
/v1/prompt-admin
```

### 7.1 列表接口

```http
GET /v1/prompt-admin/definitions
```

查询参数：

```text
agent_key
stage_key
keyword
status
source
page
size
```

返回：

```json
{
  "items": [
    {
      "id": "xxx",
      "prompt_key": "inspection.standard_review.system",
      "display_name": "标准比对提示词",
      "usage_location": "Task Inspection Agent / 标准比对判定",
      "agent_name": "Task Inspection Agent",
      "stage_name": "标准比对判定",
      "source_file": "backend/agent/prompts/inspection_prompts.py",
      "sync_status": "db_override",
      "current_source": "database",
      "active_version": 4,
      "updated_at": "2026-xx-xx"
    }
  ],
  "total": 10
}
```

### 7.2 详情接口

```http
GET /v1/prompt-admin/definitions/{prompt_key}
```

返回：

```json
{
  "prompt_key": "inspection.standard_review.system",
  "display_name": "标准比对提示词",
  "description": "根据检测值和标准证据判断合格性。",
  "usage_location": "Task Inspection Agent / 标准比对判定",
  "source_file": "backend/agent/prompts/inspection_prompts.py",
  "source_symbol": "inspection.standard_review.system",
  "code_default_content": "...",
  "active_content": "...",
  "active_version": 4,
  "current_source": "database",
  "sync_status": "db_override",
  "versions": []
}
```

### 7.3 保存草稿

```http
POST /v1/prompt-admin/definitions/{prompt_key}/versions
```

请求：

```json
{
  "content": "完整 Prompt 内容，不 trim",
  "change_summary": "调整标准比对输出格式",
  "base_hash": "前端打开编辑器时拿到的 active_content_hash"
}
```

需要用 `base_hash` 做乐观锁，防止多人同时编辑覆盖。

### 7.4 发布版本

```http
POST /v1/prompt-admin/versions/{version_id}/publish
```

逻辑：

```text
1. 将版本状态改为 approved
2. prompt_definitions.active_version_id = version_id
3. sync_status = db_override
4. 清理 PromptResolver 缓存
```

### 7.5 回滚版本

```http
POST /v1/prompt-admin/definitions/{prompt_key}/rollback
```

请求：

```json
{
  "target_version_id": "xxx"
}
```

### 7.6 同步代码默认 Prompt

```http
POST /v1/prompt-admin/sync/scan
```

用途：

```text
手动触发扫描代码 Prompt。
开发环境可以热更新。
生产环境建议只在启动时或管理员点击时扫描。
```

### 7.7 Diff 接口

```http
GET /v1/prompt-admin/definitions/{prompt_key}/diff
```

参数：

```text
left=code_default
right=active
```

返回前端可直接渲染的 diff。

---

## 8. PromptScanner 实现

### 8.1 扫描时机

推荐：

```text
开发环境：启动扫描 + 文件变更自动扫描
生产环境：启动扫描 + 管理员手动点击同步
```

### 8.2 扫描逻辑

伪代码：

```python
class PromptScanner:
    async def scan(self):
        code_prompts = load_all_prompt_modules()

        seen_keys = set()

        for item in code_prompts:
            seen_keys.add(item["key"])
            content = item["content"]
            content_hash = sha256(content)

            definition = await repo.get_definition_by_key(item["key"])

            if not definition:
                await repo.create_definition(
                    prompt_key=item["key"],
                    display_name=item["display_name"],
                    description=item.get("description"),
                    agent_key=item.get("agent_key"),
                    agent_name=item.get("agent_name"),
                    stage_key=item.get("stage_key"),
                    stage_name=item.get("stage_name"),
                    usage_location=item.get("usage_location"),
                    source_file=item.get("source_file"),
                    source_symbol=item.get("source_symbol"),
                    code_default_content=content,
                    code_content_hash=content_hash,
                    sync_status="synced",
                )
                continue

            if definition.code_content_hash != content_hash:
                next_status = (
                    "conflict"
                    if definition.active_version_id
                    else "code_changed"
                )
                await repo.update_code_default(
                    definition.id,
                    code_default_content=content,
                    code_content_hash=content_hash,
                    sync_status=next_status,
                )

        await repo.mark_missing_in_code(exclude_keys=seen_keys)
```

---

## 9. PromptResolver 实现

运行时所有 Agent 都通过 Resolver 获取 Prompt。

```python
class PromptResolver:
    def __init__(self, repo, cache):
        self.repo = repo
        self.cache = cache

    async def get(self, prompt_key: str, *, org_id: str) -> str:
        cache_key = f"{org_id}:{prompt_key}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        definition = await self.repo.get_definition_by_key(org_id, prompt_key)
        if not definition:
            raise RuntimeError(f"Prompt not found: {prompt_key}")

        if definition.active_version_id:
            version = await self.repo.get_version(definition.active_version_id)
            content = version.content
        else:
            content = definition.code_default_content

        await self.cache.set(cache_key, content, ttl=60)
        return content
```

页面发布、回滚、同步时清理缓存：

```python
await prompt_cache.delete(f"{org_id}:{prompt_key}")
```

---

## 10. 动态更新机制

### 10.1 页面改 Prompt

```text
用户编辑
  ↓
保存草稿
  ↓
发布
  ↓
active_version_id 指向新版本
  ↓
清理 Resolver 缓存
  ↓
新请求立即使用新 Prompt
```

### 10.2 代码改 Prompt

```text
开发者修改 backend/agent/prompts/*.py
  ↓
启动扫描 / 手动扫描
  ↓
code_default_content 更新
  ↓
页面展示代码默认版本变化
```

### 10.3 两边都改

页面显示：

```text
代码默认版本已变化，但当前运行使用数据库覆盖版本。
```

给三个操作：

```text
继续使用数据库版本
切换为代码默认版本
查看差异并创建新版本
```

不要自动覆盖，因为自动覆盖会导致用户不知道哪一版生效。

---

## 11. 前端状态设计

### 11.1 当前来源

```ts
type PromptCurrentSource = "code_default" | "database_override";
```

### 11.2 同步状态

```ts
type PromptSyncStatus =
  | "synced"
  | "code_changed"
  | "db_override"
  | "conflict"
  | "missing_in_code";
```

### 11.3 Prompt 详情类型

```ts
interface PromptDefinitionDetail {
  id: string;
  prompt_key: string;
  display_name: string;
  description?: string;
  agent_key?: string;
  agent_name?: string;
  stage_key?: string;
  stage_name?: string;
  usage_location?: string;
  source_file?: string;
  source_symbol?: string;
  start_line?: number;
  end_line?: number;
  current_source: PromptCurrentSource;
  sync_status: PromptSyncStatus;
  code_default_content: string;
  active_content: string;
  active_version?: number;
  active_content_hash: string;
  versions: PromptVersion[];
}
```

---

## 12. 前端组件拆分

建议拆成：

```text
PromptManageView.vue
  PromptOverviewCards.vue
  PromptLocationTree.vue
  PromptCardList.vue
  PromptEditorPanel.vue
  PromptDiffPanel.vue
  PromptVersionTimeline.vue
```

API 文件：

```text
frontend/src/api/prompt-admin.api.ts
```

Store 文件：

```text
frontend/src/stores/prompt-admin.store.ts
```

类型文件：

```text
frontend/src/types/prompt-admin.types.ts
```

---

## 13. Prompt 编辑器细节

推荐 Monaco Editor 配置：

```ts
monaco.editor.create(editorRef.value, {
  value: detail.active_content,
  language: "plaintext",
  theme: "vs",
  wordWrap: "on",
  minimap: { enabled: false },
  automaticLayout: true,
  lineNumbers: "on",
  fontSize: 14,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  renderWhitespace: "boundary",
});
```

保存时：

```ts
const content = editor.getValue(); // 不 trim
await promptAdminApi.createVersion(promptKey, {
  content,
  change_summary: summary,
  base_hash: detail.active_content_hash,
});
```

---

## 14. 权限设计

建议：

```text
普通用户：不可见
专家用户：只读查看 Prompt 和使用位置
开发者：可编辑草稿
管理员：可发布、回滚、切换代码默认版本
```

接口层也要校验：

```text
prompt:read
prompt:write
prompt:publish
prompt:rollback
prompt:sync
```

---

## 15. 高效落地路径

### 阶段 1：先替换前端页面

目标：去掉 DSPy 代码，先展示普通 Prompt 管理。

任务：

```text
1. 删除 PromptManageView.vue 中 DSPy 编译、评测、图谱上下文相关代码
2. 新建 Prompt 管理三栏页面
3. 先复用已有 /v1/agent-ops/prompts 接口展示 PromptVersion
4. 使用 textarea 或 Monaco Editor 展示内容
```

成果：

```text
页面从“DSPy 优化工作台”变成“Prompt 管理”
可以查看和编辑已有 PromptVersion
```

### 阶段 2：增加 PromptDefinition

目标：补足“提示词所在位置”。

任务：

```text
1. 新增 prompt_definitions 表
2. 新增 prompt-admin API
3. 新增前端位置树、位置说明、代码位置字段
4. 支持按 Agent / 阶段筛选
```

成果：

```text
用户能看到每个 Prompt 属于哪个 Agent、哪个阶段、做什么用
```

### 阶段 3：接入代码扫描

目标：代码变更能反映到页面。

任务：

```text
1. 新建 backend/agent/prompts/*.py
2. 实现 PromptScanner
3. 启动时扫描
4. 增加“同步代码 Prompt”按钮
5. 展示 code_changed / conflict 状态
```

成果：

```text
代码默认 Prompt 改了，页面能看到变化
```

### 阶段 4：接入运行时 Resolver

目标：页面发布后运行时立即生效。

任务：

```text
1. 实现 PromptResolver
2. 业务 Agent 改成通过 prompt_key 读取 Prompt
3. 发布/回滚时清理缓存
4. 增加版本历史和回滚
```

成果：

```text
页面改 Prompt，业务运行时使用新 Prompt
```

### 阶段 5：高级能力

可选：

```text
1. Diff 视图
2. Prompt 预览测试
3. Prompt 使用次数统计
4. Prompt 效果指标关联
5. 导出为代码补丁 / 创建 PR
```

---

## 16. 最终推荐页面示例

```text
Prompt 管理

[总 Prompt 28] [数据库覆盖 9] [代码有变化 3] [待审核 2] [缺失代码 1]

左侧：
Chat Agent
  普通问答
  RAG 回答
Task Inspection Agent
  任务创建
  标准比对
  报告生成
共享能力
  证据合成
  引用格式化

中间：
标准比对提示词
Task Inspection Agent / 标准比对判定
数据库覆盖 · v4 · 已发布

RAG 回答提示词
Chat Agent / RAG 回答
代码默认 · synced

证据合成提示词
共享能力 / 证据合成
冲突 · 代码默认已变化

右侧：
标题：标准比对提示词
位置：Task Inspection Agent / 标准比对判定
说明：根据检测值和标准证据判断 PASS / FAIL / UNCERTAIN
代码位置：backend/agent/prompts/inspection_prompts.py
当前来源：数据库覆盖
版本：v4

[编辑器]
...
[保存草稿] [发布] [查看差异] [回滚]
```

---

## 17. 最重要的实现原则

1. **Prompt Key 必须稳定**  
   不要用中文标题当唯一标识，使用 `agent.stage.role` 形式。

2. **编辑内容不能 trim**  
   保留所有空格、换行、缩进和首尾空行。

3. **生产环境不直接写源码**  
   页面修改写数据库，代码修改通过扫描同步到页面。

4. **运行时统一走 Resolver**  
   不允许业务代码到处直接 import prompt 字符串。

5. **必须有版本和回滚**  
   Prompt 是高风险配置，不能只存一份。

6. **必须有冲突处理**  
   代码和页面都改时，不自动覆盖，交给用户选择。

---

## 18. 最终一句话方案

将 Prompt 管理改造成“代码默认 Prompt 与数据库覆盖版本的统一管理中心”：代码负责默认值和可追踪位置，数据库负责在线编辑和生效版本，运行时通过 PromptResolver 统一读取，前端用位置树、卡片、Monaco 编辑器、Diff 和版本历史提供可理解、可编辑、可回滚的管理体验。
