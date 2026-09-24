# Build and install pgvector into the local PostgreSQL 18 (Windows, MSVC).
# Follows the official pgvector Windows instructions (https://github.com/pgvector/pgvector#windows).
# Must run from an ELEVATED PowerShell because it copies files into C:\Program Files\PostgreSQL\18.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_pgvector.ps1

param(
    [string]$PgRoot = "C:\Program Files\PostgreSQL\18",
    [string]$Version = "v0.8.6",
    [string]$VcVars = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
)
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Run this script from an elevated (Administrator) PowerShell." }
if (-not (Test-Path "$PgRoot\bin\pg_config.exe")) { throw "PostgreSQL not found at $PgRoot" }
if (-not (Test-Path $VcVars)) { throw "Visual Studio Build Tools (vcvars64.bat) not found at $VcVars" }

$work = Join-Path $env:TEMP "pgvector-build"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
git clone --quiet --depth 1 --branch $Version https://github.com/pgvector/pgvector.git $work
Push-Location $work
try {
    cmd /c "call `"$VcVars`" >nul && set `"PGROOT=$PgRoot`" && nmake /nologo /F Makefile.win && nmake /nologo /F Makefile.win install"
    if ($LASTEXITCODE -ne 0) { throw "nmake failed ($LASTEXITCODE)" }
} finally { Pop-Location }

if (Test-Path "$PgRoot\share\extension\vector.control") {
    Write-Host "pgvector $Version installed into $PgRoot. Next: .venv\Scripts\python.exe scripts\setup_database.py"
} else {
    throw "vector.control not found after install"
}
