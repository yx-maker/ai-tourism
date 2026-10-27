"""RAG 金标检索评测（IR 指标）：hit@1 / hit@k / MRR。

与 test/rag_eval 下 RAGAS 两步流程互补：
- RAGAS 流程评测「答案质量」（faithfulness / context_relevance / ...）
- 本脚本评测「检索质量」：给定 query，相关文档是否被检索到、排在第几位

评测方式（qrels-free 关键词判定）：
- 金标集（retrieval_golden.json）每条给出期望关键词；
- 检索结果中某篇文档的 title 或 page_content 命中任一关键词即判定为「相关」；
- 按首个相关文档的排名计算 hit@1 / hit@k / MRR。

前置条件：
- 已构建 Chroma 向量库（script/run.py，CHROMA_DIR 与主项目 .env 的
  RAG_CHROMA_DIR 一致），否则脚本给出构建指引并以退出码 0 结束（不算失败）。

用法：
    python test/rag_eval/run_retrieval_eval.py
    python test/rag_eval/run_retrieval_eval.py --top-k 5 --city 北京
    python test/rag_eval/run_retrieval_eval.py --golden path/to/golden.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_GOLDEN = Path(__file__).resolve().parent / "retrieval_golden.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


@dataclass
class EntryResult:
    id: str
    query_intent: str
    city_name: str
    query: str
    expect_keywords: List[str]
    retrieved_titles: List[str] = field(default_factory=list)
    relevant_rank: Optional[int] = None      # 首个相关文档排名（1 起），未命中为 None
    relevant_title: str = ""                 # 首个相关文档标题
    matched_field: str = ""                  # title / content
    hit1: bool = False
    hitk: bool = False
    rr: float = 0.0


def load_golden(path: Path) -> List[Dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"金标文件为空或格式错误: {path}")
    required = {"id", "city_name", "expect_keywords"}
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"金标第 {idx} 条不是对象")
        missing = required - set(row.keys())
        if missing:
            raise ValueError(f"金标第 {idx} 条缺少字段: {sorted(missing)}")
        if not isinstance(row["expect_keywords"], list) or not row["expect_keywords"]:
            raise ValueError(f"金标第 {idx} 条 expect_keywords 必须为非空数组")
    return rows


def doc_title(doc: Any) -> str:
    md = getattr(doc, "metadata", None) or {}
    return str(md.get("title", "")).strip()


def doc_content(doc: Any) -> str:
    return str(getattr(doc, "page_content", "") or "")


def judge_relevance(doc: Any, keywords: List[str]) -> Optional[str]:
    """命中返回 'title' 或 'content'，未命中返回 None。"""
    title = doc_title(doc)
    content = doc_content(doc)
    for kw in keywords:
        kw = str(kw).strip()
        if not kw:
            continue
        if kw in title:
            return "title"
    for kw in keywords:
        kw = str(kw).strip()
        if not kw:
            continue
        if kw in content:
            return "content"
    return None


def evaluate(golden: List[Dict[str, Any]], top_k: int, city_filter: Optional[str]) -> List[EntryResult]:
    from app.config import settings
    from app.domain.services.rag_retrieval_service import RagRetrievalService

    service = RagRetrievalService()
    results: List[EntryResult] = []

    for row in golden:
        city = str(row["city_name"]).strip()
        if city_filter and city != city_filter:
            continue
        day_count = row.get("day_count")
        customization = row.get("customization_requirements")
        keywords = [str(k) for k in row["expect_keywords"]]

        docs = service.retrieve_docs_for_rag_eval(
            city_name=city,
            day_count=day_count,
            customization_requirements=customization,
        )

        query = service.build_query(city, day_count, customization)
        result = EntryResult(
            id=str(row["id"]),
            query_intent=str(row.get("query_intent", "")),
            city_name=city,
            query=query,
            expect_keywords=keywords,
            retrieved_titles=[doc_title(d) or "(无标题)" for d in docs],
        )

        for rank, doc in enumerate(docs, start=1):
            matched = judge_relevance(doc, keywords)
            if matched:
                result.relevant_rank = rank
                result.relevant_title = doc_title(doc)
                result.matched_field = matched
                break

        result.hit1 = result.relevant_rank == 1
        result.hitk = result.relevant_rank is not None and result.relevant_rank <= top_k
        result.rr = 1.0 / result.relevant_rank if result.relevant_rank else 0.0
        results.append(result)

    return results


def aggregate(results: List[EntryResult]) -> Dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"total": 0}
    hit1 = sum(1 for r in results if r.hit1)
    hitk = sum(1 for r in results if r.hitk)
    mrr = sum(r.rr for r in results) / n
    title_hits = sum(1 for r in results if r.matched_field == "title")
    content_hits = sum(1 for r in results if r.matched_field == "content")
    misses = [r for r in results if r.relevant_rank is None]
    return {
        "total": n,
        "hit1": hit1,
        "hit1_rate": round(hit1 / n, 4),
        "hitk": hitk,
        "hitk_rate": round(hitk / n, 4),
        "mrr": round(mrr, 4),
        "title_field_hits": title_hits,
        "content_field_hits": content_hits,
        "miss_ids": [r.id for r in misses],
    }


def render_report(
    results: List[EntryResult],
    summary: Dict[str, Any],
    top_k: int,
    config_info: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append("# RAG 金标检索评测报告")
    lines.append("")
    lines.append(f"- 评测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- Chroma 目录：`{config_info.get('chroma_dir')}`")
    lines.append(f"- Collection：`{config_info.get('collection')}`")
    lines.append(f"- Embedding 模型：`{config_info.get('embedding_model')}`")
    lines.append(f"- top_k：{top_k}")
    lines.append(f"- 金标条数：{summary.get('total', 0)}")
    lines.append("")
    lines.append("## 汇总指标")
    lines.append("")
    lines.append("| 指标 | 数值 | 说明 |")
    lines.append("|------|------|------|")
    lines.append(f"| hit@1 | {summary.get('hit1_rate', 0):.2%} ({summary.get('hit1', 0)}/{summary.get('total', 0)}) | 首个结果即相关 |")
    lines.append(f"| hit@{top_k} | {summary.get('hitk_rate', 0):.2%} ({summary.get('hitk', 0)}/{summary.get('total', 0)}) | top-{top_k} 内出现相关文档 |")
    lines.append(f"| MRR | {summary.get('mrr', 0):.4f} | 首个相关文档排名倒数均值 |")
    lines.append(f"| title 命中 | {summary.get('title_field_hits', 0)} | 关键词命中文档标题 |")
    lines.append(f"| content 命中 | {summary.get('content_field_hits', 0)} | 关键词仅命中正文 |")
    if summary.get("miss_ids"):
        lines.append(f"| 未命中条数 | {len(summary['miss_ids'])} | {', '.join(summary['miss_ids'])} |")
    lines.append("")
    lines.append("## 逐条明细")
    lines.append("")
    lines.append("| ID | 查询意图 | 相关排名 | 首个相关文档 | 判定依据 |")
    lines.append("|----|----------|----------|--------------|----------|")
    for r in results:
        rank_text = str(r.relevant_rank) if r.relevant_rank else "未命中"
        lines.append(
            f"| {r.id} | {r.query_intent} | {rank_text} | {r.relevant_title or '-'} | {r.matched_field or '-'} |"
        )
    lines.append("")
    lines.append("## 检索结果明细（按金标顺序）")
    lines.append("")
    for r in results:
        lines.append(f"### {r.id} {r.query_intent}")
        lines.append("")
        lines.append(f"- 查询语句：`{r.query}`")
        lines.append(f"- 期望关键词：{', '.join(r.expect_keywords)}")
        lines.append(f"- 检索结果（top {top_k}）：")
        for i, title in enumerate(r.retrieved_titles[:top_k], start=1):
            mark = ""
            if r.relevant_rank == i:
                mark = " ← 相关"
            elif i <= top_k:
                mark = ""
            lines.append(f"  {i}. {title}{mark}")
        if not r.retrieved_titles:
            lines.append("  （无检索结果）")
        lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- 相关性判定：检索文档的 title 或 page_content 命中任一期望关键词即视为相关（title 优先）。")
    lines.append("- 该指标衡量「检索是否找到并排前」；答案质量评测请使用 RAGAS 两步流程（run_rag_eval.py）。")
    lines.append("- 语料扩充后，请在 retrieval_golden.json 中同步补充对应城市的金标条目。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 金标检索评测（hit@1/hit@k/MRR）")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="金标 JSON 路径")
    parser.add_argument("--top-k", type=int, default=None, help="覆盖 settings.rag_top_k")
    parser.add_argument("--city", default=None, help="只评测指定城市")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="报告输出目录")
    args = parser.parse_args()

    from app.config import settings

    # 前置检查：向量库目录不存在时给出构建指引，不算失败
    chroma_dir = Path(settings.rag_chroma_dir).expanduser()
    if not chroma_dir.is_absolute():
        chroma_dir = (ROOT_DIR / chroma_dir).resolve()
    if not settings.rag_enabled:
        print("[提示] RAG_ENABLED=false，检索未启用，本次评测跳过。")
        return 0
    if not chroma_dir.is_dir():
        print("[提示] Chroma 向量库不存在，无法进行检索评测。")
        print(f"       期望目录: {chroma_dir}")
        print("       构建方式: 在 script/ 目录配置 .env 后执行 python run.py")
        print("       （CHROMA_DIR 需与主项目 .env 的 RAG_CHROMA_DIR 一致）")
        return 0

    golden = load_golden(Path(args.golden))
    top_k = args.top_k or int(settings.rag_top_k)

    print(f"[信息] 金标条数: {len(golden)}，top_k={top_k}，chroma_dir={chroma_dir}")
    results = evaluate(golden, top_k, args.city)
    if not results:
        print("[错误] 没有可评测的条目（检查 --city 过滤或金标文件）。")
        return 1

    summary = aggregate(results)
    config_info = {
        "chroma_dir": str(chroma_dir),
        "collection": settings.rag_collection_name,
        "embedding_model": settings.openai_embedding_model_name,
    }

    print("\n========== 检索评测汇总 ==========")
    print(f"hit@1  : {summary['hit1_rate']:.2%} ({summary['hit1']}/{summary['total']})")
    print(f"hit@{top_k} : {summary['hitk_rate']:.2%} ({summary['hitk']}/{summary['total']})")
    print(f"MRR    : {summary['mrr']:.4f}")
    if summary.get("miss_ids"):
        print(f"未命中 : {', '.join(summary['miss_ids'])}")
    print("==================================")

    for r in results:
        rank_text = str(r.relevant_rank) if r.relevant_rank else "未命中"
        print(f"  {r.id} {r.query_intent}: 相关排名={rank_text} ({r.matched_field or '-'})")

    out_dir = Path(args.output_dir)
    run_dir = out_dir / f"retrieval_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report_md = render_report(results, summary, top_k, config_info)
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")

    details = [
        {
            "id": r.id,
            "query_intent": r.query_intent,
            "city": r.city_name,
            "query": r.query,
            "expect_keywords": r.expect_keywords,
            "retrieved_titles": r.retrieved_titles,
            "relevant_rank": r.relevant_rank,
            "relevant_title": r.relevant_title,
            "matched_field": r.matched_field,
            "hit1": r.hit1,
            "hitk": r.hitk,
            "rr": r.rr,
        }
        for r in results
    ]
    (run_dir / "details.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in details) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps(
            {"summary": summary, "top_k": top_k, "config": config_info},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[完成] 报告目录: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
