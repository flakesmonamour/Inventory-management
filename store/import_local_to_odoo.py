"""Import local inventory snapshots into Odoo over XML-RPC.

Usage example:
    python store/import_local_to_odoo.py --source store/raw/retail_store_inventory.csv

This script is intentionally limited to seeding master data plus opening stock.
It does not recreate historical stock moves from the local dataset.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
import xmlrpc.client

from odoo_export import odoo_authenticate, odoo_execute_kw, validate_args


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT_DIR / "store" / "raw" / "retail_store_inventory.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local inventory data into Odoo products and stock.")
    parser.add_argument("--base-url", default=os.getenv("ODOO_BASE_URL"), help="Odoo server base URL")
    parser.add_argument("--database", default=os.getenv("ODOO_DATABASE"), help="Odoo database name")
    parser.add_argument("--username", default=os.getenv("ODOO_USERNAME"), help="Odoo login username")
    parser.add_argument("--password", default=os.getenv("ODOO_PASSWORD"), help="Odoo password for XML-RPC")
    parser.add_argument("--api-key", default=os.getenv("ODOO_API_KEY"), help="Odoo API key; can replace the password in XML-RPC calls")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Path to the local source CSV/XLS/XLSX file")
    parser.add_argument(
        "--location-mode",
        choices=["per-store", "aggregate"],
        default="per-store",
        help="Whether to map Store IDs to separate internal locations or collapse everything into one stock location",
    )
    parser.add_argument(
        "--base-location",
        help="Optional internal location complete name or simple name to use as the parent stock location, e.g. WH/Stock",
    )
    parser.add_argument("--latest-date", help="Optional explicit snapshot date (YYYY-MM-DD). Defaults to the latest date in the source file")
    parser.add_argument("--limit", type=int, help="Optional limit on the number of rows to import after snapshot filtering")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without creating or updating Odoo records")
    return parser.parse_args()


def read_source(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xls", ".xlsx"}:
        try:
            return pd.read_excel(path)
        except Exception:
            return pd.read_csv(path)
    raise SystemExit(f"Unsupported source file type: {path.suffix}")


def build_snapshot(frame: pd.DataFrame, snapshot_date: str | None, limit: int | None) -> tuple[pd.DataFrame, pd.Timestamp]:
    required_columns = {"Date", "Store ID", "Product ID", "Category", "Inventory Level", "Price"}
    missing = required_columns - set(frame.columns)
    if missing:
        joined = ", ".join(sorted(missing))
        raise SystemExit(f"Source file is missing required columns: {joined}")

    working = frame.copy()
    working["Date"] = pd.to_datetime(working["Date"], errors="coerce")
    working = working.dropna(subset=["Date", "Store ID", "Product ID", "Inventory Level"])
    working["Inventory Level"] = pd.to_numeric(working["Inventory Level"], errors="coerce").fillna(0.0)
    working["Price"] = pd.to_numeric(working["Price"], errors="coerce").fillna(0.0)

    selected_date = pd.Timestamp(snapshot_date) if snapshot_date else working["Date"].max()
    snapshot = working.loc[working["Date"] == selected_date].copy()
    if snapshot.empty:
        raise SystemExit(f"No rows found for snapshot date {selected_date.date()}")

    snapshot = (
        snapshot.sort_values(["Store ID", "Product ID"])
        .groupby(["Store ID", "Product ID"], as_index=False)
        .agg(
            {
                "Date": "max",
                "Category": "last",
                "Inventory Level": "last",
                "Price": "last",
            }
        )
    )

    snapshot = snapshot.rename(
        columns={
            "Store ID": "store_id",
            "Product ID": "product_id",
            "Category": "category",
            "Inventory Level": "inventory_level",
            "Price": "price",
            "Date": "date",
        }
    )

    if limit:
        snapshot = snapshot.head(limit).copy()

    return snapshot, selected_date


def find_internal_location(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    requested_name: str | None,
) -> dict[str, Any]:
    domain: list[list[Any]] = [["usage", "=", "internal"]]
    locations = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.location",
        "search_read",
        [domain],
        {"fields": ["id", "name", "complete_name", "usage"], "order": "complete_name asc", "limit": 100},
    )
    if not locations:
        raise RuntimeError("No internal Odoo stock location was found.")

    if requested_name:
        lowered = requested_name.casefold()
        for location in locations:
            if location["complete_name"].casefold() == lowered or location["name"].casefold() == lowered:
                return location
        raise RuntimeError(f"Could not find internal location '{requested_name}'.")

    for location in locations:
        if location["complete_name"].endswith("/Stock") or location["name"] == "Stock":
            return location
    return locations[0]


def ensure_store_location(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    base_location_id: int,
    store_id: str,
    dry_run: bool,
) -> int:
    location_name = f"Store {store_id}"
    existing = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.location",
        "search_read",
        [[["usage", "=", "internal"], ["location_id", "=", base_location_id], ["name", "=", location_name]]],
        {"fields": ["id", "name"], "limit": 1},
    )
    if existing:
        return existing[0]["id"]
    if dry_run:
        return -1
    location_ids = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.location",
        "create",
        [[{"name": location_name, "usage": "internal", "location_id": base_location_id}]],
    )
    return location_ids[0] if isinstance(location_ids, list) else location_ids


def ensure_category(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    category_name: str,
    cache: dict[str, int],
    dry_run: bool,
) -> int | None:
    normalized = category_name.strip() if isinstance(category_name, str) else "Uncategorized"
    normalized = normalized or "Uncategorized"
    if normalized in cache:
        return cache[normalized]

    existing = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "product.category",
        "search_read",
        [[["name", "=", normalized]]],
        {"fields": ["id", "name"], "limit": 1},
    )
    if existing:
        cache[normalized] = existing[0]["id"]
        return cache[normalized]
    if dry_run:
        return None
    category_ids = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "product.category",
        "create",
        [[{"name": normalized}]],
    )
    category_id = category_ids[0] if isinstance(category_ids, list) else category_ids
    cache[normalized] = category_id
    return category_id


def get_product_variant(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    template_id: int,
) -> dict[str, Any]:
    rows = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "product.product",
        "search_read",
        [[["product_tmpl_id", "=", template_id]]],
        {"fields": ["id", "default_code", "product_tmpl_id"], "limit": 1},
    )
    if not rows:
        raise RuntimeError(f"Could not find a product variant for template {template_id}")
    return rows[0]


def ensure_product(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    product_code: str,
    category_id: int | None,
    price: float,
    dry_run: bool,
) -> tuple[int, int, bool]:
    existing_variant = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "product.product",
        "search_read",
        [[["default_code", "=", product_code]]],
        {"fields": ["id", "default_code", "product_tmpl_id"], "limit": 1},
    )

    values: dict[str, Any] = {
        "name": f"Product {product_code}",
        "default_code": product_code,
        "list_price": float(price),
        "is_storable": True,
        "active": True,
    }
    if category_id:
        values["categ_id"] = category_id

    if existing_variant:
        variant = existing_variant[0]
        template_id = variant["product_tmpl_id"][0]
        if not dry_run:
            odoo_execute_kw(
                models,
                database,
                uid,
                credential,
                "product.template",
                "write",
                [[template_id], values],
            )
        return template_id, variant["id"], False

    if dry_run:
        return -1, -1, True

    created = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "product.template",
        "create",
        [[values]],
    )
    template_id = created[0] if isinstance(created, list) else created
    variant = get_product_variant(models, database, uid, credential, template_id)
    return template_id, variant["id"], True


def ensure_quant(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    product_id: int,
    location_id: int,
    dry_run: bool,
) -> tuple[int, bool]:
    existing = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.quant",
        "search_read",
        [[["product_id", "=", product_id], ["location_id", "=", location_id]]],
        {"fields": ["id"], "limit": 1},
    )
    if existing:
        return existing[0]["id"], False
    if dry_run:
        return -1, True
    created = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.quant",
        "create",
        [[{"product_id": product_id, "location_id": location_id}]],
    )
    quant_id = created[0] if isinstance(created, list) else created
    return quant_id, True


def apply_inventory_quantity(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    quant_id: int,
    quantity: float,
) -> None:
    odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "stock.quant",
        "write",
        [[quant_id], {"inventory_quantity": float(quantity)}],
    )
    try:
        odoo_execute_kw(
            models,
            database,
            uid,
            credential,
            "stock.quant",
            "action_apply_inventory",
            [[quant_id]],
        )
    except RuntimeError as exc:
        if "cannot marshal None unless allow_none is enabled" not in str(exc):
            raise


def import_snapshot(args: argparse.Namespace) -> None:
    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"Source file not found: {source_path}")

    frame = read_source(source_path)
    snapshot, selected_date = build_snapshot(frame, args.latest_date, args.limit)
    credential = args.api_key or args.password
    uid, models = odoo_authenticate(args.base_url, args.database, args.username, credential)

    base_location = find_internal_location(models, args.database, uid, credential, args.base_location)
    category_cache: dict[str, int] = {}
    location_cache: dict[str, int] = {"__aggregate__": base_location["id"]}

    created_products = 0
    updated_products = 0
    created_locations = 0
    created_quants = 0
    adjusted_quants = 0

    print(
        f"Using snapshot date {selected_date.date()} with {len(snapshot):,} store/product rows "
        f"from {source_path}"
    )
    print(f"Using base stock location {base_location['complete_name']} (id={base_location['id']})")

    for row in snapshot.itertuples(index=False):
        store_id = str(row.store_id).strip()
        product_code = str(row.product_id).strip()
        category_name = str(row.category).strip()
        inventory_level = float(row.inventory_level)
        price = float(row.price)

        if args.location_mode == "per-store":
            if store_id not in location_cache:
                location_id = ensure_store_location(
                    models,
                    args.database,
                    uid,
                    credential,
                    base_location["id"],
                    store_id,
                    args.dry_run,
                )
                location_cache[store_id] = location_id
                if location_id != -1:
                    created_locations += 1
            location_id = location_cache[store_id]
        else:
            location_id = location_cache["__aggregate__"]

        category_id = ensure_category(
            models,
            args.database,
            uid,
            credential,
            category_name,
            category_cache,
            args.dry_run,
        )

        _, variant_id, created_product = ensure_product(
            models,
            args.database,
            uid,
            credential,
            product_code,
            category_id,
            price,
            args.dry_run,
        )
        if created_product:
            created_products += 1
        else:
            updated_products += 1

        quant_id, created_quant = ensure_quant(
            models,
            args.database,
            uid,
            credential,
            variant_id,
            location_id,
            args.dry_run,
        )
        if created_quant:
            created_quants += 1
        if not args.dry_run:
            apply_inventory_quantity(models, args.database, uid, credential, quant_id, inventory_level)
        adjusted_quants += 1

    print(f"Created {created_products:,} products")
    print(f"Updated {updated_products:,} existing products")
    if args.location_mode == "per-store":
        print(f"Created {created_locations:,} internal store locations")
    print(f"Created {created_quants:,} quants")
    print(f"Adjusted {adjusted_quants:,} inventory quantities")


def main() -> None:
    args = parse_args()
    validate_args(args)
    import_snapshot(args)


if __name__ == "__main__":
    main()