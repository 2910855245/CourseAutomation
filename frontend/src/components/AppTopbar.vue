<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'

const props = withDefaults(defineProps<{
  title?: string
  showRoleBadge?: boolean
  showLogout?: boolean
}>(), {
  title: 'Fuk 文理网课',
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
const isAdmin = computed(() => store.isAdminLoggedIn)
const primaryRole = computed(() => {
  if (isAdmin.value) return 'admin'
  return ''
})
const roleBadge = computed(() => {
  if (isAdmin.value) return '管理员'
  return ''
})
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <router-link to="/" class="logo">
        {{ title }}
      </router-link>
      <nav class="desktop-nav">
        <router-link to="/" exact-active-class="nav-active">
首页
</router-link>
        <router-link to="/orders" active-class="nav-active">
我的订单
</router-link>
        <router-link v-if="isAdmin" to="/admin" active-class="nav-active">
管理后台
</router-link>
        <span v-if="showRoleBadge && roleBadge" class="topbar-role-badge">{{ roleBadge }}</span>
        <a v-if="showLogout" href="#" class="logout-link" @click.prevent="emit('logout')">退出</a>
      </nav>
      <button class="hamburger" :class="{ open: mobileMenuOpen }" aria-label="菜单" @click="toggleMobileMenu">
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
        <span v-if="showRoleBadge && roleBadge" class="mn-badge">{{ roleBadge }}</span>
        <a v-if="showLogout" href="#" class="mn-item logout-link" @click.prevent="emit('logout'); closeMobileMenu()">退出</a>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky; top: 0; z-index: 100;
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border-light);
}
.topbar-inner {
  max-width: 820px; margin: 0 auto; height: 52px;
  display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
}
.logo {
  font-size: 14px; font-weight: 600;
  color: var(--c-text); text-decoration: none;
  transition: opacity .2s ease;
}
.logo:hover { opacity: .6; text-decoration: none; }

.desktop-nav { display: flex; gap: 6px; align-items: center; }
.desktop-nav a {
  position: relative;
  font-size: 13px; font-weight: 500; color: var(--c-text-secondary);
  text-decoration: none;
  padding: 6px 10px;
  transition: color .2s ease;
}
.desktop-nav a:hover {
  color: var(--c-text);
  text-decoration: none;
  opacity: 1;
}
.desktop-nav a.nav-active {
  color: var(--c-text);
}
.desktop-nav a.nav-active::after {
  content: '';
  position: absolute; left: 10px; right: 10px; bottom: 0;
  height: 1px;
  background: var(--c-text);
}
.logout-link { color: var(--c-danger) !important; }
.topbar-role-badge {
  font-size: 11px; font-weight: 600; padding: 4px 11px; border-radius: var(--radius-pill);
  letter-spacing: .04em; white-space: nowrap;
  background: var(--c-primary-bg);
  color: var(--c-primary);
  border: 1px solid var(--c-border-light);
}

.hamburger {
  display: none;
  background: none; border: none; cursor: pointer;
  width: 40px; height: 40px; position: relative;
  flex-direction: column; justify-content: center; align-items: center; gap: 5px;
  padding: 6px; border-radius: 10px;
  transition: background-color .2s cubic-bezier(.32,.72,.35,1);
}
.hamburger:active { background: var(--c-surface-3); transform: scale(.96); }
.hamburger span {
  display: block; width: 20px; height: 1.5px;
  background: var(--c-text); border-radius: 2px;
  transition: all .28s cubic-bezier(.32,.72,.35,1);
}
.hamburger.open span:nth-child(1) { transform: translateY(6.5px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-6.5px) rotate(-45deg); }

.mobile-nav {
  display: none;
  flex-direction: column;
  padding: 8px 16px 16px;
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border-light);
}
.mn-item {
  display: block;
  padding: 12px 16px;
  font-size: 14px; font-weight: 500;
  color: var(--c-text-secondary);
  text-decoration: none;
  border-radius: 12px;
  transition: all .2s cubic-bezier(.32,.72,.35,1);
}
.mn-item:hover, .mn-item.router-link-active {
  color: var(--c-text);
  background: var(--c-surface-2);
  text-decoration: none;
}
.mn-badge {
  display: inline-block;
  margin: 8px 16px;
  font-size: 11px; font-weight: 600;
  padding: 4px 11px; border-radius: var(--radius-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  border: 1px solid var(--c-border-light);
}

.slide-down-enter-active, .slide-down-leave-active {
  transition: opacity .28s cubic-bezier(.32,.72,.35,1), transform .28s cubic-bezier(.32,.72,.35,1);
}
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }

@media (max-width: 768px) {
  .desktop-nav { display: none; }
  .hamburger { display: flex; }
  .mobile-nav { display: flex; }
}
</style>
