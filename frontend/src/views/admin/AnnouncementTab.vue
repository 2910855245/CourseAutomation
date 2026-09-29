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
// 公告附加项：标题 / 图片 / 联系方式（图片支持外链或本地压缩上传）
const announcementTitle = ref('')
const announcementImage = ref('')
const contactType = ref('微信')
const contactValue = ref('')
const contactTypes = ['微信', 'QQ', '手机', 'QQ群', '其他']

async function loadAnnouncement() {
  try {
    const res = await api.announcement.get()
    if (res?.data) {
      announcementText.value = res.data.content || ''
      announcementActive.value = res.data.active
      announcementId.value = res.data.id || 0
      announcementTitle.value = res.data.title || ''
      announcementImage.value = res.data.image || ''
      contactType.value = res.data.contact_type || '微信'
      contactValue.value = res.data.contact_value || ''
    }
  } catch (e: any) {
    store.toast(e?.message || '加载公告失败', 'error')
  }
}

/** 本地选图 → 压缩成 jpeg data URL（直接存库，避免图床失效/跨域） */
async function pickImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) { store.toast('请选择图片文件', 'warning'); return }
  try {
    const dataUrl = await compressImage(file)
    if (dataUrl.length > 700 * 1024) { store.toast('图片过大，请换一张（压缩后需小于 700KB）', 'error'); return }
    announcementImage.value = dataUrl
  } catch {
    store.toast('图片处理失败', 'error')
  } finally {
    input.value = ''
  }
}

function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('read failed'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('decode failed'))
      img.onload = () => {
        // 长边压到 1080，质量 0.82：营销图清晰度够用，体积可控
        const max = 1080
        const scale = Math.min(1, max / Math.max(img.width, img.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(img.width * scale)
        canvas.height = Math.round(img.height * scale)
        const ctx = canvas.getContext('2d')
        if (!ctx) { reject(new Error('no ctx')); return }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', 0.82))
      }
      img.src = String(reader.result)
    }
    reader.readAsDataURL(file)
  })
}

async function publishAnnouncement() {
  if (!announcementText.value.trim()) return
  announcementSaving.value = true
  try {
    const res = await api.announcement.set(announcementText.value.trim(), {
      title: announcementTitle.value.trim(),
      image: announcementImage.value,
      contact_type: contactValue.value.trim() ? contactType.value : '',
      contact_value: contactValue.value.trim(),
    })
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
        <label>公告标题（可空，显示在弹窗顶部）</label>
        <input
          v-model="announcementTitle"
          class="text-input"
          placeholder="例：双十一活动 / 平台维护通知"
          maxlength="60"
        >
      </div>
      <div class="field">
        <label>公告图片（可空，支持上传或外链）</label>
        <div class="image-row">
          <img v-if="announcementImage" :src="announcementImage" alt="公告图预览" class="image-preview">
          <div v-else class="image-empty">未选择图片</div>
          <div class="image-actions">
            <label class="btn btn-ghost btn-file">
              选择图片
              <input type="file" accept="image/*" @change="pickImage">
            </label>
            <input v-model="announcementImage" class="text-input" placeholder="或粘贴图片链接 https://...">
            <button v-if="announcementImage" class="btn btn-ghost" @click="announcementImage = ''">移除</button>
          </div>
        </div>
      </div>
      <div class="field">
        <label>联系方式（可空，弹窗里显示并支持一键复制）</label>
        <div class="contact-row">
          <select v-model="contactType" class="text-input contact-type">
            <option v-for="t in contactTypes" :key="t" :value="t">{{ t }}</option>
          </select>
          <input v-model="contactValue" class="text-input" placeholder="例：fuk_help / 123456789">
        </div>
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

/* ==================== 标题 / 图片 / 联系方式 ==================== */
.text-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  font-size: 13.5px;
  background: var(--c-bg);
  color: var(--c-text);
  outline: none;
  box-sizing: border-box;
  transition: border-color .2s ease, box-shadow .2s ease, background .2s ease;
}
.text-input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, .12);
  background: var(--c-surface);
}

.image-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.image-preview {
  width: 132px;
  height: 92px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--c-border);
  flex-shrink: 0;
}
.image-empty {
  width: 132px;
  height: 92px;
  border-radius: 10px;
  border: 1px dashed var(--c-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--c-text-muted);
  flex-shrink: 0;
}
.image-actions {
  flex: 1;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.btn-file { position: relative; overflow: hidden; align-self: flex-start; }
.btn-file input[type="file"] {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.contact-row { display: flex; gap: 10px; }
.contact-type { width: 120px; flex-shrink: 0; }

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
