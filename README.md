# AI 智能旅游规划助手

> 基于大语言模型的智能旅游路线规划系统 · 毕业设计项目
>
> 一个仓库包含全部三个服务：Java 后端、Python Agent 引擎、Vue3 前端。

用户用自然语言描述出行需求（"广州出发，去银川玩三天，预算两千"），系统自动完成意图识别 → 多轮引导补全 → 天气/景点数据并行获取 → 生成结构化行程 → 基于真实数据源做预算分析 → 高德地图可视化路线。

---

## 目录

- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [详细配置](#详细配置)
- [数据库初始化](#数据库初始化)
- [项目结构](#项目结构)
- [核心功能](#核心功能)
- [数据采集脚本](#数据采集脚本)
- [UI 设计技能（skills/）](#ui-设计技能skills)
- [常见问题](#常见问题)
- [毕设改造说明](#毕设改造说明)

---

## 快速开始

### 1. 启动依赖服务

```bash
# MySQL 8.0+ 与 Redis 5.0+ 必须先于后端启动
# 创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS aitourism DEFAULT CHARSET utf8mb4;"
```

### 2. 按顺序启动三个服务

**① 后端（Java，端口 8290）**

```bash
cd ai-tourism
# 配置密钥（见「详细配置」），写入 .env.local 后启动
mvn -DskipTests spring-boot:run
```

**② Agent 引擎（Python，端口 8291）**

```bash
cd ai-tourism-agent
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows
# source .venv/bin/pip install -r requirements.txt  # Linux/Mac
cp .env.example .env      # 填入你的大模型 Key
python run.py
```

**③ 前端（Vue3，端口 3001）**

```bash
cd ai-tourism-frontend
npm install
npm run dev
```

### 3. 打开使用

| 服务 | 地址 | 说明 |
|---|---|---|
| **前端主界面** | **http://localhost:3001/index.html** | ⚠️ 必须带 `/index.html`，直接访问根路径会 404 |
| Agent 对话页 | http://localhost:8291/ | Python 服务自带的独立聊天页 |
| 后端接口 | http://localhost:8290/ | 接口文档：http://localhost:8290/doc.html |

> 首次使用请先注册账号。演示账号：`13900000001` / `123456`。

---

## 系统架构

```
┌─────────────────────┐
│  前端 Vue3 + Vite   │  3001   智能对话 / 我的行程 / 预算分析 / 地图路线
└──────────┬──────────┘
           │ HTTP
┌──────────▼──────────┐
│  后端 SpringBoot3   │  8290   用户鉴权(Sa-Token) / 会话管理 / 预算引擎
│  Java21 + MyBatis   │         景点库 / 城市坐标 / 价格数据
└──────────┬──────────┘
           │ HTTP / SSE
┌──────────▼──────────┐
│ Agent LangGraph      │  8291   意图识别 / 多轮引导 / 行程生成
│ FastAPI + Chroma     │         天气工具 / RAG 攻略检索
└─────────────────────┘
      │                    │
   MySQL 3306          Redis 6379
```

职责划分：前端负责交互与地图渲染；后端负责业务数据、权限和**预算规则引擎**（保证价格可解释、可对账）；Agent 负责自然语言理解与行程生成（LangGraph 状态机 + Checkpoint 多轮持久化）。

---

## 环境要求

| 组件 | 版本 | 备注 |
|---|---|---|
| JDK | 21+ | 项目已验证 IntelliJ 捆绑 JDK / jbr |
| Maven | 3.6+ | 也可用 IDEA 内置 Maven |
| Python | 3.11+ | 推荐 3.12 |
| Node.js | 18+ | 推荐 20/22 |
| MySQL | 8.0+ | 库名 `aitourism` |
| Redis | 5.0+ | 用于会话缓存 |

---

## 详细配置

### 后端 `ai-tourism/.env.local`

```ini
# 高德地图 MCP（行程规划、POI 检索）
AMAP_MCP_KEY=你的高德Key
# 高德 Web 服务（天气地理编码）
AMAP_WEB_API_KEY=你的高德Web服务Key
# 智谱大模型（预算/规划 LLM 调用）
ZHIPU_API_KEY=你的智谱Key
# 聚合数据火车票价（可选，留空则降级为 12306 本地票价表）
JUHE_TRAIN_API_KEY=
```

> ⚠️ 该文件**已在 `.gitignore` 中排除**，不会提交到仓库。
> 仓库中的 `application.yml` 全部为 `${环境变量}` 占位符，**不包含任何真实密钥**。

数据库连接在 `ai-tourism/src/main/resources/application.yml` 中修改（默认 `root/123456`，库 `aitourism`）。

### Agent `ai-tourism-agent/.env`

```ini
OPENAI_API_KEY=你的Key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
OPENAI_MODEL_NAME=glm-4-flash
OPENAI_MAX_OUTPUT_TOKENS=4000
```

> 用的是 OpenAI 兼容协议，改 `base-url + api-key + model-name` 即可切换任意模型服务（智谱/DeepSeek/本地 Ollama）。

---

## 数据库初始化

按顺序执行 `ai-tourism/sql/` 下的脚本：

```bash
mysql -u root -p aitourism < ai-tourism/sql/create_table.sql       # 建表（必须）
mysql -u root -p aitourism < ai-tourism/sql/seed_poi.sql           # 景点基础数据
mysql -u root -p aitourism < ai-tourism/sql/price_real_data.sql    # 酒店价格快照表
mysql -u root -p aitourism < ai-tourism/sql/seed_ticket_price.sql  # 门票价格
```

其余 `upgrade_*.sql` 为迭代升级脚本，按需执行（详见各文件注释）。

---

## 项目结构

```
.
├── ai-tourism/              # 后端 SpringBoot（8290）
│   ├── src/main/java/.../   #   controller / service / mapper / util
│   ├── src/main/resources/  #   application.yml、票价表、城市中心表
│   ├── sql/                 #   建表与数据脚本
│   └── script/              #   补录脚本
├── ai-tourism-agent/        # AI 引擎 FastAPI（8291）
│   ├── app/                 #   LangGraph 图、工具、RAG、提示词
│   ├── script/scrape/       #   数据采集脚本（景点/票价/价格）
│   ├── web/chat.html        #   独立聊天页
│   └── run.py
├── ai-tourism-frontend/     # 前端 Vue3 + Vite（3001）
│   └── src/
│       ├── views/           #   ChatView / PlansView / BudgetView
│       ├── components/      #   RouteMap 地图等
│       └── styles/          #   主题令牌（极简科技深色）
├── skills/                  # 本项目用到的 UI 设计技能（见下文）
└── README.md
```

---

## 核心功能

### 智能规划
自然语言对话式规划。Agent 会先识别意图，关键信息（出发地、天数、预算、偏好）缺失时主动追问，补全后并行拉取天气与景点数据，生成按天组织的行程 + 地图路线点。

### 预算分析（本项目的重点改造）
不是让大模型"拍脑袋报价"，而是**数据真实性分层**：

| 层级 | 数据 | 来源 |
|---|---|---|
| L1 真实 | 火车票价 | 12306 实爬票价表 / 聚合数据 API |
| L2 快照 | 酒店房价、景点门票 | 价格快照表 + 联网检索采集（带采集日期） |
| L3 估算 | 市内交通、餐饮 | 按城市消费等级系数估算 |

每条费用明细都标注 `priceSource`（来源）与 `confidence`（置信度），**绝不把估算包装成真实价格**。

关键规则：
- **往返车费必须计入**（提示词与引擎双重强制，禁止把往返价除以 2）
- 预算优先取用户文本里写的金额，而非会话表历史残留值
- 真实票价优先于攻略文本里的价格（避免 LLM 编造）

### 地图路线
高德地图渲染每日景点。所有坐标都经过**城市一致性校验**——偏离城市中心超过 80km 的坐标会被丢弃并重新从景点库获取，防止"银川的回民街画到西安""福州的西湖画到杭州"这类同名景点串城问题。

---

## 数据采集脚本

位于 `ai-tourism-agent/script/scrape/`：

| 脚本 | 用途 |
|---|---|
| `build_city_list.py` | 从高德行政区划生成全国城市清单（391 城） |
| `build_city_centers.py` | 用景点库坐标取中位数，生成各城市中心点（389 城） |
| `fetch_poi_by_city.py` | 全国景点补录（支持 `--all/--tier/--province`，断点续传） |
| `fetch_train_price_http.py` | 12306 HTTP 接口高速抓取真实票价 |
| `enrich_price_by_search.py` | 联网检索采集门票 / 酒店真实挂牌价 |
| `fix_daily_routes_coords.py` | 清洗历史会话中串城市的错误坐标 |

---

## UI 设计技能（skills/）

本项目界面设计使用了以下两个技能，已随仓库提供，可直接安装到 WorkBuddy / Claude 使用：

### `skills/ui-ux-pro-max`
UI/UX 设计决策引擎。内含风格、配色、字体、图表、图标、动效、UX 规范、产品形态等检索表（CSV），做设计选型时可直接查表而不是靠感觉。

### `skills/ui-styling`
shadcn/ui + Tailwind 组件实现技能，含画布设计所需的字体资源。

**安装方法**——复制到用户级技能目录即可：

```bash
# WorkBuddy
cp -r skills/* ~/.workbuddy/skills/

# Claude Code
cp -r skills/* ~/.claude/skills/
```

本项目的界面最终风格为**「极简科技（深色）」**：中性近黑底（`#08090A` / `#111214`）、发丝级 1px 描边、单一强调色青 `#22D3EE`、大量留白、无彩色光晕。
无障碍底线：文字对比度 ≥ 4.5:1、触控目标 ≥ 44px、全键盘可达、支持 `prefers-reduced-motion`。

---

## 常见问题

**Q：前端 `http://localhost:3001/` 打不开？**
A：必须访问 `http://localhost:3001/index.html`，根路径 404 是 Vite 配置所致。

**Q：`/actuator/health` 返回 503？**
A：Windows 版 Redis 5.0 的 INFO 格式导致 Spring 误判，**不影响业务**。用 `redis-cli ping` 返回 `PONG` 即正常。

**Q：`/v3/api-docs` 报 500？**
A：springdoc 文档生成问题，`/doc.html` 正常，不影响业务。

**Q：Java 启动后端口不是 8290？**
A：若环境变量里有 `SERVER__PORT`，Spring 宽松绑定会劫持 `server.port`。启动前执行 `Remove-Item Env:SERVER__PORT`。

**Q：改了票价 JSON 没生效？**
A：`src/main/resources/price/train_price_local.json` 是**启动时一次性读入内存**的，改完必须重启 Java。

**Q：为什么酒店房价不是"实时"的？**
A：携程/美团/飞猪等 OTA 官方 API 均要求**企业分销资质**（个人无法申请），直抓会被登录墙拦截，高德也不提供价格字段。当前方案为"真实挂牌价 + 采集日期 + 按需补采"，已尽力接近真实。

---

## 毕设改造说明

相比原始版本，本项目重点补齐了以下短板（对应开题报告中的设计要求）：

1. **预算价格真实性** —— 建立三级价格链，拒绝 LLM 凭印象报价；往返交通强制计入；每条明细可溯源。
2. **地理一致性** —— 建立 389 城中心坐标表，对 LLM 自带坐标做偏离校验，修复同名景点串城。
3. **全国数据覆盖** —— 景点库从零星城市扩充到 389 城 / 7226 条；票价覆盖全国主要城市对。
4. **界面统一** —— 前后端界面统一为「极简科技」深色设计语言，符合无障碍规范。
5. **交互闭环** —— 智能规划完成后可直接跳转预算分析并自动载入行程，无需手动复制粘贴。

---

## 说明

- 仓库默认排除了毕业论文文档（含学号、姓名等个人信息）与所有密钥文件，见 `.gitignore`。
- 如需把论文材料一并提交，删除 `.gitignore` 中"毕业论文文档"一段即可。
- 项目中的第三方 API（高德、智谱、聚合数据）Key 需自行申请，本仓库不含任何可用密钥。
