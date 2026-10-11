import { test } from 'node:test'
import assert from 'node:assert/strict'
import { PlanningGate, mergeSuggestions } from '../src/user/planning/current.ts'

test('an edit invalidates older reads and undo never accepts an old suggestion token', () => {
  const gate = new PlanningGate()
  gate.reset('journey')
  const read = gate.ticket()
  gate.invalidate()
  assert.equal(gate.accept(read, 1), false)
  assert.equal(gate.accept(gate.ticket(), 2), true)
  assert.equal(gate.accept(gate.ticket(), 1), false)
  const current = { suggestions: { token: 'undo-new', session_id: 'session' }, recommendations: [] }
  assert.equal(mergeSuggestions(current, { token: 'old', session_id: 'session', items: ['stale'] }), current)
})

test('switching sessions discards old responses and only merges current suggestions', () => {
  const gate = new PlanningGate()
  gate.reset('one')
  const read = gate.ticket()
  gate.reset('two')
  assert.equal(gate.accept(read, 100), false)
  const current = { suggestions: { token: 'current', session_id: 'two' }, recommendations: [] }
  assert.equal(mergeSuggestions(current, { token: 'current', session_id: 'one', items: ['stale'] }), current)
  const next = mergeSuggestions(current, { token: 'current', session_id: 'two', status: 'ready', items: ['valid'] })
  assert.deepEqual(next.recommendations, ['valid'])
})

test('fresh reads after a failed edit can resume without changing the suggestion token', () => {
  const gate = new PlanningGate()
  gate.reset('journey')
  const oldRead = gate.ticket()
  gate.invalidate()
  assert.equal(gate.accept(oldRead, 1), false)
  assert.equal(gate.accept(gate.ticket(), 1), true)
  const firstMutation = gate.ticket()
  gate.invalidate()
  assert.equal(gate.accept(firstMutation, 2, true), true)
  assert.equal(gate.accept(gate.ticket(), 3, true), true)
  assert.equal(gate.accept(firstMutation, 2, true), false)
})
