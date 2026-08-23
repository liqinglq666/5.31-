export type RiskLevel = 'high' | 'medium' | 'low' | 'safe' | 'unknown'

export const riskLevelTag = (level: string) => {
  if (level === 'high') return { type: 'danger', text: '高风险' }
  if (level === 'medium') return { type: 'warning', text: '中风险' }
  if (level === 'safe') return { type: 'success', text: '安全' }
  return { type: 'success', text: '低风险' }
}
