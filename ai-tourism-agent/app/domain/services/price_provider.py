"""价格数据提供者（PriceProvider）—— 预算真实化的核心数据层。

设计目标（对应论文「数据真实性分层」设计）：
    预算系统的一切价格都必须可溯源，**拿不到真实价格时明确标注为估算，绝不把估算伪装成真实价格**。

三级降级链（任一层失败自动落入下一层，永不阻断规划）：
    1. RealApi   真实 API：火车票走聚合数据/极速数据（同步 12306 各席别票价）
    2. Snapshot  快照数据：酒店价格快照表（季度采集，标注来源与采集日期）、
                          景点库 t_poi.ticket_price（真实票价）
    3. Model     系数估算：里程×票价系数、分档均价表（兜底，confidence=low）

所有价格统一封装为 PriceQuote，携带：
    price       金额（元）
    source      TRAIN_API / SNAPSHOT / ESTIMATE
    as_of       数据日期（真实/快照价为采集日，估算为生成日）
    confidence  high / medium / low
    note        人类可读说明（如「高铁二等座·聚合数据(12306同步)」）

Java 侧工具接口契约（/api/tools/*，由 ai-tourism 提供）：
    GET /api/tools/city-distance?origin=&dest=  → {km}
    GET /api/tools/poi?city_name=&count=        → {poi_list:[{poi_name,ticket_price,...}]}
    GET /api/tools/train-price?origin=&dest=&date= → {quotes:[{seat_type,price}], as_of}
    GET /api/tools/hotel-price?city=&tier=      → {price_per_night, sample_hotel, as_of}
"""
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from loguru import logger

from app.config import settings

# 待抓票价队列：真实票价缺失时记录城市对，供爬虫批量补抓，
# 使「全国城市覆盖」随使用渐进收敛，而不是靠人工猜测该抓哪些线。
PENDING_FILE = (Path(__file__).resolve().parents[2] / "script" / "scrape"
                / "pending_pairs.json")
_PENDING_LOCK = threading.Lock()


PENDING_PRICE_FILE = (Path(__file__).resolve().parents[2] / "script" / "scrape"
                      / "pending_prices.json")


