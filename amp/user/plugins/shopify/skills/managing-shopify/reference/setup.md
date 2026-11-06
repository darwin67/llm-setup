# Shopify connection setup

## Before authentication

1. Ask the user for the target `store-name.myshopify.com` hostname (not a secret). Confirm it is their intended store.
2. Confirm the store and the app belong to the SAME Shopify organization in the Dev Dashboard. Owning or having access to a store alone is not enough for client credentials.
3. Ask whether a dedicated app with exactly `read_products,read_inventory,read_orders` already exists and is installed. If not, guide the user through creating/releasing/installing one in the [Dev Dashboard](https://dev.shopify.com/dashboard/). Ask before doing any app installation or store configuration on their behalf. Do not add write scopes, `read_all_orders`, customer scopes, or reporting scopes.

### Creating a new app

In the Dev Dashboard, select the organization that owns the target store. Check its store list (Dev stores for development stores); if ownership is unclear or the store is absent, stop before installation and clarify. Do not create a replacement store, transfer ownership, or assume that the same login means the same organization.

1. Open **Apps → Create app → Start from Dev Dashboard**.
2. Name the app **Amp Store Assistant**. Leave the optional version name empty (or use `read-only-v1`). Some Dashboard versions show the configuration fields on this same Create app form; complete them there before selecting **Create app**. Otherwise open **Versions** and create a version after creating the app.
3. Set **App URL** to `https://shopify.dev/apps/default-app-home`. This integration is not embedded: uncheck **Embed app in Shopify admin**. Leave **Allowed redirection URLs** empty: this same-organization client-credentials integration has no authorization-code callback. Leave **Use legacy install flow** unchecked. If Shopify's form requires a redirect URL, stop and inspect the validation message rather than invent a callback URL.
4. Choose exactly `read_products,read_inventory,read_orders` as required Admin API scopes. Inventory levels query location IDs only; location names are deliberately omitted because they require additional access. Do not add `read_locations`, optional scopes, or write scopes. Leave unrelated features/webhooks unconfigured. If a webhooks API version is required, use the current stable `2026-10` version.
5. Select **Release**. Only after the target organization/store is confirmed, open the app's **Installs → Install app**, choose the exact target domain, review the requested permissions, and select **Install**. Stop if another store or any write permission appears.
6. Open **App settings** (or **Settings**) for **Client ID** and **Client secret**. Save them only through the private Amp secret-entry process below.

These steps follow [Shopify's Dev Dashboard app-creation guide](https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard). The store selection/install list alone does not prove client-credentials eligibility for a store in another organization.

New Dev Dashboard apps use an OAuth client ID and secret, not a permanently visible Admin API token. The plugin exchanges credentials server-side, keeps access tokens only in memory, and refreshes them before their 24-hour expiry. It refuses unexpected or missing scopes, even if Shopify granted them inadvertently.

If the store and app do not share an organization, STOP and explain that this implementation needs the appropriate Shopify authorization-code flow instead. Do not ask for a password or an arbitrary copied access token. Do not claim same-organization authentication supports other merchants' stores.

## Enter credentials privately

Store the following under PERSONAL Amp Secrets & Env Vars, not the workspace scope:

| Name | Kind | Value |
| --- | --- | --- |
| SHOPIFY_STORE_DOMAIN | Non-secret environment variable | Exact `store-name.myshopify.com` domain |
| SHOPIFY_CLIENT_ID | Secret | App Settings → Client ID |
| SHOPIFY_CLIENT_SECRET | Secret | App Settings → Client secret |

Use `manage_amp` secrets set with `scope: personal` and the name only, omitting the value so Amp opens its private masked input. If private input is unavailable, direct the user to [Personal Settings](https://ampcode.com/settings) → Secrets & Env Vars. Never request values in the conversation. Do not read, print, or inspect secret values. Existing unrelated secrets must not be changed.

After the user saves settings, refresh the orb environment with `amp orb restart-processes`, then reload the plugin if needed. Do not copy secrets into files. Personal secrets can be available to the user's other orb threads; use a dedicated least-privilege Shopify app and consider that trust boundary before saving them.

## Verify and publish

1. Call `shopify_connection` and verify the domain, store name, actual access scopes, currency, and store timezone. Never expose the token or client secret. If anything is wrong, stop.
2. Exercise a small product page, inventory item page + levels, and recent order page, then a short sales window. Follow cursors where appropriate. API access or protected-data restrictions may still need Shopify approval; do not silently broaden access.
3. Confirm the user approves publication to their personal plugin repository before pushing. A local commit is not a published or installed global plugin. New threads load published plugins; use `reload_plugins` for an existing executor thread. Puck does not execute plugins itself: Shopify calls run in an orb/runner/CLI thread, not directly in Puck.

Read-only access still exposes commercially sensitive order and inventory data. Share only what the user requested. To revoke access, uninstall/revoke the dedicated app in Shopify (with approval), and remove the corresponding personal Amp secrets only with explicit deletion approval.

## Sources

- [Amp plugins](https://ampcode.com/docs/plugin-api)
- [Amp skills](https://ampcode.com/docs/customize/skills)
- [Shopify client credentials and same-organization restriction](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant)
- [Shopify order fields and history restrictions](https://shopify.dev/docs/api/admin-graphql/2026-10/objects/Order)
- [ShopifyQL reporting requirements (not requested by this plugin)](https://shopify.dev/docs/api/admin-graphql/2026-10/queries/shopifyqlQuery)
