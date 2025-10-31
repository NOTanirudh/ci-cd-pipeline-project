<#
Simple dev setup helper for Windows. This script does NOT install heavy packages like Docker Desktop
automatically unless you explicitly uncomment the install lines. It checks for required CLIs and
prints suggested install commands.

Run as (PowerShell elevated) if you want to use Chocolatey-based installs.
#>

function Check-Tool {
    param([string]$cmd, [string]$name)
    $which = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $which) {
        Write-Host "MISSING: $name ($cmd)"
        return $false
    }
    else {
        Write-Host "OK: $name ($cmd) -> $($which.Source)"
        return $true
    }
}

Write-Host "Checking required developer tools..."
Check-Tool -cmd git -name Git
Check-Tool -cmd docker -name Docker
Check-Tool -cmd kubectl -name kubectl
Check-Tool -cmd pytest -name pytest
Check-Tool -cmd node -name Node.js
Check-Tool -cmd npm -name npm
Check-Tool -cmd pwsh -name PowerShell

Write-Host "`nIf any tools are missing consider installing them. Example (Chocolatey):"
Write-Host "(run as Administrator)"
Write-Host "choco install git -y"
Write-Host "choco install docker-desktop -y   # requires restart and manual signin for Docker Desktop"
Write-Host "choco install kubernetes-cli -y"
Write-Host "choco install python -y"
Write-Host "python -m pip install -r user-service/requirements.txt"
Write-Host "choco install nodejs -y"

Write-Host "\nTo run the demo stack locally using Docker Compose (builds the user-service image):"
Write-Host "docker-compose up --build"
