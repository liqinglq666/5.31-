<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, Download, CollectionTag, Message, Connection, CircleCheck, DocumentCopy, Document, ArrowRight, Warning, Cpu, Location, FullScreen, Close } from '@element-plus/icons-vue'
import type { TaskResult, VisualEvidence } from '@/types/api'
import { archiveTask, exportReportPdf } from '@/api/task'
import ComplianceScore from '@/components/detail/ComplianceScore.vue'
import RiskTable from '@/components/detail/RiskTable.vue'
import PaymentTimeline from '@/components/detail/PaymentTimeline.vue'
import RectificationLetter from '@/components/detail/RectificationLetter.vue'
import ReportAnchor from '@/components/detail/ReportAnchor.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import MemoryAwakeningPanel from '@/components/MemoryAwakeningPanel.vue'
import { useUserStore } from '@/store'

const props = defineProps<{
  taskResult: TaskResult | null
  taskId?: string
  creatorName?: string
  creatorEmpId?: string
  reviewerInfo?: {
    name?: string
    employee_id?: string
    position?: string
  }
  isFullscreen?: boolean
}>()

const emit = defineEmits<{
  (e: 'locate', evidence: VisualEvidence): void
  (e: 'toggle-fullscreen'): void
}>()

const userStore = useUserStore()

const reportRef = ref<HTMLElement | null>(null)
const archiving = ref(false)
const isArchived = ref(false)
const archiveTime = ref<string>('')
const activeTab = ref('compliance')
const rectificationRef = ref<InstanceType<typeof RectificationLetter> | null>(null)
const drawerVisible = ref(false)
const viewMode = ref<'report' | 'split'>('report')

const toggleViewMode = () => {
  viewMode.value = viewMode.value === 'report' ? 'split' : 'report'
}

const agentTraces = computed(() => props.taskResult?.comparison?.agent_traces || [])
const confidenceScore = computed(() => props.taskResult?.comparison?.confidence_score ?? 0)
const memoryContext = computed(() => props.taskResult?.memory_context)

// 算力消耗（Token 统计）
const tokenUsage = computed(() => props.taskResult?.token_usage)
const formattedTotalTokens = computed(() => {
  const total = tokenUsage.value?.total_tokens || 0
  return total.toLocaleString('zh-CN')
})

