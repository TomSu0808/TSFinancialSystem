import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'

globalThis.localStorage = { getItem: () => null, removeItem: () => {} }
globalThis.window = new EventTarget()
let requests = []
let failSave = false
let failRefresh = false
let partialFailure = false
axios.defaults.adapter = async (config) => {
  requests.push(config.url)
  if (config.url === '/holdings/refresh-prices') {
    if (failRefresh) throw new Error('quote service unavailable')
    return { data: { updated: 1, total: 2, results: [{ status: 'ok' }, { status: partialFailure ? 'error' : 'skipped' }] }, config }
  }
  if (failSave) throw new Error('invalid transaction')
  return { data: { id: 123 }, config }
}
const api = await import('../src/api/index.js')

test.beforeEach(() => {
  requests = []
  failSave = failRefresh = partialFailure = false
})

for (const [name, save, path] of [
  ['create', () => api.createTransaction({ action: 'sell' }), '/transactions'],
  ['update', () => api.updateTransaction(123, { price: 10 }), '/transactions/123'],
  ['delete', () => api.deleteTransaction(123), '/transactions/123'],
  ['CSV import', () => api.commitTransactionImport(new Blob(['csv'])), '/transactions/import/commit'],
  ['broker import', () => api.commitImport(5, {}), '/imports/5/commit'],
]) {
  test(`${name} refreshes quotes before resolving to the page`, async () => {
    assert.deepEqual(await save(), { id: 123 })
    assert.deepEqual(requests, [path, '/holdings/refresh-prices'])
  })
}

test('a failed save never triggers a refresh', async () => {
  failSave = true
  await assert.rejects(api.createTransaction({}), /invalid transaction/)
  assert.deepEqual(requests, ['/transactions'])
})

for (const kind of ['network', 'partial']) {
  test(`${kind} quote failure still returns saved transaction and notifies the UI`, async () => {
    failRefresh = kind === 'network'
    partialFailure = kind === 'partial'
    let warned = 0
    const onWarning = () => warned++
    window.addEventListener('quotes:refresh-failed', onWarning)
    try {
      assert.deepEqual(await api.updateTransaction(123, {}), { id: 123 })
      assert.equal(warned, 1)
    } finally {
      window.removeEventListener('quotes:refresh-failed', onWarning)
    }
  })
}
