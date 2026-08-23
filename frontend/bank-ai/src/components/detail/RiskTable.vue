<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Money,
  Timer,
  Document,
  OfficeBuilding,
  Warning,
  Check,
  List,
  DocumentCopy,
  ArrowDown,
  ArrowUp,
} from '@element-plus/icons-vue'

import type { DifferenceItem, MissingItem, BidInfo, ContractInfo, PhysicalAlert } from '@/types/api'

const props = defineProps<{
  differences?: DifferenceItem[] | string[]
  missingItems?: MissingItem[]
  matches?: string[]
  bidInfo?: BidInfo
  contractInfo?: ContractInfo
  physicalAlerts?: PhysicalAlert[]
}>()

interface RiskItem {
  type: string
  typeLabel: string
  typeTag: 'danger' | 'warning' | 'info' | 'primary' | 'success'
  icon: any
  description: string
  suggestion: string
  bidText: string
  contractText: string
  isMissing?: boolean
  originalText?: string
  riskComment?: string
  riskLevel: 'high' | 'medium' | 'low' | 'positive'
  riskLabel: string
  isFavorable: boolean
  location?: string
}

function getDiffText(d: DifferenceItem | string): string {
  return typeof d === 'string' ? d : d.description || ''
}

/** 去掉描述中常见的冗余前缀 */
function cleanClausePrefix(text: string): string {
  return text
    .replace(/^采购结果文件中[的为是提到]*/g, '')
    .replace(/^采购合同[中的为是提到]*/g, '')
    .replace(/^合同[中的为是提到]*/g, '')
    .replace(/^正式合同[中的为是提到]*/g, '')
    .replace(/^乙方[的为是提到]*/g, '')
    .replace(/^甲方[的为是提到]*/g, '')
    .trim()
}

const qtySuffixPattern = /\d+[\s]*(?:批|台|套|个|件|组|条|只|台套|套组)[）)]*$/i

/** 去除文本中的位置前缀、标点、空白，用于实质一致性比较 */
function normalizeForComparison(text: string): string {
  return text
    .replace(/【[^】]+】/g, '') // 去除【采购结果】【合同第X条】等位置标记
    .replace(/采购结果(文件)?[中的为是提到]*/g, '')
    .replace(/正式?合同[中的为是提到]*/g, '')
    .replace(/第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?/g, '')
    .replace(qtySuffixPattern, '') // 去除末尾数量后缀
    .replace(/[，。；,;]/g, '') // 去除常见标点
    .replace(/\s+/g, '') // 去除所有空白
    .trim()
}

/** 判断两边是否为严格包含关系：一侧只是另一侧末尾多了数量后缀。
 *  例如 "规格原厂配件/含安装" 与 "规格原厂配件/含安装1批" → true
 *  例如 "10个" 与 "5个" → false（数量本身是差异）
 */
function isSubstantiallySame(bid: string, contract: string): boolean {
  const b = bid.trim()
  const c = contract.trim()
  if (!b || !c) return false

  // 快速路径：完全相同
  if (b === c) return true

  // 归一化后比较：去除位置前缀、标点、空白
  const bNorm = normalizeForComparison(b)
  const cNorm = normalizeForComparison(c)
  if (bNorm && cNorm && bNorm === cNorm) return true

  // 保留原有逻辑：末尾数量后缀
  const bStripped = b.replace(qtySuffixPattern, '').trim()
  const cStripped = c.replace(qtySuffixPattern, '').trim()
  // 严格模式：只有 A 去掉末尾数量后缀 === B（或反之），才认为是伪差异
  if (bStripped === c && b !== c) return true
  if (cStripped === b && c !== b) return true
  return false
}

const missingKeywords = ['未提及', '未约定', '无相关', '未明确', '未列明', '无约定', '未涉及', '不存在', '未规定', '未见']

const EMPTY_SEMANTIC_WORDS = new Set([
  '未提及', '无', '未见相关条款', '未见', '未约定', '无相关',
  '未明确', '未列明', '无约定', '未涉及', '不存在', '未规定',
  '-', '—', '', '（合同中未找到）', '（采购结果中有）',
])

/** 判断是否为 false positive 的 missing_item */
function isFalsePositiveMissing(m: any): boolean {
  const orig = (m.original_text || '').trim()
  const cont = (m.contract_text || '').trim()

  // 1. 采购结果侧必须确有约定
  if (!orig || orig.length < 5) return true
  if (missingKeywords.some(k => orig.includes(k))) return true

  // 2. 合同侧必须确实缺失（若合同侧有实质内容，则不是缺失）
  if (cont && cont.length > 15 && !missingKeywords.some(k => cont.includes(k))) return true

  return false
}

