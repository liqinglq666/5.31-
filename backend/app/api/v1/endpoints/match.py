"""
endpoints/match.py
------------------
文件名智能配对接口。
接收两侧文件名列表，返回按共有关键词匹配成功的配对结果。
"""

from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

from app.utils.matcher import smart_match_files

router = APIRouter()


class MatchRequest(BaseModel):
    source_names: List[str]
    contract_names: List[str]


class MatchPair(BaseModel):
    source_index: int
    contract_index: int
    source_name: str
    contract_name: str
    common_keywords: List[str]


class MatchResponse(BaseModel):
    pairs: List[MatchPair]
    unmatched_source: List[int]
    unmatched_contract: List[int]


@router.post("/api/v1/match")
async def match_files(request: MatchRequest) -> dict:
    """
    智能文件名配对。
    依据文件名中去除噪声词后的共有关键词进行贪心匹配。
    """
    result = smart_match_files(request.source_names, request.contract_names)
    return {
        "code": 200,
        "message": "配对完成",
        "data": result,
    }
