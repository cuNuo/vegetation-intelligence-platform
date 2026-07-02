// frontend/src/composables/useTheme.ts
// 文件说明：主题状态组合式函数。
// 主要职责：持久化明暗主题并同步 document 根节点属性。
// 对外入口：useTheme、ThemeMode。
// 依赖边界：不依赖业务 store 或后端接口。

import { computed, readonly, shallowRef } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'canopy-lab-theme'
const storedTheme =
  typeof window === 'undefined' ? null : (window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null)
const initialTheme: ThemeMode =
  storedTheme === 'light' || storedTheme === 'dark'
    ? storedTheme
    : typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark'

const theme = shallowRef<ThemeMode>(initialTheme)

/** 同步内存主题、HTML 属性与 localStorage。 */
function applyTheme(value: ThemeMode) {
  theme.value = value
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
  window.localStorage.setItem(STORAGE_KEY, value)
}

/** 暴露只读主题状态和切换命令。 */
export function useTheme() {
  const isDark = computed(() => theme.value === 'dark')

  /** 处理 toggleTheme 对应的组件交互或数据转换逻辑。 */
  function toggleTheme() {
    applyTheme(isDark.value ? 'light' : 'dark')
  }

  applyTheme(theme.value)

  return {
    theme: readonly(theme),
    isDark,
    setTheme: applyTheme,
    toggleTheme,
  }
}