def note_missing_price(kind: str, city: Optional[str]) -> None:
    """记录缺真实价的城市（kind = hotel / ticket）。

    联网检索额度有限（实测 glm-4-flash 的 web_search 在批量调用后会静默返回空，
    不再触发检索），全国批量采集不可持续。因此改为「用多少采多少」：
    预算真正用到某城市却无真实价时才记录，之后由
    `enrich_price_by_search.py --pending` 针对性补采。
    """
    if not city:
        return
    try:
        with _PENDING_LOCK:
            data = {"hotel": [], "ticket": []}
            if PENDING_PRICE_FILE.exists():
                try:
                    loaded = json.loads(PENDING_PRICE_FILE.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = {"hotel": list(loaded.get("hotel") or []),
                                "ticket": list(loaded.get("ticket") or [])}
                except Exception:  # noqa: BLE001
                    pass
            bucket = data.setdefault(kind, [])
            if city not in bucket:
                bucket.append(city)
                data["updated_at"] = date.today().isoformat()
                PENDING_PRICE_FILE.parent.mkdir(parents=True, exist_ok=True)
                PENDING_PRICE_FILE.write_text(
                    json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 —— 记账失败绝不能影响主流程
        logger.debug(f"[PRICE] 记录缺价城市失败: {e}")


def note_missing_train_pair(origin: Optional[str], dest: Optional[str]) -> None:
    """记录一条缺失真实票价的城市对（去重、线程安全、失败静默）。"""
    if not origin or not dest:
        return
    key = f"{origin}-{dest}"
    try:
        with _PENDING_LOCK:
            data = {}
            if PENDING_FILE.exists():
                try:
                    data = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    data = {}
            pairs = data.get("pairs") or []
            if key not in pairs:
                pairs.append(key)
                data["pairs"] = pairs
                data["updated_at"] = date.today().isoformat()
                PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
                PENDING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    except Exception as e:  # noqa: BLE001 —— 记账失败绝不能影响主流程
        logger.debug(f"[PRICE] 记录待抓城市对失败: {e}")


# =====================================================================================
# 价格quote数据结构
# =====================================================================================

@dataclass
class PriceQuote:
    """一条带溯源信息的价格"""
    price: Decimal
    source: str            # TRAIN_API | SNAPSHOT | ESTIMATE
    as_of: str             # YYYY-MM-DD
    confidence: str        # high | medium | low
    note: str = ""

    @property
    def is_real(self) -> bool:
        """是否为真实数据（API 或快照），估算返回 False"""
        return self.source in ("TRAIN_API", "SNAPSHOT")

    def label(self) -> str:
        """人类可读的来源标签，用于 Prompt 与前端展示"""
        if self.source == "TRAIN_API":
            return f"真实票价·{self.note}（{self.as_of}）"
        if self.source == "SNAPSHOT":
            return f"快照价·{self.note}（{self.as_of}）"
        return f"系统估算（{self.as_of}）"


def _d(v) -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("1"))
    except Exception:
        return Decimal("0")


def _today() -> str:
    return date.today().isoformat()


# =====================================================================================
# 消费档次阶梯（与 Java BudgetEnvelopeService.TIERS 保持同一口径，
# 保证 Agent 侧 Prompt 约束与 Java 侧预算封套核验使用完全相同的档次参数）
# =====================================================================================

@dataclass(frozen=True)
class SpendTier:
    name: str
    hotel_per_night: Decimal   # 住宿（元/晚）
    food_per_day: Decimal      # 餐饮（元/天）
    local_per_day: Decimal     # 市内交通（元/天）
    ticket_factor: Decimal     # 门票系数（相对平均票价）
    other_per_day: Decimal     # 其他（元/天）
    hotel_desc: str
    food_desc: str


TIERS: List[SpendTier] = [
    SpendTier("品质", Decimal("480"), Decimal("220"), Decimal("80"), Decimal("1.30"), Decimal("120"),
              "高档酒店 / 精品民宿", "特色餐饮为主"),
    SpendTier("舒适", Decimal("260"), Decimal("120"), Decimal("45"), Decimal("1.00"), Decimal("60"),
              "舒适型连锁酒店", "常规餐饮"),
    SpendTier("经济", Decimal("120"), Decimal("70"), Decimal("25"), Decimal("0.60"), Decimal("30"),
              "青旅 / 经济型连锁", "简餐为主"),
]

# 门票均价兜底（元/景点），与 Java 端 TICKET_AVG 口径一致
TICKET_AVG = Decimal("70")


# =====================================================================================
# PriceProvider
# =====================================================================================

class PriceProvider:
    """价格数据提供者：三级降级取价 + 预算档次阶梯 + Prompt 约束块构建"""

    def __init__(self):
        self.base = (settings.java_service_url or "http://localhost:8290").rstrip("/")
        self.token = settings.java_service_internal_token
        self._today = _today()

    # ---------------- 基础 HTTP ----------------

    def _get(self, path: str, params: dict) -> Optional[dict]:
        """调用 Java 工具接口；任何失败都返回 None（由调用方降级），绝不抛出"""
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            # trust_env=False：避免 localhost 请求被系统代理拦截（与 poi.py 一致）
            with httpx.Client(timeout=6.0, trust_env=False) as client:
                resp = client.get(f"{self.base}{path}", params=params, headers=headers)
                if not resp.is_success:
                    logger.debug(f"[PRICE] {path} HTTP {resp.status_code}，降级处理")
                    return None
                data = resp.json()
                # Java 统一返回 BaseResponse：{code, message, data}
                # 注意：本项目 Java 端成功码为 0（Constants.STATUS_SUCCESS），同时兼容 200
                if isinstance(data, dict) and "data" in data and data.get("code") in (0, 200):
                    return data.get("data")
                if isinstance(data, dict) and data.get("code") not in (None, 0, 200):
                    logger.debug(f"[PRICE] {path} 业务失败: {data.get('message')}")
                    return None
                return data
        except Exception as e:
            logger.debug(f"[PRICE] {path} 调用异常: {e}，降级处理")
            return None

    # ---------------- ① 城市间距离（真实坐标库） ----------------

    def city_distance_km(self, origin: Optional[str], dest: Optional[str]) -> Optional[Decimal]:
        if not origin or not dest or origin == dest:
            return None
        data = self._get("/api/tools/city-distance", {"origin": origin, "dest": dest})
        if not data:
            return None
        km = data.get("km")
        if km is None:
            return None
        try:
            km = Decimal(str(km))
        except Exception:
            return None
        return km if km > 0 else None

    # ---------------- ② 火车票（真实 API → 缓存 → 系数模型） ----------------

    def train_round_trip(self, origin: Optional[str], dest: Optional[str],
                         budget: Optional[float] = None,
                         dist_km: Optional[Decimal] = None) -> PriceQuote:
        """往返大交通价格。

        优先查真实票价 API（Java 代理聚合数据/极速数据，同步 12306）；
        失败降级到里程系数模型（与 Java chooseTransport 同一口径）。
        """
        mode, one_way, source, note = self._train_quote(origin, dest, budget, dist_km)
        if source == "TRAIN_API":
            return PriceQuote(_d(one_way * 2), "TRAIN_API", self._today, "high", note)
        return PriceQuote(_d(one_way * 2), "ESTIMATE", self._today, "low", note)

    def _train_quote(self, origin, dest, budget, dist_km) -> Tuple[str, Decimal, str, str]:
        """返回 (方式, 单程价, source, note)"""
        # --- 第一级：真实 API ---
        if origin and dest:
            data = self._get("/api/tools/train-price", {
                "origin": origin, "dest": dest, "date": self._today})
            if data and data.get("quotes"):
                quotes = [(q.get("seat_type", ""), _d(q.get("price", 0)))
                          for q in data["quotes"] if _d(q.get("price", 0)) > 0]
                if quotes:
                    seat, price = self._pick_seat(quotes, budget)
                    as_of = data.get("as_of") or self._today
                    return seat, price, "TRAIN_API", f"{seat}·{data.get('provider', '12306聚合')}({as_of})"
        # --- 第二级：系数模型（与 Java chooseTransport 完全一致的口径） ---
        # 走估算说明该城市对未收录真实票价：记入待抓队列，供爬虫批量补抓
        if origin and dest:
            note_missing_train_pair(origin, dest)
            logger.info(f"[PRICE] {origin}→{dest} 无真实票价，已记入待抓队列 "
                        f"（script/scrape/pending_pairs.json）")
        if dist_km is None and origin and dest:
            dist_km = self.city_distance_km(origin, dest)
        if dist_km is None:
            dist_km = Decimal("800")  # 典型跨省里程兜底
            mode, price = self._model_cheapest(dist_km, budget)
            return mode, price, "ESTIMATE", f"{mode}·里程系数估算(按典型跨省800km)"
        mode, price = self._model_choose(dist_km, budget)
        return mode, price, "ESTIMATE", f"{mode}·里程系数估算({origin}→{dest})"

    @staticmethod
    def _model_options(dist_km: Decimal) -> List[Tuple[str, Decimal]]:
        """里程系数票价模型：铁路里程≈直线距离×1.3，各方式按 元/km 系数+上下限"""
        rail = dist_km * Decimal("1.3")

        def clamp(v: float, lo: float, hi: float) -> Decimal:
            return _d(max(lo, min(hi, v)))

        options = [
            ("长途大巴", clamp(float(rail) * 0.28, 60, 400)),
            ("普速列车硬座", clamp(float(rail) * 0.15, 40, 260)),
            ("普速列车硬卧", clamp(float(rail) * 0.28, 90, 480)),
            ("高铁二等座", clamp(float(rail) * 0.46, 70, 900)),
            ("高铁一等座", clamp(float(rail) * 0.74, 120, 1500)),
        ]
        if float(dist_km) > 800:
            options.append(("飞机经济舱", clamp(float(dist_km) * 0.55, 380, 1600)))
        return options

    def _model_choose(self, dist_km: Decimal, budget: Optional[float]) -> Tuple[str, Decimal]:
        options = self._model_options(dist_km)
        cap = Decimal(str(budget)) * Decimal("0.35") if budget else None
        if cap is not None:
            one_way_cap = (cap / 2).quantize(Decimal("1"))
            # 从贵到便宜：第一个「明显负担得起」（×1.2）的
            for mode, price in reversed(options):
                margin = Decimal("1.0") if (float(dist_km) > 1500 and mode == "飞机经济舱") else Decimal("1.2")
                if price * margin <= one_way_cap:
                    return mode, price
            # 再找预算内买得起的
            for mode, price in reversed(options):
                if price <= one_way_cap:
                    return mode, price
            # 都超预算：最便宜的
            return options[0][0] + "（预算紧张，已选最经济方式）", options[0][1]
        # 无预算：>1500km 飞机，否则高铁二等座
        if float(dist_km) > 1500 and options[-1][0] == "飞机经济舱":
            return options[-1]
        for mode, price in options:
            if mode == "高铁二等座":
                return mode, price
        return options[0]

    def _model_cheapest(self, dist_km: Decimal, budget=None) -> Tuple[str, Decimal]:
        return self._model_choose(dist_km, budget)

    @staticmethod
    def _pick_seat(quotes: List[Tuple[str, Decimal]], budget: Optional[float]) -> Tuple[str, Decimal]:
        """从真实报价中按预算选席别：默认二等座；预算紧则降级到预算内最便宜的席别"""
        quotes = sorted(quotes, key=lambda x: x[1])
        second = next(((s, p) for s, p in quotes if "二等" in s or "硬卧" in s), None)
        if budget:
            cap = Decimal(str(budget)) * Decimal("0.35") / 2
            if second and second[1] <= cap:
                return second
            for s, p in reversed(quotes):
                if p <= cap:
                    return s, p
            cheapest = quotes[0]
            return cheapest[0] + "（预算紧张，已选最经济席别）", cheapest[1]
        return second if second else quotes[-1]

    # ---------------- ③ 酒店（快照表 → 档次默认价） ----------------

    def hotel_per_night(self, city: Optional[str], tier: SpendTier) -> PriceQuote:
        """每晚住宿价格：优先酒店价格快照表，缺失回落档次默认价（标注估算）"""
        tier_key = {"品质": "premium", "舒适": "comfort", "经济": "economy"}.get(tier.name, "comfort")
        if city:
            data = self._get("/api/tools/hotel-price", {"city": city, "tier": tier_key})
            if data and data.get("price_per_night"):
                sample = data.get("sample_hotel") or ""
                return PriceQuote(_d(data["price_per_night"]), "SNAPSHOT",
                                  data.get("as_of") or self._today, "high",
                                  f"{tier.hotel_desc}" + (f"·{sample}" if sample else ""))
        # 无快照 → 记入待采队列，供 --pending 针对性补采（额度有限，不做全国批量）
        note_missing_price("hotel", city)
        return PriceQuote(tier.hotel_per_night, "ESTIMATE", self._today, "low", tier.hotel_desc)

    # ---------------- ④ 景点门票（景点库真实票价 → 均价兜底） ----------------

    def ticket_avg(self, city: Optional[str]) -> Tuple[Decimal, int, str]:
        """返回 (平均门票, 有价景点数, 来源说明)。无真实数据时返回均价兜底"""
        if city:
            data = self._get("/api/tools/poi", {"city_name": city, "count": 30})
            if data:
                pois = data.get("poi_list") or []
                prices = [_d(p.get("ticket_price")) for p in pois
                          if p.get("ticket_price") is not None and _d(p.get("ticket_price")) > 0]
                if prices:
                    avg = (sum(prices) / len(prices)).quantize(Decimal("1"))
                    return avg, len(prices), f"景点库真实票价（{len(prices)}个景点）"
        # 该城市景点无真实票价 → 记入待采队列
        note_missing_price("ticket", city)
        return TICKET_AVG, 0, "系统均价估算"

    # ---------------- ⑤ 档次阶梯与最低可行预算 ----------------

    def tier_total(self, tier: SpendTier, transport: Decimal, days: int,
                   hotel_quote: Optional[PriceQuote], ticket_avg: Decimal,
                   paid_poi: int) -> Decimal:
        """某档次下的预计总花费（酒店用快照真实价，其余按档次参数）"""
        nights = max(days - 1, 0)
        hotel = hotel_quote.price if (hotel_quote and hotel_quote.is_real) else tier.hotel_per_night
        ticket = ticket_avg * Decimal(max(paid_poi, 0)) * tier.ticket_factor
        total = transport + hotel * nights + tier.food_per_day * days \
            + tier.local_per_day * days + ticket + tier.other_per_day * days
        return _d(total)

    def min_feasible_budget(self, transport: Decimal, days: int,
                            eco_hotel: Decimal) -> Decimal:
        """最低可行预算：经济档 + 免费景点为主（与 Java 情形3 同口径）"""
        eco = TIERS[-1]
        nights = max(days - 1, 0)
        total = transport + eco_hotel * nights \
            + (eco.food_per_day + eco.local_per_day + eco.other_per_day) * days
        return _d(total)

    def max_feasible_days(self, transport: Decimal, budget: float,
                          eco_hotel: Decimal, days: int) -> int:
        """预算不变时可支持的最大天数（经济档、免费景点为主）"""
        eco = TIERS[-1]
        b = Decimal(str(budget))
        for d in range(max(days, 1), 0, -1):
            cost = transport + eco_hotel * (d - 1) \
                + (eco.food_per_day + eco.local_per_day + eco.other_per_day) * d
            if cost <= b:
                return d
        return 0

    # ---------------- ⑥ Prompt 约束块构建 ----------------

    def build_budget_block(self, budget_amount, day_count,
                           origin_city: Optional[str] = None,
                           dest_city: Optional[str] = None) -> str:
        """构建「预算硬约束」Prompt 块（预算反推规划的 Prompt 侧实现）。

        与旧实现的区别：所有参考价格优先取真实数据（火车票价 API / 酒店快照 /
        景点库门票），每项标注来源与日期；拿不到真实价格的项明确标注「系统估算」。
        """
        if not budget_amount:
            return ""
        try:
            total = Decimal(str(budget_amount))
        except Exception:
            logger.warning(f"[PLANNING] 预算金额无法解析，忽略预算约束: {budget_amount!r}")
            return ""
        if total <= 0:
            return ""

        days = max(int(day_count or 1), 1)
        nights = max(days - 1, 0)
        paid_poi = max(days * 2, 2)

        # ---- 取价（三级降级，任何一环失败都不阻断） ----
        dist = self.city_distance_km(origin_city, dest_city)
        transport_q = self.train_round_trip(origin_city, dest_city, float(total), dist)
        hotel_q = {t.name: self.hotel_per_night(dest_city, t) for t in TIERS}
        ticket_avg, ticket_n, ticket_src = self.ticket_avg(dest_city)

        # ---- 档次阶梯：自高向低取预算内最高档 ----
        chosen: Optional[SpendTier] = None
        chosen_total = Decimal("0")
        adjustments: List[str] = []
        for tier in TIERS:
            t_total = self.tier_total(tier, transport_q.price, days,
                                      hotel_q[tier.name], ticket_avg, paid_poi)
            if t_total <= total:
                chosen, chosen_total = tier, t_total
                break
            adjustments.append(f"「{tier.name}」档预计 {t_total} 元，超预算 {t_total - total} 元，自动降级重算")

        route_desc = f"{origin_city}→{dest_city}" if (origin_city and dest_city) else "往返大交通"

        lines = [
            "## 预算约束（硬约束，必须严格遵守）",
            f"- 用户总预算：**{total} 元**（人民币），行程 {days} 天（{nights} 晚）",
        ]
        if dist is not None:
            lines.append(f"- 行程距离：{route_desc} 约 {dist.quantize(Decimal('1'))} km")
        lines.append(f"- 往返大交通（{transport_q.note}）：约 {transport_q.price} 元")
        if dest_city:
            hq = hotel_q[chosen.name] if chosen else hotel_q["经济"]
            lines.append(f"- 住宿参考（{hq.label()}）：约 {hq.price} 元/晚")
            lines.append(f"- 景点门票参考（{ticket_src}）：平均约 {ticket_avg} 元/个"
                         + (f"，共约 {ticket_n} 个收费景点数据" if ticket_n else ""))

        if chosen is not None:
            hq = hotel_q[chosen.name]
            remain = total - chosen_total
            lines += [
                f"- **档次判定：按「{chosen.name}」档执行**，预计总花费约 {chosen_total} 元，结余约 {remain} 元",
                f"  - 住宿标准：约 {hq.price} 元/晚（{hq.label()}）",
                f"  - 餐饮标准：约 {chosen.food_per_day} 元/天（系统估算）",
                f"  - 市内交通：约 {chosen.local_per_day} 元/天（系统估算）",
                f"  - 门票合计：约 {(ticket_avg * paid_poi * chosen.ticket_factor).quantize(Decimal('1'))} 元"
                f"（按 {paid_poi} 个收费景点 × {ticket_avg} 元 × {chosen.ticket_factor}）",
                f"  - 其他（购物/纪念品）：约 {chosen.other_per_day * days} 元（系统估算）",
            ]
            if adjustments:
                lines.append("- 降级记录：" + "；".join(adjustments))
            lines += [
                "",
                f"**最终方案的总花费不得超过 {total} 元。**"
                "请在攻略末尾输出费用参考表（交通 / 住宿 / 餐饮 / 门票 / 其他 + 合计），"
                f"分项之和须等于合计，且合计不超过 {total} 元。"
                "价格请沿用上方参考价（真实价格优先），并在表格中保持一致。",
            ]
            logger.info(f"[PLANNING] 预算约束注入: 总额{total}元/{days}天/「{chosen.name}」档 "
                        f"预计{chosen_total}元 交通[{transport_q.source}]")
            return "\n".join(lines)

        # ---- 不可行：最低可行预算 + 缺口 + 四套降级方案 ----
        eco_hotel = hotel_q["经济"]
        eco_hotel_price = eco_hotel.price if eco_hotel.is_real else TIERS[-1].hotel_per_night
        min_budget = self.min_feasible_budget(transport_q.price, days, eco_hotel_price)
        gap = min_budget - total
        fit_days = self.max_feasible_days(transport_q.price, float(total), eco_hotel_price, days)

        # 最便宜交通方式可省金额（用于方案二）
        options = self._model_options(dist) if dist is not None else []
        cheapest = min((p for _, p in options), default=transport_q.price)
        save = max(transport_q.price - cheapest * 2, Decimal("0"))

        lines += [
            f"- ⚠️ **预算不足，无法支撑 {days} 天行程**：最低可行预算约 {min_budget} 元"
            f"（大交通 {transport_q.price} + 经济档吃/住/行/其他 {min_budget - transport_q.price}），"
            f"缺口约 {gap} 元",
            "- **必须先在攻略开头明确说明「预算不足」**，然后从下列方案中给出建议（可组合）：",
        ]
        if fit_days > 0 and fit_days < days:
            lines.append(f"  1. 缩短天数：{days} 天 → {fit_days} 天（大交通不变，即可控制在预算内）")
        else:
            lines.append("  1. 缩短天数：减少行程天数可显著降低住宿与餐饮支出")
        if save > 0:
            lines.append(f"  2. 更换交通：改乘普速列车硬座 / 长途大巴往返，约可省 {save} 元")
        else:
            lines.append("  2. 更换交通：改乘普速列车硬座 / 长途大巴往返，降低大交通占比")
        lines.append(f"  3. 降低住宿：已按最低档（{eco_hotel.label()} 约 {eco_hotel_price} 元/晚）计算，可改青旅床位进一步压缩")
        lines.append(f"  4. 提高预算：将总预算提高到 {min_budget} 元以上")
        if adjustments:
            lines.append("- 降级记录：" + "；".join(adjustments))
        lines += [
            "",
            "注意：**不得**在预算内硬凑一份虚假的低价行程——所有价格必须使用上方参考价口径。",
        ]
        logger.warning(f"[PLANNING] 预算不可行: 总额{total}元/{days}天 最低需{min_budget}元 缺口{gap}元")
        return "\n".join(lines)


    # ---------------- ⑦ 无预算时的真实价格参考块 ----------------

    def build_reference_block(self, origin_city: Optional[str] = None,
                              dest_city: Optional[str] = None) -> str:
        """用户未给出预算时，仍注入可信的真实价格参考，让费用表贴近真实行情。

        仅当至少取到一条真实数据（API/快照）时才返回非空块，避免纯估算噪音。
        """
        if not dest_city:
            return ""
        dist = self.city_distance_km(origin_city, dest_city)
        transport_q = self.train_round_trip(origin_city, dest_city, None, dist)
        hotel_q = self.hotel_per_night(dest_city, TIERS[1])  # 舒适档作参考
        ticket_avg, ticket_n, ticket_src = self.ticket_avg(dest_city)

        lines = ["## 真实价格参考（来源可信，费用表请优先采用）"]
        has_real = False
        route_desc = f"{origin_city}→{dest_city}" if (origin_city and dest_city) else "往返大交通"
        if transport_q.is_real:
            lines.append(f"- 往返大交通：{route_desc} {transport_q.note}，往返约 {transport_q.price} 元")
            has_real = True
        if hotel_q.is_real:
            lines.append(f"- 住宿参考：{dest_city} 舒适型酒店约 {hotel_q.price} 元/晚（{hotel_q.label()}）")
            has_real = True
        if ticket_n > 0:
            lines.append(f"- 景点门票：{dest_city} 收费景点平均约 {ticket_avg} 元/个（{ticket_src}）")
            has_real = True
        if not has_real:
            return ""
        lines.append("- 其余未列出项目请按行业常识估算，并在费用表中标注「估算」")
        return "\n".join(lines)


# 模块级单例（无状态，可复用）
_provider: Optional[PriceProvider] = None


def get_price_provider() -> PriceProvider:
    global _provider
    if _provider is None:
        _provider = PriceProvider()
    return _provider
