<#
.SYNOPSIS
  Aperio v2 installer for PowerShell.
.DESCRIPTION
  Copies the package, creates a launcher, and optionally installs the skill.
  The `/aperio` entry point is the skill; no duplicate command file is installed.
#>
[CmdletBinding()]
param(
    [string]$Prefix = $(if ($env:APERIO_PREFIX) { $env:APERIO_PREFIX } else { Join-Path $HOME ".local" }),
    [switch]$NoSkill,
    [switch]$DryRun,
    [switch]$Check,
    [switch]$Update,
    [switch]$Rollback,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Version = (Select-String -Path (Join-Path $Root "src/aperio/__init__.py") -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
$Marker = "aperio-v2-managed"
$SkillHome = if ($env:APERIO_SKILL_HOME) { $env:APERIO_SKILL_HOME } else { Join-Path $HOME ".claude/skills" }
$SkillDir = Join-Path $SkillHome "aperio"
$CommandDir = Join-Path $HOME ".claude/commands"
$CommandFile = Join-Path $CommandDir "aperio.md"

function Test-UnsafePrefix([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $true }
    $full = [IO.Path]::GetFullPath($Value)
    $root = [IO.Path]::GetPathRoot($full)
    return ($full -eq $root -or $full -eq "." -or $full -eq "")
}

if (Test-UnsafePrefix $Prefix) {
    [Console]::Error.WriteLine("install.ps1: refusing unsafe prefix: $Prefix")
    exit 2
}
if (-not $DryRun -and -not $Check -and -not $Rollback) {
    New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
    $Prefix = (Resolve-Path $Prefix).Path
}
$Lib = Join-Path $Prefix "share/aperio"
$Bin = Join-Path $Prefix "bin"
$Launcher = Join-Path $Bin "aperio_launcher.py"
$Cmd = Join-Path $Bin "aperio.cmd"

function Restore-Library([string]$BackupPath) {
    $old = "$Lib.restore-old.$(Get-Date -Format 'yyyyMMddTHHmmssfffZ')_$PID"
    $movedAside = $false
    try {
        if (Test-Path $Lib) {
            Move-Item -Force $Lib $old
            $movedAside = $true
        }
        Move-Item -Force $BackupPath $Lib
    } catch {
        # could not complete the restore: put the moved-aside copy back and
        # report the outcome instead of throwing. Never delete $old here —
        # on a rollback that copy is the only current library left.
        if ($movedAside -and -not (Test-Path $Lib)) {
            Move-Item -Force $old $Lib -ErrorAction SilentlyContinue
        }
        return $false
    }
    if (Test-Path $old) { Remove-Item -Recurse -Force $old -ErrorAction SilentlyContinue }
    return $true
}

if ($Check) {
    $installed = if (Test-Path (Join-Path $Lib "VERSION")) {
        (Get-Content (Join-Path $Lib "VERSION") -Raw).Trim()
    } else {
        "not installed"
    }
    Write-Host "installed: $installed"
    Write-Host "source:    $Version"
    if ($installed -eq $Version -and (Test-Path $Cmd)) { exit 0 }
    exit 1
}

if ($Rollback) {
    $share = Join-Path $Prefix "share"
    $backup = if (Test-Path $share) {
        Get-ChildItem -Path $share -Directory -Filter "aperio.backup.*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
    }
    if (-not $backup -or -not (Test-Path (Join-Path $backup.FullName $Marker))) {
        [Console]::Error.WriteLine("install.ps1: no valid update backup found under $share")
        exit 2
    }
    if ($DryRun) {
        Write-Host "would: remove $Lib"
        Write-Host "would: restore $($backup.FullName) to $Lib"
        exit 0
    }
    if (-not (Restore-Library $backup.FullName)) {
        [Console]::Error.WriteLine("install.ps1: could not restore the backup to $Lib")
        exit 2
    }
    Write-Host "rolled back to $((Get-Content (Join-Path $Lib 'VERSION') -Raw).Trim())"
    exit 0
}

function Invoke-Step([scriptblock]$Action, [string]$Label) {
    if ($DryRun) { Write-Host "would: $Label" } else { & $Action }
}
function Write-Text([string]$Path, [string]$Value) {
    if ($DryRun) { Write-Host "would: write $Path" }
    else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
        Set-Content -Path $Path -Value $Value -Encoding utf8
    }
}

if ($Uninstall) {
    if (Test-Path (Join-Path $Lib $Marker)) {
        Invoke-Step { Remove-Item -Recurse -Force $Lib } "remove $Lib"
        if (-not $DryRun) { Write-Host "removed $Lib" }
    } else { Write-Host "not removing $Lib`: marker missing" }
    if ((Test-Path $Cmd) -and (Select-String -Path $Cmd -Pattern "Aperio v2" -Quiet)) {
        Invoke-Step { Remove-Item -Force $Cmd } "remove $Cmd"
        if (-not $DryRun) { Write-Host "removed $Cmd" }
    }
    if ((Test-Path $Launcher) -and (Select-String -Path $Launcher -Pattern "Aperio v2" -Quiet)) {
        Invoke-Step { Remove-Item -Force $Launcher } "remove $Launcher"
        if (-not $DryRun) { Write-Host "removed $Launcher" }
    }
    if (-not $NoSkill -and (Test-Path (Join-Path $SkillDir $Marker))) {
        Invoke-Step { Remove-Item -Force (Join-Path $SkillDir "SKILL.md"), (Join-Path $SkillDir "VERSION"), (Join-Path $SkillDir $Marker) -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force (Join-Path $SkillDir "references") -ErrorAction SilentlyContinue } "remove Aperio files in $SkillDir"
        if (-not $DryRun) { if (Test-Path $SkillDir) { Remove-Item $SkillDir -Force -ErrorAction SilentlyContinue }; Write-Host "removed Aperio files in $SkillDir" }
    }
    if (-not $NoSkill -and (Test-Path $CommandFile) -and (Select-String -Path $CommandFile -Pattern "Aperio v2" -Quiet)) {
        Invoke-Step { Remove-Item -Force $CommandFile } "remove $CommandFile"
        if (-not $DryRun) { Write-Host "removed $CommandFile" }
    }
    exit 0
}

if (-not $NoSkill -and (Test-Path (Join-Path $SkillDir "SKILL.md")) -and -not (Test-Path (Join-Path $SkillDir $Marker))) {
    [Console]::Error.WriteLine("install.ps1: refusing to overwrite existing $SkillDir/SKILL.md; move it aside or use -NoSkill")
    exit 2
}

$Backup = $null
if ($Update -and (Test-Path (Join-Path $Lib $Marker))) {
    $Backup = "$Lib.backup.$(Get-Date -Format 'yyyyMMddTHHmmssfffZ')_$PID"
    Invoke-Step { Copy-Item -Recurse -Force $Lib $Backup } "back up $Lib to $Backup"
    if (-not $DryRun) {
        Get-ChildItem -Path (Join-Path $Prefix "share") -Directory -Filter "aperio.backup.*" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -ne $Backup } |
            Sort-Object Name -Descending |
            Select-Object -Skip 4 |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    Invoke-Step { New-Item -ItemType Directory -Force -Path $Lib, $Bin | Out-Null } "create $Lib and $Bin"
Invoke-Step { Remove-Item -Recurse -Force (Join-Path $Lib "aperio") -ErrorAction SilentlyContinue } "clear $Lib/aperio"
Invoke-Step { Copy-Item -Recurse -Force (Join-Path $Root "src/aperio") (Join-Path $Lib "aperio") } "copy package to $Lib"
if (-not $DryRun) {
    Get-ChildItem -Path (Join-Path $Lib "aperio") -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Join-Path $Lib "aperio") -Recurse -File -Filter "*.pyc" |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
Write-Text (Join-Path $Lib "VERSION") $Version
Write-Text (Join-Path $Lib $Marker) $Marker

$launcherText = @"
#!/usr/bin/env python3
"""Aperio v2 launcher. Installed by install.ps1."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "share" / "aperio"))
from aperio.cli import main
raise SystemExit(main())
"@
Write-Text $Launcher $launcherText

$cmdText = @"
@echo off
rem Aperio v2 launcher
python "%~dp0aperio_launcher.py" %*
"@
Write-Text $Cmd $cmdText

if (-not $NoSkill) {
    Invoke-Step { New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null } "create $SkillDir"
    Invoke-Step { Copy-Item -Force (Join-Path $Root "skill/aperio/SKILL.md") (Join-Path $SkillDir "SKILL.md") } "copy skill to $SkillDir"
    if (Test-Path (Join-Path $Root "skill/aperio/references")) {
        Invoke-Step { New-Item -ItemType Directory -Force (Join-Path $SkillDir "references") | Out-Null; Copy-Item -Force (Join-Path $Root "skill/aperio/references/*.md") (Join-Path $SkillDir "references") } "copy skill references to $SkillDir"
    }
    Write-Text (Join-Path $SkillDir "VERSION") $Version
    Write-Text (Join-Path $SkillDir $Marker) $Marker
    if ((Test-Path $CommandFile) -and (Select-String -Path $CommandFile -Pattern "Aperio v2" -Quiet)) {
        Invoke-Step { Remove-Item -Force $CommandFile } "remove legacy $CommandFile"
        if (-not $DryRun) { Write-Host "removed legacy $CommandFile" }
    }
}
} catch {
    if ($Backup -and (Test-Path $Backup)) {
        if (Restore-Library $Backup) {
            [Console]::Error.WriteLine("install.ps1: update failed; restored $Lib from backup")
        } else {
            [Console]::Error.WriteLine("install.ps1: update failed; the library could not be restored from the backup; backup kept at $Backup")
        }
    }
    throw
}

if (-not $DryRun) { Write-Host "installed Aperio $Version"; Write-Host "  binary: $Cmd"; if (-not $NoSkill) { Write-Host "  skill:  $SkillDir" } }
else { Write-Host "dry run: no files changed" }
