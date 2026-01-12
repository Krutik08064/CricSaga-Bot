# CricSaga Bot - Database Setup Script for Windows
# This script sets up the PostgreSQL database with all required tables

Write-Host "🏏 CricSaga Bot - Database Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if psql is available
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlPath) {
    Write-Host "❌ Error: PostgreSQL client (psql) not found" -ForegroundColor Red
    Write-Host "Please install PostgreSQL first" -ForegroundColor Yellow
    exit 1
}

# Get database credentials
$DB_NAME = Read-Host "Database name (default: cricsaga)"
if ([string]::IsNullOrWhiteSpace($DB_NAME)) { $DB_NAME = "cricsaga" }

$DB_USER = Read-Host "Database user (default: postgres)"
if ([string]::IsNullOrWhiteSpace($DB_USER)) { $DB_USER = "postgres" }

$DB_HOST = Read-Host "Database host (default: localhost)"
if ([string]::IsNullOrWhiteSpace($DB_HOST)) { $DB_HOST = "localhost" }

$DB_PORT = Read-Host "Database port (default: 5432)"
if ([string]::IsNullOrWhiteSpace($DB_PORT)) { $DB_PORT = "5432" }

$DB_PASSWORD = Read-Host "Database password" -AsSecureString
$DB_PASSWORD_PLAIN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASSWORD)
)

Write-Host ""
Write-Host "📋 Configuration:" -ForegroundColor Cyan
Write-Host "  Database: $DB_NAME"
Write-Host "  User: $DB_USER"
Write-Host "  Host: $DB_HOST"
Write-Host "  Port: $DB_PORT"
Write-Host ""

$confirm = Read-Host "Continue with setup? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Setup cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "🔧 Setting up database..." -ForegroundColor Cyan

# Consolidated SQL file
$sqlFile = "DATABASE_SETUP.sql"

# Set PostgreSQL password environment variable
$env:PGPASSWORD = $DB_PASSWORD_PLAIN

# Execute the SQL file
if (Test-Path $sqlFile) {
    if (Test-Path $sqlFile) {
        Write-Host "  ➤ Executing $sqlFile..." -ForegroundColor White
        $result = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $sqlFile 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    ✅ $sqlFile completed" -ForegroundColor Green
        } else {
            Write-Host "    ❌ Error executing $sqlFile" -ForegroundColor Red
            Write-Host $result -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "    ⚠️  Warning: $sqlFile not found, skipping" -ForegroundColor Yellow
    }
}

# Clear password
$env:PGPASSWORD = $null

Write-Host ""
Write-Host "✅ Database setup completed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Copy .env.example to .env"
Write-Host "  2. Update .env with your credentials"
Write-Host "  3. Run: python bb.py"
Write-Host ""
