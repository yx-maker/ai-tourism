# MindLink_AI 功能模块技术实现说明书

> **性质**：功能 → 技术实现 对照说明书（规范层文档）
> **日期**：2026-10-22 · 数据来源：`AGENTS.md`（SSOT）、`docs/specs/`（SPEC-001~021）、`docs/DATA_MODEL.md`、`docs/API_CONTRACTS.md`、实际代码
> **维护约定**：新增/修改功能时增量更新本文件，并同步 docs/README.md 索引

---

## 1. 项目概览

MindLink_AI 是一个 **AI 智能旅游助手系统**：单进程 Spring Boot 后端（:8080）+ Vue 3 前端（:3000），围绕智谱 GLM 大模型构建了普通对话、Agent 工具链、RAG 知识库问答、跨会话记忆、旅游规划工作台五大能力域。

```
浏览器 (Vue 3 + Element Plus, :3000)
   │  REST / SSE
   ▼
MindLink_AI_server  单进程聚合启动 (:8080)
   ├─ MindLink_AI_system   用户/认证/后台管理
   ├─ MindLink_AI_ai       AI 核心（对话/Agent/RAG/记忆/旅游/MCP）
   └─ MindLink_AI_common   实体/DTO/安全配置/JWT/共享数据层
   ▼
MySQL 8（22 张表） · Redis（令牌/缓存） · Elasticsearch（RAG 可选）
   ▼
智谱 GLM（OpenAI 兼容 https://open.bigmodel.cn/api/paas/v4）
   ├─ glm-4-flash    对话 / Agent / 记忆提取 / 摘要
   ├─ glm-4v-flash   图像识别（视觉）
   └─ embedding-3    1024 维向量（RAG 混合检索）
```

**模块依赖红线**：common ← system/ai（横向不依赖），common 禁止反向依赖；共享数据层（UserMapper/SysRoleService）下沉 common。

---

## 2. 技术栈总表（版本以 pom.xml / package.json 为准）

| 层 | 技术 | 版本 | 用途 |
|---|---|---|---|
| 语言/构建 | Java + Maven 多模块 | 17 | 四模块工程 |
| 框架 | Spring Boot | 3.2.0 | Web/安全/事务/配置 |
| AI 框架（Agent） | LangChain4j | 0.36.2 | MindLinkAgent、AiServices、@Tool、ToolProvider |
| AI 框架（对话/RAG） | Spring AI（OpenAI 兼容 starter） | 1.0.0-M6 | OpenAiChatModel 流式/同步、Prompt/Message 抽象 |
| MCP | MCP Java SDK | 0.14.1 | 外部托管 MCP 工具桥接 |
| Token 计数 | jtokkit | 1.1.0 | 记忆裁剪/预算核算（cl100k） |
| ORM | MyBatis-Plus | 3.5.6 | BaseMapper + LambdaQueryWrapper（非 JPA） |
| 安全 | Spring Security + JJWT | 0.12.3 | JWT 过滤器、RBAC |
| 存储 | MySQL 8 / Redis / Elasticsearch（可选） | — | 业务数据 / 令牌与缓存 / RAG 检索 |
| 工具库 | Hutool 5.8.23 · fastjson2 2.0.32 · PageHelper | — | 通用工具 / JSON / 分页 |
| 评测 | Python（tools/rag-eval） | 3.x | RAG 离线评测脚本（hit@5/MRR/nDCG） |
| 前端 | Vue 3.4 · Vite 5 · Element Plus 2.4 · Pinia 2 · TS 5.2 | — | SPA + SSE 流式渲染 |

> 历史 AI 供应商（通义千问/Ollama/豆包）已全部下线，文档提及视为过时。

---

## 3. 功能模块 → 技术实现

### 3.1 用户与权限域

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 |
|---|---|---|---|
| 注册/登录 | HmacSHA256+随机盐密码哈希；登录返回 accessToken/refreshToken（JJWT HS512），Redis 存储令牌支持主动注销 | `UserController`、`UserServiceImpl`、`TokenRedisService` | users |
| 认证防线 | Spring Security 无状态过滤器链 + 全局白名单（/user/login 等 8 项）+ JwtAuthenticationFilter | `SecurityConfig`（common）、`JwtUtils` | — |
| 密码修改令牌失效 | 改密成功后删除该用户全部 Redis 令牌（强制重登录） | `TokenRedisService` | — |
| RBAC 角色菜单 | 角色-菜单-用户三表关联，@MapperScan 三包扫描 | `SysMenuController`、`SysRoleMapper` | sys_role / sys_menu / sys_user_role / sys_role_menu |
| 后台管理/登录日志 | 管理端接口 + 登录 IP/浏览器指纹记录 | `AdminController`、`SysLoginLogService` | sys_login_log |
| 对象级授权 | 文档预览/向量回填等按资源归属校验；不存在与非本人统一 404（防资源枚举） | 各 ServiceImpl 归属校验 | — |

