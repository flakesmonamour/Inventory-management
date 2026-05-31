# MySQL Setup Notes

## Short answer

This project does not need MySQL to run in its current form.

- The dashboard in `store/step05_dss_dashboard.py` reads local files from `store/raw/`.
- The MySQL section in the dashboard is documentation and sample code, not an active dependency.
- If Mark wants to keep the project exactly as it works today, no database server is required.

## What the current code actually does

The MySQL part of the project is currently at the documentation stage.

- The dashboard shows SQL to create a database named `mini_market_dss`.
- It shows three example tables: `inventory_records`, `forecast_outputs`, and `model_metrics`.
- It shows Python sample code using `mysql.connector.connect(...)` with `host="localhost"`.
- The dashboard itself does not execute those SQL statements and does not currently query MySQL live.

That means MySQL is optional right now.

## Do we need to host MySQL somewhere?

No, not unless you want shared access across multiple machines or deployment to a server.

For this project there are three realistic options:

1. Local MySQL on Mark's machine.
2. Local MySQL in Docker on Mark's machine.
3. Hosted MySQL on a VM, cloud database, or school/lab server.

For a student project or a single-user demo, option 1 is usually enough.

## Can MySQL be local?

Yes. That is the simplest setup if Mark specifically needs MySQL.

- Install MySQL Community Server locally.
- Create the `mini_market_dss` database.
- Run the schema from the dashboard.
- Use `mysql-connector-python` from the project to insert data.

In that setup:

- The database server runs only on the local machine.
- The Python code connects to `localhost`.
- No external hosting is required.

## Can MySQL be "no-install"?

Not in the same way as SQLite.

MySQL is a server database. A MySQL server process must exist somewhere.

That server can be:

- installed directly on the laptop,
- run inside Docker on the laptop,
- or hosted remotely.

But there is no true single-file, no-server MySQL mode.

## If Mark wants no-install, what is the alternative?

Use SQLite instead of MySQL.

SQLite is:

- file-based,
- embedded,
- and requires no separate database server.

That makes SQLite the easiest choice for:

- offline demos,
- lightweight local testing,
- and simple academic submissions.

The tradeoff is that SQLite is not MySQL. If the project rubric or supervisor specifically requires MySQL, SQLite would be a substitute, not the same implementation.

## Recommendation for this project

Based on the current repository, the clean recommendation is:

1. Keep the current file-based workflow for now.
2. Treat MySQL as an optional extension, not a blocker.
3. If Mark needs a real database for presentation or rubric reasons, use local MySQL on `localhost` first.
4. Only move to hosted MySQL if multiple users or remote deployment become necessary.

If Mark already knows XAMPP, that is a practical way to host the database on his laptop. See `MYSQL_XAMPP_TODO.md` for the step-by-step setup and connection checklist.

## Minimal local MySQL workflow

If Mark decides to use MySQL, the smallest practical flow is:

1. Install MySQL Community Server or use a local Docker container.
2. Create the database `mini_market_dss`.
3. Create the three tables shown in the dashboard.
4. Export the generated prediction outputs from the project.
5. Insert them into `forecast_outputs` using `mysql-connector-python`.
6. Later, update the Streamlit dashboard to read from MySQL instead of the local files.

## Important implementation note

The repository can now read forecast data from MySQL when the dashboard is configured for it.

- The current dashboard still supports local artifacts as the default path.
- The MySQL tab is both a guide and a connection-oriented setup reference.
- To make MySQL useful in practice, you still need to create the schema, load the project outputs, and keep the database refreshed.

## Bottom line

- MySQL is not required to run this repo today.
- If Mark wants MySQL, local `localhost` setup is enough.
- No cloud hosting is required.
- There is no true no-install MySQL mode.
- If no-install is the priority, SQLite is the correct alternative.
- XAMPP is a valid local option for this project and is likely the easiest path if Mark is already familiar with it.