/** 判断是否为双向均未提及的伪差异（如两边都写"未提及保密期限"） */
function isBidirectionalMissing(bid: string, contract: string): boolean {
  const b = bid.trim()
  const c = contract.trim()
  if (!b || !c) return false
  const bidMissing = missingKeywords.some(k => b.includes(k))
  const contractMissing = missingKeywords.some(k => c.includes(k))
  // 两边都包含否定词，且内容都很短，大概率是双向未提及
  if (bidMissing && contractMissing && b.length < 30 && c.length < 30) return true
  return false
}

/** 更强力的双向空语义检测（兜底） */
function isBidirectionalEmpty(bid: string, contract: string): boolean {
  const b = bid.trim()
  const c = contract.trim()
  if (!b || !c) return false
  const isEmpty = (text: string) => {
    if (!text || EMPTY_SEMANTIC_WORDS.has(text)) return true
    if (text.length < 25 && missingKeywords.some(k => text.includes(k))) return true
    return false
  }
  return isEmpty(b) && isEmpty(c)
}

/** 从差异描述中拆分出采购结果和合同两边的值 */
function splitClauseDescription(text: string): { bid: string; contract: string } {
  const desc = text.includes('：') ? text.split('：').slice(1).join('：') : text
  // 模式1: "...，而..." 或 "...。而..."
  const m1 = desc.match(/(.+?)[，。]而(.+)/)
  if (m1 && m1[1] && m1[2]) {
    return {
      bid: cleanClausePrefix(m1[1].trim().replace(/[。；]$/, '')),
      contract: cleanClausePrefix(m1[2].trim().replace(/[。；]$/, '')),
    }
  }
  // 模式2: 用"合同"或"实际"关键词作为分界（处理付款方式等多节点文本）
  const contractMarkers = ['合同约定', '合同为', '合同约', '实际约定', '实际为', '实际']
  for (const marker of contractMarkers) {
    const idx = desc.indexOf(marker)
    if (idx > 3) {
      const bidPart = desc.slice(0, idx).replace(/[，,；;。]$/, '').trim()
      const contractPart = desc.slice(idx).trim()
      return {
        bid: cleanClausePrefix(bidPart),
        contract: cleanClausePrefix(contractPart),
      }
    }
  }
  // 模式3: "采购结果...合同..."
  const m3 = desc.match(/(.+?)[:：,，;；]合同[约为是]?(.+)/)
  if (m3 && m3[1] && m3[2]) {
    return {
      bid: cleanClausePrefix(m3[1].trim().replace(/[。；]$/, '')),
      contract: cleanClausePrefix(m3[2].trim().replace(/[。；]$/, '')),
    }
  }
  // 模式4: 包含对比词（实际/但是/然而/却/相反/现为/变成/改为）
  const m4 = desc.match(/(.+?)[，,；;。](?:实际|但是|然而|却|相反|现为|变成|改为)[上中]?[约为是]?(.*)/)
  if (m4 && m4[1]) {
    return {
      bid: cleanClausePrefix(m4[1].trim().replace(/[。；]$/, '')),
      contract: cleanClausePrefix((m4[2] || '').trim().replace(/[。；]$/, '')),
    }
  }
  // 模式5: 分号分隔（确保后半部分包含"合同"关键词，避免在多节点内容中误截断）
  const m5 = desc.match(/^(.+?)[；;](?=.*?(?:合同|实际))(.+)$/)
  if (m5 && m5[1] && m5[2]) {
    return {
      bid: cleanClausePrefix(m5[1].trim().replace(/[。；]$/, '')),
      contract: cleanClausePrefix(m5[2].trim().replace(/[。；]$/, '')),
    }
  }
  return { bid: cleanClausePrefix(desc), contract: cleanClausePrefix(desc) }
}

function classifyDiff(diffText: string): Omit<RiskItem, 'description' | 'suggestion' | 'isMissing'> {
  const d = diffText.toLowerCase()
  const base = { bidText: '', contractText: '', riskLevel: 'high' as const, riskLabel: '高风险', isFavorable: false }
  if (d.includes('供应商') || d.includes('vendor_name') || d.includes('签署方')) {
    return { ...base, type: 'vendor', typeLabel: '供应商', typeTag: 'danger' as const, icon: OfficeBuilding }
  }
  if (d.includes('金额') || d.includes('总价') || d.includes('价款') || d.includes('价格')) {
    return { ...base, type: 'amount', typeLabel: '金额', typeTag: 'danger' as const, icon: Money }
  }
  if (d.includes('交期') || d.includes('交付') || d.includes('工期') || d.includes('天数')) {
    return { ...base, type: 'delivery', typeLabel: '交期', typeTag: 'warning' as const, icon: Timer }
  }
  if (d.includes('违约') || d.includes('赔偿') || d.includes('法务') || d.includes('条款')) {
    return { ...base, type: 'legal', typeLabel: '法务', typeTag: 'warning' as const, icon: Document }
  }
  if (d.includes('必检') || d.includes('缺失') || d.includes('缺失项')) {
    return { ...base, type: 'missing', typeLabel: '必检', typeTag: 'danger' as const, icon: Warning }
  }
  return { ...base, type: 'other', typeLabel: '其他', typeTag: 'info' as const, icon: List }
}

