# Data Science Project

This repository contains a stock-level prediction workflow for perishable goods. The project combines data cleaning, feature preparation, model training, validation, and a Streamlit decision-support dashboard.

## Project layout

- `store/Step 01 & Step 02- Data Cleaning.ipynb`: data cleaning, feature engineering, scaling, and train/test preparation.
- `store/STEP 03 - Model Creation.ipynb`: SVR and LSTM model training.
- `store/STEP 04 Model Validation.ipynb`: validation metrics and prediction output generation.
- `store/step05_dss_dashboard.py`: Streamlit dashboard for forecasts, reorder alerts, expiry risk, and reporting.
- `store/raw/`: generated intermediate files and validation outputs used by the dashboard.
- `store/lstm_best_model.keras` and `store/svr_model.pkl`: trained model artifacts.

## Current status

- The dashboard now reads bundled project files using repository-relative paths, so it can run on another machine without the original author's absolute paths.
- The notebooks still contain original machine-specific paths in some cells. They are useful for understanding the workflow, but they may need path cleanup before the full training pipeline is rerun from scratch.

## Local setup

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run the dashboard

From the repository root:

```powershell
streamlit run .\store\step05_dss_dashboard.py
```

## What the dashboard shows

- Actual vs predicted stock movement
- Reorder alert tracking
- Expiry risk analysis
- Model metric summaries
- Static analytical visualizations
- Example MySQL schema and import workflow

## Database note

The current dashboard does not require a running database. It reads generated files from `store/raw/` and only includes a MySQL setup example for teams that want to persist forecast outputs.

See `MYSQL_SETUP.md` for the recommended local setup, hosting options, and the difference between MySQL and a no-install database such as SQLite.
See `MYSQL_XAMPP_TODO.md` for a laptop-hosted XAMPP walkthrough and a project-specific checklist for connecting the database to this repo.
See `MYSQL_CONNECTION_GUIDE.md` for a single project-specific guide covering the implemented dashboard changes, table schema, credential options, and the exact steps to connect XAMPP/MySQL.
See `ODOO_INTEGRATION_GUIDE.md` for the exact Odoo 15 XML-RPC connection steps, required credentials, the helper script that exports inventory data into local CSV files, and the new importer that seeds Odoo products and opening stock from the local retail inventory source.
See `DATABASE_STRATEGY.md` for the recommended roles of XAMPP/MySQL, DuckDB, and Odoo in the longer-term project architecture.
