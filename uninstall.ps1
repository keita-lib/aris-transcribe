# ARIS Transcribe uninstaller
# 使い方（PowerShell）: irm https://raw.githubusercontent.com/keita-lib/aris-transcribe/main/uninstall.ps1 | iex
# 設定とログも消す場合は、実行前に $env:ARIS_TRANSCRIBE_PURGE = "1" を設定する

$ErrorActionPreference = "Continue"
$AppName = "ARIS Transcribe"

Get-Process aris-transcribe -ErrorAction SilentlyContinue | Stop-Process -Force

foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("SendTo"))) {
    Remove-Item (Join-Path $dir "$AppName.lnk") -ErrorAction SilentlyContinue
}

if (Get-Command uv -ErrorAction SilentlyContinue) { uv tool uninstall aris-transcribe }

if ($env:ARIS_TRANSCRIBE_PURGE -eq "1") {
    Remove-Item "$env:APPDATA\aris-transcribe", "$env:LOCALAPPDATA\aris-transcribe" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "設定とログも削除しました。"
}

Write-Host "$AppName をアンインストールしました。" -ForegroundColor Green
Write-Host "ダウンロード済みの音声認識モデルは $env:USERPROFILE\.cache\huggingface\hub に残っています（ARIS STT と共有。不要なら削除してください）。"
