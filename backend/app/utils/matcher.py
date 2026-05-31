"""
utils/matcher.py
----------------
智能文件名配对算法。
根据文件名中的共有关键词，将采购结果文件与合同文件进行自动配对。
"""

import re
from typing import List, Dict, Any

# 常见干扰词 / 后缀，在匹配前应剔除
NOISE_WORDS = {
    # 版本号 / 修饰词
    "副本",
    "最终版",
    "最终",
    "版",
    "v1",
    "v2",
    "v3",
    "v4",
    "v5",
    "v1.0",
    "v2.0",
    "修改",
    "修订",
    "定稿",
    "正式",
    # 文件类型后缀（不含点号，因为在 preprocess 中已去扩展名）
    "pdf",
    "docx",
    "doc",
    "txt",
    # 业务常见通用词（过于宽泛，会降低匹配精度）
    "采购结果",
    "最终合同",
    "合同",
    "招标文件",
    "中标",
    "采购",
    "招标",
    "文件",
    "结果",
}


def _preprocess(filename: str) -> List[str]:
    """
    将文件名预处理为关键词列表：
    1. 去除扩展名
    2. 将下划线、连字符、破折号替换为空格
    3. 按空格分词
    4. 过滤空串与噪声词
    """
    # 1) 去扩展名（仅处理常见的 4 种）
    name = re.sub(r"\.(pdf|docx|doc|txt)$", "", filename, flags=re.IGNORECASE)

    # 2) 统一分隔符为空格
    name = re.sub(r"[_\-—\s]+", " ", name)

    # 3) 去除纯数字编号（如 2024, 0426）以及括号内容，保留中文/英文词
    name = re.sub(r"\d{4,}", "", name)
    name = re.sub(r"[（(].*?[）)]", "", name)

    # 4) 分词并过滤
    tokens = []
    for token in name.split():
        token_lower = token.lower().strip()
        if not token_lower or token_lower in NOISE_WORDS:
            continue
        # 进一步去掉只剩标点或空的情况
        if re.match(r"^[^\w一-鿿]+$", token_lower):
            continue
        tokens.append(token)
    return tokens


def smart_match_files(
    source_list: List[str],
    contract_list: List[str],
) -> Dict[str, Any]:
    """
    对 source_list（采购结果文件名列表）与 contract_list（合同文件名列表）进行智能配对。

    返回结构：
    {
        "pairs": [
            {
                "source_index": int,
                "contract_index": int,
                "source_name": str,
                "contract_name": str,
                "common_keywords": List[str],
            },
            ...
        ],
        "unmatched_source": List[int],    # 未匹配到的 source 索引
        "unmatched_contract": List[int],  # 未匹配到的 contract 索引
    }
    """
    source_keywords = [_preprocess(f) for f in source_list]
    contract_keywords = [_preprocess(f) for f in contract_list]

    pairs: List[Dict[str, Any]] = []
    matched_source: set = set()
    matched_contract: set = set()

    # 贪心策略：对每个 source，寻找与之共有关键词最多的未匹配 contract
    for i, src_kw in enumerate(source_keywords):
        if not src_kw:
            continue

        best_j = -1
        best_score = 0
        best_common: List[str] = []

        for j, ctr_kw in enumerate(contract_keywords):
            if j in matched_contract or not ctr_kw:
                continue

            common = set(src_kw) & set(ctr_kw)
            score = len(common)
            if score > best_score:
                best_score = score
                best_j = j
                best_common = sorted(common)

        # 只有当存在至少一个共有词时才视为配对成功
        if best_j >= 0 and best_score > 0:
            pairs.append(
                {
                    "source_index": i,
                    "contract_index": best_j,
                    "source_name": source_list[i],
                    "contract_name": contract_list[j],
                    "common_keywords": best_common,
                }
            )
            matched_source.add(i)
            matched_contract.add(best_j)

    unmatched_source = [i for i in range(len(source_list)) if i not in matched_source]
    unmatched_contract = [j for j in range(len(contract_list)) if j not in matched_contract]

    return {
        "pairs": pairs,
        "unmatched_source": unmatched_source,
        "unmatched_contract": unmatched_contract,
    }
