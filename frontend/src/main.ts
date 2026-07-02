// frontend/src/main.ts
// 文件说明：Vue 应用启动入口。
// 主要职责：创建应用、安装 Pinia 并加载全局样式。
// 对外入口：挂载到 #app。
// 依赖边界：不承载业务状态和接口调用。

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import './assets/main.css'

createApp(App).use(createPinia()).mount('#app')
