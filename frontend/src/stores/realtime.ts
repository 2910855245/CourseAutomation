/**
 * 实时通道（Pinia setup store，模块内单例）。
 *
 * 全站共用**一条** WebSocket：Orders / Payment / Admin 都通过 `subscribe()`
 * 复用连接。原实现里每个页面各自 `new WebSocket`，Orders.vue 甚至在
 * onMounted 里重复建了两条。
 *
 * 服务端消息为信封格式（见 rust_worker/src/progress.rs）：
 *   { v, topic, type, data, ts, seq }
 * `topic` 的隐私过滤在服务端完成；客户端这层的前缀匹配只是省渲染。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface RealtimeMessage {
  topic: string
  type: string
  data: any
  ts: number
  seq: number
  [k: string]: any
}

type Handler = (msg: RealtimeMessage) => void

/** 客户端心跳间隔 */
const PING_MS = 25_000
/** 超过该时长没收到任何帧 → 判定 TCP 半开，主动重连（浏览器不会告诉我们） */
const STALE_MS = 75_000
const MAX_BACKOFF_MS = 30_000

export const useRealtimeStore = defineStore('realtime', () => {
  const connected = ref(false)

  const handlers = new Set<Handler>()
  let ws: WebSocket | null = null
  let reconnectAttempt = 0
  let reconnectTimer: number | null = null
  let pingTimer: number | null = null
  let closedByUs = false
  let lastFrameAt = 0

  /** 客户端关心的 topic 前缀（`order:`、`queue`、`*`） */
  const topicPrefixes = new Set<string>()
  /** 游客逐单凭证：订单列表变化时由 renewGuestScope() 重新上报 */
  let guestOrders: { order_id: string; view_token: string }[] = []
  let adminToken = ''

  function endpoint() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/api/progress/ws/live`
  }

  function send(payload: unknown) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload))
  }

  function sendScope() {
    if (adminToken) {
      send({ type: 'auth', token: adminToken })
      return
    }
    // 没有管理令牌时走游客通道；即使一笔都没有也要发，
    // 否则 AUTH_WS_REQUIRED 开启时会被服务端 5s 超时断开。
    send({
      type: 'sub',
      orders: guestOrders.filter(o => o.order_id && o.view_token),
    })
  }

  function matches(topic: string) {
    if (topicPrefixes.size === 0) return true
    for (const p of topicPrefixes) {
      if (p === '*' || p === topic) return true
      if (topic.startsWith(p)) return true
    }
    return false
  }

  function stopTimers() {
    if (pingTimer !== null) { clearInterval(pingTimer); pingTimer = null }
    if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null }
  }

  function scheduleReconnect() {
    if (closedByUs || reconnectTimer !== null) return
    const base = Math.min(MAX_BACKOFF_MS, 500 * 2 ** reconnectAttempt)
    const delay = base * (0.5 + Math.random() * 0.5)
    reconnectAttempt += 1
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    closedByUs = false
    try {
      ws = new WebSocket(endpoint())
    } catch {
      scheduleReconnect()
      return
    }
    lastFrameAt = Date.now()

    ws.onopen = () => {
      connected.value = true
      reconnectAttempt = 0
      lastFrameAt = Date.now()
      sendScope()
      if (pingTimer !== null) clearInterval(pingTimer)
      pingTimer = window.setInterval(() => {
        if (Date.now() - lastFrameAt > STALE_MS) {
          // 半开连接：关掉让 onclose 走重连
          ws?.close()
          return
        }
        send({ type: 'ping' })
      }, PING_MS)
    }

    ws.onmessage = (e) => {
      lastFrameAt = Date.now()
      let msg: RealtimeMessage
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      // 控制帧不派发（pong / heartbeat / authenticated / subscribed / error）
      if (!msg.topic) return
      for (const handler of handlers) {
        if (matches(msg.topic)) handler(msg)
      }
    }

    ws.onclose = () => {
      connected.value = false
      if (pingTimer !== null) { clearInterval(pingTimer); pingTimer = null }
      ws = null
      scheduleReconnect()
    }
  }

  /**
   * 幂等建连。`prefixes` 传关心的 topic 前缀（如 `order:` / `queue` / `*`）。
   * 返回退订函数（只摘掉自己的 handler，连接保持）。
   */
  function subscribe(prefixes: string[], handler: Handler) {
    for (const p of prefixes) topicPrefixes.add(p)
    handlers.add(handler)
    connect()
    // 前缀集合是共享的（多个页面订阅不同前缀），退订时只摘 handler：
    // 前缀保留最多让某个 handler 多收到几条它不关心的消息，由它自己按 type 判断。
    return () => { handlers.delete(handler) }
  }

  /** 管理端登录态变化时更新（用于 auth 帧） */
  function setAdminToken(token: string) {
    if (adminToken === token) return
    adminToken = token
    if (token) sendScope()
  }

  /** 游客订单集合变化时重新上报 view_token 白名单 */
  function renewGuestScope(orders: { order_id: string; view_token: string }[]) {
    guestOrders = orders
    if (!adminToken) sendScope()
  }

  function disconnect() {
    closedByUs = true
    stopTimers()
    ws?.close()
    ws = null
    connected.value = false
  }

  // 网络/前台恢复时立即重连，不必等退避计时
  const wake = () => { if (!connected.value && handlers.size > 0) connect() }
  window.addEventListener('online', wake)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') wake()
  })

  return { connected, subscribe, setAdminToken, renewGuestScope, disconnect }
})
