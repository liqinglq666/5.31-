import api from './client'
import type { ApiResponse, ModelConfigItem } from '@/types/api'

export const getPendingUsers = () =>
  api.get<ApiResponse<any[]>>('/api/v1/admin/pending_users')

export const approveUser = (userId: string) =>
  api.post<ApiResponse<{ user_id: string }>>(`/api/v1/admin/users/${userId}/approve`)

export const getAllUsers = () =>
  api.get<
    ApiResponse<
      {
        id: string
        username: string
        full_name?: string
        employee_id?: string
        position?: string
        status: string
        is_admin?: boolean
        created_at?: string
        task_count: number
      }[]
    >
  >('/api/v1/admin/users')

export const getUserRecords = (
  userId: string,
  params: { page: number; page_size: number }
) =>
  api.get<
    ApiResponse<{
      total: number
      page: number
      page_size: number
      list: {
        task_id: string
        project_name: string
        created_at?: string
        status: string
        risk_level: string
        conclusion: string
        creator_name?: string
        creator_emp_id?: string
      }[]
    }>
  >(`/api/v1/admin/users/${userId}/records`, { params })

export const toggleUserStatus = (userId: string) =>
  api.post<ApiResponse<{ user_id: string; status: string }>>(
    `/api/v1/admin/users/${userId}/toggle_status`
  )

// ---------------------------------------------------------------------------
// 模型配置管理
// ---------------------------------------------------------------------------

export const getModelConfigs = () =>
  api.get<ApiResponse<ModelConfigItem[]>>('/api/v1/admin/models')

export const createModelConfig = (payload: Omit<ModelConfigItem, 'id' | 'created_at' | 'updated_at'>) =>
  api.post<ApiResponse<{ id: number }>>('/api/v1/admin/models', payload)

export const updateModelConfig = (modelId: number, payload: Partial<Omit<ModelConfigItem, 'id' | 'created_at' | 'updated_at'>>) =>
  api.put<ApiResponse<null>>(`/api/v1/admin/models/${modelId}`, payload)

export const deleteModelConfig = (modelId: number) =>
  api.delete<ApiResponse<null>>(`/api/v1/admin/models/${modelId}`)

export const setActiveModel = (modelId: number) =>
  api.post<ApiResponse<{ model_name: string }>>(`/api/v1/admin/models/${modelId}/set_active`)
