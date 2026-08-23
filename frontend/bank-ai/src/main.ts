import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { pinia } from './store'

const app = createApp(App)
app.use(pinia)
app.use(ElementPlus)
app.use(router)
app.mount('#app')

// 隐藏加载动画
const loadingScreen = document.getElementById('loading-screen')
if (loadingScreen) {
  loadingScreen.style.opacity = '0'
  loadingScreen.style.transition = 'opacity 0.4s ease'
  setTimeout(() => {
    loadingScreen.style.display = 'none'
  }, 400)
}

// 请求桌面通知权限（任务完成后推送）
if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
  Notification.requestPermission()
}
