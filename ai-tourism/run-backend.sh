#!/bin/bash
# AI旅游路线规划系统 - 后端启动脚本 (git-bash)
set -e
cd "$(dirname "$0")"

set +H  # 关闭 history expansion，防止 .env 中 ! 触发异常

HERMES_ENV="$LOCALAPPDATA/hermes/.env"
[ -z "$LOCALAPPDATA" ] && HERMES_ENV="$HOME/AppData/Local/hermes/.env"

# 从项目 .env.local 加载变量（优先级高）
if [ -f ".env.local" ]; then
  set -a
  . ./.env.local
  set +a
fi

# 若智谱 key 仍未设置，从 Hermes 环境加载
if [ -z "${ZHIPU_API_KEY}" ] && [ -f "$HERMES_ENV" ]; then
  set -a
  . "$HERMES_ENV"
  set +a
fi

if [ -z "${ZHIPU_API_KEY}" ]; then
  echo "[ERROR] 未找到 ZHIPU_API_KEY，请在项目根目录 .env.local 中配置"
  echo "        格式：ZHIPU_API_KEY=<你的智谱 API Key>"
  echo "        申请地址：https://open.bigmodel.cn"
  exit 1
fi

echo "==> 模型: glm-4-flash @ https://open.bigmodel.cn/api/paas/v4"
echo "==> 启动后端 (端口 8290) ..."
exec ./mvnw spring-boot:run -q 2>&1 | tee backend.log
