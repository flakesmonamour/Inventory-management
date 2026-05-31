# Odoo 15 Integration Guide

This guide follows the official Odoo 15 external API documentation.

For Odoo 15, the relevant external API flow is XML-RPC, not JSON-2.

Important: the live instance tested for this project at `https://wabkkencmptrs.odoo.com` reports server version `saas~19.3+e`. XML-RPC still works on that server, but some model names and public methods differ from older examples.

The correct integration path for this repository is:

1. connect to Odoo 15 over XML-RPC,
2. export operational inventory data,
3. stage that data locally,
4. transform it into the feature shape expected by the forecasting pipeline,
5. run forecasting,
6. optionally publish forecast outputs to MySQL for the dashboard.

## Why Odoo is different from MySQL in this repo

The dashboard currently expects forecast outputs, not raw ERP transactions.

The main dashboard dataset is shaped like this:

- `Date`
- `Store ID`
- `Product ID`
- `Actual`
- `LSTM_Predicted`
- `SVR_Predicted`
- `Inventory_Level`
- `Reorder_Alert`
- `Expiry_Risk`

Odoo does not expose data in that format directly.

Instead, Odoo exposes operational records such as:

- products,
- stock on hand,
- stock movements,
- lots and expiration metadata,
- warehouse locations.

That means Odoo is the source system, not the final dashboard dataset.

## Prerequisites

Before trying to connect Odoo, confirm these points:

1. your Odoo deployment supports the external API,
2. you have a user account with inventory access,
3. you know the user's login name,
4. you know the Odoo base URL,
5. you know the database name,
6. you have either a password or an API key for that user.

According to Odoo 15's external API documentation, the connection uses these XML-RPC endpoints:

- `{base_url}/xmlrpc/2/common`
- `{base_url}/xmlrpc/2/object`

The first endpoint is used to:

- get the server version,
- authenticate and receive the `uid`.

The second endpoint is used to call model methods through `execute_kw`.

## Exact details you need to collect from Odoo 15

### 1. Server URL

This is the instance domain.

Example:

- `https://mycompany.odoo.com`

The docs state that for Odoo Online instances, the server URL is the instance domain.

### 2. Database name

For Odoo Online instances, the docs describe the database name as the instance name.

Example:

- server URL: `https://mycompany.odoo.com`
- database name: `mycompany`

If you are on a self-hosted or custom deployment, ask the Odoo administrator for the exact database name.

### 3. Username

Use the user's login, not just the display name.

The Odoo 15 docs specifically say the username is the configured user's login as shown by the Change Password screen.

### 4. Password or API key

Odoo 15 supports API keys.

The official docs say you can use an API key by replacing the password with the key in your script, while keeping the login the same.

If you are on Odoo Online and the user does not have a local password yet, the docs say to set one first:

1. log in with an administrator account,
2. go to `Settings -> Users & Companies -> Users`,
3. open the user,
4. click `Action`,
5. choose `Change Password`,
6. set a new password.

If you prefer an API key instead:

1. log in as the target user,
2. open `Preferences` or `My Profile`,
3. open `Account Security`,
4. click `New API Key`,
5. enter a clear description,
6. click `Generate Key`,
7. copy the key immediately.

## What was added to this repository

This repository now includes a helper export script:

- `store/odoo_export.py`

This repository also now includes a local-source seed importer:

- `store/import_local_to_odoo.py`

It now follows the Odoo XML-RPC flow and exports these CSV files:

- `products.csv`
- `stock_quants.csv`
- `stock_moves.csv`
- `lots.csv`

By default, those files are written to:

- `store/raw/odoo/`

The importer reads the latest snapshot from:

- `store/raw/retail_store_inventory.csv`

and seeds:

- `product.template` / `product.product`
- `stock.location` child locations for `Store ID` values when requested
- `stock.quant` opening stock through Odoo inventory adjustments

Important: this importer seeds opening stock only. It does not recreate historical stock moves from the local CSV.

## Exact connection steps for Odoo 15

## Step 1: Get the connection values

Collect these exact values:

1. `ODOO_BASE_URL`: the instance domain
2. `ODOO_DATABASE`: the database name
3. `ODOO_USERNAME`: the user's login
4. `ODOO_PASSWORD` or `ODOO_API_KEY`: one credential to authenticate

## Step 2: Set environment variables