### 3.2 对话与会话管理

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 |
|---|---|---|---|
| 会话 CRUD | REST + 逻辑删除（显式 UPDATE is_deleted=1） | `ChatSessionController`、`ChatSessionServiceImpl` | chat_session |
| 消息持久化 | 发送时服务端注入 userId + 会话归属校验（不信任客户端） | `ChatMessageController`、`ChatMessageServiceImpl` | chat_message |
| 图像识别 | glm-4v-flash 多模态，base64/URL 双通道 | `OllamaQwenController`（vision 分支） | chat_image |

### 3.3 普通聊天链路（/ai/chat）

| 功能 | 技术实现 | 关键类 / 组件 | SPEC |
|---|---|---|---|
| SSE 流式对话 | Spring AI `OpenAiChatModel.stream()` → Reactor `Flux<String>`（text/event-stream）；userId 在 servlet 线程就地捕获防 Tomcat 回收竞态；上下文组装**必须在当前消息落库前**（调用契约） | `OllamaQwenController` | — |
| 时间感知 | SystemMessage 注入"当前时间"+ 时间事实铁律（历史日期为快照，不得当作当前事实） | `ChatPromptProvider.timeContext/timeFactRule`（chat-prompt-v3） | — |
| 无状态问题 | 日期/时间/天气类短问题（≤12 字）跳过长期记忆注入，历史保留 | `StatelessQuestions`（Agent 与普通聊天共用） | SPEC-014 R1-4 |
| 天气意图真数据 | 意图判定命中即走高德真实天气 API，模型只转述不许编造温度 | `WeatherQuestionResolver`、`GroundedWeatherResponder` | — |

### 3.4 Agent 智能体（/agent/*）

| 功能 | 技术实现 | 关键类 / 组件 | SPEC |
|---|---|---|---|
| Agent 运行时 | LangChain4j AiServices + **注解优先** `@SystemMessage`（静态模板，编程式 provider 自动失效——架构约束） | `MindLinkAgent`、`AgentConfig` | — |
| 工具调用 | 编程式 ToolProvider 按角色授权动态装配；@Tool 注解工具（天气/POI/搜索等）；工具调用日志审计 | `DynamicToolProvider`、`AgentToolRegistry`、`AgentTools` | sys_role_tool |
| 意图路由 | 三层防御（规则/黑白名单/提示注入检测），无状态/工具/普通三路分发 | `IntentRouter` | — |
| 工具链编排 | 多工具顺序编排 + 上下文传递 | `ToolChainOrchestrator`、`AgentContext` | — |
| MCP 生态 | MCP Java SDK 桥接阿里云百炼市场托管工具（联网搜索等） | `McpToolBridge`、`McpController` | — |
| 角色工具授权 | 角色→工具白名单持久化 + 管理端 CRUD | `SysRoleToolController` | sys_role_tool |

### 3.5 记忆系统（项目核心特色）

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 | SPEC |
|---|---|---|---|---|
| 短期记忆三级裁剪 | jtokkit 计数 → FULL（全量）/ WINDOW（最近 N 轮，user 消息对齐）/ SUMMARY（LLM 摘要）三档策略 | `ChatTokenManager`、`MemoryContext` | — | — |
| 两遍增量摘要 | LLM 融合摘要 + covered_until_id 游标（淘汰满 N 条才重摘要，命中缓存）；失败复用旧缓存 | `HistorySummarizer`、`ConversationMemoryService` | chat_session_summary | — |
| 统一上下文组装 | 单一入口 [system(人设+时间+任务状态+摘要+长期记忆+旅游提示词)] + [历史] + [当前问题]；Token 预算护栏超限从最旧整轮原子裁剪；逐级降级不阻断聊天 | `ContextAssembler` | — | SPEC-014 |
| 长期记忆生命周期 | LLM 只产候选 → Java 过滤（类型白名单/长度/敏感信息正则）→ 归一化 SHA-256 指纹幂等去重 → supersedesId 冲突仲裁（Java 校验归属/类型）→ 容量淘汰 → bigram 词面相关性召回 TopK → 命中计数 | `UserMemoryService`、`UserMemoryExtractor`、`MemoryFingerprints`、`MemoryCandidate` | user_memory | SPEC-014 |
| 三层架构 v2（八项能力） | 结构化 TaskState（约束仅 user_quote 来源+source_message_id）+ schema_version CAS 换版；统一预算 `TokenBudgetManager`（窗口×利用率−输出预留−安全余量，OK/COMPRESS/OVER 三档）；确定性冲突仲裁（纠正>替代、推断不覆盖显式、双推断→pending_review）；MemoryLinker 二跳联合推理；RelativeTimeResolver 相对时间→绝对时间；删除/禁止级联失效（同主题 superseded → 摘要/状态 stale → 双层过滤） | `SessionTaskState`、`TaskStateStore`、`ContextCompressor`、`TokenBudgetManager`、`MemoryConflictResolver`、`MemoryLinker`、`RelativeTimeResolver`、`ConstraintPatterns` | user_memory（scope/provenance/valid_from/until/sensitivity 等新列）、chat_session_summary（task_state JSON） | SPEC-015 |
| Prompt 集中管理 | 注入文本唯一来源 + PROMPT_VERSION 版本常量 + 契约回归测试（锁定时间铁律/防复述等关键规则） | `ChatPromptProvider`（chat-prompt-v3）、`ChatPromptContractTest` | — | SPEC-014 |
| 记忆透明可控 | 用户侧列表/停用/启用/纠正/删除（逻辑删除）/禁止注入 API，全部归属校验 | `UserMemoryController` | user_memory | SPEC-014/015 |

