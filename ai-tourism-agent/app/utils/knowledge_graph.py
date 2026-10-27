"""行程知识图谱构建器（对标 TripStar 的知识图谱可视化）。

把一次行程规划结果转成「城市 — 天数 — 景点 — 预算」的节点关系网络，
输出结构直接对接前端 ECharts `graph`（力导向图）。

节点分类（categories）
----------------------
0 城市   1 天数   2 景点   3 预算

边关系
------
城市 → 天数（包含）、天数 → 景点（安排）、景点 → 预算（消费）、城市 → 预算（汇总）

用法
----
    from app.utils import build_knowledge_graph, build_graph_from_daily_routes

    graph = build_knowledge_graph(plan, budget)
    # 或直接吃后端会话里的 dailyRoutes 结构
    graph = build_graph_from_daily_routes(session["dailyRoutes"], budget)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CATEGORY_CITY = 0
CATEGORY_DAY = 1
CATEGORY_POI = 2
CATEGORY_BUDGET = 3

CATEGORY_NAMES = ["城市", "天数", "景点", "预算"]

_BUDGET_LABELS = {
    "transport": "交通",
    "accommodation": "住宿",
    "food": "餐饮",
    "ticket": "门票",
    "other": "其他",
    "total": "总预算",
}


def _node(node_id: str, name: str, category: int, size: float) -> Dict[str, Any]:
    return {"id": node_id, "name": name, "category": category, "symbolSize": size}


def _edge(source: str, target: str, label: str = "") -> Dict[str, Any]:
    return {"source": source, "target": target, "label": label}


def _normalize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """兼容多种入参结构，统一成 {cities, days:[{day, city, pois:[{name,ticket}]}]}。"""
    cities: List[str] = []
    if plan.get("cities"):
        cities = [str(c) for c in plan["cities"]]
    elif plan.get("city"):
        cities = [str(plan["city"])]

    days_out: List[Dict[str, Any]] = []
    for idx, d in enumerate(plan.get("days") or [], start=1):
        day_no = d.get("day", idx)
        city = d.get("city") or (cities[0] if cities else "")
        pois = []
        for p in d.get("pois") or []:
            if isinstance(p, str):
                pois.append({"name": p, "ticket": None})
            else:
                pois.append({"name": p.get("name") or p.get("poiName") or "", "ticket": p.get("ticket")})
        pois = [p for p in pois if p["name"]]
        days_out.append({"day": day_no, "city": city, "pois": pois})
        if city and city not in cities:
            cities.append(city)

    return {"cities": cities, "days": days_out}


def build_knowledge_graph(plan: Dict[str, Any], budget: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建行程知识图谱。

    Args:
        plan: 归一化行程，形如
            {"cities": ["西安"],
             "days": [{"day": 1, "city": "西安", "pois": [{"name": "兵马俑", "ticket": 120}]}]}
        budget: 可选预算，形如
            {"transport": 640, "accommodation": 750, "food": 480, "ticket": 1600, "other": 400, "total": 3870}

    Returns:
        {"categories": [...], "nodes": [...], "edges": [...], "stats": {...}}
    """
    norm = _normalize_plan(plan or {})
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen = set()

    def add_node(nid: str, name: str, cat: int, size: float) -> None:
        if nid not in seen:
            seen.add(nid)
            nodes.append(_node(nid, name, cat, size))

    # 城市节点
    for city in norm["cities"]:
        add_node(f"city::{city}", city, CATEGORY_CITY, 46)

    poi_total = 0
    # 天数与景点节点
    for d in norm["days"]:
        day_id = f"day::{d['day']}"
        add_node(day_id, f"第{d['day']}天", CATEGORY_DAY, 32)
        city_id = f"city::{d['city']}" if d["city"] else None
        if city_id and city_id in seen:
            edges.append(_edge(city_id, day_id, "包含"))
        for p in d["pois"]:
            poi_total += 1
            poi_id = f"poi::{p['name']}"
            add_node(poi_id, p["name"], CATEGORY_POI, 20)
            edges.append(_edge(day_id, poi_id, "安排"))

    # 预算节点
    if budget:
        ticket_id = f"budget::ticket"
        for key, label in _BUDGET_LABELS.items():
            if key == "total":
                continue
            val = budget.get(key)
            if val is None:
                continue
            bid = f"budget::{key}"
            add_node(bid, f"{label} ¥{val}", CATEGORY_BUDGET, 26)
        total = budget.get("total")
        if total is not None:
            add_node("budget::total", f"总预算 ¥{total}", CATEGORY_BUDGET, 40)
            for key, label in _BUDGET_LABELS.items():
                if key != "total" and budget.get(key) is not None:
                    edges.append(_edge(f"budget::{key}", "budget::total", "计入"))
        # 景点 → 门票预算
        if ticket_id in seen:
            for n in list(nodes):
                if n["category"] == CATEGORY_POI:
                    edges.append(_edge(n["id"], ticket_id, "消费"))

    return {
        "categories": [{"name": n} for n in CATEGORY_NAMES],
        "nodes": nodes,
        "edges": edges,
        "stats": {"city": len(norm["cities"]), "day": len(norm["days"]), "poi": poi_total},
    }


def build_graph_from_daily_routes(
    daily_routes: Dict[str, Any],
    budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """适配后端会话的 dailyRoutes 结构。

    期望输入形如::

        {"dailyRoutes": [
            {"day": 1, "city": "西安",
             "points": [{"name": "兵马俑", "longitude": 109.27, "latitude": 34.38}]}
        ]}

    也兼容没有 dailyRoutes 包裹、直接就是列表的情况。
    """
    if isinstance(daily_routes, list):
        raw_days = daily_routes
    else:
        raw_days = (daily_routes or {}).get("dailyRoutes") or (daily_routes or {}).get("days") or []

    days = []
    for i, d in enumerate(raw_days, start=1):
        points = d.get("points") or d.get("pois") or []
        pois = []
        for p in points:
            name = p.get("name") or p.get("poiName")
            if name:
                pois.append({"name": name, "ticket": p.get("ticket")})
        days.append({"day": d.get("day", i), "city": d.get("city"), "pois": pois})

    return build_knowledge_graph({"days": days}, budget)


if __name__ == "__main__":  # pragma: no cover - 手工冒烟
    demo_plan = {
        "city": "西安",
        "days": [
            {"day": 1, "pois": [{"name": "兵马俑", "ticket": 120}, {"name": "华清宫", "ticket": 120}]},
            {"day": 2, "pois": [{"name": "大雁塔", "ticket": 50}, {"name": "陕西历史博物馆", "ticket": 0}]},
        ],
    }
    demo_budget = {"transport": 640, "accommodation": 750, "food": 480, "ticket": 1600, "other": 400, "total": 3870}
    g = build_knowledge_graph(demo_plan, demo_budget)
    print("categories:", [c["name"] for c in g["categories"]])
    print("nodes:", len(g["nodes"]), "edges:", len(g["edges"]), "stats:", g["stats"])
