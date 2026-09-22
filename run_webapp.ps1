$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$appPath = Join-Path $projectRoot "webapp\app.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project virtual environment not found. Run: python -m venv .venv"
}

& $pythonPath -m streamlit run $appPath @args
exit $LASTEXITCODE
