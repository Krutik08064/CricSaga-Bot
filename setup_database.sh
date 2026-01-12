#!/bin/bash

# CricSaga Bot - Database Setup Script
# This script sets up the PostgreSQL database with all required tables

set -e  # Exit on error

echo "🏏 CricSaga Bot - Database Setup"
echo "================================"
echo ""

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo "❌ Error: PostgreSQL client (psql) not found"
    echo "Please install PostgreSQL first"
    exit 1
fi

# Get database credentials
read -p "Database name (default: cricsaga): " DB_NAME
DB_NAME=${DB_NAME:-cricsaga}

read -p "Database user (default: postgres): " DB_USER
DB_USER=${DB_USER:-postgres}

read -p "Database host (default: localhost): " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "Database port (default: 5432): " DB_PORT
DB_PORT=${DB_PORT:-5432}

echo ""
echo "📋 Configuration:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo ""
read -p "Continue with setup? (y/n): " CONFIRM

if [ "$CONFIRM" != "y" ]; then
    echo "Setup cancelled"
    exit 0
fi

echo ""
echo "🔧 Setting up database..."

# Consolidated SQL file
sql_file="DATABASE_SETUP.sql"

# Execute the SQL file
if [ -f "$sql_file" ]; then
    echo "  ➤ Executing $sql_file..."
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$sql_file" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "    ✅ $sql_file completed"
        else
            echo "    ❌ Error executing $sql_file"
            exit 1
        fi
    else
        echo "    ⚠️  Warning: $sql_file not found, skipping"
    fi
done

echo ""
echo "✅ Database setup completed successfully!"
echo ""
echo "📝 Next steps:"
echo "  1. Copy .env.example to .env"
echo "  2. Update .env with your credentials"
echo "  3. Run: python bb.py"
echo ""
