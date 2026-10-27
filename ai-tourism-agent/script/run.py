from __future__ import annotations

"""
入口脚本：将 `getTravelData/data.csv` 切块并写入 Chroma。

切块策略（并列）：
- `CHUNK_STRATEGY=semantic` -> `SemanticChunker`
- `CHUNK_STRATEGY=recursive` -> `RecursiveCharacterTextSplitter`

所有配置优先从 `getTravelData/.env` 读取；不使用 `--data-csv` 等命令行参数。

运行流程（建议你按这个顺序看代码）：
1. `env_config.load_config()`：把 `.env` 读成强类型的 `IngestConfig`。
2. `csv_loader.iter_documents_from_csv()`：每行 CSV 生成一个原始 `Document`：
   - `page_content`：用于 embedding/切块的正文（默认列 `DATA_CONTENT_COL=text`）
   - `metadata`：用于检索时精确过滤的字段（默认 `DATA_META_COLS=*`，即全列）
3. 根据 `cfg.chunk_strategy`：
   - semantic：调用 `chunk_semantic.iter_semantic_chunks()`（SemanticChunker）
   - recursive：调用 `chunk_recursive.iter_recursive_chunks()`（RecursiveCharacterTextSplitter）
4. `vector_store.ChromaWriter.write_documents()`：把 chunk 写入 Chroma（持久化目录 `CHROMA_DIR`）
"""

import json
from typing import Iterable

from langchain_core.documents import Document

from csv_loader import iter_documents_from_csv
from env_config import load_config
from vector_store import ChromaWriter

# 注意：chunk_semantic 依赖 langchain_experimental（仅 semantic 策略需要），
# 这里改为策略分支内惰性导入，避免 recursive 策略也被强依赖阻塞。


def enrich_with_title(documents: Iterable[Document]) -> Iterable[Document]:
    """把文档标题拼进 chunk 正文（标题前缀增强）。

    动机：chunk 的 metadata 虽带 title，但 embedding 只编码 page_content，
    导致「北京滑雪」这类主题查询匹配不到标题含「雪场」的文档
    （金标评测 hit@5 仅 37.5%）。标题是攻略文档最强的主题信号，
    拼入正文后向量可同时感知主题词与正文内容。
    """
    for doc in documents:
        md = doc.metadata or {}
        title = str(md.get("title") or "").strip()
        text = doc.page_content or ""
        if title and not text.startswith(f"《{title}》"):
            yield Document(
                page_content=f"《{title}》\n{text}",
                metadata=md,
            )
        else:
            yield doc


def main() -> None:
    # 1) 读取 `.env` 并生成强类型配置
    #    这里是整个项目的“配置入口”，后续所有模块都依赖 IngestConfig。
    cfg = load_config()

    # 2) CSV -> 原始 Document（保留 metadata，用于精确过滤）
    #    iter_documents_from_csv 是迭代生成器，所以不会一次性把整个 CSV 载入内存。
    #    这对你数据量（data.csv 约 6w 行）很重要。
    #    注意：CHROMA_RESET=true 表示整库重建，此时必须忽略断点从头开始，
    #    否则会出现「collection 已清空 + 断点已到末尾 -> 静默写入 0 条」的事故。
    start_row = 0
    if cfg.chroma_reset:
        print("[reset] CHROMA_RESET=true，忽略断点从头重建，并清除断点文件")
        if cfg.checkpoint_file.exists():
            try:
                cfg.checkpoint_file.unlink()
                print(f"[reset] 已删除断点文件: {cfg.checkpoint_file}")
            except Exception as e:  # noqa: BLE001
                print(f"[reset] 断点文件删除失败（继续重建）: {e}")
    elif cfg.checkpoint_file.exists():
        try:
            raw = json.loads(cfg.checkpoint_file.read_text(encoding="utf-8"))
            last_done = int(raw.get("last_completed_row_index", -1))
            start_row = max(0, last_done + 1)
            print(
                f"[resume] checkpoint={cfg.checkpoint_file} "
                f"last_completed_row_index={last_done} start_row={start_row}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"[resume] ignore invalid checkpoint: {e}")

    documents: Iterable[Document] = iter_documents_from_csv(
        csv_path=cfg.data_csv,
        content_col=cfg.data_content_col,
        meta_cols=cfg.data_meta_cols,
        max_rows=cfg.max_rows,
        start_row=start_row,
    )

    # 3) 根据配置选择切块器
    #    两种切块器都“保留 metadata”，即 chunk 的 metadata 仍然包含原始行的所有字段。
    if cfg.chunk_strategy == "semantic":
        from chunk_semantic import iter_semantic_chunks

        chunk_iter = iter_semantic_chunks(
            documents=documents,
            chunk_mode=cfg.chunk_mode,
            chunker_backend=cfg.chunker_backend,
            ollama_base_url=cfg.ollama_base_url,
            ollama_model_name=cfg.ollama_model_name,
            semantic_breakpoint_amount=cfg.semantic_breakpoint_amount,
            semantic_add_start_index=cfg.semantic_add_start_index,
            semantic_min_chunk_size=cfg.semantic_min_chunk_size,
            openai_base_url=cfg.openai_base_url,
            openai_api_key=cfg.openai_api_key,
            openai_embedding_model=cfg.embedding_model,
        )
    elif cfg.chunk_strategy == "recursive":
        from chunk_recursive import iter_recursive_chunks

        chunk_iter = iter_recursive_chunks(
            documents=documents,
            chunk_mode=cfg.chunk_mode,
            chunk_size=cfg.recursive_chunk_size,
            chunk_overlap=cfg.recursive_chunk_overlap,
        )
    else:
        # 正常情况下 env_config.load_config() 已经保证 chunk_strategy 有效；
        # 这里仍做保护，便于你将来扩展。
        raise RuntimeError(
            f"未知 CHUNK_STRATEGY={cfg.chunk_strategy}（semantic|recursive）"
        )

    # 4) 写入 Chroma（OpenAI embedding + persistent directory）
    #    注意：SemanticChunker 用的是“切块 embedding”（HF 或 OpenAI，取决于 CHUNKER_BACKEND），
    #    而 Chroma 里存向量用的是 OpenAIEmbeddings（由 OPENAI_API_KEY + EMBEDDING_MODEL 决定）。
    #    入库前先做标题前缀增强（见 enrich_with_title），提升主题查询的向量可感知性。
    writer = ChromaWriter(
        chroma_dir=cfg.chroma_dir,
        collection=cfg.chroma_collection,
        reset=cfg.chroma_reset,
        batch_add=cfg.chroma_batch_add,
        flush_mode=cfg.chroma_flush_mode,
        openai_base_url=cfg.openai_base_url,
        openai_api_key=cfg.openai_api_key,
        embedding_model=cfg.embedding_model,
        embedding_request_timeout=cfg.embedding_request_timeout,
        embedding_show_progress=cfg.embedding_show_progress,
        checkpoint_file=cfg.checkpoint_file,
        progress_log_every_docs=cfg.progress_log_every_docs,
    )
    writer.write_documents(enrich_with_title(chunk_iter))


if __name__ == "__main__":
    main()

