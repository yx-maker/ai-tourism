# -*- coding: utf-8 -*-
"""高德 Key 读取工具（爬虫脚本共用）

禁止在代码里硬编码 Key：Key 被封或轮换时，代码里残留的旧 Key 会静默失效，
排查起来非常费劲（表现为 INVALID_USER_KEY / INVALID_USER_IP / 空结果）。

优先级：
1. 环境变量 AMAP_WEB_API_KEY
2. 仓库根目录 ai-tourism/.env.local 中的 AMAP_WEB_API_KEY

注意：这里读的是「Web服务」类型 Key，不是前端的 Web端(JS API) Key。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# script/scrape/amap_env.py -> parents[0]=scrape, [1]=script, [2]=ai-tourism-agent, [3]=毕业论文
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_LOCAL = REPO_ROOT / "ai-tourism" / ".env.local"


def _parse_env_file(path: Path, name: str) -> str:
    if not path.is_file():
        return ""
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def get_amap_web_key(required: bool = True) -> str:
    key = os.getenv("AMAP_WEB_API_KEY", "").strip()
    if not key:
        key = _parse_env_file(ENV_LOCAL, "AMAP_WEB_API_KEY")
    if not key and required:
        print(
            "[error] 未找到高德 Web服务 Key。\n"
            f"        请在 {ENV_LOCAL} 中配置 AMAP_WEB_API_KEY=xxx，\n"
            "        或设置同名环境变量。",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


__all__ = ["get_amap_web_key", "ENV_LOCAL"]
