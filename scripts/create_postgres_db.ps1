#Requires -Version 5.1
<#
.SYNOPSIS
  Crea utente/database carbon_i40 su PostgreSQL Windows (psql).
.EXAMPLE
  .\scripts\create_postgres_db.ps1 -PostgresPassword "tua_password_postgres"
#>
[CmdletBinding()]
param(
    [string]$PgSuperUser = "postgres",
    [Parameter(Mandatory = $true)]
    [string]$PostgresPassword,
    [string]$DbName = "carbon_i40",
    [string]$AppUser = "carbon",
    [string]$AppPassword = "carbon",
    [string]$PsqlPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $PsqlPath) {
    $candidates = @(
        "C:\Program Files\PostgreSQL\18\bin\psql.exe",
        "C:\Program Files\PostgreSQL\17\bin\psql.exe",
        "C:\Program Files\PostgreSQL\16\bin\psql.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $PsqlPath = $c; break }
    }
}
if (-not $PsqlPath -or -not (Test-Path $PsqlPath)) {
    Write-Error "psql.exe non trovato. Imposta -PsqlPath 'C:\Program Files\PostgreSQL\18\bin\psql.exe'"
}

Write-Host "Uso: $PsqlPath" -ForegroundColor Cyan
$env:PGPASSWORD = $PostgresPassword

$sql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$AppUser') THEN
    CREATE ROLE $AppUser LOGIN PASSWORD '$AppPassword';
  ELSE
    ALTER ROLE $AppUser WITH PASSWORD '$AppPassword';
  END IF;
END
`$`$;

SELECT 'CREATE DATABASE $DbName OWNER $AppUser'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DbName')\gexec

GRANT ALL PRIVILEGES ON DATABASE $DbName TO $AppUser;
"@

& $PsqlPath -U $PgSuperUser -h localhost -d postgres -v ON_ERROR_STOP=1 -c $sql
if ($LASTEXITCODE -ne 0) { throw "Creazione DB fallita" }

# Permessi schema public (PostgreSQL 15+)
& $PsqlPath -U $PgSuperUser -h localhost -d $DbName -v ON_ERROR_STOP=1 -c @"
GRANT ALL ON SCHEMA public TO $AppUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $AppUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $AppUser;
"@

Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
Write-Host "OK database=$DbName user=$AppUser" -ForegroundColor Green
Write-Host "Aggiorna service_config.xml se usi password diversa da 'carbon'."