const modelName = computed(() => props.taskResult?.model_name || '—')
const formattedDuration = computed(() => {
  const sec = props.taskResult?.processing_seconds
  if (sec === undefined || sec === null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s > 0 ? `${m} 分 ${s} 秒` : `${m} 分`
})

const copyTraceDetail = (text: string) => {
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

const copyCardSuggestion = (text: string) => {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('建议条款已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

const canArchive = computed(() => props.taskId && !isArchived.value)

const handleArchive = async () => {
  if (!props.taskId) return
  archiving.value = true
  try {
    const res = await archiveTask(props.taskId)
    archiveTime.value = res.data.data.archive_time
    isArchived.value = true
    ElMessage.success('任务已数字化归档')
  } catch (_err) {
    ElMessage.error('归档失败')
  } finally {
    archiving.value = false
  }
}

const exportReport = async () => {
  if (!reportRef.value) return
  ElMessage.info('正在生成合规报告 PDF，请稍候...')
  try {
    await exportReportPdf(reportRef.value)
    ElMessage.success('合规报告导出成功')
  } catch (_err) {
    ElMessage.error('PDF 导出失败')
  }
}

const openRectification = () => {
  rectificationRef.value?.open()
}

const openAgentDrawer = () => {
  drawerVisible.value = true
}

const formatDetailKey = (key: string): string => {
  const map: Record<string, string> = {
    business_diff_count: '商务差异项',
    match_count: '已匹配条款',
    vendor_match: '供应商一致性',
    amount_match: '金额一致性',
    amount_diff: '金额差异',
    delivery_match: '交期一致性',
    legal_risk_count: '法务风险项',
    missing_items_count: '缺失条款',
    missing_clause_count: '缺失条款数',
    clause_issues: '条款问题',
    initial_risk_level: '初步风险评级',
    confidence_score: '置信度',
    risk_level: '风险等级',
    review_comments: '审查结论',
    final_risk_level: '终审风险定级',
    legal_risk_assessment: '法务风险评级',
  }
  return map[key] || key
}

const formatRiskLevel = (val: string): string => {
  const map: Record<string, string> = {
    high: '高风险',
    medium: '中风险',
    low: '低风险',
  }
  return map[String(val).toLowerCase()] || val
}

const riskLevelTagType = (val: string): string => {
  const v = String(val).toLowerCase()
  if (v === 'high') return 'danger'
  if (v === 'medium') return 'warning'
  return 'success'
}

const getDetailEntries = (detail: Record<string, any> | undefined): [string, any][] => {
  if (!detail) return []
  return Object.entries(detail).filter(([key, val]) => {
    return !Array.isArray(val) && key !== 'review_comments' && key !== 'confidence_score'
  })
}

const confidenceColor = (score: number): string => {
  if (score >= 0.8) return '#10b981'
  if (score >= 0.5) return '#f59e0b'
  return '#ef4444'
}

const handleSwitchTab = (tab: string) => {
  activeTab.value = tab
}

const hasMemoryTrigger = (comment: string): boolean => {
  return (
    comment.includes('历史画像') ||
    comment.includes('历史经验') ||
    comment.includes('历史雷区')
  )
}

const hasContractText = computed(() => {
  const text = props.taskResult?.comparison?.parsed_contract_text
  return !!text && text.trim().length > 0
})

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

/** 判断是否为双向均未提及的伪差异（如两边都写"未提及保密期限"） */
function isBidirectionalMissing(bid: string, contract: string): boolean {
  const b = bid.trim()
  const c = contract.trim()
  if (!b || !c) return false
  const bidMissing = missingKeywords.some(k => b.includes(k))
  const contractMissing = missingKeywords.some(k => c.includes(k))
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

function isCoveredByKeyRows(text: string): boolean {
  const t = text.toLowerCase()
  return (
    t.includes('供应商') || t.includes('vendor') || t.includes('签署方') ||
    t.includes('金额') || t.includes('总价') || t.includes('价款') || t.includes('价格') ||
    t.includes('交期') || t.includes('交付') || t.includes('工期') || t.includes('天数') ||
    t.includes('违约') || t.includes('赔偿')
  )
}

// ========== 关键信息迷你对照表 ==========
interface CompareRow {
  key: string
  label: string
  bidDisplay: string
  contractDisplay: string
  mismatched: boolean
  isNew: boolean
}

const keyInfoRows = computed<CompareRow[]>(() => {
  const bid = props.taskResult?.bid_info
  const contract = props.taskResult?.contract_info
  const fin = props.taskResult?.financial_info
  const rows: CompareRow[] = []

  // 1. 供应商名称
  const bidVendor = bid?.vendor_name || ''
  const contractVendor = contract?.vendor_name || ''
  rows.push({
    key: 'vendor_name',
    label: '供应商名称',
    bidDisplay: bidVendor || '—',
    contractDisplay: contractVendor || '—',
    mismatched: !!(bidVendor && contractVendor && bidVendor !== contractVendor),
    isNew: !bidVendor && !!contractVendor,
  })

  // 2. 总金额
  const bidAmt = Number(bid?.total_amount) || 0
  const contractAmt = Number(contract?.total_amount) || 0
  rows.push({
    key: 'total_amount',
    label: '总金额',
    bidDisplay: bidAmt ? `¥${bidAmt.toLocaleString()}` : '—',
    contractDisplay: contractAmt ? `¥${contractAmt.toLocaleString()}` : '—',
    mismatched: bidAmt !== contractAmt && bidAmt > 0 && contractAmt > 0,
    isNew: bidAmt === 0 && contractAmt > 0,
  })

  // 3. 交期天数
  const bidDays = Number(bid?.delivery_days) || 0
  const contractDays = Number(contract?.delivery_days) || 0
  rows.push({
    key: 'delivery_days',
    label: '交期天数',
    bidDisplay: bidDays ? `${bidDays}天` : '—',
    contractDisplay: contractDays ? `${contractDays}天` : '—',
    mismatched: bidDays !== contractDays && bidDays > 0 && contractDays > 0,
    isNew: bidDays === 0 && contractDays > 0,
  })

  // 4. 违约金矩阵（三维升维展示）
  function fmtPenaltyMatrix(info: any): string {
    const lines: string[] = []
    const delay = Number(info?.delay_daily_rate) || 0
    const cap = Number(info?.penalty_cap_rate) || 0
    const term = Number(info?.termination_penalty_rate) || 0
    if (delay) lines.push(`逾期日罚息：${(delay * 100).toFixed(3)}%`)
    if (cap) lines.push(`累计上限：${(cap * 100).toFixed(1)}%`)
    if (term) lines.push(`解约赔偿：${(term * 100).toFixed(1)}%`)
    return lines.length ? lines.join('\n') : '—'
  }
  function anyPenaltyMismatch(bidInfo: any, contractInfo: any): boolean {
    const fields = ['delay_daily_rate', 'penalty_cap_rate', 'termination_penalty_rate']
    return fields.some((f) => {
      const b = Number(bidInfo?.[f]) || 0
      const c = Number(contractInfo?.[f]) || 0
      return b > 0 && c >= 0 && Math.abs(b - c) > 0.0001
    })
  }
  rows.push({
    key: 'penalty_matrix',
    label: '违约金矩阵',
    bidDisplay: fmtPenaltyMatrix(bid),
    contractDisplay: fmtPenaltyMatrix(contract),
    mismatched: anyPenaltyMismatch(bid, contract),
    isNew: false,
  })

  // 5. 其他（Agent 差异中未被前4行覆盖的项，如服务期限、有效期、付款方式等）
  let otherBidDisplay = '—'
  let otherContractDisplay = '—'
  let otherMismatched = false
  const parts: string[] = []

  const agentDiffs = props.taskResult?.comparison?.differences || []
  const agentMissing = props.taskResult?.comparison?.missing_items || []
  const extraDiffs: string[] = []

  agentDiffs.forEach((d: any) => {
    const text = typeof d === 'string' ? d : (d.description || '')
    if (text && !isCoveredByKeyRows(text)) {
      extraDiffs.push(text)
    }
  })
  agentMissing.forEach((m: any) => {
    const text = m.description || ''
    if (text && !isCoveredByKeyRows(text)) {
      extraDiffs.push(`缺失：${text}`)
    }
  })

  if (extraDiffs.length) {
    otherMismatched = true
    // 从长描述中提取核心关键词（如"有效期、付款方式、签订日期"）
    function extractDiffTopic(text: string): string {
      let topic = text.includes('：') ? (text.split('：')[0] ?? '') : text
      topic = topic.replace(/(描述)?不一致/g, '').replace(/(条款)?缺失/g, '').trim()
      // 去掉常见前缀
      topic = topic.replace(/^合同/g, '').trim()
      if (topic.length > 14) topic = topic.slice(0, 14)
      return topic
    }
    const topics = extraDiffs.map(extractDiffTopic).filter(Boolean)
    const uniqueTopics = [...new Set(topics)]
    parts.push(`${extraDiffs.length}项条款差异（${uniqueTopics.join('、')}）`)
  }

  if (parts.length) {
    otherContractDisplay = parts.join('；')
  }

  rows.push({
    key: 'other',
    label: '其他',
    bidDisplay: otherBidDisplay,
    contractDisplay: otherContractDisplay,
    mismatched: otherMismatched,
    isNew: false,
  })

  return rows
})

const sortedCompareRows = computed(() => {
  return [...keyInfoRows.value].sort((a, b) => {
    // "其他" 始终固定在最底部
    if (a.key === 'other') return 1
    if (b.key === 'other') return -1
    if (a.mismatched !== b.mismatched) return a.mismatched ? -1 : 1
    if (a.isNew !== b.isNew) return a.isNew ? -1 : 1
    return 0
  })
})

const mismatchedKeyInfoCount = computed(() => keyInfoRows.value.filter(r => r.mismatched).length)

const getStatusTag = (row: CompareRow): { type: string; effect: string; text: string } => {
  if (row.mismatched) return { type: 'danger', effect: 'dark', text: '不一致' }
  if (row.isNew) return { type: 'primary', effect: 'dark', text: '新增' }
  return { type: 'info', effect: 'plain', text: '一致' }
}

const getRiskHint = (key: string): string => {
  const hints: Record<string, string> = {
    vendor_name: '供应商主体发生变更，存在法律主体风险，需重新核实资质与授权链。',
    total_amount: '合同金额与中标结果不符，可能涉及预算超支或价格欺诈。',
    delivery_days: '交期严重偏离中标承诺，可能影响项目整体进度与投产计划。',
    penalty_matrix: '违约金矩阵发生变更（如日罚息、累计上限或解约赔偿比例变化），需逐维核对卖方违约成本。',
    other: '采购明细存在不一致、缺失或新增条目，请逐项核对规格、数量与单价。',
  }
  return hints[key] || '请业务及法务部门专项复核。'
}

/** 从条款差异描述中拆分出采购结果和合同两边的值 */
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

/** 去掉条款描述中常见的冗余前缀，保留核心值 */
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

// ========== 全局比对概览面板 ==========

// ========== 全局比对概览面板 ==========
const summaryData = computed(() => {
  const bid = props.taskResult?.bid_info
  const contract = props.taskResult?.contract_info
  const diffs = props.taskResult?.comparison?.differences || []
  const missing = props.taskResult?.comparison?.missing_items || []
  return {
    projectName: bid?.vendor_name ? `${bid.vendor_name}采购项目` : '未命名项目',
    purchaseType: '—',
    vendor: bid?.vendor_name || contract?.vendor_name || '—',
    bidAmount: Number(bid?.total_amount) || 0,
    contractAmount: Number(contract?.total_amount) || 0,
    diffCount: diffCount.value + missingCount.value,
  }
})

function detectRiskLevel(text: string): 'high' | 'medium' | 'low' {
  const t = text.toLowerCase()
  if (t.includes('金额') || t.includes('总价') || t.includes('供应商') || t.includes('缺失') || t.includes('违约')) return 'high'
  if (t.includes('有效期') || t.includes('付款') || t.includes('交期') || t.includes('交付') || t.includes('工期')) return 'medium'
  return 'low'
}

/** 将后端可能返回的英文/路径格式 type 翻译为中文 */
function translateTypeLabel(type: string): string {
  if (!type) return '其他'
  if (/^[一-龥【】]/.test(type)) return type

  const exactMap: Record<string, string> = {
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
  }
  if (exactMap[type]) return exactMap[type]

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

/** 从 original_text / contract_text 中提取条款位置 */
function extractLocation(originalText?: string, contractText?: string): string {
  const locs: string[] = []

  if (originalText) {
    let m = originalText.match(/【采购结果(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?[^】]*)】/)
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
          m = originalText.match(/【([^】]{2,20})】/)
          if (m) locs.push(`采购结果${m[1]}`)
        }
      }
    }
  }

  if (contractText) {
    let m = contractText.match(/【合同(第[一二三四五六七八九十百千零\d]+条(?:第[一二三四五六七八九十百千零\d]+款)?[^】]*)】/)
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
          m = contractText.match(/【([^】]{2,20})】/)
          if (m) locs.push(`合同${m[1]}`)
        }
      }
    }
  }

  return locs.length ? `📍 ${locs.join(' / ')}` : ''
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

  // 有正面词且无负面词 → 有利项
  if (hasPositive && !hasNegative) return true
  // riskComment 明确是正面描述
  if (rc.includes('增强了') || rc.includes('已明确') || rc.includes('完善了') || rc.includes('更有利')) return true

  return false
}

interface DiffCard {
  id: string
  title: string
  riskLevel: 'high' | 'medium' | 'low' | 'positive'
  riskLabel: string
  bidText: string
  contractText: string
  description: string
  riskComment?: string
  suggestion?: string
  isMissing: boolean
  location?: string
  visualEvidence?: VisualEvidence | null
}

const diffCardsMergedCount = ref(0)

