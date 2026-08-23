import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe } from '@/api'
import { TOKEN_KEY } from '@/utils/constants'

export interface UserInfo {
  id: string
  username: string
  full_name?: string
  employee_id?: string
  position?: string
  is_admin?: boolean
  status: string
}

const USER_INFO_KEY = 'user-info'

function loadUserInfo(): UserInfo | null {
  try {
    const raw = localStorage.getItem(USER_INFO_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const userInfo = ref<UserInfo | null>(loadUserInfo())

  const isAdmin = computed(() => userInfo.value?.is_admin ?? false)
  const isLoggedIn = computed(() => !!token.value && !!userInfo.value)
  const isGuest = computed(() => userInfo.value?.id === 'guest')
  const displayName = computed(() => {
    if (isGuest.value) return '游客'
    return userInfo.value?.full_name || userInfo.value?.username || '访客'
  })
  const employeeId = computed(() => userInfo.value?.employee_id || '')

  const permissions = computed(() => {
    const perms = new Set<string>()
    if (isGuest.value) {
      perms.add('dashboard:view')
      perms.add('records:view_limited')
      perms.add('copilot:chat')
      return perms
    }
    if (isLoggedIn.value) {
      perms.add('task:create')
      perms.add('task:view_own')
    }
    if (isAdmin.value) {
      perms.add('task:view_all')
      perms.add('task:archive')
      perms.add('user:manage')
      perms.add('admin:dashboard')
    }
    return perms
  })

  const setToken = (newToken: string) => {
    token.value = newToken
    if (newToken) {
      localStorage.setItem(TOKEN_KEY, newToken)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  const setGuestToken = (newToken: string) => {
    token.value = newToken
    userInfo.value = {
      id: 'guest',
      username: 'guest',
      full_name: '游客',
      employee_id: '',
      position: '',
      is_admin: false,
      status: 'active',
    }
    localStorage.setItem(TOKEN_KEY, newToken)
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(userInfo.value))
  }

  const clearGuest = () => {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_INFO_KEY)
  }

  const clearAuth = () => {
    clearGuest()
  }

  const hasPermission = (perm: string) => permissions.value.has(perm)

  const fetchUserInfo = async () => {
    if (!token.value) return
    if (isGuest.value) return
    try {
      const res = await getMe()
      userInfo.value = res.data.data
      localStorage.setItem(USER_INFO_KEY, JSON.stringify(res.data.data))
    } catch (_err) {
      clearAuth()
    }
  }

  return {
    token,
    userInfo,
    isAdmin,
    isLoggedIn,
    isGuest,
    displayName,
    employeeId,
    permissions,
    hasPermission,
    setToken,
    setGuestToken,
    clearAuth,
    fetchUserInfo,
  }
})
