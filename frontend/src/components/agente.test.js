// Pruebas de components/agente.js: cuándo el panel usa el agente local de la compu de la caja.
import { expect, test } from 'vitest'
import { AGENTE, usaAgente } from './agente'

test('en la compu (localhost) el panel usa su propio backend, no el agente', () => {
  expect(window.location.hostname).toBe('localhost')
  expect(usaAgente()).toBe(false)
})

test('el agente atiende solo en esta compu', () => {
  expect(new URL(AGENTE).hostname).toBe('127.0.0.1')
})