In PowerShell, from the project root:

```powershell
$env:ODOO_BASE_URL = "https://your-company.odoo.com"
$env:ODOO_DATABASE = "your_database_name"
$env:ODOO_USERNAME = "your_login"
$env:ODOO_API_KEY = "your_generated_api_key"
```

If you want to use a password instead of an API key:

```powershell
$env:ODOO_PASSWORD = "your_password"
```

Use either `ODOO_PASSWORD` or `ODOO_API_KEY`.

## Step 3: Test the connection exactly the way the docs describe

Odoo 15 says to verify the server version first through `xmlrpc/2/common`, then authenticate.

This minimal Python test follows that flow:

```python
import os
import xmlrpc.client

url = os.environ["ODOO_BASE_URL"]
db = os.environ["ODOO_DATABASE"]
username = os.environ["ODOO_USERNAME"]
password = os.getenv("ODOO_API_KEY") or os.environ["ODOO_PASSWORD"]

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
print(common.version())

uid = common.authenticate(db, username, password, {})
print("uid:", uid)
```

If `uid` is a number, authentication worked.

## Step 4: Confirm model access

The docs show that model methods are called through `xmlrpc/2/object` using `execute_kw`.

Use this check first:

```python
import os
import xmlrpc.client

url = os.environ["ODOO_BASE_URL"]
db = os.environ["ODOO_DATABASE"]
username = os.environ["ODOO_USERNAME"]
password = os.getenv("ODOO_API_KEY") or os.environ["ODOO_PASSWORD"]

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

print(models.execute_kw(
	db,
	uid,
	password,
	"product.product",
	"check_access_rights",
	["read"],
	{"raise_exception": False},
))
```

If this returns `True`, your user can read product data.

## Step 5: Inspect fields before exporting

The docs recommend `fields_get()` to inspect models and learn field names.

Example:

```python
fields = models.execute_kw(
	db,
	uid,
	password,
	"stock.move.line",
	"fields_get",
	[],
	{"attributes": ["string", "help", "type"]},
)
print(fields)
```

This is the safest way to confirm whether fields like `qty_done`, `lot_id`, `location_id`, or expiry-related fields are actually available in your database.

## Step 6: Export Odoo data to local CSV files

Run:

```powershell
& ".\.venv\Scripts\python.exe" ".\store\odoo_export.py" --output-dir ".\store\raw\odoo" --date-from 2024-01-01
```

That command authenticates through:

- `xmlrpc/2/common` to get `uid`,
- `xmlrpc/2/object` to call `search_read` through `execute_kw`.

It exports these models:

- `product.product`
- `stock.quant`
- `stock.move.line`
- `stock.production.lot` or `stock.lot`, depending on which model exists on the server

## Step 6A: Seed Odoo from the local source snapshot

If you want to push the local source dataset into Odoo first, use the importer script.

This is the correct use of the local CSV in Odoo:

1. pick the latest available snapshot date,
2. create or update products from `Product ID`,
3. optionally create one internal Odoo location per `Store ID`,
4. apply `Inventory Level` as opening stock for that product/location pair.

Run:

```powershell
& ".\.venv\Scripts\python.exe" ".\store\import_local_to_odoo.py" --source ".\store\raw\retail_store_inventory.csv" --location-mode per-store
```

Key behavior:

- `Product ID` becomes `default_code`
- products are marked storable via the live tenant's `is_storable` field
- `Category` is mapped into `product.category`
- `Store ID` can become child internal locations under `WH/Stock`
- `Inventory Level` is applied through `stock.quant` inventory adjustment logic

If you want to collapse all stores into one Odoo stock location instead, use:

```powershell
& ".\.venv\Scripts\python.exe" ".\store\import_local_to_odoo.py" --source ".\store\raw\retail_store_inventory.csv" --location-mode aggregate
```

This importer intentionally does not fabricate stock movement history. After the seed import, future stock moves should come from normal Odoo operations.

During live validation against `wabkkencmptrs.odoo.com`:

- authentication succeeded,
- `product.product` responded,
- `stock.quant` responded,
- `stock.move.line` responded,
- the lot model available on that server was `stock.lot`, not `stock.production.lot`.
- the live tenant used `is_storable` on `product.template` rather than older `detailed_type` examples,
- `stock.quant.action_apply_inventory` worked, but XML-RPC returned a `None` marshalling fault that still corresponds to a successful stock apply on this tenant.