const diffCards = computed((): DiffCard[] => {
  const cards: DiffCard[] = []
  let merged = 0

  // 1. 缺失条款（Agent missing_items）—— 优先展示
  const agentMissing = props.taskResult?.comparison?.missing_items || []
  agentMissing.forEach((m: any, idx: number) => {
    const text = m.description || ''
    if (!text) return
    // 抹杀双向均未提及的伪缺失
    if (isBidirectionalEmpty(m.original_text || '', m.contract_text || '')) {
      merged++
      return
    }
    // 抹杀 false positive：采购结果中本来就没有，或合同侧实际存在的"缺失"
    if (isFalsePositiveMissing(m)) {
      merged++
      return
    }
    const rawTitle = text.includes('：') ? text.split('：')[0] : '缺失条款'
    const cleanedTitle = rawTitle.replace(/(条款)?缺失/g, '').trim() || '缺失条款'
    const title = translateTypeLabel((typeof m === 'object' && (m as any).type) ? (m as any).type : cleanedTitle)

    cards.push({
      id: `missing-${idx}`,
      title,
      riskLevel: 'high',
      riskLabel: '高风险',
      bidText: m.original_text || '（采购结果中有）',
      contractText: m.contract_text || '（合同中未找到）',
      description: text,
      riskComment: m.risk_comment || '该条款在采购结果中有约定，但合同中完全缺失，建议立即补充。',
      suggestion: m.suggested_amendment || '',
      isMissing: true,
      location: extractLocation(m.original_text, m.contract_text),
      visualEvidence: m.visual_evidence || null,
    })
  })

  // 2. 条款差异（完整展示，不做 title 去重）
  const agentDiffs = props.taskResult?.comparison?.differences || []
  agentDiffs.forEach((d: any, idx: number) => {
    const text = typeof d === 'string' ? d : (d.description || '')
    if (!text || (text.includes('一致') && text.includes('未发现'))) return
    const rawTitle = (typeof d === 'object' && d.type) || (text.includes('：') ? text.split('：')[0] : '条款差异')
    const cleanedTitle = String(rawTitle).replace(/(描述)?不一致/g, '').trim() || '条款差异'
    const title = translateTypeLabel(cleanedTitle)

    const bc = splitClauseDescription(text)

    const bidText = typeof d === 'object' && d.original_text ? d.original_text : bc.bid
    const contractText = typeof d === 'object' && d.contract_text ? d.contract_text : bc.contract

    // 双向未提及过滤：如果两侧原文都为空或只有占位符，说明是双向未提及的伪差异，跳过
    const hasBidContent = bidText && bidText !== '—' && bidText.trim().length > 3
    const hasContractContent = contractText && contractText !== '—' && contractText.trim().length > 3
    if (!hasBidContent && !hasContractContent) {
      merged++
      return
    }

    // 双向均未提及过滤：如果两边都是"未提及""未约定"等否定描述，跳过
    if (isBidirectionalEmpty(bidText, contractText) || isBidirectionalMissing(bidText, contractText)) {
      merged++
      return
    }

    // 语义归一化：去除数量单位后若实质一致，则跳过
    if (isSubstantiallySame(bidText, contractText)) {
      merged++
      return
    }

    // 付款类差异兜底：当 Agent 只返回了空泛标题、没有具体内容时，用 financial_info 合成卡片
    const isPaymentRelated = /付款|支付|预付款|验收款|质保金|分期|节点/.test(cleanedTitle)
    const hasNoDetail = !text.includes('：') || (bc.bid === bc.contract && text.length < 30)
    if (isPaymentRelated && hasNoDetail) {
      const finNodes = props.taskResult?.financial_info?.payment_nodes || []
      if (finNodes.length) {
        const contractPaymentText = finNodes
          .map(
            (n: any) =>
              `${n.node_name || '付款节点'}${n.percentage !== undefined ? `（${(n.percentage * 100).toFixed(0)}%）` : ''}${n.condition ? `，条件：${n.condition}` : ''}`
          )
          .join('；')
        const level = isPositiveDiff(d) ? 'positive' : detectRiskLevel(text)
        cards.push({
          id: `diff-${idx}`,
          title,
          riskLevel: level,
          riskLabel:
            level === 'high'
              ? '高风险'
              : level === 'medium'
                ? '中风险'
                : level === 'positive'
                  ? '有利项'
                  : '低风险',
          bidText: '（请核对采购结果文件中的付款节点与比例）',
          contractText: contractPaymentText,
          description: `合同付款安排：${contractPaymentText}`,
          riskComment: '付款节点及比例存在差异，建议逐条核对采购结果与合同的付款比例、条件及节点设置。',
          suggestion: typeof d === 'object' ? d.suggested_amendment || '请按采购结果约定的付款节点与比例调整合同条款。' : '请按采购结果约定的付款节点与比例调整合同条款。',
          isMissing: false,
          location: extractLocation(
            typeof d === 'object' ? d.original_text : undefined,
            typeof d === 'object' ? d.contract_text : undefined
          ),
        })
        return
      }
    }

    const rawDesc = text.includes('：') ? text.split('：').slice(1).join('：') : text
    const level = isPositiveDiff(d) ? 'positive' : detectRiskLevel(text)
    cards.push({
      id: `diff-${idx}`,
      title,
      riskLevel: level,
      riskLabel: level === 'high' ? '高风险' : level === 'medium' ? '中风险' : level === 'positive' ? '有利项' : '低风险',
      bidText,
      contractText,
      description: cleanClausePrefix(rawDesc),
      riskComment: typeof d === 'object' ? (d.risk_comment || '') : '',
      suggestion: typeof d === 'object' ? d.suggested_amendment : '',
      isMissing: false,
      location: extractLocation(
        typeof d === 'object' ? d.original_text : undefined,
        typeof d === 'object' ? d.contract_text : undefined
      ),
      visualEvidence: typeof d === 'object' ? (d.visual_evidence || null) : null,
    })
  })

  // 采购明细差异已后端扁平化到 differences / missing_items，此处不再单独处理

  diffCardsMergedCount.value = merged
  // 排序：不利项（high/medium/low/missing）在前，有利项（positive）在后
  return cards.sort((a, b) => {
    const aFav = a.riskLevel === 'positive'
    const bFav = b.riskLevel === 'positive'
    if (aFav === bFav) return 0
    return aFav ? 1 : -1
  })
})

/** 提取文本中的第一个数值（支持千分位） */
function extractFirstNumber(text: string): number | null {
  const m = text.match(/(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)/)
  if (!m) return null
  return parseFloat(m[0].replace(/,/g, ''))
}

/** 为差异卡片生成 AI 审查批注文案，优先展示量化变化 */
function getDiffAlertText(card: DiffCard): string {
  if (card.riskComment && card.riskComment.trim()) {
    return card.riskComment
  }
  // 付款方式/规则类条款不提取数值计算，直接展示差异描述
  const title = card.title.toLowerCase()
  if (title.includes('付款方式') || title.includes('付款规则') || title.includes('付款节点') || title.includes('分期')) {
    return card.description || '付款条款存在差异，建议逐条核对付款节点与比例。'
  }
  // 条款差异：尝试从两侧文本中提取数值并计算变化
  const bidNum = extractFirstNumber(card.bidText)
  const contractNum = extractFirstNumber(card.contractText)
  if (bidNum !== null && contractNum !== null && bidNum !== 0 && bidNum !== contractNum) {
    const diff = contractNum - bidNum
    const absDiff = Math.abs(diff)
    const pct = ((diff / bidNum) * 100).toFixed(1)
    const direction = diff > 0 ? '高' : '低'
    if (title.includes('金额') || title.includes('价格') || title.includes('总价')) {
      return `合同金额比采购结果${direction} ${absDiff.toLocaleString()} 元（${Math.abs(parseFloat(pct))}%）`
    }
    if (title.includes('期') || title.includes('天') || title.includes('日') || title.includes('工期')) {
      return `合同交期比采购结果${direction} ${absDiff} 天`
    }
    if (title.includes('比例') || title.includes('率')) {
      return `合同约定值比采购结果${direction} ${Math.abs(parseFloat(pct))} 个百分点`
    }
    return `合同约定值比采购结果${direction} ${Math.abs(parseFloat(pct))}%`
  }
  return card.description
}

const diffCount = computed(() => {
  const diffs = props.taskResult?.comparison?.differences || []
  return diffs.filter((d: any) => {
    const text = typeof d === 'string' ? d : (d.description || '')
    if (!text || (text.includes('一致') && text.includes('未发现'))) return false
    if (typeof d === 'string') return false
    const bc = splitClauseDescription(text)
    const bidText = d.original_text || bc.bid
    const contractText = d.contract_text || bc.contract
    const hasBidContent = bidText && bidText !== '—' && bidText.trim().length > 3
    const hasContractContent = contractText && contractText !== '—' && contractText.trim().length > 3
    if (!hasBidContent && !hasContractContent) return false
    if (isBidirectionalEmpty(bidText, contractText) || isBidirectionalMissing(bidText, contractText)) return false
    if (isSubstantiallySame(bidText, contractText)) return false
    return true
  }).length
})

const missingCount = computed(() => {
  const missing = props.taskResult?.comparison?.missing_items || []
  return missing.filter((m: any) => {
    const text = m.description || ''
    if (!text) return false
    if (isBidirectionalEmpty(m.original_text || '', m.contract_text || '')) return false
    if (isFalsePositiveMissing(m)) return false
    return true
  }).length
})

const escapeHtml = (text: string): string => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

interface Annotation {
  keywords: string[]
  desc: string
  riskComment: string
  suggestion: string
  type: 'diff' | 'missing'
}

