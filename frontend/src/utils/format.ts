export function fmtMoney(v: number): string {
  return '¥' + (v || 0).toFixed(2)
}

export function fmtDate(s?: string): string {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 19)
}

export function fmtShortDate(s?: string): string {
  if (!s) return '-'
  return s.slice(5, 16).replace('T', ' ')
}

export function fmtTime(s?: string): string {
  if (!s) return '-'
  return s.slice(11, 19)
}

export const orderStatusLabel: Record<string, string> = {
  pending: '待处理', accepted: '已接单', queued: '排队中', running: '执行中',
  completed: '已完成', failed: '失败', cancelled: '已取消', paid: '已支付',
  retrying: '重试中', amount_mismatch: '金额异常', waiting: '等待明天',
}

export const orderStatusClass: Record<string, string> = {
  pending: 'warn', accepted: 'primary', queued: 'primary', running: 'primary',
  completed: 'ok', failed: 'bad', cancelled: 'muted', paid: 'ok',
  retrying: 'warn', amount_mismatch: 'bad', waiting: 'primary',
}

export const taskTypeNames: Record<string, string> = {
  video: '视频', exam: '考试', both: '视频+考试', full: '全包', chaoxing_points: '学习通积分',
}

export const agentStatusLabel: Record<string, string> = {
  pending: '待审核', active: '活跃', suspended: '已暂停',
}

export const agentStatusClass: Record<string, string> = {
  pending: 'warn', active: 'ok', suspended: 'bad',
}
