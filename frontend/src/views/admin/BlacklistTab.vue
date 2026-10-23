<script setup lang="ts">
/**
 * 拉黑管理（风控）：账号黑名单 + IP 限制 + IP 黑名单 + 下单来源记录。
 *
 * 三件事各自独立，互不干扰：
 *   - 账号黑名单：封「某个学号」，判定只看学号
 *   - IP 限制：同一 IP 窗口内最多提交 N 个不同学号（防一台机器批量代刷）
 *   - IP 黑名单：封「某个来源」，命中全站 403
 */
import { onMounted } from 'vue'
import { useAdminStore } from '@/stores/admin'

const { accounts, ips, ipRecords, ipLimit, loading, accountForm, ipForm, loadAll, addAccount, removeAccount, addIp, removeIp, saveIpLimit } = useAdminStore().state().blacklist
const { fmtDate } = useAdminStore().state().dashboard
const { getPlatformName } = useAdminStore().state().ui

onMounted(loadAll)
</script>

<template>
  <div class="bl-tab">
    <div class="tab-head">
      <span class="head-hint">拉黑判定只看学号 / IP，前台拦截都在后端，前端弹窗只是提示</span>
      <button
        class="btn btn-ghost btn-sm"
        :disabled="loading"
        @click="loadAll"
      >
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <!-- ① 账号黑名单 -->
    <div class="settings-card">
      <h3>账号黑名单 <span class="count">{{ accounts.length }}</span></h3>
      <p class="settings-hint">
        被拉黑的学号无法扫描课程、也无法提交刷课，再次尝试会弹窗提示「该账号已被本平台拉黑，无法享用免费刷课」。
      </p>
      <div class="add-row">
        <input
          v-model="accountForm.username"
          placeholder="学号，例如 251020350309"
          @keyup.enter="addAccount"
        >
        <input
          v-model="accountForm.reason"
          placeholder="原因（选填），例如 刷完恶意取消"
          @keyup.enter="addAccount"
        >
        <button
          class="btn btn-primary btn-sm"
          @click="addAccount"
        >
          拉黑账号
        </button>
      </div>
      <div
        v-if="accounts.length"
        class="row-list"
      >
        <div class="row row-head">
          <span>学号</span><span>来源平台</span><span>原因</span><span>拉黑时间</span><span />
        </div>
        <div
          v-for="a in accounts"
          :key="a.id"
          class="row"
        >
          <span class="mono">{{ a.username }}</span>
          <span class="muted">{{ a.website_id ? getPlatformName(a.website_id) : '不限平台' }}</span>
          <span class="muted ellipsis">{{ a.reason || '—' }}</span>
          <span class="muted">{{ fmtDate(a.created_at) }}</span>
          <button
            class="btn btn-xs btn-ghost"
            @click="removeAccount(a.id, a.username)"
          >
            解除
          </button>
        </div>
      </div>
      <p
        v-else-if="!loading"
        class="empty"
      >
        暂无拉黑账号
      </p>
    </div>

    <!-- ② IP 限制 -->
    <div class="settings-card">
      <h3>IP 限制</h3>
      <p class="settings-hint">
        同一个 IP 在统计窗口内最多能提交几个<strong>不同学号</strong>。正常学员自己只占 1 个；
        一台机器替几十个人代刷会在超限时被拦下（同一学号重试不重复计数）。
      </p>
      <div class="limit-row">
        <div class="field">
          <label>启用</label>
          <select v-model="ipLimit.enabled">
            <option :value="true">
              开启
            </option>
            <option :value="false">
              关闭
            </option>
          </select>
        </div>
        <div class="field">
          <label>每个 IP 最多账号数</label>
          <input
            v-model.number="ipLimit.max_accounts"
            type="number"
            min="1"
            max="200"
          >
        </div>
        <div class="field">
          <label>统计窗口（小时）</label>
          <input
            v-model.number="ipLimit.window_hours"
            type="number"
            min="1"
            max="720"
          >
        </div>
        <button
          class="btn btn-primary btn-sm"
          @click="saveIpLimit"
        >
          保存
        </button>
      </div>
    </div>

    <!-- ③ IP 黑名单 -->
    <div class="settings-card">
      <h3>IP 黑名单 <span class="count">{{ ips.length }}</span></h3>
      <p class="settings-hint">
        被拉黑的来源无法访问本站任何页面（含 API 与静态页），直接返回 403。
      </p>
      <div class="add-row">
        <input
          v-model="ipForm.ip"
          placeholder="IP，例如 1.2.3.4"
          @keyup.enter="addIp()"
        >
        <input
          v-model="ipForm.reason"
          placeholder="原因（选填）"
          @keyup.enter="addIp()"
        >
        <button
          class="btn btn-danger btn-sm"
          @click="addIp()"
        >
          拉黑 IP
        </button>
      </div>
      <div
        v-if="ips.length"
        class="row-list"
      >
        <div class="row row-head">
          <span>IP</span><span>原因</span><span>拉黑时间</span><span />
        </div>
        <div
          v-for="p in ips"
          :key="p.id"
          class="row row-ip"
        >
          <span class="mono">{{ p.ip }}</span>
          <span class="muted ellipsis">{{ p.reason || '—' }}</span>
          <span class="muted">{{ fmtDate(p.created_at) }}</span>
          <button
            class="btn btn-xs btn-ghost"
            @click="removeIp(p.id, p.ip)"
          >
            解除
          </button>
        </div>
      </div>
      <p
        v-else-if="!loading"
        class="empty"
      >
        暂无拉黑 IP
      </p>
    </div>

    <!-- ④ 下单来源记录 -->
    <div class="settings-card">
      <h3>下单来源记录 <span class="count">{{ ipRecords.length }}</span></h3>
      <p class="settings-hint">
        按 IP 聚合：提交过几个不同学号、最近一次提交时间。账号数明显偏多的就是可疑的代刷来源，可以直接拉黑。
      </p>
      <div
        v-if="ipRecords.length"
        class="row-list"
      >
        <div class="row row-head">
          <span>IP</span><span>不同学号</span><span>提交次数</span><span>最近提交</span><span />
        </div>
        <div
          v-for="r in ipRecords"
          :key="r.ip"
          class="row"
        >
          <span class="mono">{{ r.ip }}</span>
          <span
            class="num"
            :class="{ hot: r.accounts > ipLimit.max_accounts }"
          >{{ r.accounts }}</span>
          <span class="num">{{ r.submissions }}</span>
          <span class="muted">{{ fmtDate(r.last_seen) }}</span>
          <span
            v-if="r.blocked"
            class="status-tag bad"
          >已拉黑</span>
          <button
            v-else
            class="btn btn-xs btn-danger"
            @click="addIp(r.ip, `批量提交 ${r.accounts} 个学号`)"
          >
            拉黑
          </button>
        </div>
      </div>
      <p
        v-else-if="!loading"
        class="empty"
      >
        暂无下单来源记录
      </p>
    </div>
  </div>
