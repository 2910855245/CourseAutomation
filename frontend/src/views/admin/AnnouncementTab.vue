<script setup lang="ts">
// @ts-nocheck
import { ref, onMounted } from 'vue'
import { api } from '@/api'

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
  } catch {}
}

async function publishAnnouncement() {
  if (!announcementText.value.trim()) return
  announcementSaving.value = true
  try {
    const res = await api.announcement.set(announcementText.value.trim())
    if (res?.data?.id) announcementId.value = res.data.id
    announcementActive.value = true
  } catch {}
  announcementSaving.value = false
}

async function disableAnnouncement() {
  announcementSaving.value = true
  try {
    await api.announcement.disable()
    announcementActive.value = false
  } catch {}
  announcementSaving.value = false
}

onMounted(loadAnnouncement)
</script>

<template>
  <div class="announcement-tab">
    <div class="settings-card">
      <h3>系统公告</h3>
      <p class="settings-hint">
        发布公告后，用户打开首页会弹窗提示，确认后不再重复弹出。更新公告内容会重新触发弹窗。
      </p>
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
        <span v-if="announcementActive" class="announcement-status on">
          公告已启用 (ID: {{ announcementId }})
        </span>
        <span v-else class="announcement-status off">
          公告未启用
        </span>
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
}
.announcement-textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  background: var(--c-bg);
  color: var(--c-text);
  transition: border-color .15s, box-shadow .15s;
}
.announcement-textarea:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(79,110,247,.12);
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
.announcement-status {
  font-size: 12px;
  font-weight: 600;
}
.announcement-status.on {
  color: var(--c-success);
}
.announcement-status.off {
  color: var(--c-text-muted);
}
@media (max-width: 768px) {
  .announcement-tab { max-width: 100%; }
}
</style>