/** 将后端可能返回的英文/路径格式 type 翻译为中文 */
function translateTypeLabel(type: string): string {
  if (!type) return '其他'
  // 已经是中文，直接返回（过滤掉带【】前缀的物理层类型，保留原样）
  if (/^[一-龥【】]/.test(type)) return type

  const exactMap: Record<string, string> = {
    // slash 格式（老后端）
    'service/delivery_period': '服务/交付期限',
    'price/deviation': '价格偏差',
    'quantity/difference': '数量差异',
    'scope/inconsistency': '服务范围不一致',
    'payment/mismatch': '付款方式不一致',
    'penalty/weakening': '违约金条款弱化',
    'value_added/missing': '增值服务缺失',
    'warranty/shortening': '质保期缩短',
    'tax_rate/missing': '税率说明缺失',
    'delivery_time/inconsistency': '交货/交付时间不一致',
    'calculation/error': '合同明细小计计算错误',
    'other/substantive_risks': '其他实质性风险',
    'missing/item': '缺失条款',
    'vendor/change': '供应商变更',
    'amount/change': '金额变更',
    'legal/difference': '法务差异',
    'global/term': '全局条款',
    'contract/specification': '规格篡改',
    'contract/new': '合同新增项目',
    'total_price/error': '总价计算错误',
    'termination_compensation': '解约赔偿比例',
    'delay_daily_rate': '逾期违约金',
    'penalty_cap_rate': '累计违约金上限',
    'termination_penalty_rate': '解约赔偿比例',
    '违约金比例变动': '违约金条款变更',
    '违约金比例变更': '违约金条款变更',
    '逾期违约金': '逾期违约金',
    '解约违约金': '解约赔偿比例',
    // snake_case 格式（MoE 后端）
    price_deviation: '价格偏差',
    service_scope_change: '服务范围变更',
    warranty_period_reduction: '质保期缩短',
    quantity_difference: '数量差异',
    delivery_period_change: '交付期限变更',
    payment_mismatch: '付款方式不一致',
    penalty_weakening: '违约金条款弱化',
    value_added_missing: '增值服务缺失',
    tax_rate_missing: '税率说明缺失',
    delivery_time_inconsistency: '交货/交付时间不一致',
    calculation_error: '合同明细小计计算错误',
    other_substantive_risks: '其他实质性风险',
    missing_item: '缺失条款',
    vendor_change: '供应商变更',
    amount_change: '金额变更',
    legal_difference: '法务差异',
    global_term: '全局条款',
    contract_specification: '规格篡改',
    contract_new: '合同新增项目',
    total_price_error: '总价计算错误',
    service_change: '服务变更',
    scope_change: '范围变更',
    warranty_shortening: '质保期缩短',
    price_change: '价格变更',
    payment_change: '付款变更',
    delivery_change: '交付变更',
    legal_risk: '法务风险',
    missing_clause: '缺失条款',
    clause_missing: '条款缺失',
  }
  if (exactMap[type]) return exactMap[type]

  // 分段模糊翻译
  const segMap: Record<string, string> = {
    service: '服务', delivery: '交付', period: '期限',
    price: '价格', deviation: '偏差', quantity: '数量',
    difference: '差异', scope: '范围', inconsistency: '不一致',
    payment: '付款', mismatch: '不匹配', penalty: '违约金',
    weakening: '弱化', value_added: '增值服务', missing: '缺失',
    warranty: '质保', shortening: '缩短', tax_rate: '税率',
    delivery_time: '交期', calculation: '计算', error: '错误',
    other: '其他', substantive: '实质性', risks: '风险',
    item: '条款', vendor: '供应商', change: '变更',
    amount: '金额', legal: '法务', global: '全局',
    term: '期限', contract: '合同', specification: '规格',
    tamper: '篡改', new: '新增', total_price: '总价',
    termination: '解约', compensation: '赔偿', delay: '逾期',
    daily: '日', rate: '比例', cap: '上限', penalty_cap: '违约金上限',
    termination_penalty: '解约赔偿',
  }
  const translated = type
    .split('/')
    .map((s) => segMap[s] || s)
    .filter(Boolean)
    .join('/')
  return translated || '其他'
}

