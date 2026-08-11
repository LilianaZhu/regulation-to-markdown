param(
    [switch]$Dev,
    [switch]$InstallLocalPlugin
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

$PackageSpec = if ($Dev) { "$ProjectRoot[dev]" } else { $ProjectRoot }
python -m pip install --user --upgrade $PackageSpec

if ($InstallLocalPlugin) {
    $PluginRoot = Join-Path $HOME ".cursor\plugins\local\regulation-to-markdown"
    if (Test-Path $PluginRoot) {
        Remove-Item -Recurse -Force $PluginRoot
    }
    New-Item -ItemType Directory -Force -Path $PluginRoot | Out-Null

    $RootFiles = @(
        "mcp.json",
        "pyproject.toml",
        "README.md",
        "README.zh-CN.md",
        "LICENSE",
        "CHANGELOG.md",
        "SECURITY.md"
    )
    $DirectoryExtensions = @{
        ".cursor-plugin" = @(".json")
        "commands"       = @(".md", ".mdc", ".markdown", ".txt")
        "docs"           = @(".md")
        "skills"         = @(".md", ".py")
        "src"            = @(".py", ".typed")
        "assets"         = @(".svg", ".png", ".jpg", ".jpeg", ".webp")
    }

    foreach ($File in $RootFiles) {
        $Source = Join-Path $ProjectRoot $File
        if (Test-Path $Source -PathType Leaf) {
            Copy-Item -Force $Source (Join-Path $PluginRoot $File)
        }
    }
    foreach ($Directory in $DirectoryExtensions.Keys) {
        $SourceRoot = Join-Path $ProjectRoot $Directory
        if (-not (Test-Path $SourceRoot -PathType Container)) {
            continue
        }
        Get-ChildItem -Recurse -File $SourceRoot |
            Where-Object {
                $_.Extension.ToLowerInvariant() -in $DirectoryExtensions[$Directory]
            } |
            ForEach-Object {
                $Relative = $_.FullName.Substring($ProjectRoot.Length).TrimStart("\")
                $Destination = Join-Path $PluginRoot $Relative
                New-Item -ItemType Directory -Force -Path (
                    Split-Path -Parent $Destination
                ) | Out-Null
                Copy-Item -Force $_.FullName $Destination
            }
    }
    Write-Host "Local plugin copied to $PluginRoot"
}

Write-Host ""
Write-Host "Installation complete."
Write-Host "Next steps:"
Write-Host "1. Reload Cursor."
Write-Host "2. Open Customize and configure MINERU_API_TOKEN for the plugin."
Write-Host "3. Ask Agent to use the regulation-to-markdown skill on an official PDF."
