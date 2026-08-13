param(
    [switch]$Dev,
    [switch]$InstallClaudePlugin
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required and must be available as 'python' in PATH."
}

$PythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$VersionParts = $PythonVersion.Split(".")
if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 11)) {
    throw "Python 3.11 or newer is required. Found $PythonVersion."
}

if ($Dev) {
    python -m pip install --upgrade "$ProjectRoot[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Development dependency installation failed."
    }
}

python (Join-Path $ProjectRoot "scripts\mcp_launcher.py") --install-only
if ($LASTEXITCODE -ne 0) {
    throw "Plugin runtime bootstrap failed."
}

if ($InstallClaudePlugin) {
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        throw "Claude Code is required for -InstallClaudePlugin."
    }
    Push-Location $ProjectRoot
    try {
        claude plugin marketplace add "./"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to add the local Claude marketplace."
        }
        claude plugin install regulation-to-markdown@liliana-legal-tools --scope user
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install the Claude Code plugin."
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Installation complete."
Write-Host "Claude Code users:"
Write-Host "1. Configure the sensitive MinerU API Token when enabling the plugin."
Write-Host "2. Run /reload-plugins."
Write-Host "3. Invoke /regulation-to-markdown:regulation-to-markdown."
