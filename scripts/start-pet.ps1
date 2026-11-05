# Start the desktop pet without rebuilding when dist/ is already present.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root 'apps\otis-pet'
$electron = Join-Path $app 'node_modules\electron\dist\electron.exe'

if (-not (Test-Path $electron)) {
  throw "Electron is not installed. Run 'npm install' in $app first."
}

if (-not (Test-Path (Join-Path $app 'dist\pet.html'))) {
  Push-Location $app
  npm run build
  Pop-Location
}

Start-Process -FilePath $electron -ArgumentList '.' -WorkingDirectory $app
Write-Output "Otis desktop pet started from $app"
