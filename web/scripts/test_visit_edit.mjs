import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
const output = mkdtempSync(join(tmpdir(), 'tg-visit-edit-'))
after(() => rmSync(output, { recursive: true, force: true }))
try {
  execFileSync(process.execPath, [
    fileURLToPath(new URL('../node_modules/typescript/bin/tsc', import.meta.url)),
    fileURLToPath(new URL('../src/user/planning/visitEdit.ts', import.meta.url)),
    '--ignoreConfig', '--outDir', output, '--module', 'esnext', '--target', 'es2022', '--skipLibCheck',
  ], { stdio: 'pipe' })
} catch (error) {
  rmSync(output, { recursive: true, force: true })
  throw error
}
const source = readFileSync(join(output, 'visitEdit.js'), 'utf8')
const v = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
test('visit edit preserves midnight and sends integer duration', () => {
  assert.deepEqual(v.visitAction('a', '00:00', '45'), { type: 'set_visit', place: 'a', start: '00:00', duration_min: 45 })
})
test('blank fields restore automatic values individually', () => {
  assert.deepEqual(v.visitAction('a', '', '60'), { type: 'set_visit', place: 'a', start: null, duration_min: 60 })
  assert.deepEqual(v.visitAction('a', '09:15', ''), { type: 'set_visit', place: 'a', start: '09:15', duration_min: null })
})
test('invalid clock or duration cannot create an act', () => {
  for (const start of ['24:00', '9:00', '12:60']) assert.equal(v.visitAction('a', start, '30'), null)
  for (const duration of ['0', '1441', '1.5', 'NaN', '1e2', '-4']) assert.equal(v.visitAction('a', '10:00', duration), null)
  assert.equal(v.visitAction('a', '23:59', '1440').duration_min, 1440)
})
test('restore automatic time or duration leaves the other override untouched', () => {
  assert.deepEqual(v.automaticVisitAction('a', 'start'), { type: 'set_visit', place: 'a', start: null })
  assert.deepEqual(v.automaticVisitAction('a', 'duration_min'), { type: 'set_visit', place: 'a', duration_min: null })
})
test('visit actions convert displayed days to backend indexes', () => {
  assert.deepEqual(v.moveVisitAction('a', 2), { type: 'move_place', place: 'a', day: 1 })
  assert.deepEqual(v.reorderVisitAction(1, ['b', 'a']), { type: 'reorder', day: 0, order: ['b', 'a'] })
})
