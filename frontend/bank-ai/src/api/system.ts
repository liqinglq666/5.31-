import api from './client'
import type { ApiResponse, StatsData, ModelItem, ActiveModelInfo } from '@/types/api'

export const getStats = () => api.get<ApiResponse<StatsData>>('/api/v1/stats')

export const getAvailableModels = () =>
  api.get<ApiResponse<ModelItem[]>>('/api/v1/system/models')

export const getActiveModel = () =>
  api.get<ApiResponse<ActiveModelInfo>>('/api/v1/system/active_model')
