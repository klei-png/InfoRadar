import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { setUnauthorizedHandler } from './api/http'
import './styles/tokens.css'
import './styles/base.css'
import './styles/utilities.css'

// 401 踢出的跳转由请求层回调（token 清理已在 http.js 内经 auth store 完成）
setUnauthorizedHandler(() => {
  router.push('/login')
})

createApp(App).use(createPinia()).use(router).mount('#app')