### 3.6 知识库与 RAG（/knowledge、/document）

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 | SPEC |
|---|---|---|---|---|
| 文档摄取 | PDF 解析 → 三种切分策略（fixed 固定 500 字符 / 滑窗重叠 / 吸附断点，**默认 fixed**）→ embedding-3 向量化 → MySQL + ES 双写；重解析幂等（先清旧切片再写入） | `PdfUtil`（splitText/splitTextWithOverlap/splitPages）、`RagServiceImpl` | knowledge_base / knowledge_document / document_chunk / knowledge_chunk | SPEC-001/016/020 |
| 混合检索 | 向量（embedding-3）+ 关键词（BM25/MySQL LIKE）加权融合，**vector-weight=0.9**（60 金标实验：hit@5 92%、MRR 0.835）；ES 四类失败 try-catch + 挂掉自动降级 MySQL | `RagService`、`ChunkEsService` | — | SPEC-016/017 |
| 引用有效性 | `RagCitationGuard` 校验回复引用编号 ∈ 实际提供资料，越界引用记审计不当可信来源；证据标注【资料N｜doc#·chunk#】 | `RagCitationGuard` | — | SPEC-016 |
| 已删/孤儿片防护 | activeDocIds 双保险（SQL 过滤 + 内存过滤），ES 清理失败跳过写入 | `RagServiceImpl` | — | SPEC-017 |
| 短问题召回修复 | ≤2 字误判闲聊 → 改 ≤1 字；MySQL ≤20 片绕过排序 → 统一融合排序；末尾 3 片兜底取消（零相关片不注入） | `RagServiceImpl` | — | SPEC-017 诊断轮 |
| 评测工程化 | Python 离线评测链：60 条人工金标（golden.tsv，语义改写 40 + 关键词 20）→ eval_weight.py（hit@5/MRR/nDCG@5）→ 结果存档 results/；分块对照实验（fixed vs 递归 vs 递归+CCH 头前缀，合成结构语料+50% 重叠对齐）；**递归切分实验结论正向但默认保持 fixed**（含 T-PC5 回归保护） | `tools/rag-eval/eval_weight.py`、`golden.tsv`、`chunk_eval_recursive.py` | — | SPEC-017/020/021 |
| 真实语料多层 RAG | 10 篇官方来源真实旅游资料（九寨沟/故宫/兵马俑等官网）验证 + 知识提炼；Java 零改动轮 | `tools/rag-eval/` | — | SPEC-021 |

### 3.7 旅游规划（/agent/travel、工作台）

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 | SPEC |
|---|---|---|---|---|
| 计划持久化 | 保存/分页列表/详情/更新/删除 5 接口；编辑期字段白名单合并 + 服务端重算费用 + **原子乐观锁**（id+user_id+is_deleted+update_time+plan_json 五条件）阻断 400/401/404/409 | `TravelPlanController`、`TravelPlanServiceImpl` | travel_plan | SPEC-005 |
| 行程编辑重校验 | ItineraryEditValidator E/W 分级校验 → 重校验 → 费用重算 → 乐观锁落库 | `ItineraryEditValidator`、`ItineraryValidator` | — | SPEC-006 |
| 每日候选池 | 每日多景点候选 + 去重（TravelCandidateDedup）+ 可编辑路线；POI 匹配与政策约束 | `TravelFastPlanner`、`TravelPoiMatcher`、`TravelCandidateDedup`、`TravelPolicy` | — | SPEC-010 |
| 费用口径 | 同城/城际交通费用统一核算（TransportAdvisor） | `TransportAdvisor` | — | SPEC-009 |
| 携程风格工作台 | 前端工作台改造（Vue 3）+ 后端分阶段实施（P2-A/B/C） | `TravelController` + frontend | — | SPEC-007/008/011 |
| 真实数据完整性 | 数据源核验、可执行性校验（营业状态/时间窗） | `TravelDataCache`、POI 服务 | — | SPEC-012 |
| 高德数据 | 高德 Web 服务 API（POI/天气/地理编码），WebClient 节流 | `AmapWebClient`（throttle 测试覆盖） | — | — |

