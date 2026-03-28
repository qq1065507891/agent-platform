$ErrorActionPreference = "Stop"

Write-Host "[check] Running pyflakes on app/ ..."
python -m pyflakes app

if ($LASTEXITCODE -ne 0) {
  Write-Error "pyflakes found issues."
  exit $LASTEXITCODE
}

Write-Host "[ok] No pyflakes issues found in app/."
