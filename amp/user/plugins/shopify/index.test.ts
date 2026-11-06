import { afterEach, beforeEach, expect, setSystemTime, spyOn, test } from 'bun:test'
import type { PluginAPI, PluginToolContext, PluginToolDefinition } from '@ampcode/plugin'
import plugin from './index'

const scopes = 'read_products,read_inventory,read_orders'
const names = ['SHOPIFY_STORE_DOMAIN', 'SHOPIFY_CLIENT_ID', 'SHOPIFY_CLIENT_SECRET']
const original = Object.fromEntries(names.map(name => [name, process.env[name]]))
const ctx = { signal: new AbortController().signal } as PluginToolContext
const window = { start: '2026-11-01T00:00:00-07:00', end: '2026-11-02T00:00:00-08:00' }
const endPage = { hasNextPage: false, endCursor: null }

beforeEach(() => {
  setSystemTime(new Date('2026-11-04T12:00:00Z'))
  process.env.SHOPIFY_STORE_DOMAIN = 'plugin-test.myshopify.com'
  process.env.SHOPIFY_CLIENT_ID = 'fixture-client'
  process.env.SHOPIFY_CLIENT_SECRET = 'fixture-secret'
})
afterEach(() => {
  setSystemTime()
  for (const name of names) {
    if (original[name] === undefined) delete process.env[name]
    else process.env[name] = original[name]
  }
  fetchSpy?.mockRestore()
})

