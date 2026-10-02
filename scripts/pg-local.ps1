# Local, no-admin PostgreSQL control script for RESOLVE (Windows).
#
# We run PostgreSQL from EnterpriseDB's zip binaries (no installer, no admin,
# no Windows service). The cluster lives outside the repo under $PgRoot.
#
# Usage:
#   ./scripts/pg-local.ps1 start     # start the server (port 5432)
#   ./scripts/pg-local.ps1 stop      # stop the server
#   ./scripts/pg-local.ps1 status    # is it running?
#   ./scripts/pg-local.ps1 psql      # open a psql shell as the resolve user
#
# Override the install location by setting $env:PGROOT before calling.
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "psql")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$PgRoot = if ($env:PGROOT) { $env:PGROOT } else { Join-Path $env:USERPROFILE "pgroot" }
$Bin = Join-Path $PgRoot "pgsql\bin"
$Data = Join-Path $PgRoot "data"
$Log = Join-Path $PgRoot "log\pg.log"
$Port = 5432

if (-not (Test-Path $Bin)) {
    throw "PostgreSQL binaries not found at $Bin. Set `$env:PGROOT or re-run setup."
}

switch ($Action) {
    "start" {
        New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
        & "$Bin\pg_ctl.exe" -D $Data -l $Log -o "-p $Port" start
    }
    "stop" {
        & "$Bin\pg_ctl.exe" -D $Data stop
    }
    "status" {
        & "$Bin\pg_ctl.exe" -D $Data status
    }
    "psql" {
        & "$Bin\psql.exe" -U resolve -h localhost -p $Port -d resolve
    }
}
