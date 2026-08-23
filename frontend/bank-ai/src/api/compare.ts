import api from './client'
import type { ApiResponse, TaskResult } from '@/types/api'

export const postCompare = (formData: FormData, enableVisualLocalization = false) => {
  const url = enableVisualLocalization
    ? '/api/v1/compare?enable_visual_localization=true'
    : '/api/v1/compare'
  return api.post<ApiResponse<{ task_id: string }>>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const getStatus = (taskId: string) =>
  api.get<
    ApiResponse<{
      status: string
      progress: number
      message: string
      result: TaskResult | null
      process_mode?: string
      creator_name?: string
      creator_emp_id?: string
      created_at?: string
      model_name?: string
      processing_seconds?: number
    }>
  >(`/api/v1/status/${taskId}`)

export const submitContractReview = (formData: FormData) =>
  api.post<ApiResponse<{ task_id: string; status: string }>>(
    '/api/v1/contract/review',
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )

export const getContractReviewStatus = (taskId: string) =>
  api.get<
    ApiResponse<{
      task_id: string
      status: string
      result: any
      error_message: string | null
      created_at: string
      completed_at: string | null
    }>
  >(`/api/v1/contract/review/${taskId}`)

export const cancelCompare = (taskId: string) =>
  api.post<ApiResponse<{ task_id: string; status: string }>>(
    `/api/v1/compare/${taskId}/cancel`
  )

export const getRunningTasks = () =>
  api.get<
    ApiResponse<
      Array<{
        task_id: string
        file_a_name: string
        file_b_name: string
        status: string
        message: string
        progress: number
        process_mode?: string
        created_at: string
      }>
    >
  >('/api/v1/tasks/running')
