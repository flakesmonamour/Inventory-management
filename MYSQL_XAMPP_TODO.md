# Mark's XAMPP MySQL Checklist

Mark, this is your practical checklist for running the project database on your own laptop using XAMPP and then connecting it to the forecasting project.

## What you are doing

You are not replacing the forecasting project.

You are adding a local database layer so that:

- your prediction outputs are stored properly,
- your dashboard can stop depending only on local files,
- and you can later connect the workflow to a real inventory system.

For now, XAMPP is your easiest local setup because you already know it.

## Why XAMPP is acceptable

Yes, you can use XAMPP.

- XAMPP gives you MariaDB, which is MySQL-compatible for this project.
- It is fine for a student project, a local demo, and a project defense.
- It is practical because you already know the XAMPP Control Panel and phpMyAdmin.

If a supervisor strictly wants Oracle MySQL by name, then MySQL Community Server is the stricter option. But for normal use in this project, XAMPP is acceptable.

## Important project reality

Right now, your dashboard is not yet truly database-driven.

- It still reads prediction files from `store/raw/`.
- The MySQL section in the dashboard is project guidance and sample code.
- The dashboard can now read from MySQL when you configure it, but you still need to load data into the database and keep that database in sync with the forecasting workflow.

So your work here is to prepare the database properly and make the project ready for the next stage.

## Your checklist

### Phase 1: Install and start XAMPP

1. Install XAMPP on your laptop.
2. Open the XAMPP Control Panel.
3. Start the `MySQL` service.
4. Confirm that MySQL is running on port `3306`.
5. Open `http://localhost/phpmyadmin` in your browser.

If phpMyAdmin opens, your local database service is available.

### Phase 2: Create your project database

1. In phpMyAdmin, create a database named `mini_market_dss`.
2. Choose `utf8mb4` collation if phpMyAdmin asks.
3. Decide whether you will use `root` or create a dedicated local database user.

Your simplest local connection settings are:

- host: `localhost`
- port: `3306`
- database: `mini_market_dss`
- username: `root` or a dedicated local user
- password: whatever you configured in XAMPP

### Phase 3: Create your tables

Run this SQL in phpMyAdmin or the MySQL CLI:

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

That gives you the three tables this project actually needs at this stage.

### Phase 4: Test your Python connection

From the project virtual environment, test the connection with a small script like this:

```python
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="your_password_here",
    database="mini_market_dss",
)

print("Connected")
conn.close()
```

If this prints `Connected`, your laptop-hosted database is ready.

### Phase 5: Load your real project outputs into MySQL

Use these files from the repo:

- `store/raw/validation_predictions.xls`
- `store/raw/validation_metrics.xls`
- optionally `store/raw/cleaned_grocery_inventory.xls`

Important detail:

- in this project, some `.xls` outputs are really CSV-style files,
- so you should load them using the same flexible pandas logic the project already uses.

Use this pattern:

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

After this step, your database contains the same prediction results the dashboard currently reads from files.

### Phase 6: Connect your dashboard to MySQL

This is the real integration step.

You need to:

1. Move your database credentials into environment variables or Streamlit secrets.
2. Add a database loader function in the dashboard.
3. Make the dashboard choose between local files and MySQL.
4. Verify that the charts and metrics match the file-based version.

Once this is done, the project becomes genuinely database-connected.

### Phase 7: Keep the bigger goal in mind

Your XAMPP database is useful, but it is not the final system of record if you later connect to a real inventory platform like Odoo.

Think of it this way:

- XAMPP/MySQL is your local persistence and demo database.
- Odoo will eventually be the live operational inventory source.
- Your forecasting pipeline sits on top of that operational data.

That means XAMPP is a good step for now, but not the final architecture.

## Recommended order for you

1. Start MySQL in XAMPP.
2. Create `mini_market_dss` in phpMyAdmin.
3. Create the tables.
4. Test your Python connection.
5. Load `validation_predictions.xls` and `validation_metrics.xls`.
6. Only then update the dashboard to read from MySQL.
7. After that, plan the Odoo integration.

## Practical notes for you

- XAMPP is local hosting, not cloud hosting.
- This is enough for a laptop demo and project defense.
- You do not need an external server for this stage.
- MySQL is still an installed server database; XAMPP just makes local setup easier.

## Bottom line for you

Yes, you can use XAMPP.

For your current stage, it is probably the most practical choice.

But do not confuse the stages:

- right now you are making the project database-backed locally,
- later you will connect it to a real inventory source such as Odoo.