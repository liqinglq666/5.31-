import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

// Request 拦截器：自动注入 JWT Token
api.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token && config.headers) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response 拦截器：统一错误处理，401 自动登出
// 适配后端统一异常格式：{ code, message, data }
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const data = error.response?.data
    const message = data?.message || data?.detail || '请求失败，请稍后重试'

    if (status === 401) {
      const userStore = useUserStore()
      // 401 处理：游客与普通用户分别提示
      if (userStore.isGuest) {
        // 游客 token 过期，提示并跳转登录页
        ElMessage.error('已超时，请重新登录')
        userStore.clearAuth()
        window.location.href = '/login'
      } else {
        ElMessage.error('登录已过期，请重新登录')
        userStore.clearAuth()
        window.location.href = '/login'
      }
    } else if (status === 403) {
      ElMessage.error(message)
    } else if (status >= 400) {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  }
)

export default api
