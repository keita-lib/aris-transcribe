"""文字起こしの本体：モデルの読み込み、ファイルの文字起こし、各形式での書き出し。GUI と CLI で共有する。"""

import glob
import os
import site
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import __version__

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aris-transcribe")
LOG_PATH = os.path.join(LOG_DIR, "aris-transcribe.log")

# 受け付ける拡張子（ファイル選択ダイアログの絞り込み用。デコードは PyAV なので実際はもっと読める）
MEDIA_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv",
              ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma")
FORMATS = ("txt", "srt", "md")


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    if sys.stdout:
        print(line, flush=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def add_cuda_dll_dirs() -> None:
    """pipで入れたNVIDIAのライブラリ（cuBLAS等）を読み込めるようにする"""
    if getattr(sys, "frozen", False):
        roots = [sys._MEIPASS]  # exe版：同梱したDLLの場所
    else:
        roots = site.getsitepackages() + [site.getusersitepackages()]
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Result:
    path: str
    segments: list
    duration: float
    language: str
    model_desc: str
    elapsed: float


class Cancelled(Exception):
    pass


class Engine:
    """Whisper モデルを1つ持ち、ファイルを順に文字起こしする"""

    def __init__(self, model: str = "auto", device: str = "auto"):
        self.model_name = model
        self.device = device
        self.model = None
        self.batched = None
        self.desc = ""

    def load(self, on_status: Callable[[str], None] = lambda s: None) -> str:
        add_cuda_dll_dirs()
        import ctranslate2
        from faster_whisper import BatchedInferencePipeline, WhisperModel
        from faster_whisper.utils import download_model

        device = self.device
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        candidates = [device] if self.device != "auto" else ([device, "cpu"] if device == "cuda" else ["cpu"])
        last_error = None
        for dev in candidates:
            name = self.model_name if self.model_name != "auto" else ("large-v3" if dev == "cuda" else "small")
            try:
                download_model(name, local_files_only=True)
            except Exception:
                on_status(f"モデル {name} をダウンロードしています（初回のみ。数分かかります）")
            try:
                on_status(f"モデル {name} を読み込んでいます...")
                compute = "float16" if dev == "cuda" else "int8"
                self.model = WhisperModel(name, device=dev, compute_type=compute)
                # GPU では複数区間をまとめて推論する高速版を使う
                self.batched = BatchedInferencePipeline(self.model) if dev == "cuda" else None
                self.desc = f"{name} / {dev}"
                log(f"モデル読み込み完了: {self.desc} (v{__version__})")
                return self.desc
            except Exception as e:
                last_error = e
                log(f"{dev} での読み込みに失敗: {e}")
        raise RuntimeError(f"モデルを読み込めませんでした: {last_error}")

    def transcribe(
        self,
        path: str,
        language: str | None = "ja",
        initial_prompt: str | None = None,
        on_progress: Callable[[float, Segment], None] = lambda p, s: None,
        cancel: threading.Event | None = None,
    ) -> Result:
        t0 = time.time()
        common = dict(
            language=language or None,
            initial_prompt=initial_prompt or None,
            beam_size=5,
            vad_filter=True,  # 無音・BGMだけの区間を飛ばす（幻聴のような誤認識を減らす）
            condition_on_previous_text=False,  # 長尺で同じ文を繰り返す暴走を防ぐ
        )
        if self.batched is not None:
            # without_timestamps=False にしないと、30秒ごとの塊が1区間になり字幕として長すぎる
            seg_iter, info = self.batched.transcribe(path, batch_size=16, without_timestamps=False, **common)
        else:
            seg_iter, info = self.model.transcribe(path, **common)
        total = info.duration or 1.0
        segments = []
        for s in seg_iter:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            text = s.text.strip()
            if not text:
                continue
            seg = Segment(s.start, s.end, text)
            segments.append(seg)
            on_progress(min(s.end / total, 1.0), seg)
        on_progress(1.0, None)
        return Result(path, segments, info.duration, info.language, self.desc, time.time() - t0)


# ---- 書き出し ----
def _ts(sec: float, sep: str = ",") -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _hms(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def to_txt(r: Result) -> str:
    return "\n".join(s.text for s in r.segments) + "\n"


def to_srt(r: Result) -> str:
    blocks = [f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text}\n" for i, s in enumerate(r.segments, 1)]
    return "\n".join(blocks)


def to_md(r: Result) -> str:
    name = os.path.basename(r.path)
    lines = [
        f"# {name}",
        "",
        f"- 長さ: {_hms(r.duration)}",
        f"- 言語: {r.language}",
        f"- モデル: {r.model_desc}",
        f"- 作成: ARIS Transcribe {__version__}（{time.strftime('%Y-%m-%d %H:%M')}）",
        "",
    ]
    lines += [f"`{_hms(s.start)}` {s.text}  " for s in r.segments]
    return "\n".join(lines) + "\n"


WRITERS = {"txt": to_txt, "srt": to_srt, "md": to_md}


def write_outputs(r: Result, formats=FORMATS, out_dir: str | None = None) -> list[str]:
    """元ファイルと同じ名前で、拡張子だけ変えて書き出す（既定は元ファイルと同じフォルダ）"""
    base = os.path.splitext(os.path.basename(r.path))[0]
    folder = out_dir or os.path.dirname(os.path.abspath(r.path))
    os.makedirs(folder, exist_ok=True)
    written = []
    for fmt in formats:
        out = os.path.join(folder, f"{base}.{fmt}")
        # .srt / .txt は BOM 付き UTF-8 + CRLF。BOM が無いと日本語版 Windows のプレイヤーや
        # メモ帳以外のアプリが Shift_JIS と誤判定して文字化けする。.md は BOM を嫌うツールが多いので付けない
        windows_text = fmt in ("srt", "txt")
        enc, nl = ("utf-8-sig", "\r\n") if windows_text else ("utf-8", "\n")
        with open(out, "w", encoding=enc, newline=nl) as f:
            f.write(WRITERS[fmt](r))
        written.append(out)
    return written
