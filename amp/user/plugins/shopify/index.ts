import type { PluginAPI, PluginToolContext } from '@ampcode/plugin'

export const description = 'Read-only Shopify products, inventory, orders, and order-based sales snapshots. Uses personal environment secrets; never exposes mutations.'

const SCOPES = ['read_products', 'read_inventory', 'read_orders']
const VERSION = '2026-10'
const PAGE_INFO = 'pageInfo { hasNextPage endCursor }'
const ORDER_FIELDS = `id name createdAt cancelledAt test displayFinancialStatus displayFulfillmentStatus
  currentTotalPriceSet { shopMoney { amount currencyCode } }`
const QUERIES = {
  products: `query Products($first: Int!, $after: String, $search: String) {
    products(first: $first, after: $after, query: $search) {
      nodes { id title handle status totalInventory updatedAt } ${PAGE_INFO}
    }
  }`,
  inventory: `query Inventory($first: Int!, $after: String, $search: String) {
    inventoryItems(first: $first, after: $after, query: $search) {
      nodes { id sku tracked updatedAt } ${PAGE_INFO}
    }
  }`,
  levels: `query Levels($id: ID!, $first: Int!, $after: String) {
    inventoryItem(id: $id) { id sku tracked inventoryLevels(first: $first, after: $after) {
      nodes { id location { id } quantities(names: ["available", "on_hand", "committed"]) { name quantity } }
      ${PAGE_INFO}
    } }
  }`,
  orders: `query Orders($first: Int!, $after: String, $search: String) {
    orders(first: $first, after: $after, query: $search, sortKey: CREATED_AT, reverse: true) {
      nodes { ${ORDER_FIELDS} } ${PAGE_INFO}
    }
  }`,
  connection: `query Connection { shop { name myshopifyDomain currencyCode ianaTimezone }
    currentAppInstallation { accessScopes { handle } }
  }`,
}

