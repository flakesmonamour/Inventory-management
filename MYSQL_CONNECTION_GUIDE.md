# MySQL Connection Guide for This Project

This document explains two things:

1. what has already changed in this repository to support a database connection,
2. how to connect the Streamlit dashboard to a local XAMPP MySQL or MariaDB database.

## Current project state

The dashboard can now run in two modes:

- `Local files`: reads validation artifacts from `store/raw/`
- `MySQL`: reads forecast and metric data from a live MySQL or MariaDB database

The database-backed path is implemented in `store/step05_dss_dashboard.py`.

## What changed in the codebase

The database integration that already exists in the dashboard works like this:

### 1. MySQL connector import

The dashboard imports `mysql.connector` and shows an error if `mysql-connector-python` is not available.

### 2. Configurable connection defaults

The dashboard reads database defaults from either:

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

or from Streamlit secrets under `[mysql]`.

### 3. Sidebar source selector

The dashboard sidebar lets you choose:

- `Local files`
- `MySQL`

When `MySQL` is selected, the sidebar shows editable connection fields for host, port, user, password, and database.

### 4. Live MySQL queries

When MySQL mode is selected, the dashboard connects and queries these tables:

- `forecast_outputs`
- `model_metrics`

It normalizes the returned columns so they match the rest of the dashboard.

### 5. Local fallback still remains

If you keep `Local files` selected, the dashboard continues to load:

- `store/raw/validation_predictions.xls`
- `store/raw/validation_metrics.xls`
- `store/raw/cleaned_grocery_inventory.xls`

That means the project still works without a database, but it is now ready to use one.

## Files relevant to the database connection

- `store/step05_dss_dashboard.py`: connection logic, source switching, and live queries
- `requirements.txt`: already includes `mysql-connector-python`
- `MYSQL_SETUP.md`: high-level setup notes
- `MYSQL_XAMPP_TODO.md`: practical XAMPP checklist

## Recommended local database option

For this project, the simplest database setup is:

- XAMPP
- MySQL service started from XAMPP Control Panel
- phpMyAdmin at `http://localhost/phpmyadmin`
- database name: `mini_market_dss`

XAMPP uses MariaDB, which is compatible with this project.

## How to connect the database

## Step 1: Start MySQL in XAMPP

1. Open XAMPP Control Panel.
2. Start `MySQL`.
3. Confirm it is running on port `3306`.
4. Open `http://localhost/phpmyadmin`.

If phpMyAdmin opens, the database server is available on your machine.

## Step 2: Create the project database

Create a database named `mini_market_dss`.

You can do that in phpMyAdmin or with SQL:

```sql
CREATE DATABASE IF NOT EXISTS mini_market_dss;
```

## Step 3: Create the required tables

Run this SQL in phpMyAdmin, MySQL Workbench, or the MySQL CLI:

```sql
CREATE DATABASE IF NOT EXISTS mini_market_dss;
USE mini_market_dss;

CREATE TABLE IF NOT EXISTS inventory_records (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    record_date   DATE         NOT NULL,
    store_id      VARCHAR(10)  NOT NULL,
    product_id    VARCHAR(10)  NOT NULL,
    category      VARCHAR(50),
    inventory_lvl FLOAT,
    units_sold    INT,
    units_ordered INT,
    price         FLOAT,
    discount      FLOAT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TABLE IF NOT EXISTS model_metrics (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    model_name   VARCHAR(20),
    smape_pct    FLOAT,
    rmse         FLOAT,
    accuracy_pct FLOAT,
    run_date     DATE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Step 4: Confirm Python dependency is installed

This repository already lists the correct package in `requirements.txt`:

```text
mysql-connector-python
```

If your environment is already installed from `requirements.txt`, you do not need to add another package.

If needed, reinstall dependencies from the project root:

```powershell
python -m pip install -r requirements.txt
```

## Step 5: Load project output files into MySQL

The dashboard reads from MySQL only after the tables contain data.

At minimum, you need rows in:

- `forecast_outputs`
- `model_metrics`

Use the project output files:

- `store/raw/validation_predictions.xls`
- `store/raw/validation_metrics.xls`

The dashboard itself includes example Python code for loading those files into MySQL in the `MySQL Setup` tab.

If you want to do it as a standalone script, use this pattern:

```python
import pandas as pd
import mysql.connector

def read_flexible(path, **kwargs):
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.read_excel(path, **kwargs)

