# 智能旅游路线规划系统对标 TripStar 全面升级设计方案

> 对标对象：开源项目 **旅途星辰（TripStar）** —— 基于大语言模型与多智能体协作的文旅规划平台（GitHub: 1sdv/TripStar，Vue3 + FastAPI，约 2.4k Stars）。  
> 适用范围：本科毕业设计《基于大语言模型的智能旅游路线规划系统设计与实现》的项目迭代与论文撰写。  
> 升级原则：**沿用现有「Vue3 前端 + SpringBoot 后端 + Python Agent」三层架构，不推翻重构**，仅将 TripStar 的成熟能力按本系统技术栈「嫁接移植」。

---

## 一、方案概述

### 1.1 为什么对标 TripStar

TripStar 与本题**同赛道、同技术路线**（大语言模型 + 多智能体 + 地图服务 + 文旅数据），但工程完整度与功能丰富度更高，是天然的「参照系」。对标的价值有三：

1. **补功能**：TripStar 已落地而本系统缺失的能力（偏好记忆、知识图谱、预约提醒、多城市等），可直接借鉴其设计思路；
2. **补叙事**：TripStar 的「多智能体协作」「双引擎预算」「容错解析」等工程点，恰好可以转化为论文的**创新点与实验素材**；
3. **控风险**：TripStar 踩过的坑（大模型输出不稳定、网关超时、LLM 编造景点）已有成熟解法，本系统可直接复用，减少调试成本。

### 1.2 升级目标

在不影响现有核心功能（AI 路线生成、预算分析、地图可视化）稳定运行的前提下，用有限的一学期周期，把系统从「可用」提升到「有亮点、可写进论文、可答辩加分」的水平。目标产出：**8 项升级功能 + 1 套可执行数据库脚本 + 2 个可复用算法模块**。

---

## 二、现状盘点

### 2.1 现有系统架构

| 层级       | 技术栈                                                                               | 工程目录                | 端口   |
| -------- | --------------------------------------------------------------------------------- | ------------------- | ---- |
| 前端       | Vue3 + Element Plus + Axios + ECharts + 高德/OSM 双地图                                | ai-tourism-frontend | 3001 |
| 后端       | SpringBoot 3.5 + MyBatis + MySQL8 + Redis + Sa-Token(JWT) + LangChain4j + Knife4j | ai-tourism          | 8290 |
| AI Agent | Python + FastAPI + LangGraph + Chroma(向量库) + SSE + SQLite Checkpoint + LangSmith  | ai-tourism-agent    | 8291 |

### 2.2 现有能力清单

- 用户管理（注册/登录/JWT/角色权限/刷新令牌）
- AI 路线规划（自然语言 → 结构化行程，SSE 流式逐字渲染）
- AI 旅行问答（复用同一 LLM 接口与 Prompt 体系）
- 多轮对话记忆（Redis 短期记忆 + MySQL 历史回填 + Caffeine 会话级实例隔离）
- 工具调用（POI 景点检索工具、天气工具）
- 景点管理后台 CRUD（106 个真实景点 / 24 个城市，含门票价格）
- 地图可视化（高德 + OSM/Leaflet 双引擎，路线点位标记与规划）
- 预算分析（**LLM 结构化提取 + 规则兜底**双引擎，ECharts 饼图/柱状图）
- 收藏、用户偏好（当前为扁平单表存储）
- 天气分析（Open-Meteo 免费接口）
- RAG 向量检索增强（按城市过滤，注入规划提示）
- 输入护轨（敏感词/注入攻击前置校验）、可观测性（Prometheus 指标）、A/B 测试
- LangGraph 并行工作流（意图识别 → 对话引导 → 天气/景点/RAG 并行 → 路线规划 → 格式化）

> 结论：本系统在**后端工程能力**（会话隔离、护轨、可观测性、RAG）上已不弱于 TripStar，主要差距集中在**面向用户的亮点功能**与**AI 链路的高级编排**。

### 2.3 现有数据库（12 张表）

用户权限体系 5 张（t_user / t_role / t_permission / t_user_role / t_role_permission）、t_refresh_token、会话与消息 2 张（t_ai_assistant_sessions / t_ai_assistant_chat_messages）、t_poi、t_favorite、t_user_preference、t_budget。

---

## 三、TripStar 能力对标矩阵

| #  | 能力项      | TripStar 实现                        | 本系统现状                      | 差距            | 升级建议             | 优先级 |
| -- | -------- | ---------------------------------- | -------------------------- | ------------- | ---------------- | --- |
| 1  | 用户偏好记忆   | 分权重记忆库，含遗忘机制与 TOP-K 召回，自动提取入库      | 扁平单表，生成时未注入                | 缺权重、缺召回、缺自动提取 | **升级项 A：偏好记忆库**  | P0  |
| 2  | 多智能体协作   | 明确分工的天气/酒店/路线 Agent + 工作流协同        | LangGraph 多节点，但未按「智能体」显式抽象 | 缺角色化叙事与校验环节   | **升级项 B：多智能体编排** | P1  |
| 3  | 知识图谱可视化  | 行程数据实时转节点关系图（城市-天数-景点-预算）          | 无（ECharts 仅用于预算图表）         | 完全缺失          | **升级项 C：知识图谱**   | P1  |
| 4  | 景点预约提醒   | 识别需预约景点并醒目标注渠道                     | 无                          | 缺失            | **升级项 D：预约提醒**   | P0  |
| 5  | 结构化输出稳定性 | 五层容错 JSON 解析（清理/引号/截断/暴力提取/LLM 修补） | 有结构化输出，缺多层兜底               | 部分缺失          | **升级项 E：容错解析**   | P0  |
| 6  | 沉浸式伴游问答  | 悬浮窗 + 完整行程上下文记忆                    | 有 AI 问答，无悬浮窗、无行程上下文注入      | 部分缺失          | **升级项 F：伴游问答**   | P2  |
| 7  | 多城市行程规划  | 支持多城市、城际交通日、预算分城市统计                | 单城市                        | 缺失            | **升级项 G：多城市**    | P2  |
| 8  | 行程导出     | 导出图片（含地图）便于分享                      | 无                          | 缺失            | **升级项 H：导出分享**   | P2  |
| 9  | 双地图引擎    | Google + 高德自动降级                    | 高德 + OSM 可切换               | 已有，方向一致       | 保持               | —   |
| 10 | 预算明细面板   | 五类分项 + 图表                          | 五类分项 + 双引擎 + 图表            | **本系统更优**     | 保持并强化            | —   |
| 11 | 小红书攻略提纯  | 抓取真实游记并 LLM 提纯                     | RAG 向量库（自建语料）              | 数据源不同         | 可选：接入真实 UGC      | P3  |
| 12 | 多语言国际化   | 中/英/日 三语 + Prompt 语言自适应            | 仅中文                        | 缺失            | 可选               | P3  |
| 13 | 异步任务防超时  | 轮询 task_id + 进度推送                  | SSE 流式（已规避超时）              | **本系统更优**     | 保持               | —   |

