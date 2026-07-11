param(
    [Parameter(Position=0)]
    [string]$Domain,

    [Parameter(Position=1)]
    [string]$Action
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot

$ConfigJson = python -m core.cli config-json | ConvertFrom-Json
$ProjectRoot = $ConfigJson.paths.repository
$NasRoot = $ConfigJson.paths.nas_root
$NasHost = $ConfigJson.paths.nas_host
$NasUser = $ConfigJson.paths.nas_user

function Show-Help {
    Write-Host ""
    Write-Host "CORE CLI" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  core doctor"
    Write-Host "  core docs generate"
    Write-Host "  core docs serve"
    Write-Host "  core docs build"
    Write-Host "  core docs open"
    Write-Host "  core project analyze"
    Write-Host "  core project export"
    Write-Host "  core runtime status"
    Write-Host "  core runtime health"
    Write-Host "  core runtime logs"
    Write-Host "  core runtime dlq"
    Write-Host "  core runtime cleanlocks"
    Write-Host "  core runtime watch"
    Write-Host "  core runtime start"
    Write-Host "  core runtime stop"
    Write-Host "  core runtime restart"
    Write-Host "  core git status"
    Write-Host "  core version"
    Write-Host ""
}

function Invoke-Nas {
    param([string]$Script)
    ssh "$NasUser@$NasHost" "cd $NasRoot && $Script"
}

function Invoke-Docs {
    switch ($Action) {
        "generate" {
            Invoke-Nas "./gendocs"
        }
        "serve" {
            Set-Location $ProjectRoot
            python -m core.cli docs serve
            exit $LASTEXITCODE
        }
        "build" {
            Set-Location $ProjectRoot
            python -m core.cli docs build
            exit $LASTEXITCODE
        }
        "open" {
            Set-Location $ProjectRoot
            python -m core.cli docs open
            exit $LASTEXITCODE
        }
        default {
            Write-Host "Unknown docs command." -ForegroundColor Yellow
            Write-Host "Use: core docs generate | serve | build | open"
        }
    }
}

function Invoke-Project {
    switch ($Action) {
        "analyze" {
            Invoke-Nas "./genproject"
        }
        "export" {
            Invoke-Nas "./genproject"
            Write-Host ""
            Write-Host "Exports generated in project/exports" -ForegroundColor Green
        }
        default {
            Write-Host "Unknown project command." -ForegroundColor Yellow
            Write-Host "Use: core project analyze | export"
        }
    }
}

function Invoke-Runtime {
    switch ($Action) {
        "status" {
            Invoke-Nas "./tools/runtime/status"
        }
        "health" {
            Invoke-Nas "./tools/runtime/health"
        }
        "logs" {
            Invoke-Nas "./tools/runtime/logs"
        }
        "dlq" {
            Invoke-Nas "sh ./tools/runtime/dlq"
        }
        "cleanlocks" {
            Invoke-Nas "./tools/runtime/cleanlocks"
        }
        "watch" {
            Invoke-Nas "./tools/runtime/watch"
        }
        "start" {
            Invoke-Nas "docker compose up -d"
        }
        "stop" {
            Invoke-Nas "docker compose down"
        }
        "restart" {
            Invoke-Nas "docker compose down && docker compose up -d"
        }
        default {
            Write-Host "Unknown runtime command." -ForegroundColor Yellow
            Write-Host "Use: core runtime status | health | logs | dlq | cleanlocks | watch | start | stop | restart"
        }
    }
}

function Invoke-Git {
    switch ($Action) {
        "status" {
            Set-Location $ProjectRoot
            git status
        }
        "push" {
            Set-Location $ProjectRoot
            git push
        }
        default {
            Write-Host "Unknown git command." -ForegroundColor Yellow
            Write-Host "Use: core git status | push"
        }
    }
}

function Show-Version {
    Set-Location $ProjectRoot
    if (Test-Path "version.json") {
        Get-Content "version.json"
    } else {
        Write-Host "version.json not found" -ForegroundColor Yellow
    }
}

switch ($Domain) {
    "doctor" {
        Set-Location $ProjectRoot
        python -m core.cli doctor
        exit $LASTEXITCODE
    }
    "docs" {
        Invoke-Docs
    }
    "project" {
        Invoke-Project
    }
    "runtime" {
        Invoke-Runtime
    }
    "git" {
        Invoke-Git
    }
    "version" {
        Show-Version
    }
    default {
        Show-Help
    }
}
