// Pruebas de permisos por rol. Se corren con: npm test  (usa el test runner de Node, sin dependencias).
import test from 'node:test'
import assert from 'node:assert/strict'
import { PAGINAS_POR_ROL, paginasPermitidas, puedeVer, paginaInicial, paginaPermitida } from './permisos.js'

const TODAS = ['dashboard', 'stock', 'reports', 'alerts', 'settings']

test('el administrador ve todas las secciones', () => {
  for (const p of TODAS) assert.equal(puedeVer('administrador', p), true, p)
})

test('el empleado solo ve stock y alertas', () => {
  assert.deepEqual([...paginasPermitidas('usuario')].sort(), ['alerts', 'stock'])
  for (const p of ['dashboard', 'reports', 'settings']) assert.equal(puedeVer('usuario', p), false, p)
  for (const p of ['stock', 'alerts']) assert.equal(puedeVer('usuario', p), true, p)
})

test('un rol desconocido, vacío o ausente no ve nada', () => {
  for (const rol of ['', null, undefined, 'admin', 'Administrador', 'superusuario']) {
    for (const p of TODAS) assert.equal(puedeVer(rol, p), false, `${rol}/${p}`)
    assert.deepEqual(paginasPermitidas(rol), [])
  }
})

test('una sección inexistente nunca está permitida', () => {
  assert.equal(puedeVer('administrador', 'usuarios'), false)
  assert.equal(puedeVer('administrador', undefined), false)
})

test('cada rol arranca en una sección que sí puede ver', () => {
  for (const rol of Object.keys(PAGINAS_POR_ROL)) assert.equal(puedeVer(rol, paginaInicial(rol)), true, rol)
  assert.equal(paginaInicial('administrador'), 'dashboard')
  assert.equal(paginaInicial('usuario'), 'stock')
})

test('paginaPermitida redirige a la inicial cuando la sección no está permitida', () => {
  assert.equal(paginaPermitida('usuario', 'reports'), 'stock')
  assert.equal(paginaPermitida('usuario', 'settings'), 'stock')
  assert.equal(paginaPermitida('usuario', 'alerts'), 'alerts')
  assert.equal(paginaPermitida('administrador', 'reports'), 'reports')
})

test('el empleado no hereda permisos del administrador (listas independientes)', () => {
  assert.notEqual(PAGINAS_POR_ROL.usuario, PAGINAS_POR_ROL.administrador)
  assert.ok(PAGINAS_POR_ROL.usuario.length < PAGINAS_POR_ROL.administrador.length)
})