---

## 四、升级总体架构

升级后在原有三层结构上新增「记忆层」与「图谱层」，并把 Agent 层的隐式节点显式化为智能体角色：

```
┌────────────────────────── 前端 (Vue3 + Element Plus) ──────────────────────────┐
│  对话页 · 地图页 · 预算页 · 偏好页 · 收藏页 · 景点后台                             │
│  [新增] 偏好记忆管理页 · 知识图谱组件(ECharts graph) · 伴游悬浮问答窗 · 预约提醒标签  │
└───────────────────────────────────┬───────────────────────────────────────────┘
                                    │ HTTP / SSE
┌───────────────────────────────────▼───────────────────────────────────────────┐
│                     后端 (SpringBoot)                                          │
│  AuthController · ChatController · POIController · BudgetController            │
│  [新增] PreferenceMemoryService（权重+衰减+TOP-K召回）                          │
│  [新增] KnowledgeGraphService（行程 → 节点/边）                                 │
│  [强化] RobustJsonParser（多层容错） · POI 预约字段                              │
│  MySQL(13+表) · Redis · Sa-Token                                               │
└───────────────────────────────────┬───────────────────────────────────────────┘
                                    │ HTTP / SSE
┌───────────────────────────────────▼───────────────────────────────────────────┐
│                     AI Agent (Python + LangGraph)                              │
│  显式智能体：[意图] [景点] [天气] [酒店·新增] [路线编排] [行程校验·新增]            │
│  工具链：POI 工具 · 天气工具 · 酒店工具·新增 · RAG 检索                          │
│  [新增] 多层容错解析 · 偏好注入 · 多城市编排                                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、升级项详细设计

### 升级项 A：用户偏好记忆库（权重 + 遗忘 + TOP-K 召回）

**目标**：让系统「越用越懂你」——自动从历史行程中提炼稳定偏好并加权入库，下次规划时按权重召回注入 Prompt，替代当前「用户手填、生成时不生效」的扁平偏好表。

**设计要点**：

1. **偏好类型**：预算区间、旅行风格、兴趣标签、行程节奏、同行人、饮食禁忌、规避项（如「不喜欢爬山」）。
2. **权重模型**：`weight = base + α × 命中次数`，并施加**时间衰减** `weight ← weight × exp(-λ × Δt)`（半衰期约 30 天），保证近期偏好权重更高。
3. **自动提取**：行程生成成功后异步触发，由 LLM 从行程与对话中抽取稳定偏好，与库中已有项合并（同类型同键加权而非重复插入）。
4. **TOP-K 召回**：规划前按 `weight DESC` 取前 K（默认 8）条且 `weight ≥ θ`（默认 0.2）注入 Prompt。
5. **遗忘机制**：`weight < θ` 或连续 90 天未命中 → 归档或删除，避免记忆膨胀。

**数据库变更**（新增 1 表）：

```sql
CREATE TABLE IF NOT EXISTS t_user_preference_memory (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id       VARCHAR(64)  NOT NULL,
  pref_type     VARCHAR(32)  NOT NULL COMMENT 'budget/style/interest/pace/companion/diet/avoid',
  pref_key      VARCHAR(64)  NOT NULL COMMENT '偏好键，如 interest',
  pref_value    VARCHAR(255) NOT NULL COMMENT '偏好值，如 历史古迹',
  weight        DECIMAL(6,3) NOT NULL DEFAULT 1.000 COMMENT '权重',
  hit_count     INT          NOT NULL DEFAULT 1,
  source        VARCHAR(32)  DEFAULT 'auto' COMMENT 'auto/manual',
  last_hit_time DATETIME     DEFAULT CURRENT_TIMESTAMP,
  created_time  DATETIME     DEFAULT CURRENT_TIMESTAMP,
  modify_time   DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_pref (user_id, pref_type, pref_key, pref_value),
  KEY idx_user_weight (user_id, weight DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户偏好记忆库';
```

**接口设计**：

| 方法     | 路径                          | 说明             |
| ------ | --------------------------- | -------------- |
| POST   | /preference/memory/extract  | 从指定会话抽取偏好并加权入库 |
| GET    | /preference/memory/topk?k=8 | 按权重召回 TOP-K    |
| GET    | /preference/memory/list     | 分页列出全部记忆       |
| DELETE | /preference/memory/{id}     | 删除单条记忆         |

**关键实现（Java 骨架）**：

```java
@Service
@RequiredArgsConstructor
public class PreferenceMemoryServiceImpl implements PreferenceMemoryService {
    private final PreferenceMemoryMapper mapper;
    private static final double ALPHA = 0.10;   // 命中加权
    private static final double LAMBDA = 0.023; // 30天半衰期衰减系数
    private static final double THETA = 0.20;   // 召回/淘汰阈值
    private static final int TOP_K = 8;

    /** 命中加权 + 合并入库 */
    public void upsert(String userId, String type, String key, String value) {
        PreferenceMemory m = mapper.find(userId, type, key, value);
        if (m == null) {
            m = new PreferenceMemory(userId, type, key, value, 1.0, 1);
            mapper.insert(m);
        } else {
            double decayed = m.getWeight() * Math.exp(-LAMBDA * daysSince(m.getLastHitTime()));
            m.setWeight(Math.min(decayed + ALPHA, 5.0));
            m.setHitCount(m.getHitCount() + 1);
            mapper.update(m);
        }
    }

    /** TOP-K 召回 */
    public List<PreferenceMemory> recallTopK(String userId, int k) {
        return mapper.findTopK(userId, k <= 0 ? TOP_K : k, THETA);
    }
}
```

**Prompt 调整**（注入到 Agent 路线规划提示）：

```text
## 用户长期偏好（按权重降序，权重越高越应优先满足）
{preference_memory}

请在行程中优先满足高权重偏好；若与本次显式需求冲突，以本次需求为准。
```

**对应论文章节**：第 4 章「用户偏好建模与记忆库设计」、第 5 章「偏好记忆模块实现」、第 6 章「偏好注入对比实验」。

---

### 升级项 B：多智能体协作编排（显式 Agent 分工 + 行程校验闭环）

**目标**：把现有 LangGraph 的隐式节点显式化为**角色化智能体**，并新增「行程校验 Agent」形成闭环，提升方案的可解释性与论文叙事性。

**设计要点**：

1. **角色划分**：意图理解 Agent、景点检索 Agent、天气 Agent、**酒店推荐 Agent（新增，对应开题报告选做模块⑥）**、路线编排 Agent、**行程校验 Agent（新增）**。
2. **协作模式**：采用 Supervisor 模式——主控 Agent 决策 → 并行子 Agent 执行 → 聚合。
3. **校验闭环**：校验 Agent 对生成结果做一致性检查（预算合计是否等于分项之和、景点是否均来自 POI 库、地理是否顺路、天数是否匹配），不合格则回退路线编排 Agent 重生成（限 1 次），避免「LLM 编造景点」直接交付。

**LangGraph 节点调整**：

```
parallel_trigger ─┬─> fetch_weather ─┐
                  ├─> fetch_poi ─────┼─> plan_route ─> verify_plan ─┬─(通过)─> format_output
                  ├─> fetch_hotel ───┤                               └─(不通过)─> plan_route（回退1次）
                  └─> rag_retrieve ──┘
```

**关键实现（Python 骨架）**：

```python
def verify_plan_node(state: AgentState) -> dict:
    """行程校验智能体：一致性校验，不合格回退重规划。"""
    plan = state.get("route_plan") or ""
    issues = []
    if not plan:
        issues.append("行程为空")
    # 1) 预算合计校验
    if "预算" in plan and not _budget_sum_ok(plan):
        issues.append("预算分项与合计不一致")
    # 2) 景点在库校验（防编造）
    poi_names = _extract_poi_names(plan)
    known = {p["name"] for p in (state.get("poi_list") or [])}
    if known and not poi_names.issubset(known):
        issues.append(f"存在库外景点: {poi_names - known}")
    # 3) 天数一致性
    if state.get("day_count") and _count_days(plan) != state["day_count"]:
        issues.append("行程天数与需求不符")
    return {"verify_issues": issues, "verify_pass": len(issues) == 0}
```

**对应论文章节**：第 4 章「多智能体架构设计」、第 5 章「智能体协作与校验闭环实现」、第 6 章「校验 Agent 拦截率实验」。

---

### 升级项 C：知识图谱可视化

**目标**：把生成的行程数据实时转换为「城市 — 天数 — 景点 — 预算」的节点关系网络，用 ECharts 力导向图呈现，作为系统的可视化亮点。

**设计要点**：

1. **节点类型**：城市（city）、天数（day）、景点（poi）、预算（budget）、建议（tip）。
2. **边关系**：城市→天数（包含）、天数→景点（安排）、景点→预算（消费）、城市→预算（汇总）。
3. **构建位置**：后端 `KnowledgeGraphService` 从 `t_ai_assistant_sessions.daily_routes` + `t_budget` 解析生成 `nodes / edges / categories`，前端 ECharts `graph` 直接消费。

**接口设计**：`GET /trip/graph/{sessionId}` → `{ nodes: [...], edges: [...], categories: [...] }`

**关键实现（Python 可复用模块，见交付物）**：`knowledge_graph.py` 提供 `build_knowledge_graph(plan, budget)`，输出标准化 `{nodes, edges, categories}`。

**对应论文章节**：第 4 章「行程数据组织与图谱建模」、第 5 章「知识图谱可视化实现」。

---

### 升级项 D：景点预约提醒

**目标**：对需要提前预约的景点（如故宫、陕西历史博物馆）在行程中醒目标注预约渠道，避免用户白跑一趟。

**数据库变更**（t_poi 增字段）：

```sql
ALTER TABLE t_poi
  ADD COLUMN need_reservation TINYINT(1) DEFAULT 0 COMMENT '是否需提前预约',
  ADD COLUMN reservation_channel VARCHAR(255) DEFAULT NULL COMMENT '预约渠道',
  ADD COLUMN reservation_note VARCHAR(255) DEFAULT NULL COMMENT '预约提示';
```


**实现要点**：POI 检索工具返回预约字段 → 注入规划 Prompt → LLM 在行程卡片标注「⚠ 需提前预约：<渠道>」→ 前端以醒目标签渲染。

**对应论文章节**：第 5 章「景点数据增强与提示实现」。

---

### 升级项 E：容错 JSON 解析与结构化输出稳定性

**目标**：回应开题报告「核心难点（如何让 LLM 稳定输出结构化数据）」，建立**多层兜底解析器**，把结构化输出成功率提升到接近 100%。

**五层容错策略**：

1. 剥离 Markdown 代码围栏（`json ... `）与前后杂质文本；
2. 修复未转义引号、中文引号、单引号；
3. 截断修复——补齐缺失的 `}` / `]` 括号；
4. 正则暴力提取最外层 `{...}` / `[...]`；
5. 仍失败则调用 LLM 做「修复型二次请求」兜底。

**关键实现（Python 可复用模块，见交付物）**：`robust_json.py` 提供 `parse_llm_json(text)`，返回 `(obj, layer)` 便于统计各层命中率——这正是论文实验数据来源。

**对应论文章节**：第 4 章「结构化输出协议设计」、第 5 章「容错解析实现」、第 6 章「解析成功率对比实验」。

---

### 升级项 F：沉浸式伴游 AI 问答

**目标**：在页面左下角提供悬浮式 AI 问答窗，AI 拥有当前行程的完整上下文，用户可随时追问（如「第三天门票多少钱」「这个安排适合带小孩吗」）。

**实现要点**：前端新增悬浮窗组件；后端 `ChatController` 接收 `sessionId`，把该会话的行程摘要注入 System Prompt，实现「行程感知」问答。

**对应论文章节**：第 5 章「行程上下文问答实现」。

---

### 升级项 G：多城市行程规划

**目标**：支持一次旅行规划多个城市（如「西安 2 天 + 成都 3 天」），自动计算总天数、标注城际交通日、预算与天气按城市分组。

**设计要点**：会话表扩展城市列表字段；Agent 状态增加 `cities` 结构；预算按城市分组统计；天气按城市分别展示。

**对应论文章节**：第 4 章「多城市行程模型」、第 5 章「多城市规划实现」。

---

### 升级项 H：行程导出与分享

**目标**：一键将行程导出为长图（含地图缩略图），便于分享与存档。

**实现要点**：前端 `html2canvas` 截取行程卡片 + 地图组件；或后端用 OpenHTMLToPDF 生成 PDF。

**对应论文章节**：第 5 章「行程导出实现」。

---

## 六、实施路线图

| 阶段              | 升级项                   | 工作量       | 依赖            |
| --------------- | --------------------- | --------- | ------------- |
| **P0（第 1 周）**   | D 预约提醒、E 容错解析、A 偏好记忆库 | 小 / 中 / 中 | 数据库脚本先行       |
| **P1（第 2–3 周）** | B 多智能体编排与校验、C 知识图谱    | 中 / 中     | A 的偏好注入接口     |
| **P2（第 4 周）**   | F 伴游问答、G 多城市、H 导出分享   | 小 / 中 / 小 | 无             |
| **P3（可选）**      | 小红书 UGC 接入、多语言 i18n   | 大         | 外部 Cookie/Key |

**建议顺序**：先跑通数据库脚本（新增表与字段）→ 再落 P0 三项（收益快、风险低）→ 然后做 B/C 两个「论文亮点项」→ 最后补 P2 的体验项。

---

## 七、论文写作建议

### 7.1 章节映射

| 论文章节       | 可写入内容                           |
| ---------- | ------------------------------- |
| 第 3 章 需求分析 | 对标分析（TripStar 能力矩阵）→ 导出功能需求与优先级 |
| 第 4 章 系统设计 | 偏好记忆模型、多智能体架构、知识图谱数据结构、容错输出协议   |
| 第 5 章 系统实现 | 8 项升级的具体实现与关键代码                 |
| 第 6 章 系统测试 | 偏好注入对比、解析成功率、校验 Agent 拦截率三组实验   |
| 第 7 章 总结展望 | 未完成的 P3 项（UGC 接入、i18n）作为展望      |

### 7.2 可提炼的创新点

1. **带时间衰减的用户偏好记忆库与 TOP-K 召回机制**——将「记忆」从静态表单升级为可加权、可遗忘、可召回的动态模型；
2. **「双引擎预算 + 幻觉过滤」的事实约束生成**（在现有预算双引擎基础上强化，防止 LLM 编造景点与价格）；
3. **多智能体协作 + 行程校验闭环**——引入校验 Agent 对生成结果做一致性把关并触发重规划；
4. **多层容错的结构化输出解析**——显著提升 LLM 结构化输出成功率，并给出可量化的实验数据。

### 7.3 可量化的对比实验

| 实验      | 对照组             | 实验组         | 指标             |
| ------- | --------------- | ----------- | -------------- |
| 偏好记忆有效性 | 不注入偏好           | 注入 TOP-K 偏好 | 偏好命中率、人工满意度    |
| 容错解析有效性 | 直接 `json.loads` | 五层容错解析      | 解析成功率、各层命中占比   |
| 校验闭环有效性 | 无校验             | 有校验 Agent   | 库外景点拦截率、重规划触发率 |

---

## 八、交付物清单

1. **数据库升级脚本**：`ai-tourism/sql/upgrade_tripstar.sql`（新增偏好记忆表、知识图谱/行程表、POI 预约字段，含索引与注释）；
2. **可复用算法模块（Python，已跑通验证）**：
   - `ai-tourism-agent/app/utils/robust_json.py` —— 多层容错 JSON 解析器；
   - `ai-tourism-agent/app/utils/knowledge_graph.py` —— 行程知识图谱构建器；
3. **本设计文档**（本文），可直接作为第 4/5 章写作蓝本。
4. **预算硬约束模块（Java，已编译并通过 42 项断言验证）**：
   - `ai-tourism/sql/upgrade_budget_constraint.sql` —— 幂等升级脚本；
   - `ai-tourism/src/main/java/com/example/aitourism/service/BudgetEnvelopeService.java` —— 档次阶梯回退算法与核验再平衡；
   - `ai-tourism/src/main/java/com/example/aitourism/dto/budget/BudgetEnvelope.java` —— 预算封套载体；
   - `ai-tourism/src/test/java/com/example/aitourism/service/BudgetEnvelopeServiceTest.java` —— 11 组场景单元测试。
5. **大模型可插拔配置与向量检索解耦（本次新增）**：
   - `ai-tourism/src/main/resources/application.yml` —— 主模型与小模型切换至智谱 GLM-4.7-Flash，并重写可插拔后端说明；
   - `ai-tourism-agent/app/config.py` —— 默认后端切换，并新增 embedding 独立配置项；
   - `ai-tourism-agent/app/domain/services/rag_retrieval_service.py` —— embedding 客户端改为独立取配置，避免向量库失配；
   - `ai-tourism-agent/.env.example` —— 补充智谱配置与备选后端说明。

> 说明：上述模块与脚本均在本机实际运行验证通过；Java/Vue 侧代码为按现有工程规范给出的实现骨架，落地时按 `ai-tourism` 与 `ai-tourism-frontend` 的既有分层接入即可。

---

## 九、四项技术决策落地

本章记录四项关键技术决策的实现方案与验证结果。四项均已完成编码，其中预算硬约束为本次的核心工程改动。

### （一）地图引擎：统一为高德地图 Web API

前端底图、路线渲染与后端地理编码全部统一到高德，不再使用 OSM / Leaflet。

**表 9-1　高德地图落地位置**

| 层次 | 文件 | 说明 |
| --- | --- | --- |
| 前端地图配置 | `ai-tourism-frontend/src/utils/mapConfig.js` | 新增 MAP_LOCK 锁定开关 |
| 前端地图渲染 | `ai-tourism-frontend/src/utils/mapServiceManager.js` | 高德 JS API 2.0（AMap.Driving / AMap.Adaptor） |
| 后端地理编码 | `ai-tourism/src/main/java/.../ai/tool/WeatherTool.java` | 高德 Web 服务 restapi.amap.com/v3/geocode/geo |

原配置虽然默认值已是高德，但切换函数允许把地图服务改成 OSM，由此产生一个隐蔽的坐标系错位问题：高德返回 GCJ-02（火星坐标系），OSM 底图使用 WGS-84，而数据库中的景点坐标与行程点位坐标都按高德坐标系存储。一旦切换，全部点位会整体偏移约 300 至 500 米，且难以排查。因此引入锁定开关，默认锁定高德，并保留 `VITE_MAP_LOCK=false` 作为对比演示用的逃生开关。

### （二）大模型：OpenAI 兼容可插拔与免密钥通道的边界

业务代码不绑定任何具体模型厂商，切换模型只改配置、不改代码。这里有一个必须说明的架构约束：WorkBuddy 内置免密钥大模型是浏览器侧、按 Origin 精确校验的调用通道，服务端发起的请求没有匹配的 Origin，因此 SpringBoot 后端与 Python Agent 都无法直接调用该通道。这不是实现选择，而是平台的鉴权设计。

**表 9-2　三层调用方的可用模型通道**

| 调用方 | 可用通道 | 说明 |
| --- | --- | --- |
| Vue3 前端页面 | WorkBuddy 免密钥大模型 | 需先为该应用开通云服务，用于伴游问答等前端交互 |
| SpringBoot 后端 | 任意 OpenAI 兼容服务 | 改 base-url / api-key / model-name 即可切换 |
| Python Agent | 任意 OpenAI 兼容服务 | 同上 |

> 当前状态：云服务开通请求返回「云服务资源紧张，请稍后再试」，环境尚未开通，免密钥通道未接通。后端侧已在 `application.yml` 中写明 DeepSeek、国内 OpenAI 兼容服务、本地 Ollama 三类可插拔配置。

### （三）天气工具：直连外部 HTTP 服务

经核实，天气工具本来就是直接联网调用，不经过任何 MCP 中转，链路如下：

```
城市名 → ① 内置城市坐标表（零外调）
        → ② 高德地理编码 restapi.amap.com/v3/geocode/geo
     ↓
