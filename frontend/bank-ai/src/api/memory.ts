import api from './client'
import type { ApiResponse } from '@/types/api'

export const searchMemory = (data: { query: string; doc_id?: string; top_k?: number }) =>
  api.post<ApiResponse<any[]>>('/api/v1/memory/search', data)
