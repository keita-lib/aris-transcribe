# ARIS Transcribe installer
# 使い方（PowerShell）: irm https://raw.githubusercontent.com/keita-lib/aris-transcribe/main/install.ps1 | iex
# Copyright (c) 2026 Keita Nakamori / QUETTA ROBOTICS — CC BY-ND 4.0

$ErrorActionPreference = "Stop"
$AppName = "ARIS Transcribe"
# 入れる元。テスト時は環境変数 ARIS_TRANSCRIBE_SOURCE にローカルのフォルダを指定できる
$Source = if ($env:ARIS_TRANSCRIBE_SOURCE) { $env:ARIS_TRANSCRIBE_SOURCE } else { "https://github.com/keita-lib/aris-transcribe/archive/refs/heads/main.zip" }

Write-Host "== $AppName をインストールします ==" -ForegroundColor Cyan

# 1. uv（Python とパッケージの管理ツール）。無ければ入れる
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv をインストールしています..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# 2. NVIDIA の GPU があれば GPU 版、無ければ CPU 版
$hasNvidia = [bool](Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" })
$spec = if ($hasNvidia) { "aris-transcribe[gpu] @ $Source" } else { "aris-transcribe @ $Source" }
Write-Host ("GPU: " + $(if ($hasNvidia) { "NVIDIA あり → GPU 版（large-v3）" } else { "なし → CPU 版（small）" }))

# 3. 起動中なら止めてから入れ直す
Get-Process aris-transcribe -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "$AppName をインストールしています（数分かかることがあります）..."
# 同じバージョン番号のまま中身が変わった場合も、キャッシュを使わず本体を作り直す
uv tool install --python 3.12 --force --reinstall-package aris-transcribe $spec
if ($LASTEXITCODE -ne 0) { throw "インストールに失敗しました" }

$bin = (uv tool dir --bin).Trim()
$exe = Join-Path $bin "aris-transcribe.exe"
if (-not (Test-Path $exe)) { throw "実行ファイルが見つかりません: $exe" }
# aris-transcribe-cli をどこからでも使えるよう、uv のツール置き場を PATH に通す（次に開くターミナルから有効）
uv tool update-shell 2>$null | Out-Null

# 4. スタートメニューと、右クリックの「送る」メニューにショートカットを置く
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("SendTo"))) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "$AppName.lnk"))
    $lnk.TargetPath = $exe
    $lnk.Description = "$AppName — video/audio transcription by Keita Nakamori / QUETTA ROBOTICS"
    $lnk.Save()
}

Write-Host ""
Write-Host "インストールが完了しました。" -ForegroundColor Green
Write-Host "・スタートメニューの「$AppName」から起動して、動画・音声ファイルをウィンドウにドロップします"
Write-Host "・ファイルを右クリック →「送る」→「$AppName」でも文字起こしできます"
Write-Host "・結果（.txt / .srt / .md）は元のファイルと同じフォルダに書き出されます"
Write-Host "・初回はモデルのダウンロードがあります（GPU 版 約3GB / CPU 版 約0.5GB）"
Write-Host "・コマンドで使う場合: aris-transcribe-cli 動画.mp4"
Write-Host "・アンインストール: irm https://raw.githubusercontent.com/keita-lib/aris-transcribe/main/uninstall.ps1 | iex"