## Step 7: Use `search_read` directly when you need a one-off export

The docs show `search_read()` as the shortcut for search + read.

Example for products:

```python
products = models.execute_kw(
	db,
	uid,
	password,
	"product.product",
	"search_read",
	[[ ["active", "=", True] ]],
	{"fields": ["id", "default_code", "display_name"], "limit": 5},
)
print(products)
```

Example for stock moves in a date range:

```python
moves = models.execute_kw(
	db,
	uid,
	password,
	"stock.move.line",
	"search_read",
	[[
		["date", ">=", "2024-01-01"],
		["date", "<=", "2024-12-31"],
		["state", "=", "done"],
	]],
	{"fields": ["product_id", "qty_done", "date", "location_id", "location_dest_id", "lot_id"], "limit": 20},
)
print(moves)
```

## Step 8: Map Odoo data into the forecasting dataset

This is the important project-specific step.

You need to convert raw Odoo exports into a model-ready time-series table. A practical mapping is:

- `products.csv`: SKU master data
- `stock_quants.csv`: current stock levels by location
- `stock_moves.csv`: stock movement history and demand proxy
- `lots.csv`: expiry and lot tracking information

From those exports, build a daily feature table with fields such as:

- `Date`
- `Store ID`
- `Product ID`
- `Inventory_Level`
- `Units_Sold`
- `Units_Received`
- `Expiry_Days_Remaining`
- `Category`
- `Reorder_Context`

That transformed dataset becomes the new input to your notebooks or retraining pipeline.

## Step 9: Run forecasting on the transformed Odoo-backed dataset

After transforming Odoo data into the format expected by your notebooks:

1. update the cleaning notebook or preprocessing script,
2. regenerate features,
3. retrain or rerun validation,
4. produce forecast outputs,
5. write forecast outputs to `store/raw/` or MySQL.

At that point, the dashboard can keep working without major UI changes because it still consumes forecast outputs rather than raw Odoo records.

## Step 10: Optional MySQL publishing step

If you want the dashboard to run in database mode after forecasting:

1. keep Odoo as the operational source,
2. generate model outputs locally,
3. insert forecast rows into MySQL,
4. let the dashboard read from MySQL.

That architecture is often cleaner than making the dashboard query Odoo directly.

## Suggested architecture for this project

The most practical near-term design is:

1. Odoo for live operational inventory data,
2. local Python transformation and forecasting,
3. MySQL for published forecast outputs,
4. Streamlit for dashboarding.

This avoids coupling the dashboard directly to ERP models while still making Odoo the real source of truth.

## Common Odoo integration issues

### Authentication returns `False` or `uid = False`

Cause:

- wrong database name,
- wrong username,
- wrong password or API key,
- the user has no local password on Odoo Online

Fix:

- verify `ODOO_DATABASE`, `ODOO_USERNAME`, and the credential,
- if using Odoo Online, set a local password from `Settings -> Users & Companies -> Users -> Action -> Change Password`,
- if using an API key, regenerate it and try again

### XML-RPC connection errors

Cause:

- wrong endpoint,
- wrong base URL,
- API not available on the deployment

Fix:

- verify the base URL,
- use the exact Odoo 15 endpoints:
	- `/xmlrpc/2/common`
	- `/xmlrpc/2/object`

### XML-RPC fault on `execute_kw`

Cause:

- wrong model name,
- wrong field name,
- insufficient access rights

Fix:

- inspect the model with `fields_get()`,
- verify permissions with `check_access_rights`,
- test simpler models first such as `product.product`

### Empty exports

Cause:

- restrictive domains,
- no records for the selected period,
- the user cannot access those models

Fix:

- remove date filters,
- test simpler models such as `product.product`,
- confirm access rights in Odoo

## Bottom line

To connect Odoo dataset correctly in this repo:

- do not send raw Odoo tables straight into the dashboard,
- extract inventory data from Odoo first,
- transform it into the forecast pipeline shape,
- then feed the dashboard with forecast outputs or MySQL-published results.

The added `store/odoo_export.py` script is the first operational step in that flow.
The added `store/import_local_to_odoo.py` script is the optional seed step when you want to populate Odoo from the local CSV before switching to Odoo-native operations.