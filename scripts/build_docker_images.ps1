#!/usr/bin/env powershell
# Docker Build and Push Script for Fraud Detection System
# Builds Docker images and optionally pushes to registry

param(
    [string]$Registry = "",
    [string]$ImageTag = "latest",
    [string]$PushRegistry = $false,
    [string]$BuildVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"

# Colors for output
$Green = "`e[32m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Reset = "`e[0m"

function Write-Status {
    param([string]$Message, [string]$Status = "INFO")
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $Green
    if ($Status -eq "WARNING") { $color = $Yellow }
    if ($Status -eq "ERROR") { $color = $Red }
    
    Write-Host "$color[$Status]$Reset $timestamp - $Message"
}

function Get-ImageName {
    param(
        [string]$ServiceName,
        [string]$Registry,
        [string]$Tag
    )
    
    if ($Registry) {
        return "$Registry/$ServiceName`:$Tag"
    } else {
        return "fraud-detection-$ServiceName`:$Tag"
    }
}

Write-Status "Starting Docker Build Process" "INFO"
Write-Status "Registry: $Registry" "INFO"
Write-Status "Image Tag: $ImageTag" "INFO"
Write-Status "Build Version: $BuildVersion" "INFO"

# Check if Docker is running
try {
    docker version | Out-Null
} catch {
    Write-Status "Docker is not running or not installed" "ERROR"
    exit 1
}

# Set working directory to project root
$projectRoot = (Get-Item $PSScriptRoot).Parent.FullName
Push-Location $projectRoot
Write-Status "Working directory: $projectRoot" "INFO"

try {
    # Build API image
    Write-Status "Building API image..." "INFO"
    $apiImageName = Get-ImageName "api" $Registry $ImageTag
    
    $buildArgs = @(
        "-f", "Dockerfile.api",
        "-t", $apiImageName,
        "--build-arg", "BUILD_VERSION=$BuildVersion",
        "."
    )
    
    docker build @buildArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Status "Failed to build API image" "ERROR"
        exit 1
    }
    Write-Status "✓ API image built successfully: $apiImageName" "INFO"
    
    # Build Dashboard image
    Write-Status "Building Dashboard image..." "INFO"
    $dashboardImageName = Get-ImageName "dashboard" $Registry $ImageTag
    
    $buildArgs = @(
        "-f", "Dockerfile.dashboard",
        "-t", $dashboardImageName,
        "--build-arg", "BUILD_VERSION=$BuildVersion",
        "."
    )
    
    docker build @buildArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Status "Failed to build Dashboard image" "ERROR"
        exit 1
    }
    Write-Status "✓ Dashboard image built successfully: $dashboardImageName" "INFO"
    
    # List built images
    Write-Status "Built images:" "INFO"
    docker images | Select-String "fraud-detection"
    
    # Optional: Push to registry
    if ($PushRegistry -eq "true" -and $Registry) {
        Write-Status "Pushing images to registry..." "INFO"
        
        docker push $apiImageName
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to push API image" "ERROR"
            exit 1
        }
        Write-Status "✓ API image pushed: $apiImageName" "INFO"
        
        docker push $dashboardImageName
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to push Dashboard image" "ERROR"
            exit 1
        }
        Write-Status "✓ Dashboard image pushed: $dashboardImageName" "INFO"
    }
    
    # Print deployment commands
    Write-Host ""
    Write-Status "Build Complete! Deployment Commands:" "INFO"
    Write-Host ""
    
    Write-Host "$Green# Start containers with docker-compose$Reset"
    Write-Host "docker-compose up -d"
    Write-Host ""
    
    Write-Host "$Green# View logs$Reset"
    Write-Host "docker-compose logs -f api"
    Write-Host "docker-compose logs -f dashboard"
    Write-Host ""
    
    Write-Host "$Green# Stop containers$Reset"
    Write-Host "docker-compose down"
    Write-Host ""
    
    Write-Host "$Green# Access services$Reset"
    Write-Host "API:       http://localhost:8000"
    Write-Host "Dashboard: http://localhost:8501"
    Write-Host "MongoDB:   configured by MONGODB_URI (not bundled)"
    Write-Host ""
    
    Write-Status "Docker build process completed successfully!" "INFO"
    exit 0
    
} catch {
    Write-Status "Build failed: $_" "ERROR"
    exit 1
} finally {
    Pop-Location
}
