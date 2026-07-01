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

function applyTheme(value: ThemeMode) {
  theme.value = value
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
  window.localStorage.setItem(STORAGE_KEY, value)
}

export function useTheme() {
  const isDark = computed(() => theme.value === 'dark')

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
