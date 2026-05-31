import api from './client'
import type { ApiResponse } from '@/types/api'

export const getMe = () =>
  api.get<
    ApiResponse<{
      id: string
      username: string
      full_name?: string
      employee_id?: string
      position?: string
      is_admin?: boolean
      status: string
    }>
  >('/api/v1/auth/me')

export const login = (formData: URLSearchParams) =>
  api.post('/api/v1/auth/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