export default async function (amp: PluginAPI) {
  let cached: { key: string; token: string; expiresAt: number } | undefined

  async function request(url: string, options: RequestInit, signal: AbortSignal) {
    try {
      return await fetch(url, { ...options, redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]) })
    } catch {
      throw new Error('Shopify request interrupted or unavailable. No store changes were attempted.')
    }
  }

  function checkScopes(scopes: string[]) {
    if (scopes.some(scope => !SCOPES.includes(scope))) {
      throw new Error(`Refusing credentials with permissions outside the approved read-only set: ${SCOPES.join(', ')}. Use a dedicated read-only app.`)
    }
    const missing = SCOPES.filter(scope => !scopes.includes(scope))
    if (missing.length) throw new Error(`Shopify app is missing required read scopes: ${missing.join(', ')}.`)
  }

  async function graphql(query: string, variables: Record<string, unknown>, ctx: PluginToolContext) {
    const domain = process.env.SHOPIFY_STORE_DOMAIN?.trim().toLowerCase()
    const clientID = process.env.SHOPIFY_CLIENT_ID
    const secret = process.env.SHOPIFY_CLIENT_SECRET
    if (!domain || !clientID || !secret) {
      throw new Error('Setup required: set personal SHOPIFY_STORE_DOMAIN and store SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET through Amp Secrets & Env Vars. Never paste credentials into chat.')
    }
    if (!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(domain)) {
      throw new Error('SHOPIFY_STORE_DOMAIN must be the exact store-name.myshopify.com hostname, without a URL or path.')
    }
    const key = JSON.stringify([domain, clientID, secret])
    if (!cached || cached.key !== key || Date.now() >= cached.expiresAt) {
      const response = await request(`https://${domain}/admin/oauth/access_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ grant_type: 'client_credentials', client_id: clientID, client_secret: secret }),
      }, ctx.signal)
      if (!response.ok) throw new Error(`Shopify authentication failed (HTTP ${response.status}). Verify app installation and same-organization eligibility in the Dev Dashboard.`)
      const result = await response.json()
      checkScopes(typeof result.scope === 'string' ? result.scope.split(',').map((scope: string) => scope.trim()).filter(Boolean) : [])
      if (typeof result.access_token !== 'string' || !Number.isFinite(result.expires_in) || result.expires_in <= 60) {
        throw new Error('Shopify returned an invalid token response.')
      }
      cached = { key, token: result.access_token, expiresAt: Date.now() + (result.expires_in - 60) * 1000 }
    }
    const response = await request(`https://${domain}/admin/api/${VERSION}/graphql.json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Shopify-Access-Token': cached.token },
      body: JSON.stringify({ query, variables }),
    }, ctx.signal)
    if (response.status === 401) cached = undefined
    if (!response.ok) throw new Error(`Shopify read failed (HTTP ${response.status}). Check app access or retry later if rate-limited.`)
    const result = await response.json()
    if (result.errors?.length || !result.data) throw new Error('Shopify rejected the read query. Check API permissions, protected order-data eligibility, search syntax, or rate limits. No partial result was returned.')
    return result.data
  }

  function register(name: string, description: string, properties: Record<string, object>, required: string[], execute: (input: Record<string, unknown>, ctx: PluginToolContext) => Promise<unknown>) {
    amp.registerTool({
      name, description,
      inputSchema: { type: 'object', properties, required, additionalProperties: false },
      async execute(input, ctx) { return JSON.stringify(await execute(input, ctx)) },
    })
  }

  register('shopify_connection', 'Check the configured Shopify store identity and approved read-only scopes. Never returns credentials.', {}, [], async (_, ctx) => {
    const data = await graphql(QUERIES.connection, {}, ctx)
    checkScopes(data.currentAppInstallation.accessScopes.map((scope: { handle: string }) => scope.handle))
    return { ...data, readOnly: true, apiVersion: VERSION, orderHistory: 'Last 60 days only' }
  })

  const pagination = {
    first: { type: 'integer', minimum: 1, maximum: 50, description: 'Page size (default 20, max 50).' },
    after: { type: 'string', description: 'endCursor from the previous page. Keep the same search filter.' },
    search: { type: 'string', description: 'Shopify search filter, not GraphQL. For example sku:ABC or status:active.' },
  }
  function page(input: Record<string, unknown>) {
    const first = input.first ?? 20
    if (!Number.isInteger(first) || Number(first) < 1 || Number(first) > 50) throw new Error('first must be an integer from 1 to 50.')
    if (input.after !== undefined && typeof input.after !== 'string') throw new Error('after must be a cursor string.')
    if (input.search !== undefined && typeof input.search !== 'string') throw new Error('search must be a string.')
    return { first, after: input.after ?? null, search: input.search ?? null }
  }
  register('shopify_products', 'List/search products with status and total inventory. Follow pageInfo for more results.', pagination, [], async (input, ctx) => (await graphql(QUERIES.products, page(input), ctx)).products)
  register('shopify_inventory', 'List/search inventory item IDs, SKUs and tracking status. Use shopify_inventory_levels for quantities by location.', pagination, [], async (input, ctx) => (await graphql(QUERIES.inventory, page(input), ctx)).inventoryItems)
  register('shopify_inventory_levels', 'Read available, on-hand and committed quantities per location ID for an inventory item. Location names are intentionally omitted to keep read_inventory access. Follow pageInfo for all locations.', {
    id: { type: 'string', description: 'InventoryItem GraphQL ID from shopify_inventory.' }, first: pagination.first, after: pagination.after,
  }, ['id'], async (input, ctx) => {
    if (typeof input.id !== 'string' || !/^gid:\/\/shopify\/InventoryItem\/\d+$/.test(input.id)) throw new Error('Expected an InventoryItem GraphQL ID.')
    return (await graphql(QUERIES.levels, { ...page(input), id: input.id }, ctx)).inventoryItem
  })
  register('shopify_orders', 'List/search orders from the last 60 days with totals and payment/fulfillment status. Excludes customer names, addresses, emails and phone numbers. Follow pageInfo for all matches.', pagination, [], async (input, ctx) => ({
    ...(await graphql(QUERIES.orders, page(input), ctx)).orders, orderHistory: 'Last 60 days only; older date filters cannot produce complete history.',
  }))

  register('shopify_sales_summary', 'Order-based sales snapshot, NOT Shopify Analytics or period revenue. Sums current order totals for non-test, non-cancelled orders CREATED in a date window within the past 59 days. Includes unpaid orders, taxes and shipping; returns after the window affect current totals. Refuses incomplete results over 5000 orders.', {
    start: { type: 'string', description: 'Inclusive ISO 8601 timestamp with explicit timezone, e.g. 2026-11-01T00:00:00-07:00.' },
    end: { type: 'string', description: 'Exclusive ISO 8601 timestamp with explicit timezone. Use correct America/Los_Angeles DST offsets if requested.' },
  }, ['start', 'end'], async (input, ctx) => {
    const parseDate = (value: unknown) => {
      if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('Dates must be ISO 8601 timestamps with an explicit timezone.')
      if (new Date(value.slice(0, 10)).toISOString().slice(0, 10) !== value.slice(0, 10)) throw new Error('Dates must use valid calendar days.')
      return new Date(value)
    }
    const start = parseDate(input.start)
    const end = parseDate(input.end)
    if (start >= end || end.getTime() > Date.now() || start.getTime() < Date.now() - 59 * 86400_000) throw new Error('Use a non-empty window within the past 59 days, ending no later than now.')
    const search = `created_at:>='${start.toISOString()}' created_at:<'${end.toISOString()}'`
    let after: string | null = null
    let scanned = 0
    let included = 0
    const totals = new Map<string, { units: bigint; scale: number; orders: number }>()
    while (true) {
      const { orders } = await graphql(QUERIES.orders, { first: 50, after, search }, ctx)
      for (const order of orders.nodes) {
        scanned++
        if (order.test || order.cancelledAt) continue
        included++
        const { amount, currencyCode } = order.currentTotalPriceSet.shopMoney
        if (!/^\d+(?:\.\d+)?$/.test(amount)) throw new Error('Unexpected order money value; no summary returned.')
        const [whole, fraction = ''] = amount.split('.')
        const previous = totals.get(currencyCode) ?? { units: 0n, scale: 0, orders: 0 }
        const scale = Math.max(previous.scale, fraction.length)
        const units = BigInt(whole + fraction) * 10n ** BigInt(scale - fraction.length)
        totals.set(currencyCode, { units: previous.units * 10n ** BigInt(scale - previous.scale) + units, scale, orders: previous.orders + 1 })
      }
      if (!orders.pageInfo.hasNextPage) break
      if (scanned >= 5000) throw new Error('More than 5000 matching orders. Narrow the window; no incomplete summary was returned.')
      const cursor = orders.pageInfo.endCursor
      if (!cursor || cursor === after) throw new Error('Shopify pagination did not advance; no incomplete summary was returned.')
      after = cursor
    }
    return {
      start: start.toISOString(), endExclusive: end.toISOString(), scanned, included,
      totals: Array.from(totals, ([currency, value]) => {
        const digits = value.units.toString().padStart(value.scale + 1, '0')
        return { currency, orders: value.orders, currentOrderTotal: value.scale ? `${digits.slice(0, -value.scale)}.${digits.slice(-value.scale)}` : digits }
      }),
      complete: true,
      definition: 'Sum of currentTotalPriceSet.shopMoney for non-test, non-cancelled orders created in [start,end). Includes unpaid orders, tax and shipping. Not period cash receipts, net sales, or Shopify Analytics; later order adjustments affect this snapshot. Currencies are never combined.',
    }
  })

  await amp.registerSkill({ path: 'skills/managing-shopify' })
}
