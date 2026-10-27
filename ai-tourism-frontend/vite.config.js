import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  root: '.', // 明确指定根目录
  publicDir: 'public', // 静态资源目录
  build: {
    outDir: 'dist', // 输出目录
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html') // 明确指定入口文件
      }
    }
  },
  server: {
    port: 3001,
    // 只监听本机：开发期无需对外暴露，绑 0.0.0.0 只会扩大暴露面。
    // （后端 CorsConfig 用的是 allowedOriginPatterns("*")，本身不限制来源，
    //   所以这里纯粹是本地安全考量，不是为了迁就 CORS。）
    host: '127.0.0.1',
    strictPort: true,
    allowedHosts: [
      'www.aitrip.chat',     // 域名
      'aitrip.chat',         // 根域名
      'localhost',           // 本地开发
      '127.0.0.1'            // 本地IP
    ]
  }
})