### 3.8 景点数据（/scenic）

| 功能 | 技术实现 | 关键类 / 组件 | 数据表 |
|---|---|---|---|
| 景点/评论 | 幂等建表（db/scenic_schema.sql）+ CRUD | `ScenicController` | scenic_spot / scenic_comment |

### 3.9 前端（frontend/）

| 功能 | 技术实现 |
|---|---|
| 单页应用 | Vue 3.4 + TypeScript 5.2 + Pinia 2 状态管理 + Element Plus 2.4 组件库 + Vite 5 构建（dev :3000，占用自动递增） |
| 流式渲染 | SSE（EventSource/fetch-stream）逐 token 渲染，"AI思考中"状态机与终止信号处理 |
| 记忆工作台 | 携程风格规划工作台（SPEC-011）、单日行程详情（SPEC-008）；记忆管理页面后端 API 已就绪（/memory/*） |

---

## 4. SPEC 索引（功能 ↔ 规格 ↔ 状态）

| SPEC | 主题 | 状态 |
|---|---|---|
| 001 | RAG 切片写入链路统一与向量/ES 接线 | 已实现 |
| 002 | AI 端到端质量评估与主链路注入防御 | 已实现 |
| 003 | 认证配置治理与安全加固 | 已实现 |
| 004 | 对象级授权加固（预览/回填/改密令牌） | 已实现 |
| 005 | 旅行计划持久化基础 | 已实现 |
| 006 | 行程编辑、重校验与费用重算（含决策简报） | 已实现 |
| 007 | 旅行规划体验与性能改进（提案/审核/批次1） | 已实现 |
| 008 | 单日行程详情 UI 升级 | 已实现 |
| 009 | 同城交通费用口径统一 | 已实现 |
| 010 | 每日景点候选池与可编辑路线 | 已实现 |
| 011 | 携程风格工作台改造（含 P2 分阶段计划） | 已实现 |
| 012 | 旅游行程真实数据完整性 | 设计稿+P1 已提交 |
| 013 | AI 开发技能库（调研设计） | 设计稿（仓库源+人工同步安装） |
| 014 | 长期记忆 + 统一上下文组装 + Prompt 集中（含 R1 审查修订） | 已实现（R1 审查通过） |
| 015 | 记忆系统三层架构与上下文感知压缩（八项能力） | 已实现（本地验证） |
| 016 | 基于 rag-skills 的 RAG 工程加固（引用守卫/幂等/权重实验） | 已实现 |
| 017 | RAG 评测工程化（金标 60 + 权重复核）+ 召回诊断轮（10 项核实 3 项修复） | 已实现（497/497） |
| 020 | RAG 递归结构感知切分（实验+局部实现，默认关闭） | 实验完成（501/501） |
| 021 | 真实旅游语料验证与多层 RAG 增强 | 已实现（Java 零改动，501/501） |

## 5. 横切关注点

| 关注点 | 实现 |
|---|---|
| 安全 | JWT 无状态认证、RBAC、对象级授权、防提示注入（IntentRouter 三层防御 + 注入文本"系统自动注入"标签 + 角色隔离）、敏感信息正则拒收（密码/手机号/密钥）、参数化 SQL（MyBatis-Plus） |
| 降级 | 记忆/摘要/RAG/ES 任何子系统失败 → 安全默认值（无记忆/窗口/降级 MySQL），绝不阻断聊天主流程 |
| 测试 | JUnit 5 + Mockito + AssertJ，**501/501 全绿**（SPEC-021 时点）；命令 `mvn -pl MindLink_AI_ai -am test`（**必须带 -am**，否则本地仓库过期 SNAPSHOT 导致 NoClassDefFound）；真实模型/DB 验证用 18080 独立实例 |
| 可观测 | memory_strategy/history_tokens/long_term_memories/assembly_millis 响应统计、工具调用审计日志、引用越界审计 |
| 文档治理 | docs/（规范层：AGENTS/API_CONTRACTS/DATA_MODEL/SPEC/ADR）与 doc/（历史层只读）分层；SPEC 驱动开发；过程记忆（MEMORY.md + memory/ HOT/WARM/COLD）与在线业务记忆严格隔离 |
