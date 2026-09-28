/**
 * 主题单一真源（TS 侧）。
 *
 * 这里的品牌色/字体/圆角同时喂给两处：
 * 1. Naive UI —— 通过 GlobalThemeOverrides；
 * 2. 手写样式 —— `styles/main.css` 的 `:root` / `[data-theme="dark"]`
 *    使用同一组字面量（CSS 无法 import TS，只能人工对齐；改色时两处一起改）。
 *
 * 之所以不在运行时把品牌色写回 CSS 变量：内联样式优先级高于
 * `[data-theme="dark"]`，会让暗色主题的浅蓝主色失效。
 */
import type { GlobalThemeOverrides } from 'naive-ui'

interface Brand {
  primary: string
  hover: string
  pressed: string
  suppl: string
  faded: string
}

/** 浅色主题品牌色（= main.css `:root`） */
const lightBrand: Brand = {
  primary: '#0071e3',
  hover: '#1a80e6',
  pressed: '#005bb8',
  suppl: '#3d94ea',
  faded: 'rgba(0, 113, 227, .10)',
}

/** 暗色主题品牌色（= main.css `[data-theme="dark"]`，暗底上提亮） */
const darkBrand: Brand = {
  primary: '#3d94ea',
  hover: '#58a5ef',
  pressed: '#2b7fd4',
  suppl: '#4aa0ee',
  faded: 'rgba(61, 148, 234, .16)',
}

const FONT_FAMILY =
  "'Geist Sans', -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
const FONT_FAMILY_MONO =
  "'Geist Mono', ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace"

function buildOverrides(brand: Brand): GlobalThemeOverrides {
  return {
    common: {
      primaryColor: brand.primary,
      primaryColorHover: brand.hover,
      primaryColorPressed: brand.pressed,
      primaryColorSuppl: brand.suppl,
      fontFamily: FONT_FAMILY,
      fontFamilyMono: FONT_FAMILY_MONO,
      fontSize: '14px',
      // 对齐 main.css 的 --radius-md / --radius-sm
      borderRadius: '10px',
      borderRadiusSmall: '6px',
    },
    Button: {
      borderRadiusMedium: '10px',
      borderRadiusLarge: '12px',
      fontWeight: '600',
    },
    Card: { borderRadius: '14px' },
    Dialog: { borderRadius: '14px' },
    Input: { borderRadius: '10px' },
    Message: { borderRadius: '12px' },
  }
}

export const lightThemeOverrides = buildOverrides(lightBrand)
export const darkThemeOverrides = buildOverrides(darkBrand)
