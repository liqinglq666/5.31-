export interface ContractItem {
  name: string
  specification?: string
  quantity?: number
  unit_price?: number
  total_price?: number
  position?: string
}

export interface ItemDifference {
  field: string
  field_label: string
  bid_value: any
  contract_value: any
  diff_pct?: number
}

export interface ItemComparison {
  name: string
  position: string
  status: 'match' | 'mismatch' | 'missing_in_contract' | 'new_in_contract'
  differences: ItemDifference[]
}

export interface PenaltyMatrix {
  delay_daily_rate?: number
  penalty_cap_rate?: number
  termination_penalty_rate?: number
}

export interface BidInfo {
  vendor_name: string
  total_amount: number | string
  delivery_days: number | string
  delay_daily_rate?: number
  penalty_cap_rate?: number
  termination_penalty_rate?: number
  items?: ContractItem[]
}

export interface ContractInfo {
  vendor_name: string
  total_amount: number | string
  delivery_days: number | string
  delay_daily_rate?: number
  penalty_cap_rate?: number
  termination_penalty_rate?: number
  items?: ContractItem[]
}

export interface VisualEvidence {
  page_index: number
  bbox: [number, number, number, number]
  matched_text: string
  confidence: number
}

export interface DifferenceItem {
  type?: string
  description: string
  suggested_amendment?: string
  original_text?: string
  contract_text?: string
  risk_comment?: string
  is_favorable_to_buyer?: boolean
  visual_evidence?: VisualEvidence | null
}

export interface MissingItem {
  clause_name?: string
  description: string
  suggested_amendment?: string
  original_text?: string
  contract_text?: string
  risk_comment?: string
  visual_evidence?: VisualEvidence | null
}

export interface AgentTrace {
  stage?: number
  agent: string
  action: string
  description?: string
  status: string
  detail?: Record<string, any>
}

export interface PhysicalAlert {
  source: string
  tool: string
  side: string
  item_name: string
  type: string
  description: string
  deviation?: number
  deviation_pct?: number
}

export interface ComparisonResult {
  risk_level: string
  conclusion?: string
  confidence_score?: number
  differences: DifferenceItem[] | string[]
  missing_items?: MissingItem[]
  matches?: string[]
  agent_traces?: AgentTrace[]
  parsed_contract_text?: string
  physical_alerts?: PhysicalAlert[]
}

export interface PaymentNode {
  node_name: string
  percentage: number
  amount: number
  condition: string
}

export interface FinancialInfo {
  total_amount?: number
  warranty_ratio?: number
  payment_nodes?: PaymentNode[]
}

export interface TaskResult {
  bid_info: BidInfo
  contract_info: ContractInfo
  comparison: ComparisonResult
  process_mode?: string
  financial_info?: FinancialInfo
  created_at?: string
  model_name?: string
  processing_seconds?: number
  memory_context?: MemoryContext
  token_usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
}

export interface StatsData {
  total_reviews: number
  today_new: number
  high_risk_ratio: number
  avg_duration_seconds: number
}

export interface RecordItem {
  task_id: string
  project_name: string
  created_at: string
  status: string
  risk_level: string
  conclusion: string
  creator_id?: string
  creator_name?: string
  creator_emp_id?: string
  is_archived?: boolean
  archive_time?: string
  reviewer_name?: string
  reviewer_emp_id?: string
  remark?: string
  remark_time?: string
  remark_reviewer_name?: string
  remark_reviewer_emp_id?: string
}

export interface TrendData {
  dates: string[]
  totals: number[]
  risks: number[]
}

export interface PieDataItem {
  name: string
  value: number
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface RecordsResponse {
  total: number
  list: RecordItem[]
}

export interface ModelItem {
  id: string
  name: string
  provider: string
  version: string
  description?: string
  recommended: boolean
}

export interface ModelGroup {
  provider: string
  models: ModelItem[]
}

export interface MemoryContext {
  supplier_context: string
  rag_context: string
}

export interface RunningTask {
  taskId: string
  fileName: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  progress: number
  message: string
  processMode?: string
  startTime: string
  visible: boolean
  result?: TaskResult | null
  isCancelling?: boolean
  batchInfo?: { current: number; total: number }
  intervalId?: number
}

export interface ModelConfigItem {
  id: number
  provider: string
  model_name: string
  api_model_id?: string
  base_url?: string
  api_key: string
  temperature?: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface ActiveModelInfo {
  model_name: string
  provider: string
  base_url?: string
  temperature?: string
}
