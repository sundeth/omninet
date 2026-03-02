#!/bin/bash
# Creates the staging database alongside the default production one.
# The POSTGRES_DB env var already creates omnipet_prd as the default database.
# This script creates the additional omnipet_dev database for staging.

set -e
set -u

echo "Creating additional staging database (omnipet_dev)..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE omnipet_dev'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'omnipet_dev')\gexec
EOSQL
echo "Staging database created."