</template>

<style scoped>
.bl-tab {
  display: flex;
  flex-direction: column;
  gap: 18px;
  animation: bl-in .3s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes bl-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.tab-head { display: flex; align-items: center; gap: 12px; }
.head-hint { font-size: 12.5px; color: var(--c-text-muted); }

.settings-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 22px 24px;
  box-shadow: var(--shadow-xs);
}
.settings-card h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
  margin-bottom: 8px;
}
.count {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--c-primary);
  background: var(--c-primary-bg);
  padding: 1px 8px;
  border-radius: 999px;
}
.settings-hint {
  font-size: 12.5px;
  color: var(--c-text-muted);
  line-height: 1.7;
  margin-bottom: 16px;
}
.settings-hint strong { color: var(--c-text-secondary); font-weight: 600; }

/* 输入行 */
.add-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.add-row input { flex: 1 1 180px; min-width: 0; }

.limit-row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; min-width: 120px; }
.field label { font-size: 12px; color: var(--c-text-muted); }

/* 记录行 */
.row-list { display: flex; flex-direction: column; gap: 4px; }
.row {
  display: grid;
  grid-template-columns: minmax(92px, 1.2fr) minmax(62px, .9fr) minmax(88px, 1.4fr) minmax(92px, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 12.5px;
}
/* 网格项默认 min-width:auto 会被长内容撑破列宽（时间戳被裁、卡片横向滚动），
   显式归零后 ellipsis 才真正生效 */
.row > * { min-width: 0; }
.row:not(.row-head):nth-child(odd) { background: var(--c-bg); }
.row-ip { grid-template-columns: minmax(96px, 1.2fr) minmax(104px, 2fr) minmax(92px, 1fr) auto; }
.row-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  padding-bottom: 4px;
}
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--c-text); }
.muted { color: var(--c-text-muted); font-size: 12px; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { font-weight: 700; font-variant-numeric: tabular-nums; color: var(--c-text-secondary); }
.num.hot { color: var(--c-danger); }
.empty { font-size: 12.5px; color: var(--c-text-muted); }

.status-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.7;
  white-space: nowrap;
}
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }

/* 后台在这个宽度区间侧栏仍占位置，内容区只剩 ~500px：早点切成两列，
   不然记录行会撑破卡片出现横向滚动条 */
@media (max-width: 900px) {
  .settings-card { padding: 18px; }
  .row-head { display: none; }
  .row, .row-ip { grid-template-columns: 1fr 1fr; }
  .row .ellipsis { grid-column: 1 / -1; }
}
</style>