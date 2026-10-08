"""ARIS Transcribe の画面：ファイルをドロップすると、順番に文字起こしして .txt / .srt / .md を書き出す。"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, core

SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "aris-transcribe")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")
DEFAULT_SETTINGS = {"language": "ja", "formats": ["txt", "srt", "md"], "prompt": "", "model": "auto", "device": "auto"}
LANGUAGES = ["ja", "en", "auto"]


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict) -> None:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ---- 文字起こしワーカー ----
class Worker(threading.Thread):
    """モデルの読み込みと文字起こしはこのスレッドで行い、結果は events で画面に返す"""

    def __init__(self, settings: dict, events: queue.Queue):
        super().__init__(daemon=True)
        self.engine = core.Engine(settings["model"], settings["device"])
        self.events = events
        self.jobs: queue.Queue = queue.Queue()
        self.cancel = threading.Event()

    def run(self):
        try:
            desc = self.engine.load(on_status=lambda s: self.events.put(("status", s)))
        except Exception as e:
            self.events.put(("fatal", str(e)))
            return
        self.events.put(("ready", desc))
        while True:
            iid, path, language, prompt, formats = self.jobs.get()
            if self.cancel.is_set():
                self.events.put(("cancelled", iid))
                continue
            self.events.put(("start", iid))
            try:
                r = self.engine.transcribe(
                    path, language, prompt,
                    on_progress=lambda ratio, seg, iid=iid: self.events.put(("progress", (iid, ratio, seg))),
                    cancel=self.cancel,
                )
                written = core.write_outputs(r, formats)
                core.log(f"完了: {path} ({r.duration:.0f}s を {r.elapsed:.0f}s)")
                self.events.put(("done", (iid, r, written)))
            except core.Cancelled:
                core.log(f"中止: {path}")
                self.events.put(("cancelled", iid))
            except Exception as e:
                core.log(f"失敗: {path}: {e}")
                self.events.put(("failed", (iid, str(e))))


# ---- 画面 ----
class App:
    def __init__(self, files: list[str]):
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            self.root = TkinterDnD.Tk()
            dnd = DND_FILES
        except Exception as e:  # ドラッグ&ドロップが使えない環境でも、ファイル選択で動かす
            core.log(f"ドラッグ&ドロップを使えません: {e}")
            self.root = tk.Tk()
            dnd = None

        self.settings = load_settings()
        self.events: queue.Queue = queue.Queue()
        self.worker = Worker(self.settings, self.events)
        self.jobs: dict[str, dict] = {}  # iid -> {"path", "outputs"}
        self.pending = 0
        self.ready = False

        self._build(dnd)
        self.worker.start()
        self.add_files(files)
        self.root.after(100, self._poll)

    def _build(self, dnd):
        r = self.root
        r.title(f"ARIS Transcribe {__version__}")
        r.geometry("760x560")
        r.minsize(560, 420)
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        pad = {"padx": 12, "pady": 6}

        # ドロップ先
        self.drop = tk.Label(
            r, text="ここに動画・音声ファイルをドロップ\n（クリックで選ぶこともできます。複数まとめてOK）",
            relief="groove", bd=2, height=4, cursor="hand2", font=("Yu Gothic UI", 11), fg="#444",
        )
        self.drop.pack(fill="x", **pad)
        self.drop.bind("<Button-1>", lambda e: self.choose_files())
        if dnd:
            self.drop.drop_target_register(dnd)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
            r.drop_target_register(dnd)
            r.dnd_bind("<<Drop>>", self._on_drop)

        # 設定
        opts = ttk.Frame(r)
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="言語").grid(row=0, column=0, sticky="w")
        self.lang = tk.StringVar(value=self.settings["language"])
        ttk.Combobox(opts, textvariable=self.lang, values=LANGUAGES, width=6, state="readonly").grid(row=0, column=1, padx=(4, 16))
        ttk.Label(opts, text="書き出す形式").grid(row=0, column=2, sticky="w")
        self.fmt_vars = {}
        for i, fmt in enumerate(core.FORMATS):
            v = tk.BooleanVar(value=fmt in self.settings["formats"])
            ttk.Checkbutton(opts, text=f".{fmt}", variable=v).grid(row=0, column=3 + i, padx=2)
            self.fmt_vars[fmt] = v
        ttk.Label(opts, text="ヒント").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.prompt = tk.StringVar(value=self.settings["prompt"])
        ttk.Entry(opts, textvariable=self.prompt).grid(row=1, column=1, columnspan=6, sticky="ew", pady=(6, 0), padx=(4, 0))
        opts.columnconfigure(6, weight=1)
        ttk.Label(opts, text="固有名詞や専門用語をスペース区切りで書いておくと、認識が安定します", foreground="#777").grid(
            row=2, column=1, columnspan=6, sticky="w", padx=(4, 0))

        # ファイル一覧
        lst = ttk.Frame(r)
        lst.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(lst, columns=("status",), show="tree headings", height=6)
        self.tree.heading("#0", text="ファイル")
        self.tree.heading("status", text="状態")
        self.tree.column("#0", width=480)
        self.tree.column("status", width=200, anchor="w")
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.open_output())

        # 進み具合
        self.bar = ttk.Progressbar(r, maximum=1000)
        self.bar.pack(fill="x", padx=12)
        self.live = ttk.Label(r, text="", foreground="#555")
        self.live.pack(fill="x", padx=12, pady=(4, 0))

        # ボタンと状態表示
        bottom = ttk.Frame(r)
        bottom.pack(fill="x", **pad)
        self.status = ttk.Label(bottom, text="準備しています...")
        self.status.pack(side="left")
        ttk.Button(bottom, text="書き出したファイルを表示", command=self.open_output).pack(side="right")
        self.stop_btn = ttk.Button(bottom, text="中止", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right", padx=6)

        r.protocol("WM_DELETE_WINDOW", self.quit)

    # ---- 操作 ----
    def _on_drop(self, event):
        self.add_files(self.root.tk.splitlist(event.data))

    def choose_files(self):
        pattern = " ".join(f"*{e}" for e in core.MEDIA_EXTS)
        files = filedialog.askopenfilenames(
            title="文字起こしするファイルを選ぶ", filetypes=[("動画・音声", pattern), ("すべてのファイル", "*.*")])
        self.add_files(files)

    def add_files(self, files):
        formats = [f for f, v in self.fmt_vars.items() if v.get()]
        if files and not formats:
            messagebox.showwarning("ARIS Transcribe", "書き出す形式を1つ以上選んでください")
            return
        language = None if self.lang.get() == "auto" else self.lang.get()
        for path in files:
            path = os.path.abspath(path)
            if os.path.isdir(path):
                continue
            iid = self.tree.insert("", "end", text=os.path.basename(path), values=("待機中",))
            self.jobs[iid] = {"path": path, "outputs": []}
            self.worker.jobs.put((iid, path, language, self.prompt.get().strip(), formats))
            self.pending += 1
        if files:
            self.worker.cancel.clear()
            self.stop_btn.configure(state="normal")
            self._save()

    def stop(self):
        self.worker.cancel.set()
        self.status.configure(text="中止しています...")

    def open_output(self):
        sel = self.tree.selection() or [i for i in self.tree.get_children() if self.jobs[i]["outputs"]][-1:]
        if not sel:
            return
        job = self.jobs[sel[0]]
        target = job["outputs"][0] if job["outputs"] else job["path"]
        subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])

    def _save(self):
        self.settings.update(language=self.lang.get(), prompt=self.prompt.get().strip(),
                             formats=[f for f, v in self.fmt_vars.items() if v.get()])
        try:
            save_settings(self.settings)
        except OSError as e:
            core.log(f"設定を保存できません: {e}")

    def quit(self):
        if self.pending and not messagebox.askyesno("ARIS Transcribe", "文字起こしの途中です。終了しますか？"):
            return
        self._save()
        self.root.destroy()

    # ---- ワーカーからの知らせ ----
    def _finish_one(self):
        self.pending -= 1
        if self.pending <= 0:
            self.pending = 0
            self.stop_btn.configure(state="disabled")
            self.bar["value"] = 0
            self.live.configure(text="")
            self.worker.cancel.clear()
            self.status.configure(text=f"待機中（{self.worker.engine.desc}）")

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "status":
                    self.status.configure(text=data)
                elif kind == "ready":
                    self.ready = True
                    self.status.configure(text=f"待機中（{data}）")
                elif kind == "fatal":
                    self.status.configure(text="モデルを読み込めませんでした")
                    messagebox.showerror("ARIS Transcribe", f"{data}\n\nログ: {core.LOG_PATH}")
                elif kind == "start":
                    self.tree.set(data, "status", "文字起こし中 0%")
                    self.tree.see(data)
                    self.status.configure(text=f"文字起こし中: {self.jobs[data]['path']}")
                    self.bar["value"] = 0
                elif kind == "progress":
                    iid, ratio, seg = data
                    self.bar["value"] = ratio * 1000
                    self.tree.set(iid, "status", f"文字起こし中 {ratio * 100:.0f}%")
                    if seg is not None:
                        self.live.configure(text=f"{core._hms(seg.start)}  {seg.text}")
                elif kind == "done":
                    iid, res, written = data
                    self.jobs[iid]["outputs"] = written
                    speed = res.duration / res.elapsed if res.elapsed else 0
                    self.tree.set(iid, "status", f"完了（{res.elapsed:.0f}秒・{speed:.0f}倍速）")
                    self._finish_one()
                elif kind == "cancelled":
                    self.tree.set(data, "status", "中止")
                    self._finish_one()
                elif kind == "failed":
                    iid, err = data
                    self.tree.set(iid, "status", f"失敗: {err[:60]}")
                    self._finish_one()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def run(self):
        self.root.mainloop()


def main() -> None:
    # exe のアイコンにファイルをドロップした場合や「送る」メニューから渡された場合は、引数で来る
    App([a for a in sys.argv[1:] if os.path.isfile(a)]).run()
