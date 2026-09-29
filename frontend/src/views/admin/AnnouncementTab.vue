<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'

// 原来三个操作全是 `catch {}` 静默吞错、成功也没有任何提示：
// 发布成功/失败在界面上唯一的差别只是徽标文字，操作者很容易误判。
const store = useAppStore()

const announcementText = ref('')
const announcementActive = ref(false)
const announcementSaving = ref(false)
const announcementId = ref(0)

async function loadAnnouncement() {
  try {
    const res = await api.announcement.get()
    if (res?.data) {
      announcementText.value = res.data.content || ''
      announcementActive.value = res.data.active
      announcementId.value = res.data.id || 0
    }
  } catch (e: any) {
    store.toast(e?.message || '加载公告失败', 'error')
  }
}

async function publishAnnouncement() {
  if (!announcementText.value.trim()) return
  announcementSaving.value = true
  try {
    const res = await api.announcement.set(announcementText.value.trim())
    if (res?.success === false) { store.toast(res.message || '发布失败', 'error'); return }
    if (res?.data?.id) announcementId.value = res.data.id
    announcementActive.value = true
    store.toast('公告已发布，前台访客下次打开首页即可看到', 'success')
  } catch (e: any) {
    store.toast(e?.message || '发布失败', 'error')
  } finally {
    announcementSaving.value = false
  }
}

async function disableAnnouncement() {
  announcementSaving.value = true
  try {
    const res = await api.announcement.disable()
    if (res?.success === false) { store.toast(res.message || '停用失败', 'error'); return }
    announcementActive.value = false
    store.toast('公告已停用', 'success')
  } catch (e: any) {
    store.toast(e?.message || '停用失败', 'error')
  } finally {
    announcementSaving.value = false
  }
}

onMounted(loadAnnouncement)
</script>

<template>
  <div class="announcement-tab">
    <div class="settings-card">
      <div class="card-head">
        <div class="card-title-wrap">
          <h3>系统公告</h3>
          <p class="settings-hint">
            改内容会重新弹一次；用户看到后不再重复弹。
          </p>
        </div>
        <span
          class="announcement-status"
          :class="announcementActive ? 'on' : 'off'"
        >
          <span class="status-dot" />
          {{ announcementActive ? `已启用 · ID ${announcementId}` : '未启用' }}
        </span>
      </div>
      <div class="field">
        <label>公告内容</label>
        <textarea
          v-model="announcementText"
          placeholder="输入公告内容，支持换行"
          rows="6"
          class="announcement-textarea"
        ></textarea>
      </div>
      <div class="announcement-actions">
        <button
          class="btn btn-primary"
          :disabled="announcementSaving || !announcementText.trim()"
          @click="publishAnnouncement"
        >
          {{ announcementSaving ? '发布中...' : '发布公告' }}
        </button>
        <button
          v-if="announcementActive"
          class="btn btn-ghost"
          :disabled="announcementSaving"
          @click="disableAnnouncement"
        >
          停用公告
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.announcement-tab {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  animation: an-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes an-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.settings-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 26px 28px;
  box-shadow: var(--shadow-xs);
  transition: box-shadow .25s cubic-bezier(.32, .72, .35, 1);
}
.settings-card:hover { box-shadow: var(--shadow-sm); }

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.card-title-wrap h3 {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
  margin-bottom: 4px;
}
.settings-hint {
  font-size: 12.5px;
  color: var(--c-text-secondary);
  line-height: 1.6;
}

.announcement-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
}
.announcement-status.on {
  background: var(--c-success-bg);
  color: var(--c-success);
}
.announcement-status.on .status-dot { background: var(--c-success); }
.announcement-status.off {
  background: var(--c-bg);
  color: var(--c-text-muted);
}
.announcement-status.off .status-dot { background: var(--c-text-muted); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; }

.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
.field label { font-size: 12.5px; font-weight: 600; color: var(--c-text-secondary); }

.announcement-textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  background: var(--c-bg);
  color: var(--c-text);
  transition: border-color .2s ease, box-shadow .2s ease, background .2s ease;
}
.announcement-textarea:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, .12);
  background: var(--c-surface);
}
.announcement-textarea::placeholder {
  color: var(--c-text-muted);
}

.announcement-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 20px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  white-space: nowrap;
  transition: transform .2s cubic-bezier(.32, .72, .35, 1), background .2s ease, box-shadow .2s ease, opacity .2s ease;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); }
.btn:active:not(:disabled) { transform: scale(.97); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: var(--shadow-xs); }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); }
.btn-ghost { background: transparent; color: var(--c-text-secondary); }
.btn-ghost:hover:not(:disabled) { color: var(--c-primary); background: var(--c-primary-bg); transform: none; }

@media (max-width: 768px) {
  .announcement-tab { max-width: 100%; }
  .settings-card { padding: 20px; }
  .card-head { flex-direction: column; gap: 10px; }
}
</style>
