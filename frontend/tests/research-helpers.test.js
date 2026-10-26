import test from 'node:test'
import assert from 'node:assert/strict'
import {
  TASK_ENTRIES,
  evidenceLabel,
  isActiveStatus,
  parseStructuredReport,
  parseSourceStatus,
  sourceList,
  mergeSources,
  versionLabel,
  dataAsOf,
} from '../src/research.js'

test('four research task entries map to existing templates', () => {
  assert.deepEqual(TASK_ENTRIES.map((t) => t.key), ['company', 'earnings', 'holdings', 'thesis'])
  for (const task of TASK_ENTRIES) {
    assert.ok(task.template)
    assert.ok(task.tools)
  }
})

test('report structured JSON degrades safely', () => {
  assert.equal(parseStructuredReport({ report_json: 'not-json' }), null)
  assert.equal(parseStructuredReport({ report_json: null }), null)
  const parsed = parseStructuredReport({
    report_json: JSON.stringify({ degraded: false, summary: 'ok', key_facts: [] }),
  })
  assert.equal(parsed.summary, 'ok')
})

test('source list merges provider and model sources without duplicates', () => {
  const report = {
    sources_json: JSON.stringify([{ url: 'https://a.example', title: 'A' }]),
  }
  const structured = {
    sources: [
      { url: 'https://a.example', title: 'A duplicate' },
      { url: 'https://b.example', title: 'B' },
    ],
  }
  const sources = sourceList(report, structured)
  assert.equal(sources.length, 2)
  assert.deepEqual(sources.map((s) => s.url), ['https://a.example', 'https://b.example'])
})

test('evidence labels distinguish facts, analysis and assumptions', () => {
  assert.equal(evidenceLabel('fact', false).text, '有来源事实')
  assert.equal(evidenceLabel('fact', true).color, 'orange')
  assert.equal(evidenceLabel('analysis', false).text, '分析判断')
  assert.equal(evidenceLabel('assumption', false).text, '待验证假设')
})

test('active statuses and version labels', () => {
  assert.equal(isActiveStatus('running'), true)
  assert.equal(isActiveStatus('queued'), true)
  assert.equal(isActiveStatus('completed'), false)
  assert.equal(versionLabel({ version: 2 }), 'v2')
  assert.equal(versionLabel({}), 'v1')
})

test('data as of prefers explicit report cutoff', () => {
  assert.equal(dataAsOf({ data_cutoff: '2026-10-26' }), '2026-10-26')
  assert.equal(dataAsOf({
    input_snapshot_json: JSON.stringify({ data_cutoff: '2026-10-25' }),
  }), '2026-10-25')
})

test('source status parses and unknown returns null', () => {
  assert.equal(parseSourceStatus({ source_status_json: 'x' }), null)
  assert.equal(parseSourceStatus({
    source_status_json: JSON.stringify({ status: 'no_sources_returned' }),
  }).status, 'no_sources_returned')
})

test('mergeSources keeps only new sources', () => {
  const merged = mergeSources(
    [{ url: 'https://a.example' }],
    [{ url: 'https://a.example' }, { url: 'https://b.example' }],
  )
  assert.equal(merged.length, 2)
})
