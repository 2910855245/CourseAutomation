/**
 * Admin state singleton — shared between Admin.vue and all tab components.
 *
 * We intentionally do NOT wrap with reactive(). When refs are spread into a
 * reactive() object, Vue auto-unwraps them, so destructuring produces plain
 * values that lose reactivity. Keeping the raw object preserves the refs so
 * each tab component gets live, reactive references.
 */

let _state: Record<string, any> | null = null

export function initAdminState(refs: Record<string, any>) {
  _state = refs
  return _state
}

export function useAdminState(): Record<string, any> {
  if (!_state) {
    throw new Error('useAdminState() called before initAdminState()')
  }
  return _state
}
