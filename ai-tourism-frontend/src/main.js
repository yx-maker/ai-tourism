import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.js'

import './styles/theme.css'
import './styles/ui.css'
import './styles/markdown.css'

createApp(App).use(router).mount('#app')
