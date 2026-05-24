<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'

const props = withDefaults(defineProps<{
  title?: string
  showRoleBadge?: boolean
  showLogout?: boolean
}>(), {
  title: 'FUCK 文理网课',
  showRoleBadge: true,
  showLogout: false,
})

const emit = defineEmits<{ logout: [] }>()
const mobileMenuOpen = ref(false)

function toggleMobileMenu() {
  mobileMenuOpen.value = !mobileMenuOpen.value
}

function closeMobileMenu() {
  mobileMenuOpen.value = false
}

const store = useAppStore()
const isAdmin = computed(() => {
  const u = store.userInfo as any
  if (!u) return false
  return u.role === 'admin' || u.is_admin
})
const isSubAdmin = computed(() => {
  const u = store.userInfo as any
  if (!u) return false
  return u.role === 'sub_admin'
})
const isAgent = computed(() => {
  const u = store.userInfo as any
  if (!u) return false
  if (u.role === 'agent') return true
  return u.agent_status === 'active'
})
const primaryRole = computed(() => {
  if (isAdmin.value) return 'admin'
  if (isSubAdmin.value) return 'sub_admin'
  if (isAgent.value) return 'agent'
  return ''
})
const roleBadge = computed(() => {
  if (isAdmin.value && isAgent.value) return '管理员·代理'
  if (isAdmin.value) return '管理员'
  if (isSubAdmin.value && isAgent.value) return '合伙人·代理'
  if (isSubAdmin.value) return '合伙人'
  if (isAgent.value) return '代理'
  return ''
})
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <router-link to="/" class="logo">
        <svg class="logo-icon" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 10.5V6a2 2 0 00-2-2H4a2 2 0 00-2 2v12a2 2 0 002 2h7"/><path d="M22 10.5L12 16l-3-1.7"/><path d="M12 16v5"/><path d="M22 10.5V12"/>
        </svg>
        <span>{{ title }}</span>
      </router-link>
      <nav class="desktop-nav">
        <router-link to="/">
首页
</router-link>
        <router-link to="/orders">
我的订单
</router-link>
        <router-link v-if="isAdmin" to="/admin">
管理后台
</router-link>
        <router-link v-if="isSubAdmin" to="/admin">
合伙人后台
</router-link>
        <router-link v-if="isAgent" to="/agent">
代理中心
</router-link>
        <span v-if="showRoleBadge && roleBadge" class="topbar-role-badge" :class="'role-' + primaryRole">{{ roleBadge }}</span>
        <a v-if="showLogout" href="#" class="logout-link" @click.prevent="emit('logout')">退出</a>
      </nav>
      <button class="hamburger" :class="{ open: mobileMenuOpen }" @click="toggleMobileMenu">
        <span></span><span></span><span></span>
      </button>
    </div>
    <Transition name="slide-down">
      <div v-if="mobileMenuOpen" class="mobile-nav" @click="closeMobileMenu">
        <router-link to="/" class="mn-item">
首页
</router-link>
        <router-link to="/orders" class="mn-item" @click="closeMobileMenu()">
我的订单
</router-link>
        <router-link v-if="isAdmin" to="/admin" class="mn-item">
管理后台
</router-link>
        <router-link v-if="isSubAdmin" to="/admin" class="mn-item">
合伙人后台
</router-link>
        <router-link v-if="isAgent" to="/agent" class="mn-item">
代理中心
</router-link>
        <span v-if="showRoleBadge && roleBadge" class="mn-badge" :class="'role-' + primaryRole">{{ roleBadge }}</span>
        <a v-if="showLogout" href="#" class="mn-item logout-link" @click.prevent="emit('logout'); closeMobileMenu()">退出</a>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky; top: 0; z-index: 100;
  background: rgba(255,255,255,.82); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--c-border);
}
.topbar-inner {
  max-width: 1120px; margin: 0 auto; height: var(--topbar-h);
  display: flex; align-items: center; justify-content: space-between; padding: 0 24px;
}
.logo {
  display: flex; align-items: center; gap: 8px;
  font-size: 18px; font-weight: 700; color: var(--c-text); text-decoration: none;
}
.logo-icon { color: var(--c-primary); }
.logo:hover { text-decoration: none; }
.desktop-nav { display: flex; gap: 28px; align-items: center; }
.desktop-nav a {
  font-size: 13.5px; font-weight: 500; color: var(--c-text-secondary);
  text-decoration: none; transition: color .15s;
}
.desktop-nav a:hover, .desktop-nav a.router-link-active { color: var(--c-primary); text-decoration: none; }
.logout-link { color: #ef4444 !important; }
.topbar-role-badge {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  letter-spacing: 0.5px; white-space: nowrap;
}
.topbar-role-badge.role-admin { background: #fef2f2; color: #dc2626; }
.topbar-role-badge.role-sub_admin { background: #fefce8; color: #ca8a04; }
.topbar-role-badge.role-agent { background: #ecfdf5; color: #059669; }

.hamburger {
  display: none;
  background: none; border: none; cursor: pointer;
  width: 40px; height: 40px; position: relative;
  flex-direction: column; justify-content: center; align-items: center; gap: 5px;
  padding: 6px; border-radius: 8px;
}
.hamburger:active { background: var(--c-bg); }
.hamburger span {
  display: block; width: 22px; height: 2px;
  background: var(--c-text); border-radius: 2px;
  transition: all .25s ease;
}
.hamburger.open span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

.mobile-nav {
  display: none;
  flex-direction: column;
  padding: 8px 16px 16px;
  background: rgba(255,255,255,.98);
  border-bottom: 1px solid var(--c-border);
}
.mn-item {
  display: block;
  padding: 12px 16px;
  font-size: 14px; font-weight: 500;
  color: var(--c-text-secondary);
  text-decoration: none;
  border-radius: 8px;
  transition: all .15s;
}
.mn-item:hover, .mn-item.router-link-active {
  color: var(--c-primary);
  background: var(--c-primary-bg);
  text-decoration: none;
}
.mn-badge {
  display: inline-block;
  margin: 8px 16px;
  font-size: 11px; font-weight: 600;
  padding: 3px 10px; border-radius: 10px;
}
.mn-badge.role-admin { background: #fef2f2; color: #dc2626; }
.mn-badge.role-sub_admin { background: #fefce8; color: #ca8a04; }
.mn-badge.role-agent { background: #ecfdf5; color: #059669; }

.slide-down-enter-active, .slide-down-leave-active { transition: all .2s ease; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }

@media (max-width: 768px) {
  .desktop-nav { display: none; }
  .hamburger { display: flex; }
  .mobile-nav { display: flex; }
}
</style>
