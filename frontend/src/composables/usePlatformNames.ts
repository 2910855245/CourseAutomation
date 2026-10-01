import { ref } from 'vue'
import { api } from '../api'

const platformNames = ref<Record<number, string>>({})
const loaded = ref(false)

export function usePlatformNames() {
  async function load() {
    if (loaded.value) return
    try {
      const res = await api.courses.platforms()
      if (res.success && res.data) {
        const map: Record<number, string> = {}
        for (const p of res.data) {
          map[p.id] = p.name
        }
        platformNames.value = map
        loaded.value = true
      }
    } catch {}
  }

  function getName(id: number): string {
    const fallback: Record<number, string> = { 1: '在线课程', 2: '劳动课程', 3: '公益课程', 4: '学习通' }
    return platformNames.value[id] || fallback[id] || '平台' + id
  }

  /** 清缓存：域名监控检测后平台名可能刚被首页文案纠正，需要重新拉一次 */
  function reset() {
    loaded.value = false
  }

  return { platformNames, load, getName, reset }
}