经纬度 → Open-Meteo 预报 api.open-meteo.com/v1/forecast（免费、无需 key）
     ↓
      逐日天气（温度 / 降水 / 降雪 / 风速 / 阵风 / 风向）→ 5 分钟 Caffeine 缓存
```

本次做了一处可靠性加固：原实现每次调用都新建 `OkHttpClient`，会产生独立的连接池与线程池，且未设置任何超时，上游挂起时会拖住整个 Agent 工作流。改为全局复用单一客户端并显式设置连接 5 秒、读取 10 秒、整调用 15 秒超时，超时后快速降级为「暂时无法获取天气数据」，保证天气取不到也不会阻塞行程规划。

### （四）预算系统：从「事后估算」升级为「事前硬约束」

这是本次最核心的工程改动，也是论文的主要创新点。

原实现的流程是「生成行程 → 从行程文本提取费用 → 求和 → 展示」。预算仅作为输入提示存在，最终总预算恒等于五个分项之和，用户给的预算不构成任何约束——用户说预算 3000 元，系统可能给出 4800 元的方案。新流程把顺序反过来：解析预算 → 反推预算封套 → 在封套内生成行程 → 核验与再平衡 → 输出。

#### 1. 核心算法：档次阶梯回退

给定总预算、天数与出发地到目的地，先由既有票价模型选出往返大交通，再把剩余可支配预算交给三级消费档次阶梯，自高向低试探，取预算内可承受的最高档。

**表 9-3　三级消费档次参数**

| 档次 | 住宿（元/晚） | 餐饮（元/天） | 市内交通（元/天） | 门票系数 | 其他（元/天） |
| --- | --- | --- | --- | --- | --- |
| 品质 | 480 | 220 | 80 | 1.30 | 120 |
| 舒适 | 260 | 120 | 45 | 1.00 | 60 |
| 经济 | 120 | 70 | 25 | 0.60 | 30 |

```
品质档合计 ≤ 预算 ?  采用品质档
     否则 舒适档合计 ≤ 预算 ?  采用舒适档
          否则 经济档合计 ≤ 预算 ?  采用经济档
               否则 经济档 + 免费景点为主 ≤ 预算 ?  采用并提示
                    否则 判定不可行 → 给出最低可行预算与三类降级路径
