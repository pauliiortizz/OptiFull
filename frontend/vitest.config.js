// Tests del frontend: Vitest + Testing Library sobre jsdom (sin navegador). Reusa la config de Vite (alias '@',
// plugin de React) y agrega lo propio de los tests. La cobertura sale en coverage/lcov.info para SonarQube Cloud.
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/**/*.test.{js,jsx}', 'src/test/**'],
      reporter: ['text-summary', 'text', 'lcov'],
      reportsDirectory: 'coverage',
    },
  },
}))