pred_df = read_flexible("store/raw/validation_predictions.xls", parse_dates=["Date"])
metrics_df = read_flexible("store/raw/validation_metrics.xls")

conn = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="your_password_here",
    database="mini_market_dss",
)
cursor = conn.cursor()

forecast_sql = """
INSERT INTO forecast_outputs (
    forecast_date, store_id, product_id, actual_sold,
    lstm_predicted, svr_predicted, inventory_level,
    reorder_alert, expiry_risk
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

forecast_rows = [
    (
        row["Date"].date(),
        row["Store ID"],
        row["Product ID"],
        float(row["Actual"]),
        float(row["LSTM_Predicted"]),
        float(row["SVR_Predicted"]),
        float(row["Inventory_Level"]),
        int(row["Reorder_Alert"]),
        int(row["Expiry_Risk"]),
    )
    for _, row in pred_df.iterrows()
]

metric_sql = """
INSERT INTO model_metrics (model_name, smape_pct, rmse, accuracy_pct, run_date)
VALUES (%s, %s, %s, %s, CURDATE())
"""

metric_rows = [
    (
        row["Model"],
        float(row["sMAPE (%)"]),
        float(row["RMSE"]),
        float(row["Accuracy (%)"]),
    )
    for _, row in metrics_df.iterrows()
]

cursor.executemany(forecast_sql, forecast_rows)
cursor.executemany(metric_sql, metric_rows)
conn.commit()
cursor.close()
conn.close()
```

## Step 6: Choose how the dashboard gets credentials

You have two supported options.

### Option A: Enter credentials in the Streamlit sidebar

Run the dashboard, choose `MySQL`, and fill in:

- host
- port
- user
- password
- database

This is the quickest way to test.

### Option B: Use environment variables

In PowerShell, from the project root:

```powershell
$env:MYSQL_HOST = "localhost"
$env:MYSQL_PORT = "3306"
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = "your_password_here"
$env:MYSQL_DATABASE = "mini_market_dss"
streamlit run .\store\step05_dss_dashboard.py
```

When the dashboard opens, those values appear as the default connection values.

### Option C: Use Streamlit secrets

Create `.streamlit/secrets.toml` and add:

```toml
[mysql]
host = "localhost"
port = 3306
user = "root"
password = "your_password_here"
database = "mini_market_dss"
```

The dashboard reads these values automatically.

## Step 7: Run the dashboard in MySQL mode

From the repository root:

```powershell
streamlit run .\store\step05_dss_dashboard.py
```

Then:

1. open the sidebar,
2. change `Load dashboard data from` to `MySQL`,
3. confirm the connection details,
4. wait for the dashboard to load.

If the connection works and the tables contain rows, the dashboard will read live database data.

## Expected success behavior

When MySQL mode is active and the query succeeds:

- the dashboard loads without stopping,
- charts use rows returned from `forecast_outputs`,
- metrics use rows returned from `model_metrics`,
- the `MySQL Setup` tab shows connected mode information.

## Common failure cases

### `mysql-connector-python is not available`

Cause:

- the environment does not have the connector installed

Fix:

```powershell
python -m pip install -r requirements.txt
```

### `ERROR LOADING DATA` with access denied

Cause:

- wrong user or password

Fix:

- verify your XAMPP MySQL credentials
- test the same credentials in phpMyAdmin

### `ERROR LOADING DATA` with unknown database

Cause:

- `mini_market_dss` does not exist

Fix:

- create the database first

### Connected, but no rows found in `forecast_outputs`

Cause:

- schema exists, but forecast data was not inserted

Fix:

- load `store/raw/validation_predictions.xls` into `forecast_outputs`

### Connected, but no rows found in `model_metrics`

Cause:

- schema exists, but metric data was not inserted

Fix:

- load `store/raw/validation_metrics.xls` into `model_metrics`

## Minimal connection checklist

Use this order:

1. Start MySQL in XAMPP.
2. Create `mini_market_dss`.
3. Create the tables.
4. Install dependencies in the project environment.
5. Insert rows into `forecast_outputs` and `model_metrics`.
6. Run Streamlit.
7. Switch the sidebar source to `MySQL`.

## Bottom line

You do not need to rewrite the dashboard to connect the database.

The database connection support is already in the project.

What still must be done on your machine is:

- start the MySQL server,
- create the schema,
- load the project outputs into the tables,
- run the dashboard in MySQL mode with correct credentials.