```

该算法是 O(3) 的确定性过程，无随机性、无外部依赖，可被单元测试完全覆盖。这正是它相比「让大模型自己估」的优势：可复现、可解释、可验证。以「往返 800 元、5 天、8 个景点」为基准算例：品质档 5548 元、舒适档 3525 元、经济档 2241 元、经济档免门票 1905 元。因此预算 8000 元对应品质档，4000 元对应舒适档，3000 元对应经济档，2100 元对应经济档加免费景点，1200 元则判定不可行（最低需 1505 元）。

#### 2. 核验再平衡：只压不抬

行程生成后用封套核验实际费用：高于封套上限的分项截断到上限，低于上限的分项保持原值（尊重行程实际内容，不虚增）。由于封套各分项之和本身不超过用户预算，截断后总预算必然落在预算内。这是「严格按预算」的工程保证——不靠提示词约束大模型，而靠后置的确定性截断兜底。同时把达成状态与结余写入数据库，供前端展示。

#### 3. 落地清单

**表 9-4　预算硬约束改动清单**

| 层次 | 文件 | 变更 |
| --- | --- | --- |
| 数据库 | `sql/upgrade_budget_constraint.sql` | 新增（幂等）：预算表加 5 个字段，会话表加 2 个字段 |
| 算法 | `service/BudgetEnvelopeService.java` | 新增：档次阶梯 + 可行性判定 + 核验再平衡 |
| 数据模型 | `dto/budget/BudgetEnvelope.java` | 新增：预算封套载体 |
| 实体与 Mapper | `Budget.java` / `BudgetMapper.java` / `Session.java` / `SessionMapper.java` | 新增字段与读写 |
| 服务集成 | `service/impl/BudgetServiceImpl.java` | analyze() 插入建封套、融合、核验再平衡三步 |
| 单元测试 | `test/.../BudgetEnvelopeServiceTest.java` | 新增：11 组场景 |
| Agent 状态 | `app/graph/state.py` | 新增 budget_amount / origin_city |
| Agent 意图 | `app/prompt/intent-recognition-system-prompt.txt` 等 | 新增预算与出发地提取规则、区间校验与多轮继承 |
| Agent 规划 | `app/domain/services/planning_service.py` | 新增预算提示块构建，把预算拆成各分项参考标准注入 Prompt |
| 前端 | `views/BudgetView.vue` | 新增预算达成状态条与出行方案卡片 |

#### 4. 验证结果

Java 封套引擎以 42 项断言覆盖 11 组场景，全部通过，关键结果如下。

**表 9-5　预算封套引擎验证结果**

| 场景 | 输入 | 期望 | 结果 |
| --- | --- | --- | --- |
| 预算充裕 | 8000 元 / 5 天 | 品质档，住宿 480 元/晚，4 晚 | 通过 |
| 预算中等 | 4000 元 / 5 天 | 降级舒适档，合计 3525，记录降级原因 | 通过 |
| 预算紧张 | 3000 元 / 5 天 | 降级经济档，合计 2241，记录 2 次降级 | 通过 |
| 预算极紧 | 2100 元 / 5 天 | 取消收费景点，门票归零 | 通过 |
| 预算不可行 | 1200 元 / 5 天 | 判定不可行，最低需 1505，给出缩短天数建议 | 通过 |
| 未指定预算 | — | 舒适档参考值，状态 UNKNOWN | 通过 |
| 核验再平衡 | LLM 给出 1600 / 2500 / 1200 / 900 / 800 | 截断为 925 / 480 / 350 / 336 / 150，合计 2241 不超过 3000 | 通过 |
| 只压不抬 | 住宿 100、餐饮 50 | 保持原值，产生结余 | 通过 |
| 边界值 | 恰好等于封套合计 | 可行且结余为 0 | 通过 |

Python 侧预算提示块以 9 组「预算 × 天数」组合验证，各分项标准之和全部不超过总预算，例如 4000 元 / 5 天对应大交通 1400 元、住宿 292 元每晚、餐饮 130 元每天，合计 3998 元。分配采用向下取整而非四舍五入，确保分项标准之和永不超过用户总预算。

#### 5. 可直接用于论文的表述

> 本文提出一种预算反推式行程规划方法：将用户给定的总预算作为硬约束，通过档次阶梯回退算法在 O(3) 时间内求出预算内可承受的最高消费档次，并据此生成各分项费用上限（预算封套）；行程生成后再以「只压不抬」的截断规则对实际费用做核验与再平衡，从而在工程上保证输出总预算恒不超过用户给定预算。相比将预算作为提示词软约束交由大模型自行把握的做法，本方法具有确定性、可复现、可单元测试验证的特点。实验表明，在 11 组典型场景下该方法均能将输出总预算收敛至预算之内，包括大模型提取值严重超支的情形。

---

## 十、免费大模型选型与接入

本章说明在免密钥通道不可用的前提下，后端与 Agent 侧改用何种模型服务，以及由此产生的配置解耦改动。除一处 embedding 解耦外，全部改动只涉及配置文件，未触碰任何业务代码。

### （一）选型结论

选型遵循三条硬性条件：一是服务端可直接调用，据此排除仅限浏览器侧的免密钥通道；二是长期免费或免费额度充足，满足毕设期间反复调试的需要；三是遵循 OpenAI 兼容协议，避免把工程绑定到某一厂商的私有 SDK。

需要特别说明的是，**选型结论在实测后被修正**。初步调研阶段依据厂商文档选定 GLM-4.7-Flash，但实测发现该模型持续返回 429 过载，无法用于演示；同时发现同系列的部分模型属思考型，在本项目的短输出场景下会返回空内容。最终改用 **智谱 GLM-4-Flash**，实测可用且与项目现有的 JSON 模式用法兼容。

**表 10-1　候选模型服务对比**

| 服务 | 免费形态 | 关键限制 | 接入地址 |
| --- | --- | --- | --- |
| 智谱 GLM-4-Flash（采用） | 免费，实测可用 | 支持 json_object 模式 | open.bigmodel.cn/api/paas/v4 |
| 智谱 GLM-4.7-Flash（已排除） | 免费，200K 上下文 / 128K 最大输出 | 实测持续 429 过载，重试无效 | 同上 |
| 智谱 GLM-4.5-Flash / GLM-4.5-Air（已排除） | 免费 | 思考型模型，max_tokens 偏小时 content 返回空 | 同上 |
| 硅基流动 SiliconFlow | 30 余个 Free 标签模型，一个 Key 通用 | 模型名区分大小写且须带组织前缀 | api.siliconflow.cn/v1 |
| 火山方舟（豆包） | 每模型 50 万 tokens，另有每日 200 万协作奖励 | 额度按天重置 | ark.cn-beijing.volces.com/api/v3 |
| NVIDIA Build | 不限调用次数，40 次每分钟 | 需手机号验证 | build.nvidia.com |
| DeepSeek 官方 | 新用户 100 万 tokens | 有效期仅 3 天，已不作为默认 | api.deepseek.com/v1 |

> 需要说明的是，免费额度政策变动频繁，上表数据为 2026 年 10 月的公开信息，实际以厂商控制台实时显示为准。例如 DeepSeek 的新用户额度已从 500 万 tokens 缩减至 100 万，且有效期由长期缩短为 3 天。这提示在工程实践中，模型服务应始终通过配置项接入而非硬编码，以便在服务不可用时快速切换。

### （二）接入改动

切换模型只需替换 base-url、api-key、model-name 三个值。这三个值由四个类通过 `@Value` 注解读取，因此业务代码零改动，重启服务即可生效。密钥不写入受版本控制的 application.yml，而是放在被 .gitignore 忽略的 .env.local 中，由启动脚本注入为环境变量。

```yaml
openai:
  api-key:    "${ZHIPU_API_KEY}"
  base-url:   "https://open.bigmodel.cn/api/paas/v4"
  model-name: "glm-4-flash"
