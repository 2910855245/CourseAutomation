import { ref, reactive, computed } from 'vue'

export const DRAFT_KEY = 'setup_draft'

export function useSetupWizard() {
  const totalSteps = 8
  const currentStep = ref(1)
  const loading = ref(false)
  const error = ref('')
  const success = ref('')
  const completedSteps = reactive(new Set<number>())
  const maxReachedStep = ref(1)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let extraSave: (() => Record<string, any>) | null = null

  const steps = computed(() => [
    { num: 1, title: '欢迎' },
    { num: 2, title: '环境' },
    { num: 3, title: '数据库' },
    { num: 4, title: '管理员' },
    { num: 5, title: '收款' },
    { num: 6, title: '定价' },
    { num: 7, title: 'AI' },
    { num: 8, title: '完成' },
  ])

  function goStep(n: number) {
    if (n < 1 || n > totalSteps) return
    currentStep.value = n
    if (n > maxReachedStep.value) maxReachedStep.value = n
    error.value = ''
    success.value = ''
  }

  function nextStep() {
    if (currentStep.value < totalSteps) goStep(currentStep.value + 1)
  }

  function prevStep() { goStep(currentStep.value - 1) }

  function markDone(n: number) {
    completedSteps.add(n)
    debouncedSave()
  }

  function setExtraSave(fn: () => Record<string, any>) {
    extraSave = fn
  }

  function saveDraft() {
    const base = {
      currentStep: currentStep.value,
      completedSteps: Array.from(completedSteps),
      maxReachedStep: maxReachedStep.value,
    }
    const draft = extraSave ? { ...base, ...extraSave() } : base
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) } catch {}
  }

  function debouncedSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(saveDraft, 300)
  }

  function restoreDraft(): Record<string, any> | null {
    try {
      const raw = localStorage.getItem(DRAFT_KEY)
      if (!raw) return null
      const d = JSON.parse(raw)
      currentStep.value = d.currentStep ?? 1
      maxReachedStep.value = d.maxReachedStep ?? 1
      if (d.completedSteps) d.completedSteps.forEach((n: number) => completedSteps.add(n))
      return d
    } catch { return null }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY) } catch {}
  }

  function cleanup() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
  }

  return {
    totalSteps, currentStep, loading, error, success, completedSteps, maxReachedStep, steps,
    goStep, nextStep, prevStep, markDone, setExtraSave, saveDraft, debouncedSave, restoreDraft, clearDraft, cleanup,
  }
}
