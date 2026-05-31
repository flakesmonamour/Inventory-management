"""Import local validation artifacts into a MySQL or MariaDB database.

Usage example:
    python store/import_local_to_mysql.py --host localhost --user root --password secret --database mini_market_dss

Connection values can also be supplied through MYSQL_* environment variables.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

try:
    import mysql.connector as mysql_connector
except Exception as exc:  # pragma: no cover - import error path depends on environment
    mysql_connector = None
    MYSQL_CONNECTOR_IMPORT_ERROR = exc
else:
    MYSQL_CONNECTOR_IMPORT_ERROR = None


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local forecast artifacts into MySQL/MariaDB.")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "localhost"), help="Database host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")), help="Database port")
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"), help="Database user")
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""), help="Database password")
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "mini_market_dss"), help="Target database name")
    parser.add_argument("--predictions", default=str(RAW_DIR / "validation_predictions.xls"), help="Path to local predictions artifact")
    parser.add_argument("--metrics", default=str(RAW_DIR / "validation_metrics.xls"), help="Path to local metrics artifact")
    parser.add_argument("--replace", action="store_true", help="Delete existing rows from forecast_outputs and model_metrics before import")
    return parser.parse_args()


def read_flexible(path: str | Path, **kwargs) -> pd.DataFrame:
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.read_excel(path, **kwargs)


def ensure_connector_available() -> None:
    if mysql_connector is None:
        raise RuntimeError(f"mysql-connector-python is unavailable: {MYSQL_CONNECTOR_IMPORT_ERROR}")


def validate_database_name(database_name: str) -> str:
    if not database_name.replace("_", "").isalnum():
        raise ValueError("Database name must contain only letters, numbers, and underscores.")
    return database_name


def create_schema(cursor, database_name: str) -> None:
    safe_database_name = validate_database_name(database_name)
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{safe_database_name}`")
    cursor.execute(f"USE `{safe_database_name}`")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_outputs (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            forecast_date   DATE        NOT NULL,
            store_id        VARCHAR(10) NOT NULL,
            product_id      VARCHAR(10) NOT NULL,
            actual_sold     FLOAT,
            lstm_predicted  FLOAT,
            svr_predicted   FLOAT,
            inventory_level FLOAT,
            reorder_alert   TINYINT(1)  DEFAULT 0,
            expiry_risk     TINYINT(1)  DEFAULT 0,
            created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS model_metrics (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            model_name   VARCHAR(20),
            smape_pct    FLOAT,
            rmse         FLOAT,
            accuracy_pct FLOAT,
            run_date     DATE,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def load_sources(predictions_path: str, metrics_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    pred_df = read_flexible(predictions_path, parse_dates=["Date"])
    metrics_df = read_flexible(metrics_path)

    required_pred_columns = [
        "Date", "Store ID", "Product ID", "Actual", "LSTM_Predicted",
        "SVR_Predicted", "Inventory_Level", "Reorder_Alert", "Expiry_Risk",
    ]
    required_metric_columns = ["Model", "sMAPE (%)", "RMSE", "Accuracy (%)"]

    missing_pred = [column for column in required_pred_columns if column not in pred_df.columns]
    missing_metrics = [column for column in required_metric_columns if column not in metrics_df.columns]
    if missing_pred:
        raise ValueError(f"Predictions file is missing columns: {missing_pred}")
    if missing_metrics:
        raise ValueError(f"Metrics file is missing columns: {missing_metrics}")

    return pred_df, metrics_df


def build_rows(pred_df: pd.DataFrame, metrics_df: pd.DataFrame):
    forecast_rows = [
        (
            row["Date"].date(),
            str(row["Store ID"]),
            str(row["Product ID"]),
            float(row["Actual"]),
            float(row["LSTM_Predicted"]),
            float(row["SVR_Predicted"]),
            float(row["Inventory_Level"]),
            int(row["Reorder_Alert"]),
            int(row["Expiry_Risk"]),
        )
        for _, row in pred_df.dropna(subset=["Date"]).iterrows()
    ]
    metric_rows = [
        (
            str(row["Model"]),
            float(row["sMAPE (%)"]),
            float(row["RMSE"]),
            float(row["Accuracy (%)"]),
        )
        for _, row in metrics_df.iterrows()
    ]
    return forecast_rows, metric_rows


def import_into_database(args: argparse.Namespace) -> None:
    ensure_connector_available()
    pred_df, metrics_df = load_sources(args.predictions, args.metrics)
    forecast_rows, metric_rows = build_rows(pred_df, metrics_df)

    connection = mysql_connector.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        connection_timeout=5,
    )
    try:
        cursor = connection.cursor()
        create_schema(cursor, args.database)

        if args.replace:
            cursor.execute("DELETE FROM forecast_outputs")
            cursor.execute("DELETE FROM model_metrics")

        cursor.executemany(
            """
            INSERT INTO forecast_outputs (
                forecast_date, store_id, product_id, actual_sold,
                lstm_predicted, svr_predicted, inventory_level,
                reorder_alert, expiry_risk
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            forecast_rows,
        )
        cursor.executemany(
            """
            INSERT INTO model_metrics (
                model_name, smape_pct, rmse, accuracy_pct, run_date
            )
            VALUES (%s, %s, %s, %s, CURDATE())
            """,
            metric_rows,
        )
        connection.commit()
        print(f"Imported {len(forecast_rows):,} forecast rows into forecast_outputs")
        print(f"Imported {len(metric_rows):,} metric rows into model_metrics")
    finally:
        connection.close()


def main() -> None:
    args = parse_args()
    import_into_database(args)


if __name__ == "__main__":
    main()