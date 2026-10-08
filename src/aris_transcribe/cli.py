"""コマンドラインから使う入口：aris-transcribe-cli 動画.mp4 [...]"""

import argparse
import sys

from . import __version__, core


def main() -> None:
    p = argparse.ArgumentParser(prog="aris-transcribe-cli", description="動画・音声ファイルを文字起こしする（ARIS Transcribe）")
    p.add_argument("files", nargs="+", help="文字起こしするファイル（mp4, mkv, mp3, wav など）")
    p.add_argument("-l", "--language", default="ja", help="言語（ja, en など。auto で自動判定）。既定: ja")
    p.add_argument("-f", "--formats", default="txt,srt,md", help="書き出す形式（txt, srt, md をカンマ区切り）。既定: txt,srt,md")
    p.add_argument("-o", "--out-dir", default=None, help="書き出し先のフォルダ。既定: 元ファイルと同じ場所")
    p.add_argument("-m", "--model", default="auto", help="auto / small / medium / large-v3 / large-v3-turbo など。既定: auto")
    p.add_argument("-d", "--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("-p", "--prompt", default=None, help="固有名詞などのヒント（認識が安定する）")
    p.add_argument("-V", "--version", action="version", version=f"ARIS Transcribe {__version__}")
    a = p.parse_args()

    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    bad = [f for f in formats if f not in core.FORMATS]
    if bad:
        p.error(f"未対応の形式: {', '.join(bad)}")
    language = None if a.language == "auto" else a.language

    engine = core.Engine(a.model, a.device)
    engine.load(on_status=lambda s: print(s, file=sys.stderr, flush=True))

    failed = 0
    for path in a.files:
        print(f"\n== {path}", file=sys.stderr, flush=True)

        def progress(ratio, seg):
            if seg is not None:
                print(f"\r[{ratio * 100:5.1f}%] {seg.text[:60]:<60}", end="", file=sys.stderr, flush=True)

        try:
            r = engine.transcribe(path, language, a.prompt, on_progress=progress)
        except Exception as e:
            failed += 1
            core.log(f"失敗: {path}: {e}")
            print(f"\n失敗しました: {e}", file=sys.stderr)
            continue
        written = core.write_outputs(r, formats, a.out_dir)
        speed = r.duration / r.elapsed if r.elapsed else 0
        print(f"\n完了: {len(r.segments)} 区間 / 長さ {core._hms(r.duration)} / {r.elapsed:.0f} 秒（{speed:.1f} 倍速）", file=sys.stderr)
        for w in written:
            print(w)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
