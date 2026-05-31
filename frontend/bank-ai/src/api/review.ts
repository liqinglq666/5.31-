import api from './client'
import type { ApiResponse } from '@/types/api'

export const getChartTrend = () => api.get<ApiResponse<any>>('/api/v1/chart/trend')

export const getClauseDistribution = () =>
  api.get<ApiResponse<any>>('/api/v1/chart/clause-distribution')

export const getDashboardStats = () => api.get<ApiResponse<any>>('/api/v1/dashboard/stats')

export const getDashboardInsights = () => api.get<ApiResponse<any>>('/api/v1/dashboard/insights')

export const refreshInsights = () => api.post<ApiResponse<any>>('/api/v1/dashboard/insights/refresh')

export const getCopilotContext = (page_id: string, item_id?: string) =>
  api.get<ApiResponse<any>>('/api/v1/copilot/context-chat', {
    params: { page_id, item_id },
  })
