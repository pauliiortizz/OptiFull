// Se carga antes de cada archivo de test (ver vitest.config.js).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  try { window.localStorage.clear(); window.sessionStorage.clear() } catch { /* sin almacenamiento */ }
})

// jsdom no trae estas APIs del navegador; los componentes las usan (tema, animaciones, graficos).
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })
}
if (!window.ResizeObserver) {
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
if (!window.IntersectionObserver) {
  window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} takeRecords() { return [] } }
}
if (!window.HTMLElement.prototype.scrollIntoView) window.HTMLElement.prototype.scrollIntoView = () => {}
if (!window.URL.createObjectURL) window.URL.createObjectURL = () => 'blob:prueba'
if (!window.URL.revokeObjectURL) window.URL.revokeObjectURL = () => {}