const annotatedContractText = computed(() => {
  const sourceText = props.taskResult?.comparison?.parsed_contract_text || ''
  if (!sourceText) {
    return '<div style="color: #9ca3af; padding: 20px;">未能获取合同原文。</div>'
  }

  // ---------- 1. 收集所有批注 ----------
  const allAnnotations: Annotation[] = []

  const diffs = props.taskResult?.comparison?.differences || []
  diffs.forEach((item: any) => {
    if (typeof item === 'string') {
      allAnnotations.push({ keywords: [item], desc: item, riskComment: '', suggestion: '', type: 'diff' })
    } else {
      const kw = [item.description, item.original_text, item.risk_comment]
        .filter(Boolean)
        .map((s: string) => s.trim())
        .filter((s: string) => s.length >= 4)
      allAnnotations.push({
        keywords: kw,
        desc: item.description || '',
        riskComment: item.risk_comment || '',
        suggestion: item.suggested_amendment || '',
        type: 'diff',
      })
    }
  })

  const missing = props.taskResult?.comparison?.missing_items || []
  missing.forEach((item: any) => {
    const kw = [item.description, item.original_text, item.risk_comment]
      .filter(Boolean)
      .map((s: string) => s.trim())
      .filter((s: string) => s.length >= 4)
    allAnnotations.push({
      keywords: kw,
      desc: item.description || '',
      riskComment: item.risk_comment || '',
      suggestion: item.suggested_amendment || '',
      type: 'missing',
    })
  })

  if (allAnnotations.length === 0) {
    // 无批注时直接返回原文
    return `<div style="white-space: pre-wrap; line-height: 1.85; color: #334155;">${escapeHtml(sourceText)}</div>`
  }

  // ---------- 2. 按段落分割原文 ----------
  // 先按双换行分割，如果段落太大再按单换行细分
  const rawBlocks = sourceText.split(/\n\n/)
  const paragraphs: string[] = []
  rawBlocks.forEach(block => {
    const trimmed = block.trim()
    if (!trimmed) return
    // 如果一个块超过 300 字且包含单换行，再细分
    if (trimmed.length > 300 && trimmed.includes('\n')) {
      trimmed.split('\n').forEach(line => {
        const t = line.trim()
        if (t) paragraphs.push(t)
      })
    } else {
      paragraphs.push(trimmed)
    }
  })

  // ---------- 3. 遍历段落，插入批注 ----------
  const htmlParts: string[] = []
  const usedAnnotations = new Set<number>()

  paragraphs.forEach(para => {
    // 输出原文段落
    htmlParts.push(`<div style="margin-bottom: 10px; line-height: 1.85; color: #334155;">${escapeHtml(para)}</div>`)

    // 查找匹配该段落的批注（按关键词长度降序，优先长词）
    const matchedIndices: number[] = []
    allAnnotations.forEach((ann, idx) => {
      if (usedAnnotations.has(idx)) return
      const sortedKw = [...ann.keywords].sort((a, b) => b.length - a.length)
      const hit = sortedKw.some(kw => para.includes(kw))
      if (hit) matchedIndices.push(idx)
    })

    matchedIndices.forEach(idx => {
      usedAnnotations.add(idx)
      const ann = allAnnotations[idx]!
      const isDiff = ann.type === 'diff'
      const borderColor = isDiff ? '#ef4444' : '#f59e0b'
      const bgColor = isDiff ? '#fef2f2' : '#fffbeb'
      const titleColor = isDiff ? '#b91c1c' : '#92400e'
      const icon = isDiff ? '🛑' : '⚠️'
      const title = isDiff ? '【法务 Agent 批注 — 风险差异】' : '【法务 Agent 批注 — 缺失条款】'

      let body = escapeHtml(ann.desc)
      if (ann.riskComment) {
        body += `\n\n<span style="color: #7f1d1d; font-weight: 600;">风险提示：</span>${escapeHtml(ann.riskComment)}`
      }
      if (ann.suggestion) {
        body += `\n\n<span style="color: #15803d; font-weight: 600;">✨ 建议修改为：</span>${escapeHtml(ann.suggestion)}`
      }

      htmlParts.push(
        `<div style="background: ${bgColor}; border-left: 4px solid ${borderColor}; padding: 14px 18px; margin: 6px 0 20px 0; border-radius: 0 10px 10px 0; color: #374151; font-size: 14px; line-height: 1.7;">
          <div style="font-weight: 700; margin-bottom: 8px; color: ${titleColor}; font-size: 15px;">${icon} ${title}</div>
          <div style="white-space: pre-wrap;">${body}</div>
        </div>`
      )
    })
  })

  // ---------- 4. 未匹配到的批注统一放在文末 ----------
  const remaining = allAnnotations.filter((_, idx) => !usedAnnotations.has(idx))
  if (remaining.length > 0) {
    htmlParts.push(`<div style="margin-top: 24px; padding-top: 16px; border-top: 2px dashed #e2e8f0;">
      <div style="font-weight: 700; color: #475569; margin-bottom: 12px; font-size: 15px;">📌 以下批注未能自动定位到原文位置，请全文参考：</div>
    </div>`)
    remaining.forEach(ann => {
      const isDiff = ann.type === 'diff'
      const borderColor = isDiff ? '#ef4444' : '#f59e0b'
      const bgColor = isDiff ? '#fef2f2' : '#fffbeb'
      const titleColor = isDiff ? '#b91c1c' : '#92400e'
      const icon = isDiff ? '🛑' : '⚠️'
      const title = isDiff ? '【风险差异】' : '【缺失条款】'

      let body = escapeHtml(ann.desc)
      if (ann.riskComment) body += `\n\n风险提示：${escapeHtml(ann.riskComment)}`
      if (ann.suggestion) body += `\n\n✨ 建议修改为：${escapeHtml(ann.suggestion)}`

      htmlParts.push(
        `<div style="background: ${bgColor}; border-left: 4px solid ${borderColor}; padding: 12px 16px; margin: 8px 0; border-radius: 0 8px 8px 0; color: #374151; font-size: 14px; line-height: 1.7;">
          <div style="font-weight: 700; margin-bottom: 6px; color: ${titleColor};">${icon} ${title}</div>
          <div style="white-space: pre-wrap;">${body}</div>
        </div>`
      )
    })
  }

  return htmlParts.join('')
})
</script>

