/**
 * Admin 视图共享类型定义
 */

export interface PendingUser {
  id: string
  username: string
  full_name: string | null
  employee_id: string | null
  position: string | null
  status: string
  created_at: string | null
}

export interface AdminUser {
  id: string
  username: string
  full_name?: string
  employee_id?: string
  position?: string
  status: string
  is_admin?: boolean
  created_at?: string
  task_count: number
}

export interface UserRecordItem {
  task_id: string
  project_name: string
  created_at?: string
  status: string
  risk_level: string
  conclusion: string
  creator_name?: string
  creator_emp_id?: string
}