let fetchSpy: ReturnType<typeof spyOn> | undefined
async function tools(handler: (body: any) => unknown, scope = scopes) {
  const registered = new Map<string, PluginToolDefinition>()
  fetchSpy = spyOn(globalThis, 'fetch').mockImplementation(async (url, options) => {
    expect(String(url)).toStartWith('https://plugin-test.myshopify.com/admin/')
    expect(options?.redirect).toBe('error')
    if (String(url).endsWith('/oauth/access_token')) {
      return Response.json({ access_token: 'fixture-token', expires_in: 86399, scope })
    }
    const body = JSON.parse(String(options?.body))
    // Arbitrary user text must never become an executable operation or selection.
    expect(body.query.trim()).toStartWith('query ')
    expect(body.query).not.toMatch(/\bmutation\b|\bemail\b|\bshippingAddress\b|\bcustomer\s*\{/)
    return Response.json(handler(body))
  })
  await plugin({
    registerTool(tool: PluginToolDefinition) { registered.set(tool.name, tool) },
    async registerSkill({ path }: { path: string }) {
      const skill = await Bun.file(`${import.meta.dir}/${path}/SKILL.md`).text()
      expect(skill).toContain('name: managing-shopify')
      expect(await Bun.file(`${import.meta.dir}/${path}/reference/setup.md`).exists()).toBe(true)
    },
  } as unknown as PluginAPI)
  return async (name: string, input = {}) => JSON.parse(String(await registered.get(name)!.execute(input, ctx)))
}

function order(amount: string, currencyCode = 'USD', extra = {}) {
  return { test: false, cancelledAt: null, currentTotalPriceSet: { shopMoney: { amount, currencyCode } }, ...extra }
}

test('all read tools return store identity, list cursors, and per-location quantities without credentials', async () => {
  const productPage = { nodes: [{ id: 'product1', title: 'Tea', totalInventory: 17 }], pageInfo: { hasNextPage: true, endCursor: 'next-product' } }
  const inventoryPage = { nodes: [{ id: 'gid://shopify/InventoryItem/9', sku: 'TEA', tracked: true }], pageInfo: endPage }
  const levels = { id: 'gid://shopify/InventoryItem/9', inventoryLevels: { nodes: [{ location: { id: 'gid://shopify/Location/3' }, quantities: [{ name: 'available', quantity: 17 }, { name: 'committed', quantity: 4 }] }], pageInfo: endPage } }
  const call = await tools(({ query, variables }) => {
    if (query.includes('query Connection')) return { data: { shop: { myshopifyDomain: 'plugin-test.myshopify.com', name: 'Fixture store' }, currentAppInstallation: { accessScopes: scopes.split(',').map(handle => ({ handle })) } } }
    if (query.includes('query Products')) {
      expect(variables).toEqual({ first: 7, after: 'previous', search: 'title:"mutation { bad }"' })
      return { data: { products: productPage } }
    }
    if (query.includes('query Inventory')) return { data: { inventoryItems: inventoryPage } }
    if (query.includes('query Levels')) {
      // Model Shopify's field-level restriction with only read_inventory granted.
      if (/location\s*\{[^}]*\bname\b/.test(query)) return { errors: [{ message: 'Location.name requires read_locations' }] }
      return { data: { inventoryItem: levels } }
    }
    return { data: { orders: { nodes: [order('12.34')], pageInfo: endPage } } }
  })
  const connection = await call('shopify_connection')
  expect(connection.readOnly).toBe(true)
  expect(connection.shop.myshopifyDomain).toBe('plugin-test.myshopify.com')
  expect(JSON.stringify(connection)).not.toMatch(/fixture-token|fixture-secret/)
  expect(await call('shopify_products', { first: 7, after: 'previous', search: 'title:"mutation { bad }"' })).toEqual(productPage)
  expect(await call('shopify_inventory')).toEqual(inventoryPage)
  expect(await call('shopify_inventory_levels', { id: 'gid://shopify/InventoryItem/9' })).toEqual(levels)
  expect((await call('shopify_orders')).nodes).toEqual([order('12.34')])
})

test('rejects write, unrelated read, and missing scopes before returning any store data', async () => {
  for (const scope of [`${scopes},write_orders`, `${scopes},read_customers`, 'read_products']) {
    const call = await tools(() => { throw new Error('Must not query store data') }, scope)
    await expect(call('shopify_products')).rejects.toThrow(/approved read-only set|missing required read scopes/)
    fetchSpy!.mockRestore()
  }
})

test('sales summary follows pages, excludes canceled/test orders, preserves decimals and currencies, and handles LA DST', async () => {
  const call = await tools(({ variables }) => {
    expect(variables.search).toBe("created_at:>='2026-11-01T07:00:00.000Z' created_at:<'2026-11-02T08:00:00.000Z'")
    return { data: { orders: variables.after === null
      ? { nodes: [order('100.1'), order('999', 'USD', { test: true }), order('10.005', 'KWD')], pageInfo: { hasNextPage: true, endCursor: 'page2' } }
      : { nodes: [order('0.02'), order('70', 'USD', { cancelledAt: '2026-11-01T10:00:00Z' }), order('0.005', 'KWD'), order('30', 'JPY')], pageInfo: endPage },
    } }
  })
  expect(await call('shopify_sales_summary', window)).toMatchObject({
    start: '2026-11-01T07:00:00.000Z', endExclusive: '2026-11-02T08:00:00.000Z', scanned: 7, included: 5, complete: true,
    totals: [
      { currency: 'USD', orders: 2, currentOrderTotal: '100.12' },
      { currency: 'KWD', orders: 2, currentOrderTotal: '10.010' },
      { currency: 'JPY', orders: 1, currentOrderTotal: '30' },
    ],
  })
})

test('empty sales windows return no included orders, not fabricated money', async () => {
  const call = await tools(() => ({ data: { orders: { nodes: [], pageInfo: endPage } } }))
  expect(await call('shopify_sales_summary', window)).toMatchObject({ scanned: 0, included: 0, totals: [], complete: true })
})

test('fails closed on GraphQL partial errors and does not expose upstream secrets', async () => {
  const call = await tools(() => ({ data: { products: { nodes: [] } }, errors: [{ message: 'fixture-secret fixture-token' }] }))
  await expect(call('shopify_products')).rejects.toThrow('No partial result was returned')
  try { await call('shopify_products') } catch (error) { expect(String(error)).not.toMatch(/fixture-secret|fixture-token/) }
})

test('fails rather than report incomplete sales when pagination stalls or exceeds 5000 orders', async () => {
  let call = await tools(() => ({ data: { orders: { nodes: [order('0.01')], pageInfo: { hasNextPage: true, endCursor: 'stuck' } } } }))
  await expect(call('shopify_sales_summary', window)).rejects.toThrow('pagination did not advance')
  fetchSpy!.mockRestore()
  let page = 0
  call = await tools(() => ({ data: { orders: { nodes: Array.from({ length: 50 }, () => order('0.01')), pageInfo: { hasNextPage: true, endCursor: `page${++page}` } } } }))
  await expect(call('shopify_sales_summary', window)).rejects.toThrow('More than 5000 matching orders')
})

test('rejects missing secrets, hostile domains, invalid page sizes, and ambiguous or out-of-history dates', async () => {
  const call = await tools(() => { throw new Error('Must not query store data') })
  delete process.env.SHOPIFY_CLIENT_SECRET
  await expect(call('shopify_connection')).rejects.toThrow('Setup required')
  process.env.SHOPIFY_CLIENT_SECRET = 'fixture-secret'
  process.env.SHOPIFY_STORE_DOMAIN = 'plugin-test.myshopify.com.attacker.example'
  await expect(call('shopify_connection')).rejects.toThrow('exact store-name.myshopify.com')
  process.env.SHOPIFY_STORE_DOMAIN = 'plugin-test.myshopify.com'
  await expect(call('shopify_products', { first: 51 })).rejects.toThrow('1 to 50')
  for (const start of ['2026-11-01', '2026-09-01T00:00:00Z', '2026-11-03T00:00:00Z', '2026-02-30T00:00:00Z']) {
    await expect(call('shopify_sales_summary', { ...window, start })).rejects.toThrow()
  }
})