<template>
  <el-card shadow="hover" class="result-card">
    <template #header>
      <div class="card-header">
        <div class="header-left">
          <el-icon><DocumentChecked /></el-icon>
          <span>比对结果</span>
        </div>
        <div class="header-right">
          <el-button
            v-if="!isFullscreen"
            type="primary"
            text
            size="small"
            @click="emit('toggle-fullscreen')"
          >
            <el-icon><FullScreen /></el-icon>
            <span>全屏</span>
          </el-button>
          <el-button
            v-else
            type="info"
            text
            size="small"
            @click="emit('toggle-fullscreen')"
          >
            <el-icon><Close /></el-icon>
            <span>返回</span>
          </el-button>
        </div>
      </div>
    </template>

    <!-- 占位状态 -->
    <div v-if="!taskResult" class="result-placeholder">
      <el-empty description='请先上传文件并点击"开始智能比对"' />
    </div>

    <div v-else>
      <!-- 顶部概览状态栏 -->
      <div class="status-bar">
        <div class="status-item">
          <span class="status-label">风险定级</span>
          <el-tag :type="riskLevelTagType(taskResult.comparison.risk_level)" size="small" effect="dark">
            {{ formatRiskLevel(taskResult.comparison.risk_level) }}
          </el-tag>
        </div>
        <div class="status-item">
          <span class="status-label">全局置信度</span>
          <span class="status-value" :style="{ color: confidenceColor(confidenceScore) }">
            {{ Math.round(confidenceScore * 100) }}%
          </span>
        </div>
        <div class="status-item">
          <span class="status-label">差异项</span>
          <span class="status-value status-value--danger">{{ diffCount }} 项</span>
        </div>
        <div class="status-item">
          <span class="status-label">缺失项</span>
          <span class="status-value status-value--warning">{{ missingCount }} 项</span>
        </div>
        <div class="status-item">
          <span class="status-label">生成时间</span>
          <span class="status-value status-value--muted">{{ taskResult?.created_at || '—' }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">算力消耗</span>
          <span class="status-value">
            {{ formattedTotalTokens }} Tokens
            <span v-if="tokenUsage" class="token-breakdown">
              输入 {{ tokenUsage.prompt_tokens.toLocaleString('zh-CN') }} / 输出 {{ tokenUsage.completion_tokens.toLocaleString('zh-CN') }}
            </span>
          </span>
        </div>
        <div class="status-item">
          <span class="status-label">底层模型</span>
          <span class="status-value status-value--muted">{{ modelName }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">执行耗时</span>
          <span class="status-value status-value--muted">{{ formattedDuration }}</span>
        </div>
      </div>

      <!-- 左右双屏 -->
      <el-row :gutter="24" class="split-view-row">
        <!-- 左侧：合同原文（仅双屏模式显示） -->
        <el-col v-if="viewMode === 'split'" :span="12">
          <el-card shadow="hover" class="contract-text-card">
            <template #header>
              <div class="contract-text-header">
                <div class="header-left">
                  <el-icon><Document /></el-icon>
                  <span>合同原文</span>
                </div>
                <div class="header-right">
                  <el-tag v-if="diffCount > 0" type="danger" size="small" effect="light" class="header-tag">
                    {{ diffCount }} 处风险差异
                  </el-tag>
                  <el-tag v-if="missingCount > 0" type="warning" size="small" effect="light" class="header-tag">
                    {{ missingCount }} 处缺失条款
                  </el-tag>
                </div>
              </div>
            </template>
            <div class="contract-text-body">
              <!-- 关键信息迷你对照表 -->
              <div v-if="keyInfoRows.length" class="key-info-compare">
                <div class="kic-header">
                  <div class="kic-title">
                    <el-icon><DocumentCopy /></el-icon>
                    <span>中标 vs 合同 关键信息对照</span>
                  </div>
                  <el-tag
                    v-if="mismatchedKeyInfoCount > 0"
                    type="danger"
                    size="small"
                    effect="dark"
                  >
                    {{ mismatchedKeyInfoCount }} 项不一致
                  </el-tag>
                  <el-tag v-else type="success" size="small">全部一致</el-tag>
                </div>
                <div class="kic-table">
                  <div class="kic-row kic-row--header">
                    <div class="kic-cell">维度</div>
                    <div class="kic-cell">采购结果</div>
                    <div class="kic-cell">正式合同</div>
                    <div class="kic-cell">状态</div>
                  </div>
                  <div
                    v-for="row in sortedCompareRows"
                    :key="row.key"
                    :class="['kic-row', row.mismatched && 'kic-row--mismatch', row.isNew && 'kic-row--new']"
                  >
                    <div class="kic-cell kic-cell--label">{{ row.label }}</div>
                    <div class="kic-cell kic-cell--bid">{{ row.bidDisplay }}</div>
                    <div
                      class="kic-cell kic-cell--contract"
                      :class="{ 'kic-cell--risk': row.mismatched, 'kic-cell--new': row.isNew }"
                    >
                      {{ row.contractDisplay }}
                    </div>
                    <div class="kic-cell kic-cell--status">
                      <el-tag
                        :type="getStatusTag(row).type"
                        size="small"
                        :effect="getStatusTag(row).effect"
                      >
                        {{ getStatusTag(row).text }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </div>

              <div
                v-if="hasContractText"
                v-html="annotatedContractText"
                class="contract-text-content"
              ></div>
              <el-empty v-else description="暂无合同原文，请确保后端已开启原文解析" />
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：AI 报告 -->
        <el-col :span="viewMode === 'split' ? 12 : 24">
          <div class="right-panel">
            <div class="panel-toolbar">
              <el-button
                v-if="!userStore.isGuest"
                type="primary"
                plain
                class="view-mode-toggle"
                @click="toggleViewMode"
              >
                {{ viewMode === 'report' ? '🔍 显示合同原文' : '📄 返回标准报告' }}
              </el-button>
              <el-button
                v-if="!userStore.isGuest"
                type="primary"
                plain
                @click="openAgentDrawer"
              >
                <el-icon><Connection /></el-icon>
                智能体风险透视
              </el-button>
            </div>

            <!-- 全息历史数据库唤醒：置于 Tabs 之外，始终置顶显示 -->
            <MemoryAwakeningPanel
              v-if="memoryContext"
              :supplier-context="memoryContext.supplier_context"
              :rag-context="memoryContext.rag_context"
              class="memory-awakening-top"
            />

            <el-tabs v-model="activeTab" type="border-card" class="report-tabs">
              <!-- 页签 1：合规审查报告 -->
              <el-tab-pane label="合规审查报告" name="compliance">
                <div ref="reportRef" class="report-body">
                  <ReportAnchor
                    v-if="taskResult"
                    class="report-anchor"
                    :active-tab="activeTab"
                    @switch-tab="handleSwitchTab"
                  />
                  <div class="report-title">智能合规审查报告</div>
                  <div class="report-subtitle">Intelligent Compliance Review Report</div>
                  <div class="report-meta">
                    生成时间：{{ taskResult?.created_at || '—' }}
                  </div>

                  <ComplianceScore
                    :task-result="taskResult"
                    :creator-name="creatorName"
                    :creator-emp-id="creatorEmpId"
                    :process-mode="taskResult.process_mode"
                    :is-archived="isArchived"
                    :archive-time="archiveTime"
                    :reviewer-info="reviewerInfo"
                    :created-at="taskResult?.created_at"
                  />

                  <RiskTable
                    :differences="taskResult.comparison?.differences"
                    :missing-items="taskResult.comparison?.missing_items"
                    :matches="taskResult.comparison?.matches"
                    :bid-info="taskResult.bid_info"
                    :contract-info="taskResult.contract_info"
                    :physical-alerts="taskResult.comparison?.physical_alerts"
                  />

                  <!-- 全局比对概览面板 -->
                  <div class="report-section summary-panel-section">
                    <div class="section-title">
                      <el-icon><DocumentCopy /></el-icon>
                      全局比对概览
                    </div>
                    <div class="summary-panel">
                      <el-row :gutter="24">
                        <el-col :xs="24" :sm="12">
                          <div class="summary-item">
                            <div class="summary-label">项目名称</div>
                            <div class="summary-value">{{ summaryData.projectName }}</div>
                          </div>
                        </el-col>
                        <el-col :xs="24" :sm="12">
                          <div class="summary-item">
                            <div class="summary-label">采购类型</div>
                            <div class="summary-value">{{ summaryData.purchaseType }}</div>
                          </div>
                        </el-col>
                      </el-row>
                      <el-row :gutter="24" class="summary-row-second">
                        <el-col :xs="24" :sm="8">
                          <div class="summary-item">
                            <div class="summary-label">供应商</div>
                            <div class="summary-value">{{ summaryData.vendor }}</div>
                          </div>
                        </el-col>
                        <el-col :xs="24" :sm="10">
                          <div class="summary-item summary-item--amount">
                            <div class="summary-label">金额对比</div>
                            <div class="summary-amount-wrap">
                              <span class="summary-amount-bid">¥{{ summaryData.bidAmount.toLocaleString() }}</span>
                              <el-icon class="amount-vs-icon"><ArrowRight /></el-icon>
                              <span class="summary-amount-contract">¥{{ summaryData.contractAmount.toLocaleString() }}</span>
                            </div>
                          </div>
                        </el-col>
                        <el-col :xs="24" :sm="6">
                          <div class="summary-item">
                            <div class="summary-label">差异项</div>
                            <el-tag type="danger" size="small" effect="dark">{{ summaryData.diffCount }} 处</el-tag>
                          </div>
                        </el-col>
                      </el-row>
                    </div>
                  </div>

                  <!-- 差异卡片流 -->
                  <div v-if="diffCards.length > 0" class="report-section diff-card-stream-section">
                    <div class="section-title">
                      <el-icon><Warning /></el-icon>
                      差异卡片流
                      <el-tag type="danger" size="small" class="risk-count-tag">{{ diffCards.length }} 项</el-tag>
                      <el-tag v-if="diffCardsMergedCount > 0" type="info" size="small" effect="plain" class="risk-count-tag">
                        已智能合并 {{ diffCardsMergedCount }} 项实质一致
                      </el-tag>
                    </div>
                    <el-space direction="vertical" fill style="width: 100%">
                      <el-card
                        v-for="card in diffCards"
                        :key="card.id"
                        shadow="hover"
                        class="diff-card"
                        :class="{ 'diff-card--missing': card.isMissing, 'diff-card--positive': card.riskLevel === 'positive' }"
                      >
                        <template #header>
                          <div class="diff-card-header">
                            <div class="diff-card-title">{{ card.title }}</div>
                            <div class="diff-card-actions">
                              <el-tag
                                :type="card.riskLevel === 'high' ? 'danger' : card.riskLevel === 'medium' ? 'warning' : card.riskLevel === 'positive' ? 'success' : 'info'"
                                effect="light"
                                size="small"
                              >
                                {{ card.riskLabel }}
                              </el-tag>
                              <el-button
                                v-if="card.suggestion"
                                type="primary"
                                link
                                size="small"
                                :icon="DocumentCopy"
                                @click="copyCardSuggestion(card.suggestion)"
                              >
                                复制建议
                              </el-button>
                              <el-button
                                v-if="card.visualEvidence"
                                type="warning"
                                link
                                size="small"
                                :icon="Location"
                                @click="emit('locate', card.visualEvidence)"
                              >
                                定位原文
                              </el-button>
                              <el-tooltip
                                v-else-if="card.contractText && card.contractText !== '（合同中未找到）'"
                                content="该文档为纯图片扫描件，暂不支持像素级定位"
                                placement="top"
                              >
                                <el-button
                                  type="info"
                                  link
                                  size="small"
                                  disabled
                                >
                                  定位原文
                                </el-button>
                              </el-tooltip>
                            </div>
                          </div>
                          <div v-if="card.location" class="diff-card-location">
                            {{ card.location }}
                          </div>
                        </template>

                        <div class="diff-card-body">
                          <el-row :gutter="20">
                            <el-col :span="12">
                              <div class="diff-source-block">
                                <div class="diff-source-label">📄 采购结果约定</div>
                                <div class="diff-source-text diff-source-text--bid">{{ card.bidText }}</div>
                              </div>
                            </el-col>
                            <el-col :span="12">
                              <div class="diff-source-block">
                                <div class="diff-source-label">📝 合同约定</div>
                                <div class="diff-source-text diff-source-text--contract">{{ card.contractText }}</div>
                              </div>
                            </el-col>
                          </el-row>
                        </div>

                        <div class="diff-card-footer">
                          <div class="diff-alert">
                            <el-icon class="diff-alert-icon"><Warning /></el-icon>
                            <div class="diff-alert-content">
                              <div class="diff-alert-title">✨ AI 审查批注</div>
                              <div class="diff-alert-text">{{ getDiffAlertText(card) }}</div>
                            </div>
                          </div>
                        </div>
                      </el-card>
                    </el-space>
                  </div>

                  <!-- AI 智能助手 -->
                  <AIAssistant v-if="taskId" :task-id="taskId" />

                  <!-- 底部悬浮操作栏 -->
                  <div v-if="taskId" class="report-sticky-footer">
                    <div class="sticky-footer-inner">
                      <el-button
                        v-if="canArchive"
                        type="warning"
                        size="large"
                        :icon="CollectionTag"
                        :loading="archiving"
                        @click="handleArchive"
                      >
                        确认归档
                      </el-button>
                      <el-button
                        v-if="taskResult"
                        type="primary"
                        size="large"
                        class="mobile-hide-btn"
                        @click="exportReport"
                      >
                        <el-icon><Download /></el-icon>
                        导出合规报告
                      </el-button>
                      <el-button
                        type="danger"
                        size="large"
                        class="mobile-hide-btn"
                        @click="openRectification"
                      >
                        <el-icon><Message /></el-icon>
                        AI 生成官方整改告知函
                      </el-button>
                    </div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- 页签 2：财务履约视图 -->
              <el-tab-pane label="财务履约视图" name="financial">
                <PaymentTimeline
                  :financial-info="taskResult.financial_info"
                  :contract-total-amount="taskResult.contract_info?.total_amount"
                  :bid-info="taskResult.bid_info"
                  :contract-info="taskResult.contract_info"
                />
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-col>
      </el-row>
    </div>
  </el-card>

  <!-- 多智能体协作推演轨迹抽屉 -->
  <el-drawer
    v-model="drawerVisible"
    title="多智能体协作推演轨迹"
    size="80%"
    :style="{ maxWidth: '600px' }"
    :with-header="true"
    class="agent-drawer"
  >
    <div class="drawer-body">
      <el-timeline v-if="agentTraces.length">
        <el-timeline-item
          v-for="(trace, idx) in agentTraces"
          :key="idx"
          :type="trace.status === 'success' ? 'success' : 'warning'"
          :color="trace.status === 'success' ? '#10b981' : '#f59e0b'"
          :icon="CircleCheck"
          :timestamp="trace.agent"
          placement="top"
        >
          <div class="timeline-card">
            <div class="timeline-header">
              <div class="timeline-header-main">
                <span class="timeline-title">{{ trace.action }}</span>
                <el-tag
                  :type="trace.status === 'success' ? 'success' : 'warning'"
                  size="small"
                  effect="light"
                >
                  {{ trace.status === 'success' ? '已完成' : trace.status }}
                </el-tag>
              </div>
              <!-- 风控总管置信度仪表盘 -->
              <div
                v-if="trace.agent && trace.agent.includes('风控') && trace.detail && typeof trace.detail.confidence_score === 'number'"
                class="confidence-dashboard"
              >
                <el-progress
                  type="dashboard"
                  :percentage="Math.round(trace.detail.confidence_score * 100)"
                  :width="70"
                  :stroke-width="5"
                  :color="confidenceColor(trace.detail.confidence_score)"
                />
                <div class="confidence-label">全局置信度</div>
              </div>
            </div>

            <!-- 阶段描述 -->
            <div v-if="trace.description" class="timeline-description">
              {{ trace.description }}
            </div>

            <!-- Token 消耗 -->
            <div v-if="trace.detail && trace.detail.tokens" class="timeline-tokens">
              <el-tag type="info" size="small" effect="plain">
                <el-icon><Cpu /></el-icon>
                {{ trace.detail.tokens.toLocaleString('zh-CN') }} Tokens
              </el-tag>
            </div>

            <!-- Detail 人言化映射 -->
            <div v-if="trace.detail" class="timeline-detail">
              <el-descriptions
                size="small"
                :column="2"
                border
                class="agent-descriptions"
              >
                <el-descriptions-item
                  v-for="([key, val]) in getDetailEntries(trace.detail)"
                  :key="key"
                  :label="formatDetailKey(key)"
                >
                  <el-tag
                    v-if="key === 'business_diff_count'"
                    type="danger"
                    size="small"
                  >
                    {{ val }} 项
                  </el-tag>
                  <el-tag
                    v-else-if="key === 'match_count'"
                    type="success"
                    size="small"
                  >
                    {{ val }} 项
                  </el-tag>
                  <el-tag
                    v-else-if="key === 'missing_items_count'"
                    type="warning"
                    size="small"
                  >
                    {{ val }} 项
                  </el-tag>
                  <el-tag
                    v-else-if="key === 'initial_risk_level' || key === 'risk_level'"
                    :type="riskLevelTagType(val)"
                    size="small"
                  >
                    {{ formatRiskLevel(val) }}
                  </el-tag>
                  <el-tag
                    v-else-if="key === 'legal_risk_assessment' || key === 'final_risk_level'"
                    :type="riskLevelTagType(val)"
                    size="small"
                    effect="dark"
                  >
                    {{ formatRiskLevel(val) }}
                  </el-tag>
                  <span v-else class="kv-plain">{{ val }}</span>
                </el-descriptions-item>
              </el-descriptions>

              <!-- 审查结论列表 -->
              <div
                v-if="trace.detail.review_comments && Array.isArray(trace.detail.review_comments) && trace.detail.review_comments.length"
                class="detail-comments"
              >
                <div class="comments-label">审查结论</div>
                <ul class="comments-list">
                  <li
                    v-for="(comment, cidx) in trace.detail.review_comments"
                    :key="cidx"
                  >
                    <el-icon class="comment-icon"><CircleCheck /></el-icon>
                    <span>{{ comment }}</span>
                    <el-tag
                      v-if="trace.agent && trace.agent.includes('风控') && hasMemoryTrigger(comment)"
                      type="warning"
                      effect="dark"
                      size="small"
                      class="memory-buff-tag"
                    >
                      🧠 历史记忆触发
                    </el-tag>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else description="暂无智能体协作轨迹" />
    </div>
  </el-drawer>

  <!-- 整改函 Drawer 放在根层级，避免被 el-card overflow 裁剪 -->
  <RectificationLetter
    ref="rectificationRef"
    :task-id="taskId"
  />
</template>

<style scoped>
.result-card {
  border-radius: 12px;
  min-height: 560px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.report-body {
  background: #fff;
  padding: 24px 28px;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(30, 58, 138, 0.06);
}

.report-body * {
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
}

.pdf-exporting,
.pdf-exporting * {
  font-family: 'Microsoft YaHei', 'PingFang SC', SimSun, sans-serif !important;
  font-weight: 500 !important;
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
}

/* PDF 导出时隐藏干扰元素 */
.pdf-exporting .report-sticky-footer,
.pdf-exporting .ai-assistant,
.pdf-exporting .report-anchor {
  display: none !important;
}

/* PDF 导出时优化分页 */
.pdf-exporting .report-section,
.pdf-exporting .digital-seal,
.pdf-exporting .el-table {
  break-inside: avoid;
  page-break-inside: avoid;
}

.pdf-exporting .report-title,
.pdf-exporting .section-title {
  break-after: avoid;
  page-break-after: avoid;
}

.report-title {
  font-size: 24px;
  font-weight: 700;
  text-align: center;
  color: #1e3a8a;
  margin-bottom: 4px;
  letter-spacing: 2px;
}

.report-subtitle {
  font-size: 12px;
  color: #64748b;
  text-align: center;
  margin-bottom: 8px;
  letter-spacing: 1px;
}

.report-meta {
  font-size: 12px;
  color: #64748b;
  text-align: center;
  margin-bottom: 12px;
}

.report-tabs {
  border-radius: 8px;
}

.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.report-sticky-footer {
  position: sticky;
  bottom: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-top: 1px solid #e2e8f0;
  padding: 14px 28px;
  margin: 28px -28px -24px;
  z-index: 20;
}

.sticky-footer-inner {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
}

/* ========== 多智能体协作网络 ========== */
.agent-network-section {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 22px;
}

.agent-title {
  color: #0f172a;
  border-left-color: #3b82f6;
}

.agent-icon {
  color: #3b82f6;
  font-size: 18px;
}

.confidence-tag {
  margin-left: 8px;
  font-weight: 600;
}

.agent-steps-wrapper {
  padding: 16px 8px 8px;
}

.agent-steps :deep(.el-step__title) {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.agent-steps :deep(.el-step__description) {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  margin-top: 4px;
}

.agent-step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #dbeafe;
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.agent-steps :deep(.el-step__head.is-success) .agent-step-icon {
  background: #dcfce7;
  color: #16a34a;
}

.agent-steps :deep(.el-step__line) {
  background-color: #cbd5e1;
  height: 2px;
}

.agent-steps :deep(.el-step__line-inner) {
  border-color: #3b82f6;
  height: 2px;
}

/* 轨迹卡片 */
.agent-trace-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.trace-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  opacity: 0;
  transform: translateY(12px);
  animation: traceFadeIn 0.5s ease forwards;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.trace-card:hover {
  box-shadow: 0 6px 20px rgba(30, 58, 138, 0.1);
  transform: translateY(-2px);
}

.trace-card--success {
  border-left: 4px solid #22c55e;
}

.trace-card--warning {
  border-left: 4px solid #f59e0b;
}

@keyframes traceFadeIn {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.trace-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.trace-agent-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.trace-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
}

.trace-card-body {
  margin-bottom: 10px;
}

.trace-action {
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
  margin-bottom: 8px;
}

.trace-detail {
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trace-detail-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.trace-detail-key {
  color: #64748b;
  font-weight: 500;
  flex-shrink: 0;
}

.trace-detail-value {
  color: #1e293b;
  font-weight: 600;
}

.trace-card-footer {
  display: flex;
  justify-content: flex-end;
}

/* ========== Agent Drawer ========== */
.agent-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.drawer-body {
  padding: 20px 24px;
}

.agent-drawer :deep(.el-timeline-item__node) {
  width: 28px;
  height: 28px;
}

.agent-drawer :deep(.el-timeline-item__wrapper) {
  padding-left: 32px;
}

.agent-drawer :deep(.el-timeline-item__timestamp) {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

/* Timeline Card */
.timeline-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 18px;
  position: relative;
  transition: box-shadow 0.2s ease;
}

.timeline-card:hover {
  box-shadow: 0 4px 16px rgba(30, 58, 138, 0.08);
}

.timeline-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.timeline-header-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.timeline-title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

/* Detail Metrics */
.detail-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.metric-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
}

.metric-label {
  color: #64748b;
  font-weight: 500;
}

.metric-value {
  color: #1e293b;
  font-weight: 700;
}

/* Comments List */
.detail-comments {
  margin-bottom: 14px;
}

.comments-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 8px;
}

.comments-list {
  list-style: none;
  padding: 0;
  margin: 0;
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comments-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: #334155;
  line-height: 1.8;
}

.comment-icon {
  color: #10b981;
  font-size: 14px;
  margin-top: 3px;
  flex-shrink: 0;
}

/* Key-Value pairs */
.detail-kv {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kv-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.kv-key {
  color: #64748b;
  font-weight: 500;
  flex-shrink: 0;
}

.kv-value {
  color: #1e293b;
  font-weight: 600;
}

/* Confidence Dashboard */
.confidence-dashboard {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-top: -4px;
}

.confidence-label {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
}

/* Agent Descriptions */
.agent-descriptions {
  margin-bottom: 14px;
}

.agent-descriptions :deep(.el-descriptions__body) {
  background: #fff;
}

.agent-descriptions :deep(.el-descriptions__label) {
  font-weight: 600;
  color: #475569;
}

.agent-descriptions :deep(.el-descriptions__content) {
  color: #1e293b;
}

.kv-plain {
  font-size: 13px;
  color: #334155;
}

/* Timeline Description */
.timeline-description {
  font-size: 13px;
  color: #64748b;
  line-height: 1.7;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
}

/* Timeline Tokens */
.timeline-tokens {
  margin-bottom: 10px;
}

.timeline-tokens .el-tag {
  font-weight: 600;
}

/* 历史记忆 Buff 标签 */
.memory-buff-tag {
  margin-left: 8px;
  font-weight: 600;
  flex-shrink: 0;
}

/* ========== 双屏布局 & 状态栏 ========== */
.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 20px;
  margin-bottom: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-label {
  color: #64748b;
  font-weight: 500;
}

.status-value {
  font-weight: 700;
  color: #1e293b;
}

.status-value--danger {
  color: #dc2626;
}

.status-value--warning {
  color: #d97706;
}

.status-value--muted {
  color: #64748b;
}

.token-breakdown {
  display: block;
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
  margin-top: 2px;
}

.split-view-row {
  margin-top: 4px;
}

/* 左侧合同原文卡片 */
.contract-text-card {
  height: 70vh;
  border-radius: 10px;
}

.contract-text-card :deep(.el-card__body) {
  padding: 0;
  height: calc(70vh - 55px);
}

.contract-text-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 600;
  color: #1e40af;
}

.contract-text-header .header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.contract-text-header .header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-tag {
  font-weight: 600;
}

.contract-text-body {
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px;
  background: #fff;
}

.contract-text-content {
  font-size: 15px;
  line-height: 1.85;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* ========== 关键信息迷你对照表 ========== */
.key-info-compare {
  margin: -4px 0 16px 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}

.kic-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 1px solid #e2e8f0;
}

.kic-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #1e40af;
}

.kic-table {
  display: table;
  width: 100%;
  font-size: 13px;
}

.kic-row {
  display: table-row;
  transition: background-color 0.15s ease;
}

.kic-row:not(.kic-row--header):hover {
  background-color: #f8fafc;
}

.kic-row--header {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
}

.kic-row--header .kic-cell {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
}

.kic-row--mismatch {
  background: #fef2f2;
}

.kic-row--mismatch .kic-cell--contract {
  color: #dc2626;
  font-weight: 700;
}

.kic-row--new {
  background: #eff6ff;
}

.kic-row--new .kic-cell--contract {
  color: #2563eb;
  font-weight: 700;
}

.kic-cell--new {
  color: #2563eb;
  font-weight: 700;
}

.kic-cell {
  display: table-cell;
  padding: 7px 10px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
  word-break: break-word;
  overflow-wrap: break-word;
}

.kic-cell--label {
  color: #64748b;
  font-weight: 500;
  width: 80px;
}

.kic-cell--bid {
  color: #334155;
  width: 100px;
}

.kic-cell--contract {
  color: #334155;
  width: 120px;
}

.kic-cell--status {
  text-align: right;
  width: 70px;
}

.kic-cell--risk {
  color: #dc2626;
  font-weight: 700;
}

/* ========== 合同关键信息对照表（详细版） ========== */
.key-info-detail-section {
  margin-bottom: 22px;
}

.key-info-detail-table {
  display: table;
  width: 100%;
  font-size: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}

.kic-detail-row {
  display: table-row;
  transition: background-color 0.15s ease;
}

.kic-detail-row:not(.kic-detail-row--header):hover {
  background-color: #f8fafc;
}

.kic-detail-row--header {
  background: #f1f5f9;
  font-weight: 600;
  color: #475569;
}

.kic-detail-row--header .kic-detail-cell {
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.kic-detail-row--mismatch {
  background: #fef2f2;
}

.kic-detail-row--mismatch:hover {
  background: #fee2e2;
}

.kic-detail-row--mismatch .kic-detail-cell--contract {
  color: #dc2626;
  font-weight: 700;
}

.kic-detail-row--new {
  background: #eff6ff;
}

.kic-detail-row--new:hover {
  background: #dbeafe;
}

.kic-detail-row--new .kic-detail-cell--contract {
  color: #2563eb;
  font-weight: 700;
}

.kic-detail-cell--new {
  color: #2563eb;
  font-weight: 700;
}

.kic-detail-cell {
  display: table-cell;
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
  word-break: break-word;
  overflow-wrap: break-word;
}

.kic-detail-cell--dim {
  color: #64748b;
  font-weight: 600;
  width: 100px;
}

.kic-detail-cell--bid {
  color: #334155;
  width: 140px;
}

.kic-detail-cell--contract {
  color: #334155;
  width: 140px;
}

.kic-detail-cell--status {
  text-align: center;
  width: 90px;
}

.kic-detail-cell--hint {
  color: #7f1d1d;
  font-size: 13px;
  line-height: 1.6;
}

.kic-hint-text {
  color: #991b1b;
  font-weight: 500;
}

.kic-hint-text--ok {
  color: #94a3b8;
}

/* 高亮标记样式 */
.contract-mark {
  border-radius: 3px;
  padding: 1px 2px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
}

.contract-mark--diff {
  background-color: rgba(254, 202, 202, 0.55);
  color: #991b1b;
  border-bottom-color: #ef4444;
}

.contract-mark--diff:hover {
  background-color: rgba(254, 202, 202, 0.9);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.contract-mark--missing {
  background-color: rgba(253, 230, 138, 0.55);
  color: #92400e;
  border-bottom-color: #f59e0b;
}

.contract-mark--missing:hover {
  background-color: rgba(253, 230, 138, 0.9);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
}

/* 右侧报告面板 */
.right-panel {
  position: relative;
  height: 70vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
}

.right-panel .panel-toolbar {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 10;
  display: flex;
  gap: 8px;
}

.right-panel .panel-toolbar .el-button {
  font-weight: 600;
}

/* 全息历史数据库唤醒置顶容器 */
.memory-awakening-top {
  margin: 12px 12px 8px;
  position: relative;
  z-index: 5;
}

.right-panel .report-tabs {
  border: none;
  border-radius: 0;
}

.right-panel .report-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  border-radius: 10px 10px 0 0;
}

/* ========== 采购明细逐项对比 ========== */
.item-comparison-section {
  margin-bottom: 22px;
}

.item-comparison-table {
  display: table;
  width: 100%;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}

.ic-row {
  display: table-row;
  transition: background-color 0.15s ease;
}

.ic-row:not(.ic-row--header):hover {
  background-color: #f8fafc;
}

.ic-row--header {
  background: #f1f5f9;
  font-weight: 600;
  color: #475569;
}

.ic-row--header .ic-cell {
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.ic-row--mismatch {
  background: #fef2f2;
}

.ic-row--mismatch:hover {
  background: #fee2e2;
}


.ic-row--missing_in_contract {
  background: #fffbeb;
}

.ic-row--missing_in_contract:hover {
  background: #fef3c7;
}

.ic-row--new_in_contract {
  background: #eff6ff;
}

.ic-row--new_in_contract:hover {
  background: #dbeafe;
}

.ic-cell {
  display: table-cell;
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
  word-break: break-word;
  overflow-wrap: break-word;
}

.ic-cell--position {
  color: #64748b;
  font-size: 12px;
  width: 160px;
}

.ic-cell--name {
  color: #1e293b;
  font-weight: 600;
  width: 120px;
}

.ic-cell--bid {
  color: #334155;
  width: 240px;
  font-size: 13px;
  line-height: 1.6;
}

.ic-cell--contract {
  color: #334155;
  width: 240px;
  font-size: 13px;
  line-height: 1.6;
}

.ic-cell--contract.ic-cell--risk {
  color: #dc2626;
  font-weight: 600;
}

.ic-cell--contract.ic-cell--new {
  color: #2563eb;
  font-weight: 600;
}

.ic-cell--status {
  text-align: center;
  width: 100px;
}

/* ========== 全局比对概览面板 ========== */
.summary-panel-section {
  margin-bottom: 22px;
}

.summary-panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 20px 24px;
}

.summary-row-second {
  margin-top: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.summary-value {
  font-size: 14px;
  color: #1e293b;
  font-weight: 600;
}

.summary-item--amount .summary-amount-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.summary-amount-bid {
  font-size: 16px;
  font-weight: 700;
  color: #1e40af;
}

.summary-amount-contract {
  font-size: 16px;
  font-weight: 700;
  color: #2563eb;
}

.amount-vs-icon {
  color: #94a3b8;
  font-size: 14px;
}

/* ========== 差异卡片流 ========== */
.diff-card-stream-section {
  margin-bottom: 22px;
}

.diff-card {
  border-left: 4px solid #ef4444;
  border-radius: 10px;
  transition: box-shadow 0.25s ease;
}

.diff-card:hover {
  box-shadow: 0 6px 24px rgba(239, 68, 68, 0.1);
}

.diff-card--missing {
  border-left-color: #f59e0b;
}

.diff-card--missing:hover {
  box-shadow: 0 6px 24px rgba(245, 158, 11, 0.1);
}

.diff-card--positive {
  border-left-color: #22c55e;
}

.diff-card--positive:hover {
  box-shadow: 0 6px 24px rgba(34, 197, 94, 0.1);
}

.diff-card :deep(.el-card__header) {
  padding: 14px 18px;
  background: #fafafa;
  border-bottom: 1px solid #f1f5f9;
}

.diff-card :deep(.el-card__body) {
  padding: 18px;
}

.diff-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.diff-card-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.diff-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.diff-card-body {
  margin-bottom: 16px;
}

.diff-source-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-source-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.diff-source-text {
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  color: #334155;
  word-break: break-word;
  overflow-wrap: break-word;
  min-height: 48px;
}

.diff-source-text--bid {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.diff-card--positive .diff-source-text--contract {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
}

.diff-source-text--contract {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #7f1d1d;
}

.diff-card-footer {
  border-top: 1px dashed #e2e8f0;
  padding-top: 14px;
}

.diff-alert {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: linear-gradient(135deg, #fffbeb 0%, #fff7ed 100%);
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 12px 14px;
}

.diff-alert-icon {
  font-size: 16px;
  color: #f59e0b;
  margin-top: 2px;
  flex-shrink: 0;
}

.diff-alert-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.diff-alert-title {
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
}

.diff-alert-text {
  font-size: 13px;
  color: #78350f;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
}

.diff-card-location {
  font-size: 12px;
  color: #475569;
  font-weight: 500;
  margin-top: 6px;
  padding: 4px 8px;
  background: #f1f5f9;
  border-radius: 4px;
  display: inline-block;
}

/* ============================================================================
   移动端响应式
   ============================================================================ */
@media (max-width: 768px) {
  .compare-card :deep(.el-card__header) {
    padding: 12px;
  }

  .compare-card :deep(.el-card__body) {
    padding: 12px;
  }

  .detail-header {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }

  .detail-title-section {
    width: 100%;
  }

  .detail-title {
    font-size: 16px;
  }

  .detail-subtitle {
    font-size: 12px;
  }

  .detail-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }

  .summary-panel {
    padding: 12px;
  }

  .summary-row-second {
    margin-top: 12px;
  }

  .summary-item--amount .summary-amount-wrap {
    gap: 6px;
  }

  .diff-card :deep(.el-card__header) {
    padding: 10px 12px;
  }

  .diff-card :deep(.el-card__body) {
    padding: 12px;
  }

  .diff-card-header {
    gap: 8px;
  }

  .diff-card-title {
    font-size: 13px;
  }

  .diff-card-actions {
    gap: 6px;
  }

  .diff-source-text {
    padding: 10px 12px;
    font-size: 13px;
  }

  .diff-alert {
    padding: 10px 12px;
  }

  .diff-alert-title,
  .diff-alert-text {
    font-size: 12px;
  }

  /* 表格横向滚动 */
  :deep(.el-table__body-wrapper) {
    overflow-x: auto;
  }

  /* 标签页横向滚动 */
  :deep(.el-tabs__nav-wrap) {
    overflow-x: auto;
  }

  /* ========== 手机端：隐藏导出报告和整改函按钮 ========== */
  .mobile-hide-btn {
    display: none !important;
  }

  /* ========== 手机端：底部悬浮栏垂直全宽堆叠 ========== */
  .report-sticky-footer {
    padding: 10px 12px;
    margin: 16px -12px -12px;
  }

  .sticky-footer-inner {
    flex-direction: column;
    gap: 8px;
  }

  .sticky-footer-inner .el-button {
    width: 100%;
    height: 44px;
    font-size: 14px;
    margin: 0;
  }

  /* ========== 手机端：状态栏 2行4列网格 ========== */
  .status-bar {
    flex-wrap: wrap;
    gap: 8px 4px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }

  .status-item {
    flex: 0 0 calc(25% - 3px);
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 11px;
    text-align: center;
  }

  .status-label {
    font-size: 10px;
    color: #94a3b8;
  }

  .status-value {
    font-size: 11px;
  }

  /* ========== 手机端：差异卡片上下堆叠 ========== */
  .diff-card-body .el-row {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .diff-card-body .el-col {
    width: 100% !important;
    max-width: 100% !important;
    flex: 0 0 100% !important;
    padding: 0 !important;
  }

  /* ========== 手机端：关键信息对照表改为卡片式 ========== */
  .kic-table {
    display: block;
  }

  .kic-row {
    display: block;
    margin-bottom: 10px;
    padding: 10px 12px;
    background: #f8fafc;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
  }

  .kic-row--header {
    display: none;
  }

  .kic-cell {
    display: block;
    padding: 4px 0;
    border-bottom: none;
    width: 100% !important;
  }

  .kic-cell--label {
    font-size: 12px;
    color: #86909c;
    margin-bottom: 2px;
  }

  .kic-cell--bid,
  .kic-cell--contract {
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 4px;
  }

  .kic-cell--status {
    text-align: left;
    margin-top: 4px;
  }

  /* ========== 手机端：整体字体和间距微调 ========== */
  .report-anchor {
    display: none !important;
  }

  .report-section {
    margin-bottom: 12px;
  }

  .report-body {
    padding: 16px 12px;
  }

  .report-title {
    font-size: 20px;
  }

  .section-title {
    font-size: 15px;
  }

  .diff-source-text {
    font-size: 14px;
    padding: 10px 12px;
  }

  .diff-alert-title,
  .diff-alert-text {
    font-size: 13px;
  }

  .contract-text-content {
    font-size: 14px;
  }

  /* 面板工具栏按钮缩小间距 */
  .panel-toolbar {
    position: relative;
    top: auto;
    right: auto;
    padding: 8px 12px;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }

  .panel-toolbar .el-button {
    font-size: 12px;
    padding: 6px 10px;
  }
}
</style>