/** 从 original_text / contract_text / description 中提取条款位置或条款名称 */
function extractLocation(originalText?: string, contractText?: string, description?: string): string {
  const locs: string[] = []

  // 1. 优先从 original_text / contract_text 提取【...】或 "第X条" 位置
  if (originalText) {
    let m = originalText.match(/【采购结果([^】]*)】/)
    if (m) {
      locs.push(`采购结果${m[1]}`)
    } else {
      m = originalText.match(/采购结果(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?)/)
      if (m) {
        locs.push(`采购结果${m[1]}`)
      } else {
        m = originalText.match(/(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?)/)
        if (m) {
          locs.push(`采购结果${m[1]}`)
        } else {
          m = originalText.match(/【([^】]{2,30})】/)
          if (m) locs.push(`采购结果${m[1]}`)
        }
      }
    }
  }

  if (contractText) {
    let m = contractText.match(/【合同([^】]*)】/)
    if (m) {
      locs.push(`合同${m[1]}`)
    } else {
      m = contractText.match(/合同(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?)/)
      if (m) {
        locs.push(`合同${m[1]}`)
      } else {
        m = contractText.match(/(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?)/)
        if (m) {
          locs.push(`合同${m[1]}`)
        } else {
          m = contractText.match(/【([^】]{2,30})】/)
          if (m) locs.push(`合同${m[1]}`)
        }
      }
    }
  }

  // 2. 兜底：从 description 中提取条款名称（如"项目总价"、"质量保证期"等）
  if (!locs.length && description) {
    const clausePatterns = [
      /(?:关于|涉及|针对|在)["']?(.{2,12}?)(?:条款|项|内容|约定|比例|金额|价格|期限|期|方式)["']?/,
      /(?:项目总价|合同总金额|单价|总价|金额|价款|违约金|质保期|交付期|付款方式|预付款|尾款|税率|赔偿|违约金|日罚息|上限)[\s：:]*/,
      /^(项目总价|合同总金额|单价|总价|金额|价款|违约金|质保期|质量保证期|交付期|交货期|付款方式|预付款|尾款|税率|赔偿|日罚息|上限|服务范围|货物所有权|毁损灭失风险)/,
    ]
    for (const pat of clausePatterns) {
      const m = description.match(pat)
      if (m && m[1]) {
        const name = m[1].trim()
        if (name.length >= 2 && name.length <= 15) {
          locs.push(`${name}`)
          break
        }
      }
      if (m && !m[1] && m[0]) {
        const name = m[0].trim().replace(/[：:]$/, '')
        if (name.length >= 2 && name.length <= 15) {
          locs.push(`${name}`)
          break
        }
      }
    }
  }

  return locs.length ? `📍 ${locs.join(' / ')}` : ''
}

function getFallbackSuggestion(diffText: string) {
  const d = diffText.toLowerCase()
  if (d.includes('供应商')) {
    return '核对供应商资质文件，确保合同签署方与中标方完全一致，避免法律主体风险。'
  }
  if (d.includes('金额') || d.includes('总价') || d.includes('价款')) {
    return '重新核算合同价款，明确差异原因，必要时启动补充协议或重新招标流程。'
  }
  if (d.includes('交期') || d.includes('交付') || d.includes('工期')) {
    return '评估交期变更对项目进度的影响，要求供应商提供书面延期说明及补救措施。'
  }
  if (d.includes('违约') || d.includes('赔偿')) {
    return '将违约金比例调整回采购结果约定值，确保违约条款不低于原始承诺。'
  }
  if (d.includes('付款') || d.includes('支付') || d.includes('节点') || d.includes('分期')) {
    return '核对付款节点、比例及条件是否与采购结果一致，避免资金支付风险。'
  }
  if (d.includes('必检') || d.includes('缺失')) {
    return '立即补充缺失条款，否则视为重大合规缺陷，建议暂缓签署。'
  }
  return '对该差异项进行专项复核，并与业务及法务部门沟通确认整改方案。'
}

/** 判断是否为正面差异（合同比采购结果更有利、更完善） */
function isPositiveDiff(item: any): boolean {
  // 优先信任后端明确标记的 is_favorable_to_buyer 字段（清单核对法引入）
  if (typeof item === 'object' && item.is_favorable_to_buyer === true) {
    return true
  }
  if (typeof item === 'object' && item.is_favorable_to_buyer === false) {
    return false
  }

  const suggestion = typeof item === 'object' ? (item.suggested_amendment || '') : ''
  const riskComment = typeof item === 'object' ? (item.risk_comment || '') : ''
  const description = typeof item === 'string' ? item : (item.description || '')

  // 后端 prompt 要求：正面差异 suggested_amendment 必须为空
  const hasNoSuggestion = !suggestion || suggestion.trim().length === 0
  if (!hasNoSuggestion) return false

  const positiveKeywords = ['增强', '有利', '已明确', '完善', '优于', '提高', '确保', '合理', '合规', '充分', '升级', '上调']
  const negativeKeywords = ['差异', '不一致', '不符', '下调', '降低', '缺失', '遗漏', '风险', '不利', '缩小', '减少', '不足']

  const rc = riskComment.toLowerCase()
  const desc = description.toLowerCase()

  const hasPositive = positiveKeywords.some(k => rc.includes(k) || desc.includes(k))
  const hasNegative = negativeKeywords.some(k => rc.includes(k) || desc.includes(k))

  if (hasPositive && !hasNegative) return true
  if (rc.includes('增强了') || rc.includes('已明确') || rc.includes('完善了') || rc.includes('更有利')) return true

  return false
}

const mergedCount = ref(0)

const riskItems = computed((): RiskItem[] => {
  const items: RiskItem[] = []
  let merged = 0

  // 1. 缺失条款（完整展示，不做 title 去重）
  const missing = props.missingItems || []
  for (const m of missing) {
    const text = m.description || ''
    if (!text) continue
    // 双向均未提及的伪缺失，直接抹杀
    if (isBidirectionalEmpty(m.original_text || '', m.contract_text || '')) {
      merged++
      continue
    }
    // 抹杀 false positive：采购结果中本来就没有，或合同侧实际存在的"缺失"
    if (isFalsePositiveMissing(m)) {
      merged++
      continue
    }

    const cls = classifyDiff(text)
    const suggestion = m.suggested_amendment || getFallbackSuggestion(text)
    items.push({
      ...cls,
      typeLabel: translateTypeLabel((m as any).type || cls.typeLabel),
      riskLevel: 'high',
      riskLabel: '高风险',
      isFavorable: false,
      description: text,
      suggestion,
      bidText: m.original_text || '（采购结果中有）',
      contractText: m.contract_text || '（合同中未找到）',
      isMissing: true,
      originalText: m.original_text || '',
      riskComment: m.risk_comment || '',
      location: extractLocation(m.original_text, m.contract_text, text),
    })
  }

  // 2. 条款差异（完整展示，不做 title 去重）
  const diffs = props.differences || []
  for (const d of diffs) {
    const text = getDiffText(d)
    if (!text || (text.includes('一致') && text.includes('未发现'))) continue

    const cls = classifyDiff(text)
    const suggestion = typeof d === 'object' && d.suggested_amendment
      ? d.suggested_amendment
      : getFallbackSuggestion(text)
    const bc = splitClauseDescription(text)
    const bidText = typeof d === 'object' && d.original_text ? d.original_text : bc.bid
    const contractText = typeof d === 'object' && d.contract_text ? d.contract_text : bc.contract

    // 双向未提及过滤：如果两侧原文都为空或只有占位符，说明是双向未提及的伪差异，跳过
    const hasBidContent = bidText && bidText !== '—' && bidText.trim().length > 3
    const hasContractContent = contractText && contractText !== '—' && contractText.trim().length > 3
    if (!hasBidContent && !hasContractContent) {
      merged++
      continue
    }

    // 双向均未提及过滤：如果两边都是"未提及""未约定"等否定描述，说明两边都没这个条款，跳过
    if (isBidirectionalEmpty(bidText, contractText) || isBidirectionalMissing(bidText, contractText)) {
      merged++
      continue
    }

    // 语义归一化：去除数量单位后若实质一致，则跳过
    if (isSubstantiallySame(bidText, contractText)) {
      merged++
      continue
    }

    const favorable = isPositiveDiff(d)
    const riskLevel: RiskItem['riskLevel'] = favorable
      ? 'positive'
      : (cls.typeTag === 'danger' ? 'high' : cls.typeTag === 'warning' ? 'medium' : 'low')
    const riskLabel = favorable
      ? '有利项'
      : (cls.typeTag === 'danger' ? '高风险' : cls.typeTag === 'warning' ? '中风险' : '低风险')

    items.push({
      ...cls,
      typeLabel: translateTypeLabel((typeof d === 'object' && d.type) || cls.typeLabel),
      typeTag: favorable ? 'success' : cls.typeTag,
      riskLevel,
      riskLabel,
      isFavorable: favorable,
      description: text,
      suggestion,
      bidText,
      contractText,
      isMissing: false,
      originalText: typeof d === 'object' ? (d.original_text || '') : '',
      riskComment: typeof d === 'object' ? (d.risk_comment || '') : '',
      location: extractLocation(
        typeof d === 'object' ? d.original_text : undefined,
        typeof d === 'object' ? d.contract_text : undefined,
        text
      ),
    })
  }

  mergedCount.value = merged
  return items
})

const matchItems = computed(() => {
  return (props.matches || []).filter((m) => m && m.trim())
})

const showAllRisks = ref(false)
const isExpanded = ref(false)
const isMatchExpanded = ref(false)

const sortedRiskItems = computed((): RiskItem[] => {
  return [...riskItems.value].sort((a, b) => {
    // 排序：不利项在前，有利项在后
    if (a.isFavorable !== b.isFavorable) {
      return a.isFavorable ? 1 : -1
    }
    // 同类型内：缺失项在前，其次是按 severity
    if (a.isMissing !== b.isMissing) {
      return a.isMissing ? -1 : 1
    }
    const tagWeight: Record<string, number> = { danger: 3, warning: 2, info: 1, primary: 0, success: -1 }
    return (tagWeight[b.typeTag] || 0) - (tagWeight[a.typeTag] || 0)
  })
})

const displayedRiskItems = computed((): RiskItem[] => {
  if (showAllRisks.value) return sortedRiskItems.value
  return sortedRiskItems.value.slice(0, 3)
})

const remainingCount = computed(() =>
  Math.max(0, sortedRiskItems.value.length - displayedRiskItems.value.length)
)

const copySuggestion = (text: string) => {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('条款已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}
</script>

<template>
  <div class="risk-table">
    <!-- 物理引擎强制警报（置信度 1.0，最高优先级） -->
    <div v-if="props.physicalAlerts && props.physicalAlerts.length" id="section-physical" class="report-section physical-alert-section">
      <div class="section-title physical-section-title">
        <el-icon><Warning /></el-icon>
        物理引擎强制警报
        <el-tag type="danger" size="small" effect="dark" class="risk-count-tag">{{ props.physicalAlerts.length }} 项</el-tag>
        <el-tag type="info" size="small" effect="plain" class="risk-count-tag">置信度 1.0</el-tag>
      </div>
      <div class="physical-alert-list">
        <div
          v-for="(alert, idx) in props.physicalAlerts"
          :key="idx"
          class="physical-alert-card"
        >
          <div class="physical-alert-header">
            <div class="physical-alert-tags">
              <el-tag type="danger" size="small" effect="dark">物理引擎</el-tag>
              <el-tag type="info" size="small" effect="plain">{{ alert.side }}</el-tag>
              <el-tag type="warning" size="small" effect="light">{{ alert.item_name }}</el-tag>
            </div>
            <div class="physical-alert-index">#{{ idx + 1 }}</div>
          </div>
          <div class="physical-alert-body">
            <div class="physical-alert-meta">
              <span class="meta-label">检测工具</span>
              <span class="meta-value">{{ alert.tool }}</span>
              <span class="meta-divider">|</span>
              <span class="meta-label">问题类型</span>
              <span class="meta-value">{{ alert.type }}</span>
            </div>
            <div class="physical-alert-desc">{{ alert.description }}</div>
            <div v-if="alert.deviation !== undefined || alert.deviation_pct !== undefined" class="physical-alert-deviation">
              <span class="deviation-label">偏差量化：</span>
              <span v-if="alert.deviation !== undefined" class="deviation-value">{{ alert.deviation }}</span>
              <span v-if="alert.deviation_pct !== undefined" class="deviation-pct">（{{ alert.deviation_pct }}%）</span>
            </div>
          </div>
          <div class="physical-alert-llm-note">
            <div class="llm-note-label">✨ LLM 补充说明</div>
            <div class="llm-note-text">
              该条目由物理引擎基于「单价 × 数量 = 小计」的数学硬规则强制验算检出，置信度 1.0。
              <span v-if="alert.deviation_pct && alert.deviation_pct > 0">
                合同约定金额比采购结果高出 {{ alert.deviation_pct }}%，属于实质性数值偏差，建议立即核对原始报价单与合同附件中的计算明细。
              </span>
              <span v-else-if="alert.deviation_pct && alert.deviation_pct < 0">
                合同约定金额比采购结果低 {{ Math.abs(alert.deviation_pct) }}%，需警惕是否存在漏项、折扣未明确或笔误导致的隐性风险。
              </span>
              <span v-else>
                如确认数据无误，请检查是否存在四舍五入规则差异或税率计算口径不一致。
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 核心风险透视 -->
    <div v-if="sortedRiskItems.length" id="section-risk" class="report-section risk-table-section">
      <div class="section-title risk-section-title" @click="isExpanded = !isExpanded">
        <el-icon><Warning /></el-icon>
        核心风险透视
        <el-tag type="danger" size="small" class="risk-count-tag">{{ riskItems.length }} 项</el-tag>
        <el-tag v-if="mergedCount > 0" type="info" size="small" effect="plain" class="risk-count-tag">
          已智能合并 {{ mergedCount }} 项实质一致
        </el-tag>
        <el-icon class="expand-icon" :class="{ 'is-expanded': isExpanded }">
          <ArrowDown v-if="!isExpanded" />
          <ArrowUp v-else />
        </el-icon>
      </div>

      <div v-show="isExpanded" class="risk-card-list">
        <div v-for="(item, idx) in displayedRiskItems" :key="idx" class="risk-card">
          <div class="risk-card-header">
            <div class="risk-type">
              <el-icon class="type-icon"><component :is="item.icon" /></el-icon>
              <el-tag :type="item.typeTag" size="small" effect="dark" class="type-tag">
                {{ item.typeLabel }}
              </el-tag>
              <el-tag
                :type="item.isFavorable ? 'success' : (item.riskLevel === 'high' ? 'danger' : 'warning')"
                size="small"
                effect="light"
                class="risk-level-tag"
              >
                {{ item.riskLabel }}
              </el-tag>
              <el-tag v-if="item.isMissing" type="danger" size="small" effect="plain" class="missing-tag">
                缺失
              </el-tag>
            </div>
            <div class="risk-index">#{{ idx + 1 }}</div>
          </div>
          <div class="risk-card-body">
            <!-- 条款位置 -->
            <div v-if="item.location" class="risk-location">
              {{ item.location }}
            </div>
            <!-- 采购结果约定 vs 合同约定 -->
            <div class="risk-compare-row">
              <div class="risk-compare-col risk-compare-col--bid">
                <div class="risk-compare-label">📄 采购结果约定</div>
                <div class="risk-compare-text">{{ item.bidText || '—' }}</div>
              </div>
              <div
                class="risk-compare-col"
                :class="item.isFavorable ? 'risk-compare-col--contract-favorable' : 'risk-compare-col--contract-unfavorable'"
              >
                <div class="risk-compare-label">📝 合同约定</div>
                <div class="risk-compare-text">{{ item.contractText || '—' }}</div>
              </div>
            </div>
            <!-- AI 审查批注 -->
            <div
              class="risk-comment-block"
              :class="{ 'risk-comment-block--favorable': item.isFavorable }"
            >
              <div class="risk-comment-label">✨ AI 审查批注</div>
              <div class="risk-comment-text">
                <div v-if="item.description" class="ai-comment-line"
                  ><strong>差异说明：</strong>{{ item.description }}</div>
                <div v-if="item.suggestion" class="ai-comment-line"
                  ><strong>修改建议：</strong>{{ item.suggestion }}</div>
                <div v-if="item.riskComment" class="ai-comment-line"
                  ><strong>风险批注：</strong>{{ item.riskComment }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 展开/收起 Toggle -->
      <div v-show="isExpanded && (remainingCount > 0 || showAllRisks)" class="risk-toggle-wrap">
        <el-button
          type="primary"
          link
          class="risk-toggle-btn"
          @click="showAllRisks = !showAllRisks"
        >
          <template v-if="!showAllRisks">
            <el-icon><ArrowDown /></el-icon>
            展开剩余 {{ remainingCount }} 项风险提示
          </template>
          <template v-else>
            <el-icon><ArrowUp /></el-icon>
            收起
          </template>
        </el-button>
      </div>
    </div>

    <!-- 一致项 -->
    <div v-if="matchItems.length" class="report-section">
      <div class="section-title section-title--success" @click="isMatchExpanded = !isMatchExpanded">
        <el-icon><Check /></el-icon>
        一致项确认
        <el-tag type="success" size="small" class="risk-count-tag">{{ matchItems.length }} 项</el-tag>
        <el-icon class="expand-icon" :class="{ 'is-expanded': isMatchExpanded }">
          <ArrowDown v-if="!isMatchExpanded" />
          <ArrowUp v-else />
        </el-icon>
      </div>
      <div v-show="isMatchExpanded" class="match-tag-list">
        <el-tag
          v-for="(m, idx) in matchItems"
          :key="idx"
          type="success"
          size="default"
          effect="plain"
          class="match-tag-item"
        >
          <el-icon class="tag-icon"><Check /></el-icon>
          {{ m }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-section {
  margin-bottom: 22px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1e40af;
  border-left: 4px solid #2563eb;
  padding-left: 10px;
  margin-bottom: 14px;
}

.section-title--success {
  color: #166534;
  border-left-color: #22c55e;
  cursor: pointer;
  user-select: none;
}

.risk-count-tag {
  margin-left: 6px;
  font-weight: 500;
}

/* 风险卡片列表 */
.risk-card-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  transition: box-shadow 0.2s ease;
}

.risk-card:hover {
  box-shadow: 0 4px 16px rgba(30, 58, 138, 0.08);
}

.risk-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.risk-location {
  font-size: 12px;
  color: #475569;
  font-weight: 500;
  margin-bottom: 10px;
  padding: 4px 8px;
  background: #f1f5f9;
  border-radius: 4px;
  display: inline-block;
}

.risk-type {
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-icon {
  font-size: 16px;
  color: #64748b;
}

.type-tag {
  font-weight: 600;
}

.risk-level-tag {
  margin-left: 4px;
  font-weight: 600;
}

.risk-index {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

.risk-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ===== 采购结果 vs 合同原文 并排 ===== */
.risk-compare-row {
  display: flex;
  gap: 12px;
}

.risk-compare-col {
  flex: 1;
  min-width: 0;
  border-radius: 8px;
  padding: 12px 14px;
}

.risk-compare-col--bid {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.risk-compare-col--contract {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.risk-compare-col--contract-favorable {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
}

.risk-compare-col--contract-favorable .risk-compare-label {
  color: #166534;
}

.risk-compare-col--contract-unfavorable {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.risk-compare-col--contract-unfavorable .risk-compare-label {
  color: #991b1b;
}

.risk-compare-label {
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 6px;
  color: #475569;
}

.risk-compare-col--bid .risk-compare-label {
  color: #1e40af;
}

.risk-compare-col--contract .risk-compare-label {
  color: #991b1b;
}

.risk-compare-text {
  font-size: 13px;
  color: #334155;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
  font-weight: 500;
}

/* ===== 差异说明 ===== */
.risk-desc-block {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 12px 14px;
}

.risk-desc-label {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 6px;
}

.risk-desc-text {
  font-size: 13px;
  color: #78350f;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
}

/* ===== 修改建议 ===== */
.risk-suggestion-block {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border: 1px solid #bbf7d0;
  border-left: 4px solid #16a34a;
  border-radius: 0 8px 8px 0;
  padding: 12px 14px;
  transition: box-shadow 0.25s ease;
}

.risk-suggestion-block:hover {
  box-shadow: 0 4px 16px rgba(22, 163, 74, 0.1);
}

.risk-suggestion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.risk-suggestion-label {
  font-size: 12px;
  font-weight: 700;
  color: #15803d;
}

.copy-btn {
  font-weight: 600;
}

.risk-suggestion-text {
  font-size: 13px;
  color: #14532d;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ===== 风险提示 ===== */
.risk-comment-block {
  background: linear-gradient(135deg, #fef2f2 0%, #fff5f5 100%);
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 12px 14px;
}

.risk-comment-label {
  font-size: 12px;
  font-weight: 700;
  color: #991b1b;
  margin-bottom: 6px;
}

.risk-comment-text {
  font-size: 13px;
  color: #7f1d1d;
  line-height: 1.7;
  font-weight: 500;
  word-break: break-word;
  overflow-wrap: break-word;
}

.ai-comment-line {
  margin-bottom: 6px;
}

.ai-comment-line:last-child {
  margin-bottom: 0;
}

/* 有利项的 AI 审查批注绿色样式 */
.risk-comment-block--favorable {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border: 1px solid #bbf7d0;
}

.risk-comment-block--favorable .risk-comment-label {
  color: #166534;
}

.risk-comment-block--favorable .risk-comment-text {
  color: #166534;
}

.missing-tag {
  margin-left: 6px;
}

/* 差异标签列表 */
.diff-tag-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-tag-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  height: auto;
  white-space: normal;
  line-height: 1.6;
}

.tag-icon {
  font-size: 14px;
  margin-top: 2px;
  flex-shrink: 0;
}

.tag-text {
  font-size: 13px;
}

/* 一致项标签 */
.match-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.match-tag-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  height: auto;
  white-space: normal;
  line-height: 1.5;
}

/* 展开/收起 Toggle */
.risk-toggle-wrap {
  display: flex;
  justify-content: center;
  margin-top: 14px;
}

.risk-toggle-btn {
  font-weight: 600;
  font-size: 13px;
  padding: 6px 16px;
  border-radius: 20px;
  background: #f1f5f9;
  transition: background 0.2s ease;
}

.risk-toggle-btn:hover {
  background: #e2e8f0;
}

/* ===== 折叠控制 ===== */
.risk-section-title {
  cursor: pointer;
  user-select: none;
}

.expand-icon {
  margin-left: auto;
  transition: transform 0.3s ease;
  color: #64748b;
}

.expand-icon.is-expanded {
  transform: rotate(180deg);
}

/* ===== 物理引擎强制警报 ===== */
.physical-alert-section {
  margin-bottom: 22px;
}

.physical-section-title {
  color: #991b1b;
  border-left-color: #dc2626;
}

.physical-alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.physical-alert-card {
  background: linear-gradient(135deg, #fef2f2 0%, #fff5f5 100%);
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 14px 16px;
  transition: box-shadow 0.2s ease;
}

.physical-alert-card:hover {
  box-shadow: 0 4px 16px rgba(220, 38, 38, 0.1);
}

.physical-alert-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.physical-alert-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.physical-alert-index {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

.physical-alert-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.physical-alert-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
}

.meta-label {
  color: #64748b;
  font-weight: 500;
}

.meta-value {
  color: #1e293b;
  font-weight: 600;
}

.meta-divider {
  color: #cbd5e1;
}

.physical-alert-desc {
  font-size: 13px;
  color: #7f1d1d;
  line-height: 1.7;
  font-weight: 500;
  word-break: break-word;
  overflow-wrap: break-word;
}

.physical-alert-deviation {
  font-size: 13px;
  color: #dc2626;
  font-weight: 600;
  background: #fee2e2;
  padding: 6px 10px;
  border-radius: 6px;
  display: inline-block;
}

.deviation-label {
  color: #991b1b;
}

.deviation-value {
  font-weight: 700;
}

.deviation-pct {
  font-weight: 700;
}

.physical-alert-llm-note {
  background: linear-gradient(135deg, #fffbeb 0%, #fff7ed 100%);
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 10px 12px;
}

.llm-note-label {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 4px;
}

.llm-note-text {
  font-size: 12px;
  color: #78350f;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
}
</style>
