# Build dist\wukong_fetch_ocr\ (onedir). Run from repo root:
#   .\scripts\build_wukong_fetch_ocr_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> pip install -e .[paddle,bundle] ..." -ForegroundColor Cyan
python -m pip install -e '.\[paddle,bundle]'

Write-Host "==> PyInstaller (may take several minutes) ..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm (Join-Path $Root "packaging\run_test_01_fetch_ocr.spec")

$Dist = Join-Path $Root "dist\wukong_fetch_ocr"
$Out = Join-Path $Dist "wukong_fetch_ocr.exe"
if (-not (Test-Path $Out)) {
    Write-Host "Build failed: exe not found." -ForegroundColor Red
    exit 1
}

Write-Host "==> Copy register script, server, wukong_invite package, novice README ..." -ForegroundColor Cyan
Copy-Item (Join-Path $Root "scripts\register_input_assistant_task.ps1") -Destination $Dist -Force
Copy-Item (Join-Path $Root "scripts\input_assistant_server.py") -Destination $Dist -Force
Copy-Item (Join-Path $Root "packaging\README_wukong_fetch_ocr_NOVICE.txt") -Destination $Dist -Force
$SrcPkg = Join-Path $Root "src\wukong_invite"
$DstPkg = Join-Path $Dist "wukong_invite"
if (Test-Path $DstPkg) {
    Remove-Item $DstPkg -Recurse -Force
}
Copy-Item $SrcPkg $Dist -Recurse -Force

Write-Host "OK: $Out" -ForegroundColor Green
Write-Host "Zip the whole dist\wukong_fetch_ocr folder. Novices: README_wukong_fetch_ocr_NOVICE.txt then register_input_assistant_task.ps1" -ForegroundColor Yellow
