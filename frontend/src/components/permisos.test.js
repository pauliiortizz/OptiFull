// Pruebas de permisos por rol. Se corren con: npm test (Vitest).
import { expect, test } from 'vitest'
import { PAGINAS_POR_ROL, paginasPermitidas, puedeVer, paginaInicial, paginaPermitida } from './permisos.js'

const TODAS = ['dashboard', 'productos', 'ventas', 'reports', 'alerts', 'settings']

test('el administrador ve todas las secciones', () => {
  for (const p of TODAS) expect(puedeVer('administrador', p), p).toBe(true)
})

test('el empleado solo ve productos, ventas y alertas', () => {
  expect([...paginasPermitidas('usuario')].sort()).toEqual(['alerts', 'productos', 'ventas'])
  for (const p of ['dashboard', 'stock', 'reports', 'settings']) expect(puedeVer('usuario', p), p).toBe(false)
  for (const p of ['productos', 'ventas', 'alerts']) expect(puedeVer('usuario', p), p).toBe(true)
})

test('un rol desconocido, vacío o ausente no ve nada', () => {
  for (const rol of ['', null, undefined, 'admin', 'Administrador', 'superusuario']) {
    for (const p of TODAS) expect(puedeVer(rol, p), `${rol}/${p}`).toBe(false)
    expect(paginasPermitidas(rol)).toEqual([])
  }
})

test('una sección inexistente nunca está permitida', () => {
  expect(puedeVer('administrador', 'usuarios')).toBe(false)
  expect(puedeVer('administrador', undefined)).toBe(false)
})

test('cada rol arranca en una sección que sí puede ver', () => {
  for (const rol of Object.keys(PAGINAS_POR_ROL)) expect(puedeVer(rol, paginaInicial(rol)), rol).toBe(true)
  expect(paginaInicial('administrador')).toBe('dashboard')
  expect(paginaInicial('usuario')).toBe('productos')
})

test('paginaPermitida redirige a la inicial cuando la sección no está permitida', () => {
  expect(paginaPermitida('usuario', 'reports')).toBe('productos')
  expect(paginaPermitida('usuario', 'stock')).toBe('productos')
  expect(paginaPermitida('usuario', 'alerts')).toBe('alerts')
  expect(paginaPermitida('administrador', 'reports')).toBe('reports')
})

test('el empleado no hereda permisos del administrador (listas independientes)', () => {
  expect(PAGINAS_POR_ROL.usuario).not.toBe(PAGINAS_POR_ROL.administrador)
  expect(PAGINAS_POR_ROL.usuario.length).toBeLessThan(PAGINAS_POR_ROL.administrador.length)
})
