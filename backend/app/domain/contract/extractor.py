"""
domain/contract/extractor.py
----------------------------
合同信息结构化提取逻辑。

封装大模型调用、Prompt 工程、JSON 后处理与 RAG 检索。
"""

import json
import logging
import re
from typing import Dict, List, Optional, Any

from app.infrastructure.llm.client import chat_completion
from app.domain.contract.entities import ContractInfo, FinancialInfo

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 15000
MAX_DIRECT_LENGTH = 15000


def _tolerance_rule_prompt(tol: float) -> str:
    """金额容差规则 Prompt 片段（避免多处重复硬编码）。"""
    return _tolerance_rule_prompt(tol)


# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------

def _strip_markdown_json(text: str) -> str:
    """去除 LLM 返回的 markdown 代码块标记（```json ... ```），保留纯 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉开头的 ```json 或 ```
        text = text[text.find("\n") + 1 :]
    if text.endswith("```"):
        text = text[: text.rfind("```")].rstrip()
    return text.strip()


def _truncate_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """如果文本过长，采用智能截断：保留开头和结尾，中间省略。

    合同的关键商务条款通常在前半部分，违约责任、争议解决等通常在后半部分，
    因此截断时保留首尾，比单纯尾部截断更能保留关键信息。
    """
    if len(text) <= max_length:
        return text
    head_len = max_length * 2 // 3
    tail_len = max_length // 3
    return (
        text[:head_len]
        + "\n\n[内容过长，中间部分已省略...]\n\n"
        + text[-tail_len:]
    )


_CJK_RADICAL_MAP = str.maketrans({
    "⽇": "日",  # ⽇ -> 日
    "⽉": "月",  # ⽉ -> 月
    "⾄": "至",  # ⾄ -> 至
    "⽌": "止",  # ⽌ -> 止
    "⼄": "乙",  # ⼄ -> 乙
    "⽅": "方",  # ⽅ -> 方
    "⽬": "目",  # ⽬ -> 目
})


def _normalize_cjk_radicals(text: str) -> str:
    """将 OCR 误识别的 CJK 部首字符还原为标准汉字。"""
    return text.translate(_CJK_RADICAL_MAP)


def _correct_service_period_days(text: str, reference: str, current_value: float) -> float:
    """
    后处理校正 service_period_days。
    LLM 常把'有效期至YYYY年MM月DD日'误算为365天（受'一年期运维'干扰），
    此处用正则从原文中抓取签约日期与截止日期，用 Python 精确计算天数差。
    """
    from datetime import datetime

    text = _normalize_cjk_radicals(text)
    reference = _normalize_cjk_radicals(reference)

    # 1. 从 reference 或全文中提取"有效期至"日期
    end_match = re.search(r"有效期[至到](\d{4})年(\d{1,2})月(\d{1,2})日", reference + text)
    if not end_match:
        end_match = re.search(r"有效期[至到]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not end_match:
        return current_value

    end_year, end_month, end_day = map(int, end_match.groups())

    # 2. 提取起始日期
    # 优先找"签约日期"，但表头 OCR 经常把截止日期错配到签约日期格子里，
    # 所以使用 findall 取最后一个匹配（通常最后一行签字页的日期是正确的）。
    start_matches = re.findall(r"签约日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if start_matches:
        start_year, start_month, start_day = map(int, start_matches[-1])
    else:
        start_match = re.search(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起", text)
        if not start_match:
            return current_value
        start_year, start_month, start_day = map(int, start_match.groups())

    try:
        start_dt = datetime(start_year, start_month, start_day)
        end_dt = datetime(end_year, end_month, end_day)
        delta = (end_dt - start_dt).days
        if delta > 0:
            return float(delta)
    except Exception:
        pass

    return current_value


def _correct_penalty_rate_from_text(text: str, extracted_rate: float) -> float:
    """
    扫描原文中的违约金比例表达，对 LLM 误读 ‰ / % 的情况进行校正。

    常见误读场景：
    - 原文 0.5‰，LLM 输出 0.5（忘了除以 1000）
    - 原文 0.5‰，LLM 输出 0.05（误当作 0.5%）
    - 原文 5%，LLM 输出 5（忘了除以 100）
    """
    if extracted_rate == 0:
        return 0.0

    # 1) 千分号 ‰ / 千分之
    per_mille_patterns = [
        r"(\d+\.?\d*)\s*‰",
        r"千分之\s*(\d+\.?\d*)",
    ]
    for pattern in per_mille_patterns:
        for match in re.findall(pattern, text):
            try:
                val = float(match)
                correct = val / 1000.0  # 0.5‰ = 0.0005
                # 如果提取值和正确值差异很大，但和原始值接近 → 说明忘了除 1000
                if abs(extracted_rate - correct) > 0.0001 and abs(extracted_rate - val) < 0.01:
                    return correct
                # 如果提取值 ≈ 正确值 * 100（当成了 %）→ 0.5‰ 被当成 0.5%
                if abs(extracted_rate - val / 100.0) < 0.001:
                    return correct
            except ValueError:
                continue

    # 2) 百分号 % / 百分之
    percent_patterns = [
        r"(\d+\.?\d*)\s*%",
        r"百分之\s*(\d+\.?\d*)",
    ]
    for pattern in percent_patterns:
        for match in re.findall(pattern, text):
            try:
                val = float(match)
                correct = val / 100.0  # 5% = 0.05
                if abs(extracted_rate - correct) > 0.001 and abs(extracted_rate - val) < 0.01:
                    return correct
            except ValueError:
                continue

    return extracted_rate


# ---------------------------------------------------------------------------
# Prompt 生成器（支持动态规则注入）
# ---------------------------------------------------------------------------

def _build_extraction_system_prompt(rules: Optional[Dict] = None) -> str:
    """组装合同关键信息提取的 System Prompt，支持可配置规则注入。"""
    base = (
        "你是一位严谨的金融合同信息提取专家。\n"
        "【输入格式声明】你接收到的文本已经由 IBM Docling 多模态视觉模型解析为标准 Markdown 格式。"
        "原文档的标题层级（#、##、### 等）、嵌套表格（| 列1 | 列2 |）、无序列表（- / *）均被完美保留。"
        "请充分利用 # 标题层级来定位章节，利用 |...| 表格结构来精确提取行列数据。\n\n"
        "请从用户提供的文本中精确提取以下信息：\n"
        "1. 供应商名称（vendor_name，字符串）\n"
        "2. 总金额（total_amount）：对于总金额、交期天数、违约金比例这几个核心商务指标，"
        "你不能只输出一个数字！你必须输出一个包含 value (数值) 和 reference (精确条款出处) 的对象。"
        "例如：\"total_amount\": {\"value\": 100000, \"reference\": \"合同第3条(一)款\"}。"
        "value 必须是纯数字（单位：元），缺失时填 0；reference 必须精确到章节与条款号（如'第3条第2款'或'附件一'）。"
        "如果找不到精确条款号，必须摘录原文中描述该指标的核心句子作为 reference（如'原文：逾期每日按合同总价0.5‰支付违约金'），"
        "绝对禁止只写'原文未明确标明'六个字而无实质内容！\n"
        "3. 交期天数（delivery_days）：同样输出嵌套对象。value 为整数天数，缺失时填 0；reference 为精确条款号。\n"
        "4. 违约金矩阵（极其重要：必须严格区分不同场景的违约金，全部转换为小数形式，如 5% 为 0.05，0.5‰ 为 0.0005，缺失填 0）：\n"
        "   - 逾期日罚息比例（delay_daily_rate）：例如\"每日按合同总价0.5‰支付违约金\"。输出嵌套对象 {value, reference}。\n"
        "   - 累计违约金上限比例（penalty_cap_rate）：例如\"违约金累计不超过合同总额的10%\"。输出嵌套对象 {value, reference}。\n"
        "   - 解约赔偿比例（termination_penalty_rate）：例如\"质量不达标解除合同，支付合同总价15%的违约金\"。输出嵌套对象 {value, reference}。\n"
        "   你必须对号入座，绝对禁止将日罚息提取到解约赔偿中！\n"
        "   【reference 铁律】对于违约金矩阵的三个字段，reference 必须包含原文摘录：\n"
        "   若能定位条款号，格式为'第X条：原文摘录...'；若无法定位条款号，格式为'原文摘录：\"...\"'。\n"
        "   绝对禁止只写'原文未明确标明'六个字！\n"
        "5. 服务期限/合同有效期（service_period_days）——【极其重要：必须与交付周期严格区分】：\n"
        "   这个字段 ONLY 对应'合同有效期'或'服务期限'条款，绝对禁止将'交付周期'、'开发周期'、'项目实施周期'填入此处！\n"
        "   例如'系统开发为期6个月，自合同签订之日起180个工作日内完成系统验收上线'属于交付周期，应忽略，不要提取。\n"
        "   你只提取明确写着'合同有效期'、'本合同有效期至...'、'服务期限自...至...'、'运维期/质保期'等表述。\n"
        "   计算规则：\n"
        "   - 如果文本写'自X起Y年'，value = Y × 365（如2年=730）。\n"
        "   - 如果文本写'有效期至YYYY年MM月DD日止'，你必须找到合同中的'签约日期'，计算从签约日到截止日的总天数。\n"
        "   - 如果文本写'自系统验收合格之日起一年'，value = 365。\n"
        "   输出嵌套对象 {value, reference}，reference 必须同时包含：条款号 + 起止日期原文 + 你的计算依据。\n"
        "   例如：'第2条（三）：本合同有效期至2028年07月31日止；签约日期为2026年07月16日；计算得746天'。\n"
        "   如果找不到具体日期，必须摘录原文中描述有效期的核心句子。缺失时 value 填 0。\n"
        "6. 采购物品/服务明细清单（items 数组）：逐项提取每一项的品名(name)、规格型号(specification)、"
        "数量(quantity，纯数字)、单价(unit_price，元，纯数字)、小计金额(total_price，元，纯数字)、"
        "位置(position，如'合同第1条采购明细第2项')。\n"
        "\n### 提取规则\n"
        "1. **位置信息**：每个 item 的 position 必须准确标注该条目在原文中的位置，格式为'合同第X条采购明细第Y项'。"
        "如果文本中没有明确编号，请根据上下文推断或标注为'合同第1条采购明细'。绝对禁止留空。\n"
        "2. **核心商务指标出处绑定**：对于 total_amount、delivery_days、delay_daily_rate、penalty_cap_rate、termination_penalty_rate，"
        "你必须在提取数值的同时，利用 Markdown 标题层级（#、##）和段落上下文，定位并记录该数值所在的精确条款编号。"
        "reference 字段必须填写，严禁省略。\n"
        "3. **小计计算校验**：提取 total_price 时，请检查单价 × 数量是否等于小计金额。"
        "如果文本中的小计金额与单价×数量的乘积不一致，请如实提取文本中的数值（不要修改），"
        "后续比对环节会自动标记为'合同明细小计计算错误'。\n"
        "4. **服务类项目**：如果采购的是服务（如保洁、培训、安保、法律顾问等），"
        "name 填写服务名称，specification 可填写服务标准/要求，quantity 填写服务数量/频次（如'1年'、'12场'，纯数字部分提取为数值），"
        "unit_price 和 total_price 按文本实际填写。\n"
        "5. 所有数字字段如果缺失，必须严格使用数字 0 填充，禁止使用字符串'未知'或其他文本。\n"
        "6. **Markdown 表格解析（极其重要）**：采购明细数据一定存在于规范的 Markdown 表格中（格式为 `| 表头1 | 表头2 | ... |`）。"
        "你必须严格按照表头与数据行的对应关系提取，绝对禁止跨行错配——不得将上一行的数量错配给下一行的单价，"
        "不得将表头误当作数据行提取，不得将不同表格的数据混为一谈。"
        "如果表格存在合并单元格，请根据视觉对齐关系推断正确的字段归属。"
        "每一行数据必须独立、准确地映射到 name / specification / quantity / unit_price / total_price 字段。\n"
        "7. **Markdown 标题层级导航**：利用 # / ## / ### 等标题层级快速定位章节。"
        "例如 `## 采购清单` 或 `### 货物明细` 下方的表格即为 items 的数据源。"
        "`# 合同条款` 或 `## 违约责任` 下方的段落即为违约金矩阵的数据源。\n"
        "8. **智能纠错与字段分离（极其重要）**：\n"
        "   - **OCR 容错**：如果文本存在明显的识别错字或漏字（如将'心脑血管专项'识别为'心脑血项'），你必须自动联系上下文，提取纠正后的正确文本。\n"
        "   - **字段剥离**：绝对禁止将'规格/型号'混入'品名(name)'中。即使原文写在一起（如'在线式UPS电源20kVA'），你也必须智能拆分：name 提取为'在线式UPS电源'，specification 提取为'20kVA'。\n"
        "请直接输出 JSON 对象，不要包含任何其他文字。\n\n"
        "输出格式示例：\n"
        '{\n'
        '  "vendor_name": "XXX公司",\n'
        '  "total_amount": {"value": 100000, "reference": "合同第3条(一)款"},\n'
        '  "delivery_days": {"value": 30, "reference": "合同第4条第1款"},\n'
        '  "delay_daily_rate": {"value": 0.0005, "reference": "合同第7条第2款"},\n'
        '  "penalty_cap_rate": {"value": 0.05, "reference": "合同第7条第3款"},\n'
        '  "termination_penalty_rate": {"value": 0.15, "reference": "合同第8条"},\n'
        '  "service_period_days": {"value": 730, "reference": "合同第2条：有效期自2026年07月16日至2028年07月15日"},\n'
        '  "items": [\n'
        '    {"name": "显示器", "specification": "23.8寸", "quantity": 500, "unit_price": 1200, "total_price": 600000, "position": "合同第1条采购明细第1项"},\n'
        '    {"name": "会议桌", "specification": "1.8m", "quantity": 10, "unit_price": 3500, "total_price": 35000, "position": "合同第1条采购明细第2项"}\n'
        '  ]\n'
        '}'
    )
    if not rules:
        return base

    extras: List[str] = []
    tol = rules.get("price_tolerance", 0.0)
    if tol and tol > 0:
        extras.append(
            _tolerance_rule_prompt(tol)
        )

    clauses = rules.get("required_clauses", []) or []
    if clauses:
        extras.append(
            f"【必检条款规则】：必须严格检查合同中是否包含以下条款：{', '.join(clauses)}。"
            f"如果缺失其中任何一项，必须在结果中明确列出，并标记为高风险缺失项。"
        )

    custom = rules.get("custom_requirements", "")
    if custom and custom.strip():
        extras.append(
            f"【用户自定义专属要求】：{custom.strip()}"
            f"（请最高优先级遵循此要求调整你的分析和输出）。"
        )

    if extras:
        return base + "\n\n" + "\n".join(extras)
    return base


def _build_financial_system_prompt(rules: Optional[Dict] = None) -> str:
    """组装财务付款提取的 System Prompt，支持可配置规则注入。"""
    base = (
        "你是一位严谨的金融合同条款提取专家。请从用户提供的合同文本中，精准提取财务付款安排。"
        "首先输出整体财务信息：合同总标的额（total_amount，单位元，必须转换为纯数字，缺失时填 0）、"
        "质保金留存比例（warranty_ratio，如 0.05 表示 5%，必须转换为纯数字，缺失时填 0）。"
        "然后提取所有的付款节点，对每个节点输出：节点名称（node_name）、"
        "付款占比（percentage，如 0.3 表示 30%，必须转换为纯数字）、"
        "付款金额（amount，单位元，若文本中未直接给出则根据合同总金额与占比计算，必须转换为纯数字，缺失时填 0）、"
        "付款条件（condition，如'合同签订后 7 日内'、'验收合格后 15 日内'等）。"
        "\n\n### 提取规则\n"
        "1. 必须仔细阅读全文，找出合同中所有涉及付款的条款，不要遗漏任何付款节点。\n"
        "2. 常见的付款节点包括：预付款、定金、进度款、阶段款、验收款、尾款、质保金、结算款等。\n"
        "3. 如果合同只提到分期付款但没有明确节点，请根据上下文合理拆分为多个节点。\n"
        "4. 所有数字字段如果缺失，必须严格使用数字 0 填充，禁止使用字符串'未知'或其他文本。\n"
        "5. 只要合同中出现任何与付款、支付、价款相关的条款，payment_nodes 就必须包含至少一个节点，绝对禁止输出空数组 []。\n"
        "6. 【极其重要】你必须严格按照文本中的原始数字提取付款占比，绝对禁止自行修正或调整数字以使总和等于100%。"
        "即使文本中的付款比例加起来超过100%或存在其他看似'不合理'的情况，也要如实提取原始数字，不要自作聪明修改。\n"
        "【致命错误示例】文本明确写'合同签订后预付50%，6月底第一次渗透测试完成验收后支付30%，12月全部工作完成验收后支付30%'，"
        "如果你输出 0.2（20%）给最后一个节点，因为觉得 50%+30%+30%=110% 超过了100%，这是严重错误！"
        "正确输出必须是 0.3（30%），严格按照原文提取，不允许任何修正。\n"
        "6.5 【铁律】payment_nodes 中每个节点的 percentage 必须是原文中明确写出的百分比数字之一。"
        "你绝对禁止发明或推算任何百分比。如果原文写了三个百分比（50%、30%、30%），你的 payment_nodes 中必须有且仅有这三个百分比，"
        "顺序与原文一致，不得合并、拆分或修改任何一个数字。\n"
        "7. 请直接输出 JSON 对象，不要包含任何其他文字。\n\n"
        "### 输出格式示例\n"
        '{\n'
        '  "total_amount": 1000000,\n'
        '  "warranty_ratio": 0.05,\n'
        '  "payment_nodes": [\n'
        '    {"node_name": "预付款", "percentage": 0.3, "amount": 300000, "condition": "合同签订后 7 日内"},\n'
        '    {"node_name": "验收款", "percentage": 0.65, "amount": 650000, "condition": "验收合格后 15 日内"},\n'
        '    {"node_name": "质保金", "percentage": 0.05, "amount": 50000, "condition": "质保期满后 7 日内"}\n'
        '  ]\n'
        '}\n\n'
        "【强制约束】payment_nodes 字段绝对不能为空数组。如果文本中确实没有付款信息，请输出一个节点："
        '{"node_name": "一次性付款", "percentage": 1.0, "amount": total_amount, "condition": "合同中未明确分期付款条件"}。'
    )
    if not rules:
        return base

    extras: List[str] = []
    tol = rules.get("price_tolerance", 0.0)
    if tol and tol > 0:
        extras.append(
            _tolerance_rule_prompt(tol)
        )

    clauses = rules.get("required_clauses", []) or []
    if clauses:
        extras.append(
            f"【必检条款规则】：必须严格检查合同中是否包含以下条款：{', '.join(clauses)}。"
            f"如果缺失其中任何一项，必须在结果中明确列出，并标记为高风险缺失项。"
        )

    custom = rules.get("custom_requirements", "")
    if custom and custom.strip():
        extras.append(
            f"【用户自定义专属要求】：{custom.strip()}"
            f"（请最高优先级遵循此要求调整你的分析和输出）。"
        )

    if extras:
        return base + "\n\n" + "\n".join(extras)
    return base


# ---------------------------------------------------------------------------
# 核心提取函数
# ---------------------------------------------------------------------------

async def extract_contract_info(
    text: str,
    model_id: Optional[str] = None,
    rules: Optional[Dict] = None,
    doc_id: Optional[str] = None,
    memory_manager: Optional[Any] = None,
) -> tuple[ContractInfo, dict]:
    """异步调用大模型，从文本中提取 ContractInfo，支持可配置规则与混合上下文。

    当传入 doc_id + memory_manager 时，采用 "12K Head + 3K Tail" 混合提取策略：
    - Head：原文前 12000 字符（保留完整结构）
    - Tail：从 Milvus 检索关键条款补充（最多 3000 字符）
    否则回退到传统智能截断。

    返回 (提取结果, token_usage)。
    """
    if doc_id and memory_manager is not None:
        head_text = text[:12000]
        try:
            tail_context = await memory_manager.retrieve_context(
                doc_id=doc_id,
                query="付款节点、违约金比例、交期天数、总金额、合同期限、服务范围、质保期",
                top_k=2,
            )
        except Exception as exc:
            logger.warning("[Extractor] 检索补充上下文失败: %s", exc)
            tail_context = ""
        tail_text = tail_context[:3000]
        safe_text = (
            f"【合同前文】\n{head_text}\n\n"
            f"【关键条款检索补充】\n{tail_text}"
        )
    else:
        safe_text = _truncate_text(text)

    messages = [
        {"role": "system", "content": _build_extraction_system_prompt(rules)},
        {"role": "user", "content": safe_text},
    ]
    json_str, usage = await chat_completion(
        messages, model_id=model_id, response_format={"type": "json_object"}
    )
    json_str = _strip_markdown_json(json_str)
    info = ContractInfo.model_validate_json(json_str)
    # 校正累计违约金上限比例：LLM 常把 ‰ 误读为 % 或遗漏除 1000
    info.penalty_cap_rate.value = _correct_penalty_rate_from_text(text, info.penalty_cap_rate.value)
    # 校正服务期限天数：LLM 易受"一年期运维"干扰而误填365
    info.service_period_days.value = _correct_service_period_days(
        text, info.service_period_days.reference, info.service_period_days.value
    )
    return info, usage


def _sanitize_financial_json(raw_json: str) -> str:
    """预处理 LLM 返回的财务 JSON，为缺失字段补默认值，避免 Pydantic validation error。"""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json
    if not isinstance(data.get("payment_nodes"), list):
        data["payment_nodes"] = []
    for node in data["payment_nodes"]:
        if not isinstance(node, dict):
            continue
        if node.get("percentage") is None:
            node["percentage"] = 0.0
        if node.get("amount") is None:
            node["amount"] = 0.0
        if not node.get("node_name"):
            node["node_name"] = "未命名付款节点"
        if not node.get("condition"):
            node["condition"] = "未明确"
    return json.dumps(data, ensure_ascii=False)


async def extract_financial_info(
    text: str, model_id: Optional[str] = None, rules: Optional[Dict] = None
) -> tuple[FinancialInfo, dict]:
    """异步调用大模型，从合同文本中提取财务付款安排，支持可配置规则。

    若首次提取的 payment_nodes 为空数组，会自动使用强化 Prompt 重试一次，
    以降低因 LLM 漏读导致的提取失败率。
    返回 (提取结果, token_usage)。"""
    safe_text = _truncate_text(text)
    messages = [
        {"role": "system", "content": _build_financial_system_prompt(rules)},
        {"role": "user", "content": safe_text},
    ]
    json_str, usage = await chat_completion(
        messages, model_id=model_id, response_format={"type": "json_object"}
    )
    json_str = _strip_markdown_json(json_str)
    json_str = _sanitize_financial_json(json_str)
    result = FinancialInfo.model_validate_json(json_str)

    # 付款节点为空时，使用强化 Prompt 重试一次
    if not result.payment_nodes:
        logger.warning(
            "[FinancialExtraction] 首次提取付款节点为空（model=%s），尝试重试...", model_id
        )
        retry_prompt = (
            _build_financial_system_prompt(rules)
            + "\n\n【重要提醒】上一轮提取未找到任何付款节点，请再次仔细阅读文本，"
            "特别注意查找以下关键词：预付款、定金、进度款、阶段款、验收款、尾款、质保金、结算款、"
            "付款方式、付款条件、分期付款。必须找出所有付款节点并输出。"
        )
        messages = [
            {"role": "system", "content": retry_prompt},
            {"role": "user", "content": safe_text},
        ]
        json_str, retry_usage = await chat_completion(
            messages, model_id=model_id, response_format={"type": "json_object"}
        )
        json_str = _sanitize_financial_json(json_str)
        result = FinancialInfo.model_validate_json(json_str)
        usage["prompt_tokens"] += retry_usage["prompt_tokens"]
        usage["completion_tokens"] += retry_usage["completion_tokens"]
        usage["total_tokens"] += retry_usage["total_tokens"]
        logger.info(
            "[FinancialExtraction] 重试后付款节点数量: %s", len(result.payment_nodes)
        )

    return result, usage


