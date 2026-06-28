#!/usr/bin/env python3
"""Run all SQL migration files in migrations/ directory in order."""
import glob
import os
import re
import sys

import pyodbc

MSSQL_SERVER   = os.getenv("MSSQL_SERVER",   "host.docker.internal")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER     = os.getenv("MSSQL_USER",     "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "1qaz2WSX")


def get_conn():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        "Encrypt=no;TrustServerCertificate=yes;LoginTimeout=30;",
        autocommit=True,
    )


def split_batches(sql: str) -> list[str]:
    batches = re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)
    return [b.strip() for b in batches if b.strip() and not b.strip().startswith("--")]


def run_file(conn, filepath: str):
    with open(filepath, encoding="utf-8") as f:
        sql = f.read()

    cursor = conn.cursor()
    for batch in split_batches(sql):
        try:
            cursor.execute(batch)
            print(f"  OK: {batch[:80].replace(chr(10), ' ')}...")
        except pyodbc.Error as e:
            print(f"  WARN [{e.args[0]}]: {e.args[1][:120]}")
    print(f"  Done: {os.path.basename(filepath)}")


def main():
    print(f"Connecting to {MSSQL_SERVER}/{MSSQL_DATABASE}...")
    conn = get_conn()
    print("Connected.\n")

    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "migrations", "*.sql")))
    if not files:
        print("No migration files found in migrations/")
        sys.exit(0)

    for filepath in files:
        print(f"Running: {os.path.basename(filepath)}")
        run_file(conn, filepath)
        print()

    conn.close()
    print("All migrations complete.")


if __name__ == "__main__":
    main()
