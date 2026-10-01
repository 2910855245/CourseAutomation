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
const roleBadge = computed(() => (isAdmin.value ? '管理员' : ''))
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <!-- 标识：单色描边几何 F —— 无外框、无底色、无渐变，只靠两笔横一竖立住，
           颜色随主题自动深浅（用户点名要"简单"） -->
      <router-link to="/" class="logo">
        <span class="logo-mark" aria-hidden="true">
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
            <path d="M7.5 4.8h9M7.5 12h6.8M7.5 4.8v14.4" />
          </svg>
        </span>
        <span class="logo-text">{{ title }}</span>
      </router-link>

      <nav class="desktop-nav">
        <router-link to="/" exact-active-class="nav-active">首页</router-link>
        <router-link to="/orders" active-class="nav-active">我的订单</router-link>
        <router-link to="/invite" active-class="nav-active">邀请有礼</router-link>
        <router-link v-if="isAdmin" to="/admin" active-class="nav-active">管理后台</router-link>
        <a v-if="showLogout" href="#" class="logout-link" @click.prevent="emit('logout')">退出</a>
      </nav>

      <div class="topbar-actions">
        <span v-if="showRoleBadge && roleBadge" class="topbar-role-badge">{{ roleBadge }}</span>
        <button
          class="theme-toggle"
          :title="store.isDark ? '切换到浅色' : '切换到暗色'"
          :aria-label="store.isDark ? '切换到浅色' : '切换到暗色'"
          @click="store.toggleTheme()"
        >
          <svg v-if="store.isDark" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" /></svg>
        </button>
        <button class="hamburger" :class="{ open: mobileMenuOpen }" aria-label="菜单" @click="toggleMobileMenu">
          <span></span><span></span><span></span>
        </button>
      </div>
    </div>

    <Transition name="slide-down">
      <div v-if="mobileMenuOpen" class="mobile-nav">
        <router-link to="/" class="mn-item" @click="closeMobileMenu()">首页</router-link>
        <router-link to="/orders" class="mn-item" @click="closeMobileMenu()">我的订单</router-link>
        <router-link to="/invite" class="mn-item" @click="closeMobileMenu()">邀请有礼</router-link>
        <router-link v-if="isAdmin" to="/admin" class="mn-item" @click="closeMobileMenu()">管理后台</router-link>
        <a v-if="showLogout" href="#" class="mn-item logout-link" @click.prevent="emit('logout'); closeMobileMenu()">退出</a>
        <span v-if="showRoleBadge && roleBadge" class="mn-badge">{{ roleBadge }}</span>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--c-bg) 80%, transparent);
  backdrop-filter: saturate(180%) blur(14px);
  -webkit-backdrop-filter: saturate(180%) blur(14px);
  border-bottom: 1px solid var(--c-border-light);
}
.topbar-inner {
  max-width: 960px;
  margin: 0 auto;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: 0 var(--space-6);
}

/* ---------- 标识 ---------- */
.logo { display: inline-flex; align-items: center; gap: 9px; text-decoration: none; }
.logo:hover { opacity: 1; text-decoration: none; }
/* 极简线标：单色、无外框、无阴影，只有品牌蓝描边 */
.logo-mark {
  width: 26px;
  height: 26px;
  display: grid;
  place-content: center;
  color: var(--c-primary);
  transition: transform var(--t) var(--ease);
}
.logo:hover .logo-mark { transform: translateY(-1px) scale(1.03); }
.logo-text {
  font-size: var(--fs-md);
  font-weight: 700;
  letter-spacing: var(--tracking-title);
  color: var(--c-text);
}

/* ---------- 导航 ---------- */
.desktop-nav { display: flex; align-items: center; gap: var(--space-1); }
.desktop-nav a {
  position: relative;
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-secondary);
  text-decoration: none;
  transition: color var(--t-fast) var(--ease), background var(--t-fast) var(--ease);
}
.desktop-nav a:hover {
  color: var(--c-text);
  background: var(--c-surface-2);
  opacity: 1;
  text-decoration: none;
}
.desktop-nav a.nav-active { color: var(--c-primary); font-weight: 600; }
.desktop-nav a.nav-active::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 1px;
  height: 2px;
  border-radius: 2px;
  background: var(--c-primary);
}
.logout-link { color: var(--c-danger) !important; }

/* ---------- 右侧动作 ---------- */
.topbar-actions { display: flex; align-items: center; gap: var(--space-2); }

.topbar-role-badge {
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: .02em;
  white-space: nowrap;
}

.theme-toggle {
  display: grid;
  place-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 1px solid var(--c-border-light);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-secondary);
  cursor: pointer;
  transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease),
              border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease);
}
.theme-toggle:hover { background: var(--c-surface); color: var(--c-text); border-color: var(--c-border); }
.theme-toggle:active { transform: scale(.94); }

/* ---------- 汉堡菜单 ---------- */
.hamburger {
  display: none;
  width: 44px;
  height: 44px;
  padding: 11px;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--c-border-light);
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
}
.hamburger span {
  display: block;
  width: 16px;
  height: 1.5px;
  border-radius: 2px;
  background: var(--c-text);
  transition: transform var(--t) var(--ease), opacity var(--t) var(--ease);
}
.hamburger.open span:nth-child(1) { transform: translateY(5.5px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-5.5px) rotate(-45deg); }

/* ---------- 移动端菜单 ---------- */
.mobile-nav {
  display: none;
  flex-direction: column;
  padding: var(--space-2) var(--space-4) var(--space-4);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border-light);
  box-shadow: var(--shadow-sm);
}
.mn-item {
  padding: 12px 14px;
  border-radius: var(--radius);
  font-size: var(--fs-base);
  font-weight: 500;
  color: var(--c-text-secondary);
  text-decoration: none;
  transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
}
.mn-item:hover, .mn-item.router-link-active {
  color: var(--c-text);
  background: var(--c-surface-2);
  text-decoration: none;
  opacity: 1;
}
.mn-badge {
  align-self: flex-start;
  margin: var(--space-2) 14px 0;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: var(--fs-xs);
  font-weight: 600;
}

.slide-down-enter-active, .slide-down-leave-active {
  transition: opacity var(--t) var(--ease), transform var(--t) var(--ease-out);
}
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }

@media (max-width: 768px) {
  /* 粘顶栏在手机上每滚动一帧都要重算一次背景模糊（GPU 常驻开销），
     是移动端最明显的耗电点之一；换成不透明底色，视觉上几乎无差 */
  .topbar {
    background: var(--c-bg);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .topbar-inner { padding: 0 var(--space-4); }
  .desktop-nav { display: none; }
  .hamburger { display: flex; }
  .mobile-nav { display: flex; }
}
</style>