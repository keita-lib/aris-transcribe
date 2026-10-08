# ARIS Transcribe

**動画や音声のファイルをドロップすると、文字起こしして .txt / .srt / .md を書き出す。** Windows 用の文字起こしツールです。

- mp4、mkv、mov、mp3、wav、m4a など、一般的な動画・音声ファイルをそのまま読み込めます（ffmpeg を別に入れる必要はありません）
- 結果は **元のファイルと同じフォルダ** に、同じ名前で書き出します（`講義.mp4` → `講義.txt` / `講義.srt` / `講義.md`）
- 音声認識（[faster-whisper](https://github.com/SYSTRAN/faster-whisper)）は手元の PC で動きます。音声を外部のサービスに送りません
- NVIDIA の GPU があれば高精度の large-v3（1時間の動画を数分で）、無ければ CPU で small モデルを自動で使います
- 複数のファイルをまとめてドロップすると、順番に処理します

## 書き出す形式

| 形式 | 中身 |
|---|---|
| `.txt` | 文字だけ。1区間1行 |
| `.srt` | 字幕ファイル。動画プレイヤー（VLC など）で動画と同じフォルダに置くと字幕として表示されます |
| `.md` | 各行の頭に時刻が付いたメモ。動画の該当箇所を探すのに便利です |

## インストール

PowerShell を開いて、次の1行を実行します。

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-transcribe/main/install.ps1 | iex
```

インストーラーが行うこと：

1. [uv](https://docs.astral.sh/uv/)（Python とパッケージの管理ツール）が無ければ入れる。Python を別に入れる必要はありません
2. NVIDIA の GPU があれば GPU 版、無ければ CPU 版の ARIS Transcribe を入れる
3. スタートメニューと、右クリックの「送る」メニューにショートカットを作る

初回の文字起こしの前に、音声認識モデルをダウンロードします（GPU 版 約3GB / CPU 版 約0.5GB）。[ARIS STT](https://github.com/keita-lib/aris-stt) を入れている場合は、同じモデルを使い回します。

## 使い方

### 画面で使う

1. スタートメニューから「ARIS Transcribe」を起動します
2. 動画・音声ファイルをウィンドウにドロップします（ウィンドウ上部の枠をクリックして選ぶこともできます）
3. 終わると「完了」と表示され、元のファイルと同じフォルダに結果ができます。「書き出したファイルを表示」でそのフォルダを開けます

ファイルを右クリック →「送る」→「ARIS Transcribe」でも、すぐに文字起こしが始まります。

| 設定 | 内容 |
|---|---|
| 言語 | `ja`（日本語）/ `en`（英語）/ `auto`（自動判定） |
| 書き出す形式 | `.txt` / `.srt` / `.md` から選ぶ |
| ヒント | 固有名詞や専門用語をスペース区切りで書いておくと、認識が安定します |

設定は次回の起動時にも引き継がれます（`%APPDATA%\aris-transcribe\settings.json`）。

### コマンドで使う

```powershell
aris-transcribe-cli 講義.mp4                      # .txt / .srt / .md を書き出す
aris-transcribe-cli *.mp3 -f txt                  # .txt だけ
aris-transcribe-cli talk.mp4 -l en -o D:\notes    # 英語、書き出し先を指定
aris-transcribe-cli --help                        # すべてのオプション
```

## 知っておいてほしいこと

- 同じ名前の .txt / .srt / .md がすでにある場合は上書きします
- 音楽や効果音だけの区間は自動で飛ばします
- 文字起こしした内容の扱い（著作権など）は、元の動画・音声の権利に従ってください
- ログ：`%LOCALAPPDATA%\aris-transcribe\aris-transcribe.log`

## アンインストール

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-transcribe/main/uninstall.ps1 | iex
```

設定とログも消す場合は、先に `$env:ARIS_TRANSCRIBE_PURGE = "1"` を実行してください。

## ライセンス

[CC BY-ND 4.0](LICENSE)（表示 - 改変禁止）。利用・共有・再配布の際は作者表記を残してください。改変したものは配布できません。詳しくは [NOTICE](NOTICE) を参照してください。

ARIS Transcribe by Keita Nakamori / QUETTA ROBOTICS
