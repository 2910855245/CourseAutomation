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
    return platformNames.value[id] || '平台' + id
  }

  return { platformNames, load, getName }
}
