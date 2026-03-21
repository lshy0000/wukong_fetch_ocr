#Requires -Version 5.1
<#
.SYNOPSIS
  Register input_assistant_server as a scheduled task (at logon, interactive, highest).

.DESCRIPTION
  - Requires admin once (script re-launches with UAC).
  - Secret file: %LOCALAPPDATA%\wukong_input_assistant\secret.txt (created if missing).
  - New installs use the same default secret as wukong_fetch_ocr / input_assistant_client (no env vars needed).
  - Uses pythonw.exe (no console). Not a Session 0 Windows service.
  - If this .ps1 sits next to input_assistant_server.py (zip bundle), that folder is used as working directory.

.PARAMETER Unregister
  Remove the scheduled task (admin).

.PARAMETER ListenHost
  Default 127.0.0.1

.PARAMETER Port
  Default 47821

.PARAMETER TaskName
  Default WukongInputAssistant

.PARAMETER NoStart
  Do not start the task immediately after register.
#>
param(
    [switch]$Unregister,
    [string]$ListenHost = "127.0.0.1",
    [string]$Port = "47821",
    [string]$TaskName = "WukongInputAssistant",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    $exe = if ($PSVersionTable.PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $MyInvocation.MyCommand.Path
    )
    if ($Unregister) { $argList += "-Unregister" }
    if ($ListenHost -ne "127.0.0.1") { $argList += "-ListenHost"; $argList += $ListenHost }
    if ($Port -ne "47821") { $argList += "-Port"; $argList += $Port }
    if ($TaskName -ne "WukongInputAssistant") { $argList += "-TaskName"; $argList += $TaskName }
    if ($NoStart) { $argList += "-NoStart" }
    Start-Process -FilePath $exe -Verb RunAs -ArgumentList $argList | Out-Null
    Write-Host "UAC prompt opened. Approve to continue as Administrator."
    exit 0
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    exit 0
}

# Must match Python wukong_invite.input_assistant_defaults.BUNDLED_INPUT_ASSISTANT_SECRET
$BundledAssistantSecret = "wukong-invite-local-v1-7f3c9a2e4b8d1f6e0c5a9b3d7e1f4a8c2e6b0d4f8a1c5e9b3d7f0a4c8e2b6"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverNextToScript = Join-Path $ScriptDir "input_assistant_server.py"
$pkgNextToScript = Join-Path $ScriptDir "wukong_invite\__init__.py"
# Zip 分发：与本 ps1 同目录有 server.py 且自带 wukong_invite 包；仓库内 scripts\ 仅有 server 无旁路包 → 走仓库根
if ((Test-Path -LiteralPath $serverNextToScript) -and (Test-Path -LiteralPath $pkgNextToScript)) {
    $WorkingDir = (Resolve-Path $ScriptDir).Path
    $serverScript = $serverNextToScript
    Write-Host "Bundle (zip) mode: $serverScript" -ForegroundColor Cyan
}
else {
    $WorkingDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
    $serverScript = Join-Path $WorkingDir "scripts\input_assistant_server.py"
    if (-not (Test-Path -LiteralPath $serverScript)) {
        Write-Error "Server script not found: $serverScript"
        exit 1
    }
}

$pyExe = $null
try {
    $raw = & py -3 -c 'import sys; print(sys.executable)' 2>$null
    if ($raw) { $pyExe = [string]$raw.Trim() }
} catch {}
if (-not $pyExe) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $pyExe = $cmd.Source }
}
if (-not $pyExe -or -not (Test-Path -LiteralPath $pyExe)) {
    Write-Error "Python not found. Install Python and ensure py -3 or python is on PATH."
    exit 1
}

$pyDir = Split-Path -Parent $pyExe
$pywExe = Join-Path $pyDir "pythonw.exe"
if (-not (Test-Path -LiteralPath $pywExe)) {
    $pywExe = $pyExe
}

$dataDir = Join-Path $env:LOCALAPPDATA "wukong_input_assistant"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$secretFile = Join-Path $dataDir "secret.txt"
if (-not (Test-Path -LiteralPath $secretFile)) {
    [System.IO.File]::WriteAllText($secretFile, $BundledAssistantSecret, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Created secret file (bundled default): $secretFile"
}
else {
    Write-Host "Using existing secret file: $secretFile"
}

$argLine = "`"$serverScript`" --host $ListenHost --port $Port --secret-file `"$secretFile`""
$action = New-ScheduledTaskAction -Execute $pywExe -Argument $argLine -WorkingDirectory $WorkingDir

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "Registered task: $TaskName"
Write-Host "  Trigger: At logon for $userId"
Write-Host "  Run: Interactive + Highest"
Write-Host "  Listen: ${ListenHost}:${Port}"
Write-Host ""
Write-Host "Optional: test ping from dev machine (Python + repo src on path):"
Write-Host "  cd <repo_root>"
Write-Host "  python scripts\input_assistant_client.py ping"
Write-Host ""

if (-not $NoStart) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started task (if already running, no second instance)."
}
