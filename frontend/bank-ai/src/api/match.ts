import api from './client'
import type { ApiResponse } from '@/types/api'

export interface MatchPair {
  source_index: number
  contract_index: number
  source_name: string
  contract_name: string
  common_keywords: string[]
}

export interface MatchResult {
  pairs: MatchPair[]
  unmatched_source: number[]
  unmatched_contract: number[]
}

export const postMatchFiles = (data: {
  source_names: string[]
  contract_names: string[]
}) => api.post<ApiResponse<MatchResult>>('/api/v1/match', data)