```

**表 10-2　大模型接入改动清单**

| 层次 | 文件 | 变更 |
| --- | --- | --- |
| 后端主模型 | `ai-tourism/src/main/resources/application.yml` | openai 块的 base-url 与 model-name 切换为智谱 GLM-4-Flash |
| 后端小模型 | 同文件 openai-small 块 | 同步切换，用于会话标题生成 |
| 配置注释 | 同文件 | 重写可插拔后端说明，并列明三个已实测排除的模型名及原因 |
| 启动脚本 | `ai-tourism/run-backend.sh` | 密钥校验由 DEEPSEEK_API_KEY 改为 ZHIPU_API_KEY，并从 .env.local 加载 |
| 密钥隔离 | `ai-tourism/.gitignore` | 新增 .env.local 忽略规则，避免密钥误提交 |
| Agent 默认值 | `ai-tourism-agent/app/config.py` | openai_base_url 与 openai_model_name 默认值改为智谱 |
| Agent 环境模板 | `ai-tourism-agent/.env.example` | 补充智谱配置项与备选后端注释 |
| 向量检索解耦 | `app/config.py` 与 `app/domain/services/rag_retrieval_service.py` | 新增 embedding 独立配置项，不再复用对话模型配置 |

### （三）必须规避的陷阱：Embedding 与对话模型解耦

改造过程中发现一处隐蔽缺陷。Agent 侧的向量检索服务在构建 Embeddings 客户端时，直接复用了对话模型的 `openai_base_url` 与 `openai_api_key`，而 embedding 模型名却是单独配置的。这带来两个后果：其一，一旦把 base_url 指向新的服务商，embedding 请求也会跟着发往该服务商，而该服务商并无 `text-embedding-3-small` 模型，检索会直接报错；其二，即便新服务商提供 embedding 模型，其向量维度与已入库的 Chroma 集合也不一致，必须整库重建才能恢复检索。

更需要注意的是，这类故障不会在服务启动阶段暴露，而只会在实际触发检索时出现，表现为检索结果为空或异常，容易被误判为「知识库没数据」。因此本次把 embedding 配置从对话模型配置中独立出来，新增 `openai_embedding_base_url` 与 `openai_embedding_api_key` 两项，留空时自动回退到原值。这样既保持了现有向量库的完全兼容，又允许对话模型自由切换。这是本次改动中唯一超出「改三行配置」范围的代码调整。

### （四）模型可用性实测

选型阶段对候选模型逐一做了真实调用探测，结果如下。这一步是必要的：厂商文档标注"免费"并不等于"可用"，实际可用性必须在目标时段实测。

**表 10-3　模型可用性实测结果（2026-10-10）**

| 模型名 | 调用结果 | 说明 |
| --- | --- | --- |
| glm-4.7-flash | HTTP 429 | 返回「该模型当前访问量过大」，间隔重试仍为 429，判定不可用 |
| glm-4-flash | 正常 | content 非空，支持 json_object 模式 |
| glm-4-flash-250414 | 正常 | content 非空 |
| glm-4-air | 正常 | content 非空 |
| glm-4.5-flash | content 为空 | 仅返回 reasoning_content，思考内容占满 max_tokens |
| glm-4.5-air | content 为空 | 同上 |

由此得出两条对工程有直接影响的结论。其一，免费模型存在真实的容量竞争，新发布的 Flash 档反而更容易过载，因此不宜按「版本号越高越好」来选型。其二，思考型模型在短输出场景下会返回空 content——这对本项目的会话标题生成（max_tokens 仅 200）是致命的，且失败方式隐蔽：接口返回 200，只有 content 是空字符串。

### （五）端到端验证

改动后在真实调用链路上做了两组验证，覆盖项目中两种典型用法。

**表 10-4　两条调用链实测结果**

| 场景 | 调用配置 | 实测结果 |
| --- | --- | --- |
| 预算提取（JSON 模式） | glm-4-flash / max_tokens 2000 / response_format=json_object | 返回 `{"transport":800,"hotel":1040,"food":600,"ticket":280,"other":240}`，JSON 解析通过，合计 2960 |
| 会话标题生成 | glm-4-flash / max_tokens 200 | 返回「成都5日游预算」，content 非空 |

第一组结果尤为关键：该返回值可直接送入本方案的预算封套引擎做核验再平衡，说明模型输出与硬约束模块能够无缝衔接。

此外还执行了三项静态校验：`application.yml` 经 YAML 解析确认结构正确，openai 与 openai-small 两块取值符合预期；`config.py` 与 `rag_retrieval_service.py` 通过语法编译检查；embedding 回退逻辑经逐项核对，两项为空时的取值与改动前完全一致，不影响已入库向量。密钥隔离方面，已确认 `.gitignore` 规则能正确匹配 `.env.local`，密钥不会被纳入版本控制。

### （六）部署联调中发现并修复的问题

在真实环境启动联调时，发现三个会直接阻断运行的问题，均已修复。这三项都不是本次改造引入的，而是原有工程在目标机器上的既有缺陷，因长期未做全新环境启动而未被发现。

**表 10-5　启动联调问题与修复**

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 启动即失败，报 `Public Key Retrieval is not allowed` | MySQL 8 默认使用 caching_sha2_password 认证，在 `useSSL=false` 时 JDBC 未允许客户端获取服务端公钥 | JDBC URL 追加 `allowPublicKeyRetrieval=true` |
| 启动失败，报 `Port 57584 was already in use` | 运行环境存在 `SERVER__PORT` 环境变量，被 Spring Boot 宽松绑定识别为 `server.port`，覆盖了 application.yml 中的 8290 | 启动前清除该环境变量（非项目配置项） |
| 接口调用报 `Unknown column 'user_budget' in 'field list'` | 表结构升级脚本未在目标库执行，而 Java 代码已在写入新字段 | 执行 `sql/upgrade_budget_constraint.sql`（幂等，可重复执行） |

第三项尤其值得注意：当代码与数据库结构不同步时，故障发生在写入阶段而非启动阶段。服务能正常启动，健康检查也正常，只有真正调用业务接口才会暴露，排查成本明显更高。这提示数据库升级脚本必须纳入部署清单，并且要设计成幂等的，避免重复执行出错。

联调中还观察到一处边界行为：若在会话记录建立之前调用预算分析接口，预算值虽能正确解析并参与封套计算，但回写会话表的更新会命中 0 行。正常流程中会话先由对话接口创建，因此不影响主链路，但属于可加固点。

### （七）联调验证结果

在上述问题全部修复后，完成了一次完整的真实链路验证，覆盖从注册登录到模型调用再到数据落库的全过程。

**表 10-6　端到端联调结果**

| 环节 | 验证内容 | 结果 |
| --- | --- | --- |
| 用户鉴权 | 注册、登录并获取 JWT | 通过 |
| 预算分析接口 | `POST /budget/analyze`，行程含"预算4000元" | 返回 user_budget 4000、status WITHIN_BUDGET、total 2655、remaining 1345 |
| 档次回退 | 检查 envelope_json | 「品质」档预计 5330 元超预算 1330 元，自动降级「舒适」档，封套合计 3265 |
| 流式对话 | `POST /ai_assistant/chat-stream`（SSE） | 正常流式返回，事件中 model 字段为 glm-4-flash，确认命中新模型 |
| 对话记忆 | 检查 Redis 键 | 写入 `ai:memory:test-session-001` |
| 数据落库 | 检查 t_budget 表 | 五类分项与新字段（user_budget / budget_status / remaining_budget / envelope_json / plan_json）均正确写入 |

其中"档次回退"一项最能说明硬约束机制在真实链路上生效：用户给出 4000 元预算，系统先按品质档试算得出 5330 元超出预算，随即自动降级到舒适档重算，最终封套合计 3265 元、实际花费 2655 元，全程未超过用户给定预算。

### （八）Agent 侧意图识别的两处缺陷与修复

把 Python 侧 Agent（LangGraph）一并接入联调后，暴露出两处此前仅靠单元测试无法发现的缺陷。这两处与本次模型替换无关，属于原有代码，但会让 Agent 主链路整体退化。

**缺陷一：意图识别结果丢字段。** `recognize_intent()` 的返回字典只包含 intent_type、city_name、day_count、customization_requirements、confidence、guidance_reason 六项，而 `_apply_rule_validation()` 中已解析出的 `budget_amount` 与 `origin_city` 没有被带回。下游节点 `llm_intent_recognition_node` 其实已经写好了接收逻辑（分别用于预算硬约束输入与出发地里程估算），但取到的永远是 None，只能回退到 state 中的旧值，而 state 中同样为空。后果是：预算硬约束引擎在 Agent 链路上始终处于空转状态——不报错、不告警，只是静默失效。

**缺陷二：多城市校验把出发地误判为竞争目的地。** `_validate_city_name()` 会在 user_input 中扫描全部已知城市，只要命中两个及以上就判定为多目的地，清空 city_name 并转入引导模式。但"从广州出发去成都"这类表述里，广州是起点而非目的地，同样会被计入。于是 city_name 被清空、意图被改写为 tourism_need_guidance，进入对话引导节点；而引导节点又无法从后续回答中消除这个矛盾（用户回答里通常仍会带上出发地），形成引导死循环。

值得说明的是，提示词本身是对的：`intent-recognition-system-prompt.txt` 的示例中已明确给出"从广州出发去成都玩4天，预算3000元 → city_name=成都, origin_city=广州"，模型也确实按此正确输出（日志中 city_name=成都、day_count=3、confidence=0.95）。问题完全出在模型之后的程序规则层——规则层以过于简单的方式覆盖了正确的模型输出。

**修复方式**

1. `_validate_city_name()` 增加 origin_city 形参，统计多城市时先剔除出发地；同时保留"origin_city 未知时仍按原逻辑判定"的行为，使防护能力不被削弱。
2. `_apply_rule_validation()` 与 `recognize_intent()` 补齐 budget_amount、origin_city 的透传，并对 origin_city 做与 city_name 一致的轻量清洗。
3. 降级路径 `_fallback_extraction()` 此前完全不具备出发地与预算提取能力，补充基于"从X出发"模式与预算正则的提取，使模型不可用时的降级行为与主路径保持一致。

**表 10-7　意图识别修复前后对照**

| 观察点 | 修复前 | 修复后 |
| --- | --- | --- |
| 意图识别结果 | tourism_need_guidance, city_name=None | tourism, city_name=成都 |
| 多城市告警 | 触发，['广州','成都'] 判为多城市 | 不触发 |
| budget_amount | 未返回（恒为 None） | 3000.0 |
| origin_city | 未返回（恒为 None） | 广州 |
| 路由去向 | 对话引导节点（循环） | 主规划流程 |
| 最终输出 | 反复追问"是以成都为中心吗" | 完整三日行程＋费用表，合计 3000 元 |
| 预算约束注入 | 未生效 | `[PLANNING] 已注入预算约束: 总额4000元 / 4天` |

修复后做了三组回归验证，确认没有把真正的多目的地防护一起放掉。

**表 10-8　意图识别回归验证**

| 输入 | 预期 | 实际 |
| --- | --- | --- |
| 我想去成都和重庆玩5天，预算5000元 | 继续引导（真多目的地） | 引导："以成都为中心还是重庆呢？" |
| 我想去成都玩3天，预算3000元 | 直接出行程 | 完整三日行程＋费用表 |
| 从上海出发去西安玩4天，预算4000元 | 直接出行程 | 完整行程，注入预算约束 4000 元 |

另补充一组不依赖模型的离线校验，覆盖出发地豁免、真多城市拦截、非法地理词拦截、出发地后缀清洗、降级路径提取与字段透传共 18 项断言，全部通过。

**方法论提醒。** 这组缺陷的排查过程说明：模型输出正确并不等于链路正确。本例中模型表现完全符合预期，问题出在其后的确定性规则层，而规则层的覆盖是静默的——不抛异常、不打错误日志，只把意图悄悄改写成另一条分支。因此对"模型＋规则"混合架构，测试重点应放在规则层对模型输出的改写行为上，而不是模型自身的准确率。

**联调环境陷阱。** Agent 以 `python -m uvicorn app.main:app` 方式启动时，`app/main.py` 中 `__main__` 分支里的 `reload=True` 并不会生效——该参数只在直接执行 `python app/main.py` 时才被读取。这会导致修改代码后服务仍以旧代码运行，排查时极易误判为"修复无效"。重启时显式加上 `--reload` 即可；本文档中所有结论均以日志行号与源码行号的对应关系确认过代码确实已重载。

补充一点后续踩到的细节：即使加了 `--reload`，如果监听范围是**整个工程目录**（包含 `.venv`，里面有几万个文件），实测会出现 `app/` 下的改动不被触发的情况。把监听范围收窄到源码目录（`--reload-dir app`）后，重载才稳定可靠。

### （九）天气工具联网实时化

联调中发现行程里的天气段落始终是"无法获取实时天气信息"，但系统并不报错，只是静默降级。逐层排查后确认，这不是单一原因，而是**三层配置叠加**的结果。

**第一层：提供商指向了未配置的服务。** `.env` 中 `WEATHER_PROVIDER=qweather`，但和风天气所需的 JWT 四项（`QWEATHER_API_HOST` / `JWT_PROJECT_ID` / `JWT_KEY_ID` / `JWT_PRIVATE_KEY_PATH`）全部为空，`_generate_qweather_jwt()` 必然返回 None，于是每次调用都先白白走一遍和风分支再回退。

**第二层：回退目标同样缺密钥。** 回退到的 openweathermap 分支，其地理编码步骤 `_get_city_coordinates()` 依赖 `OPENWEATHER_API_KEY`，而该值为空，直接返回 `(None, None)`，最终提示"获取城市经纬度失败"。**关键在于：真正取数的 Open-Meteo 预报接口本身是免密钥的**，被卡住的只是它前面那道地理编码。

**第三层：备用密钥不可用。** 尝试改用项目里已有的高德 Key 做地理编码，结果两个 Key 都不可用于服务端调用：一个报 `USERKEY_PLAT_NOMATCH`（是 JS API Key，不能用于 Web 服务接口），另一个报 `INVALID_USER_SIGNATURE`（该 Key 启用了数字签名，服务端调用需额外用私钥生成 `sig`，而项目里没有对应私钥）。

**表 10-9　天气链路各环节实测**

| 环节 | 接口 | 是否需要密钥 | 实测结果 |
| --- | --- | --- | --- |
| 地理编码 | Open-Meteo geocoding | 否 | 受限网络下不可达（超时/502） |
| 地理编码 | OpenWeather geocoding | 是 | 无密钥时返回 401 |
| 地理编码 | 高德 geocode | 是 | JS Key 报 10009；另一 Key 报 10007 需签名 |
| 预报取数 | Open-Meteo forecast | 否 | **200，正常返回逐日数据** |

结论是：**联网实时取天气在技术上完全可行，且不需要任何密钥**；唯一障碍是地理编码这一环。

**修复方案：三级降级的地理编码 + 熔断**

1. **首选 Open-Meteo 地理编码**（免密钥、覆盖全球）——正常网络下即走此路，完全联网实时；
2. **次选 OpenWeather 地理编码**——仅在配置了 `OPENWEATHER_API_KEY` 时尝试，保留原有兼容性；
3. **兜底本地城市坐标表**——内置 130 余个中国城市（直辖市、省会/首府、热门旅游城市）的经纬度，用于受限网络或离线场景；
4. **熔断**——联网地理编码连续失败 2 次后进入 300 秒冷却期，冷却期内直接走本地表。实测受限网络下首次调用需等约 7.7 秒超时，熔断后降到约 2.0 秒。

同时把 `.env` 的 `WEATHER_PROVIDER` 从 `qweather` 改回 `openweathermap`，消除每轮无意义的和风分支尝试。

**验证结果**

**表 10-10　天气工具验证结果**

| 城市 | 结果 |
| --- | --- |
| 成都市（带"市"后缀） | 实时数据，10-11 气温 17.6~23.7℃ |
| 杭州 | 实时数据，10-11 气温 16.5~26.2℃ |
| 丽江 | 实时数据，10-11 气温 6.8~20.8℃ |
| 三亚（端到端） | 实时数据，10-11 气温 23.4~31.1℃ |
| 廊坊（不在本地表） | 优雅降级，提示"获取城市经纬度失败"，不影响行程主体 |

端到端日志确认全链路打通：`调用天气工具 → Open-Meteo 地理编码超时 → 本地坐标表兜底 三亚 → 天气查询成功`，天气数据随后被注入行程规划 Prompt。

**顺带发现的两处集成断点。** 排查过程中还暴露出 Agent 向 Java 后端发起的两个调用所对应的接口**在 Java 侧根本不存在**，且都已实际返回 404：

**表 10-11　Agent 期望但后端缺失的接口**

| Agent 侧调用 | 期望的后端接口 | 实际结果 |
| --- | --- | --- |
| `poi_search` 工具 | `GET /api/tools/poi` | 404（后端只有 `/poi/page`、`/poi/cities`，无 `/api/tools/*`） |
| `callback_service` 结构化输出回传 | `POST /ai_assistant/callback` | 404（后端 `/ai_assistant` 下只有 `session_modify`、`get_history`、`session_list`） |

这两处的影响都是"静默降级"：POI 查询失败后返回错误 JSON，但上层日志仍打印"POI 查询成功"，导致下游"POI 数据解析失败，跳过经纬度填充"；结构化输出回传失败只记一条 WARNING，前端拿不到带经纬度的结构化行程。由于行程正文仍能正常生成，这两个问题在只看最终输出时很容易被忽略，属于典型的"链路局部断裂但不影响主流程"缺陷，需要专门核对接口清单才能发现。
