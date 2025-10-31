# Helper script to run the CI/CD pipeline locally
param(
    [Parameter(Mandatory=$false)]
    [string]$DockerHubUsername,
    
    [Parameter(Mandatory=$false)]
    [string]$DockerHubPassword,
    
    [Parameter(Mandatory=$false)]
    [string]$GithubRepo = "NOTanirudh/ci-cd-pipeline-project"
)

# Check if .env exists, if not create it
if (-not (Test-Path .env)) {
    if ($DockerHubUsername -and $DockerHubPassword) {
        @"
DOCKERHUB_USER=$DockerHubUsername
DOCKERHUB_PASS=$DockerHubPassword
DOCKERHUB_REPO=$DockerHubUsername/user-service
GITHUB_REPO=$GithubRepo
"@ | Out-File .env -Encoding UTF8
        Write-Host "Created .env file with provided credentials"
    }
    else {
        Write-Host "Warning: No DockerHub credentials provided. Image push will be skipped."
        @"
GITHUB_REPO=$GithubRepo
"@ | Out-File .env -Encoding UTF8
    }
}

# Ensure docker is running
$docker = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "Warning: Docker Desktop is not running. Starting it now..."
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "Waiting for Docker to start..."
    Start-Sleep -Seconds 30
}

# Start the stack
Write-Host "Starting the CI/CD pipeline stack..."
docker-compose down
docker-compose up --build -d

# Wait for services to be ready
Write-Host "Waiting for services to be ready..."
Start-Sleep -Seconds 10

# Start the frontend
Write-Host "Starting the React frontend..."
Push-Location cicd-dashboard
npm install
npm start
Pop-Location