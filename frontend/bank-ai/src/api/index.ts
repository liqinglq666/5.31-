/**
 * api/index.ts
 * -----------
 * API 入口兼容层。
 * 所有 API 已按领域拆分为独立文件，此处保留 re-export 以保持旧导入路径兼容。
 * 新代码建议直接从具体领域文件导入，如 `import { getStats } from '@/api/system'`
 */

export { default } from './client'

// 认证
export { getMe, login } from './auth'

// 比对与审查
export {
  postCompare,
  getStatus,
  submitContractReview,
  getContractReviewStatus,
  cancelCompare,
  getRunningTasks,
} from './compare'

// 任务管理
export { getRecords, exportExcel, addRemark } from './task'

// 管理
export {
  getPendingUsers,
  approveUser,
  getAllUsers,
  getUserRecords,
  toggleUserStatus,
} from './admin'

// 系统
export { getStats, getAvailableModels } from './system'

// 记忆层
export { searchMemory } from './memory'

// 配对
export { postMatchFiles, type MatchPair, type MatchResult } from './match'

// 审查结果（图表/洞察/Copilot）
export {
  getChartTrend,
  getClauseDistribution,
  getDashboardStats,
  getDashboardInsights,
  refreshInsights,
  getCopilotContext,
} from './review'
