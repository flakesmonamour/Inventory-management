# Project Database Strategy

## What this project actually is

This project is a decision support system for perishable-goods inventory forecasting.

Its purpose is to:

- reduce waste from expiry,
- reduce stock-outs,
- forecast short-term stock demand,
- and support better restocking decisions.

The project plan states three key stages:

1. train the model on an external dataset,
2. build the forecasting and dashboard pipeline,
3. validate the model with real-life inventory data by linking it to an installed free inventory management system.

That third point is the important one. The real destination is not just storing predictions in a local database. The real destination is connecting the forecasting system to a live operational inventory platform.

## Current architecture

Right now the repo is still in a local, batch-oriented stage.

- notebooks clean and prepare data,
- notebooks train LSTM and SVR,
- validation outputs are written to files,
- the Streamlit dashboard reads those files from `store/raw/`.

So the current project is:

- file-based,
- batch-generated,
- and not yet connected to a live inventory application.

## What the plan says about MySQL

The plan explicitly lists MySQL as a DBMS for:

- POS transaction data,
- inventory records,
- SKU master data,
- and daily forecast outputs.

So MySQL is part of the intended build direction.

However, in the current repo, MySQL is still only partially implemented.

- The dashboard includes schema and example insert code.
- The runtime still reads files.
- The dashboard can now read forecast data from MySQL when configured, but the database still needs to be populated and maintained as part of the workflow.

## What Odoo changes

Once you move toward Odoo, the architecture changes.

Odoo is not just another storage layer. It is an operational inventory system.

According to Odoo's official documentation, Odoo Inventory supports inventory and warehouse workflows such as:

- product management,
- lot and serial tracking,
- expiration dates,
- reordering rules,
- lead times,
- replenishment,
- stock reporting,
- and forecasted reports.

That matters because your project is specifically about perishable goods, expiry risk, and replenishment decisions. Odoo is much closer to the actual business process than a standalone MySQL database.

## What the Odoo API means for this project

Odoo's official documentation shows that external integration can be done through its JSON-2 API.

The main integration pattern is:

- send HTTP requests,
- authenticate with a bearer API key,
- specify the Odoo database if needed,
- call model methods over `/json/2/<model>/<method>`.

This means your future system can pull real inventory and sales-related data from Odoo instead of relying on static CSV files.

That is the more important integration target than local MySQL.

One important caveat: the official Odoo documentation also notes that external API availability depends on the Odoo deployment and pricing model. That means you should confirm early whether your chosen Odoo setup exposes the API you want. If it does not, the fallback is usually a controlled export flow or a small custom Odoo module rather than direct database coupling.

## Where DuckDB fits

DuckDB is strong for this project for one specific reason: it matches the current Python analytics workflow very well.

From DuckDB's own documentation:

- it is embedded and in-process,
- there is no separate DBMS server to install and maintain,
- it works well inside Python,
- it can query Pandas data directly,
- and it is designed for analytical OLAP workloads.

Those are very good properties for:

- data cleaning,
- feature engineering,
- validation analysis,
- local experimentation,
- and fast analytical queries over structured tabular data.

## Where DuckDB does not fit as well

DuckDB is not the best answer to every part of this project.

It is excellent for analytics, but it is not the same thing as integrating with a live inventory application.

So if the question is:

- “What should we use inside Python for local analytical work?”

DuckDB is a strong candidate.

If the question is:

- “What should be the operational source of real inventory truth?”

DuckDB is not the answer. Odoo is closer to that role.

If the question is:

- “What should we use to satisfy the project plan's relational database requirement right now?”

Local MySQL or XAMPP is the simplest direct answer.

## Recommended role of each system

The cleanest architecture is this:

### Odoo

Use Odoo as the operational system of record.

It should eventually provide:

- product master data,
- stock on hand,
- stock movements,
- expiry-related metadata where available,
- replenishment context,
- and actual live inventory transactions.

### DuckDB

Use DuckDB as the local analytical engine for Python work.

It is best suited for:

- staging extracted inventory data,
- joining and transforming operational data,
- feature engineering,
- local model validation,
- and fast analytical querying during development.

### MySQL or XAMPP

Use MySQL only if you need a relational persistence layer for the current milestone.

That makes sense for:

- satisfying the project plan's DBMS requirement,
- storing prediction outputs for the dashboard,
- and demonstrating a database-backed DSS locally.

But MySQL should not be mistaken for the final operational inventory source if Odoo is the real future target.

## Best recommendation for your project

For this project, the strongest practical recommendation is:

1. Keep XAMPP/MySQL as the immediate local relational database milestone.
2. Treat DuckDB as the better Python-native analytical layer.
3. Treat Odoo as the future live inventory integration target.

In other words:

- XAMPP/MySQL solves the short-term database requirement.
- DuckDB solves the local analytics and Python workflow problem.
- Odoo solves the real-world inventory integration problem.

## Suggested phased path

### Phase A: Immediate project milestone

- finish XAMPP/MySQL local setup,
- load prediction and metrics outputs,
- wire the Streamlit dashboard to read from MySQL.

### Phase B: Better Python analytics workflow

- evaluate replacing some CSV/XLS intermediate steps with DuckDB tables,
- use DuckDB for local joins, transformations, and feature preparation,
- keep the ML experimentation workflow simpler and faster.

### Phase C: Real inventory validation

- connect to an installed inventory system such as Odoo,
- pull real inventory and movement data through the API,
- map Odoo products, stock, and movement history into your forecasting inputs,
- validate forecasts against real operational data.

### Phase D: Final architecture decision

At that point, decide whether you want:

- Odoo as source + DuckDB as analytics + Streamlit as DSS, or
- Odoo as source + MySQL as persistence + Streamlit as DSS, or
- both, if you need separate operational and analytical layers.

## Bottom line

Yes, DuckDB makes a lot of sense for this project because you are working in Python and doing analytical forecasting work.

But DuckDB does not replace the need to think clearly about the live inventory source.

The real architectural direction appears to be:

- forecasting in Python,
- validation against a real installed inventory platform,
- and eventual integration with something like Odoo.

So the best understanding of the project is this:

- today: local batch DSS,
- next: local database-backed DSS,
- later: live inventory-connected DSS,
- eventually: Odoo-backed forecasting and replenishment decision support.