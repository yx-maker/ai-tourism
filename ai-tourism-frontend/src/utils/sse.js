/**
 * SSE 事件流解析（纯函数，无框架依赖，便于单独测试）
 *
 * 后端 /ai_assistant/chat-stream 的事件格式：
 *   data: {"choices":[{"index":0,"text":"...","finish_reason":null,"model":"glm-4-flash"}]}\n\n
 *
 * 关键点：必须按 \n\n 事件边界缓冲。
 * 直接对每个网络分片做 JSON.parse 会在分片切断 JSON 时抛错并丢内容——
 * 这是最容易踩、且只在长回复时才暴露的坑。
 */

/**
 * 从单个 SSE 事件块中抽出 data 负载（一个事件可能有多行 data:）。
 *
 * ⚠️ 本后端有一个反直觉的编码特征，必须容错：
 * 服务层返回的字符串本身已经带 "data: " 前缀并以 \n\n 结尾，
 * 而 Spring 的 ServerSentEventHttpMessageWriter 在写 Flux<String> 时
 * 会把整个字符串按换行拆开、逐行再补一个 "data:"，
 * 于是客户端收到的事件块实际长这样：
 *
 *   data:data: {"choices":[{"index":0,"text":"你好",...}]}
 *   data:
 *   data:
 *
 * 按标准 SSE 剥一层后拿到的是 "data: {json}"，直接 JSON.parse 必失败。
 * 因此这里循环剥掉重复前缀，直到负载不再以 data: 开头。
 * （合法负载是 JSON，以 { 或 [ 开头，所以不会误伤。）
 */
export function extractPayload(block) {
  let payload = ''
  for (const line of block.split('\n')) {
    const t = line.trimStart()
    if (t.startsWith('data:')) payload += t.slice(5).trim()
  }
  let guard = 0
  while (payload.startsWith('data:') && guard++ < 8) {
    payload = payload.slice(5).trim()
  }
  return payload
}

/**
 * 解析一条 data 负载，取出增量文本与结束标记。
 * 无法解析或非对话事件时返回 null。
 */
export function parseChoice(payload) {
  if (!payload || payload === '[DONE]') return null
  let json
  try {
    json = JSON.parse(payload)
  } catch {
    return null
  }
  const choice = json?.choices?.[0]
  if (!choice) return null
  return {
    text: typeof choice.text === 'string' ? choice.text : '',
    finishReason: choice.finish_reason && choice.finish_reason !== 'null' ? choice.finish_reason : null,
    model: choice.model || null
  }
}

/**
 * 消费一个 fetch Response 的 SSE 流。
 *
 * @param {Response} response  原始响应（未解包）
 * @param {(delta: {text:string, finishReason:string|null, model:string|null}) => void} onDelta
 * @returns {Promise<{text:string, finished:boolean, chunks:number}>}
 */
export async function consumeSSE(response, onDelta) {
  if (!response?.body) throw new Error('响应没有可读流')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  let text = ''
  let finished = false
  let chunks = 0

  const handle = (block) => {
    const delta = parseChoice(extractPayload(block))
    if (!delta) return
    if (delta.text) {
      text += delta.text
      chunks += 1
    }
    if (delta.finishReason) finished = true
    onDelta?.(delta)
  }

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let idx
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      if (block.trim()) handle(block)
    }
  }

  // 收尾：处理结尾没有空行的事件
  if (buf.trim()) handle(buf)

  return { text, finished, chunks }
}
