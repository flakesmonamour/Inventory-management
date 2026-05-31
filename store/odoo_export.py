"""Export inventory-related datasets from Odoo 15 XML-RPC into local CSV files.

Usage example:
    python store/odoo_export.py --output-dir store/raw/odoo --date-from 2024-01-01

Configuration can be provided via environment variables:
    ODOO_BASE_URL
    ODOO_DATABASE
    ODOO_USERNAME
    ODOO_PASSWORD
    ODOO_API_KEY
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any
import xmlrpc.client

import pandas as pd


DEFAULT_EXPORTS = {
    "products": {
        "model": "product.product",
        "fields": ["id", "default_code", "display_name", "categ_id", "active", "create_date", "write_date"],
        "domain": [["active", "=", True]],
    },
    "stock_quants": {
        "model": "stock.quant",
        "fields": ["id", "product_id", "location_id", "quantity", "reserved_quantity", "in_date", "write_date"],
        "domain": [],
    },
    "stock_moves": {
        "model": "stock.move.line",
        "fields": ["id", "product_id", "location_id", "location_dest_id", "lot_id", "qty_done", "date", "state", "reference"],
        "domain": [],
    },
    "lots": {
        "model": "stock.production.lot",
        "fields": ["id", "name", "product_id", "product_qty", "create_date", "write_date", "expiration_date", "use_date", "removal_date", "alert_date"],
        "domain": [],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Odoo inventory datasets to CSV files.")
    parser.add_argument("--base-url", default=os.getenv("ODOO_BASE_URL"), help="Odoo server base URL, e.g. https://mycompany.example.com")
    parser.add_argument("--database", default=os.getenv("ODOO_DATABASE"), help="Odoo database name")
    parser.add_argument("--username", default=os.getenv("ODOO_USERNAME"), help="Odoo login username")
    parser.add_argument("--password", default=os.getenv("ODOO_PASSWORD"), help="Odoo password for XML-RPC")
    parser.add_argument("--api-key", default=os.getenv("ODOO_API_KEY"), help="Odoo API key; in Odoo 15 this can replace the password in XML-RPC calls")
    parser.add_argument("--output-dir", default=os.getenv("ODOO_OUTPUT_DIR", "store/raw/odoo"), help="Directory where CSV exports will be written")
    parser.add_argument("--date-from", help="Optional lower bound date for stock move lines, format YYYY-MM-DD")
    parser.add_argument("--date-to", help="Optional upper bound date for stock move lines, format YYYY-MM-DD")
    parser.add_argument("--batch-size", type=int, default=500, help="Maximum number of records to fetch per XML-RPC batch")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    missing = [name for name in ["base_url", "database", "username"] if not getattr(args, name)]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Missing required configuration: {joined}. Use CLI flags or ODOO_* environment variables.")
    if not (args.password or args.api_key):
        raise SystemExit("Missing required credential: provide either --password/ODOO_PASSWORD or --api-key/ODOO_API_KEY.")


def odoo_authenticate(base_url: str, database: str, username: str, credential: str) -> tuple[int, xmlrpc.client.ServerProxy]:
    common = xmlrpc.client.ServerProxy(f"{base_url.rstrip('/')}/xmlrpc/2/common", allow_none=True)
    try:
        version = common.version()
        print(f"Connected to Odoo server version: {version.get('server_version', 'unknown')}")
        uid = common.authenticate(database, username, credential, {})
    except OSError as exc:
        raise RuntimeError(f"Could not reach Odoo at {base_url}: {exc}") from exc

    if not uid:
        raise RuntimeError("Authentication failed. Check database name, username, and password/API key.")

    models = xmlrpc.client.ServerProxy(f"{base_url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
    return uid, models


def add_date_domain(domain: list[list[Any]], field_name: str, date_from: str | None, date_to: str | None) -> list[list[Any]]:
    result = list(domain)
    if date_from:
        result.append([field_name, ">=", date_from])
    if date_to:
        result.append([field_name, "<=", date_to])
    return result


def flatten_odoo_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    flattened: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (int, type(None))):
                row[f"{key}_id"] = value[0]
                row[f"{key}_name"] = value[1]
            else:
                row[key] = value
        flattened.append(row)
    return pd.DataFrame(flattened)


def odoo_execute_kw(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    kwargs = kwargs or {}
    try:
        return models.execute_kw(database, uid, credential, model, method, args, kwargs)
    except xmlrpc.client.Fault as exc:
        raise RuntimeError(f"Odoo XML-RPC fault for {model}.{method}: {exc}") from exc


def model_exists(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    model_name: str,
) -> bool:
    rows = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        "ir.model",
        "search_read",
        [[["model", "=", model_name]]],
        {"fields": ["model"], "limit": 1},
    )
    return bool(rows)


def get_model_field_names(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    model_name: str,
) -> set[str]:
    fields = odoo_execute_kw(
        models,
        database,
        uid,
        credential,
        model_name,
        "fields_get",
        [],
        {"attributes": ["type"]},
    )
    return set(fields.keys())


def resolve_export_specs(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
) -> dict[str, dict[str, Any]]:
    export_specs = {name: dict(spec) for name, spec in DEFAULT_EXPORTS.items()}
    lot_model_candidates = ["stock.production.lot", "stock.lot"]
    for candidate in lot_model_candidates:
        if model_exists(models, database, uid, credential, candidate):
            export_specs["lots"]["model"] = candidate
            break
    return export_specs


def export_model(
    models: xmlrpc.client.ServerProxy,
    database: str,
    uid: int,
    credential: str,
    model: str,
    fields: list[str],
    domain: list[list[Any]],
    batch_size: int,
    order: str,
) -> pd.DataFrame:
    offset = 0
    all_rows: list[dict[str, Any]] = []
    while True:
        rows = odoo_execute_kw(
            models,
            database,
            uid,
            credential,
            model,
            "search_read",
            [domain],
            {
                "fields": fields,
                "offset": offset,
                "limit": batch_size,
                "order": order,
            },
        )
        if not rows:
            break
        all_rows.extend(rows)
        offset += len(rows)
        if len(rows) < batch_size:
            break
    return flatten_odoo_records(all_rows)


def export_all(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    credential = args.api_key or args.password
    uid, models = odoo_authenticate(args.base_url, args.database, args.username, credential)

    export_specs = resolve_export_specs(models, args.database, uid, credential)

    for export_name, spec in export_specs.items():
        domain = spec["domain"]
        if export_name == "stock_moves":
            domain = add_date_domain(domain, "date", args.date_from, args.date_to)

        available_fields = get_model_field_names(models, args.database, uid, credential, spec["model"])
        export_fields = [field for field in spec["fields"] if field == "id" or field in available_fields]
        if not export_fields:
            print(f"Skipped {export_name} ({spec['model']}): no requested fields exist on this server.")
            continue

        try:
            frame = export_model(
                models,
                args.database,
                uid,
                credential,
                spec["model"],
                export_fields,
                domain,
                args.batch_size,
                "write_date desc" if "write_date" in spec["fields"] else "id desc",
            )
        except RuntimeError as exc:
            print(f"Skipped {export_name} ({spec['model']}): {exc}")
            continue
        output_path = output_dir / f"{export_name}.csv"
        frame.to_csv(output_path, index=False)
        print(f"Wrote {len(frame):,} rows to {output_path}")


def main() -> None:
    args = parse_args()
    validate_args(args)
    export_all(args)


if __name__ == "__main__":
    main()