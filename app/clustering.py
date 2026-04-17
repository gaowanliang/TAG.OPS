"""按标签对识别结果聚类。"""
from __future__ import annotations

from typing import Dict, List


def categorize_by_top_n(
    results: Dict[str, dict],
    top_n: int = 3,
    min_images: int = 2,
) -> Dict[str, List[dict]]:
    """根据每张图片的前 N 个标签聚类。

    参数:
      results: {path: {tags: {tag: conf}, ...}}  —— 只要项中有 "tags" 字典即可。
      top_n: 取每张图置信度最高的前 N 个标签作为分类键。
      min_images: 类别最少包含图片数，低于此值的类别会被过滤。

    返回: {category_name: [{path, confidence, tags}, ...]}，按类别图片数降序。
    """
    categories: Dict[str, List[dict]] = {}
    for path, result in results.items():
        tags = result.get("tags")
        if not tags:
            continue
        # tags 已经按置信度排序（postprocess_tags 的默认行为）
        top_tags = list(tags.keys())[:top_n]
        for tag in top_tags:
            clean = tag.replace("_", " ").title()
            categories.setdefault(clean, []).append(
                {"path": path, "confidence": tags[tag], "tags": tags}
            )

    filtered = {k: v for k, v in categories.items() if len(v) >= min_images}
    return dict(sorted(filtered.items(), key=lambda kv: len(kv[1]), reverse=True))
