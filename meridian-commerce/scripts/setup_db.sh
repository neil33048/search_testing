#!/bin/bash
# setup_db.sh - Initialize local development database
#
# Usage: ./scripts/setup_db.sh
#
# Creates the meridian_dev database and runs initial migrations.
# Requires PostgreSQL to be running locally.

set -e

# Configuration
DB_NAME="${MERIDIAN_DB_NAME:-meridian_dev}"
DB_USER="${MERIDIAN_DB_USER:-meridian}"
DB_PASSWORD="${MERIDIAN_DB_PASSWORD:-meridian_dev}"
DB_HOST="${MERIDIAN_DB_HOST:-localhost}"
DB_PORT="${MERIDIAN_DB_PORT:-5432}"

echo "=== Meridian Commerce Database Setup ==="
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Host: $DB_HOST:$DB_PORT"
echo ""

# Check if PostgreSQL is running
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    echo "Error: PostgreSQL is not running on $DB_HOST:$DB_PORT"
    echo "Please start PostgreSQL and try again."
    exit 1
fi

# Create user if not exists
echo "Creating database user..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c \
    "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || \
    echo "User $DB_USER already exists"

# Create database if not exists
echo "Creating database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c \
    "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || \
    echo "Database $DB_NAME already exists"

# Grant privileges
echo "Granting privileges..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c \
    "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# Enable extensions
echo "Enabling extensions..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c \
    "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c \
    "CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";"

# Run Alembic migrations
echo "Running migrations..."
export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
alembic upgrade head

echo ""
echo "=== Database setup complete! ==="
echo "Connection string: postgresql://$DB_USER:****@$DB_HOST:$DB_PORT/$DB_NAME"
