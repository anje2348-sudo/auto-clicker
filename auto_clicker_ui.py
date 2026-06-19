"""
放置天堂 - 頭目自動偵測 + 傳送術（螢幕監控版）
不開啟新 Chrome，直接監控你畫面上的遊戲視窗。
使用 pyautogui + OpenCV。
"""

import os, sys, time, json, threading, traceback
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
import pyautogui

pyautogui.FAILSAFE = True   # 滑鼠移到左上角緊急停止


# ─── 路徑 / 設定 ──────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(get_base_dir(), "settings.json")

DEFAULT = {
    "boss_template": "",     # 頭目圖片路徑
    "threshold":     0.75,   # 比對相似度
    "check_interval": 5,     # 偵測間隔（秒）
    "click_delay":   1.0,    # 點擊後等待
    "skill_x": 0, "skill_y": 0,       # 技能 tab 座標
    "teleport_x": 0, "teleport_y": 0, # 傳送術座標
}

def load_cfg():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return {**DEFAULT, **json.load(f)}
    except Exception:
        return DEFAULT.copy()

def save_cfg(d):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─── 監控執行緒 ──────────────────────────────────────────────────────
class Monitor:
    def __init__(self, cfg, log_fn, status_fn, done_fn):
        self.cfg = cfg
        self.log = log_fn
        self.set_status = status_fn
        self.on_done = done_fn
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def screenshot_bgr(self):
        img = pyautogui.screenshot()
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def detect_boss(self, screen, template):
        best = 0.0
        for scale in [0.8, 0.9, 1.0, 1.1, 1.2]:
            h, w = template.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            if nh > screen.shape[0] or nw > screen.shape[1]:
                continue
            resized = cv2.resize(template, (nw, nh))
            result = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, v, _, _ = cv2.minMaxLoc(result)
            if v > best:
                best = v
        return best >= self.cfg["threshold"], best

    def do_teleport(self):
        sx, sy = int(self.cfg["skill_x"]), int(self.cfg["skill_y"])
        tx, ty = int(self.cfg["teleport_x"]), int(self.cfg["teleport_y"])

        if sx == 0 and sy == 0:
            self.log("  ✗ 尚未設定「技能」按鈕位置", "warn")
            return
        if tx == 0 and ty == 0:
            self.log("  ✗ 尚未設定「傳送術」按鈕位置", "warn")
            return

        self.log(f"  → 點擊技能 ({sx}, {sy})", "action")
        pyautogui.click(sx, sy)
        time.sleep(self.cfg["click_delay"])

        self.log(f"  → 點擊傳送術 ({tx}, {ty})", "action")
        pyautogui.click(tx, ty)
        self.log("  ✓ 傳送術施放完成", "ok")
        time.sleep(self.cfg["click_delay"])

    def run(self):
        try:
            self._run_impl()
        except Exception as e:
            err = traceback.format_exc()
            self.log(f"[錯誤] {e}", "error")
            messagebox.showerror("錯誤", f"{e}\n\n{err}")
        finally:
            self.on_done()

    def _run_impl(self):
        # 載入頭目模板
        tmpl_path = self.cfg.get("boss_template", "")
        if not tmpl_path or not os.path.exists(tmpl_path):
            self.log("[錯誤] 請先選擇頭目圖片", "error")
            self.set_status("請選擇頭目圖片", "red")
            return

        # 用 PIL 讀圖（支援中文路徑）
        try:
            pil_img = Image.open(tmpl_path).convert("RGB")
            template = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            self.log(f"[錯誤] 無法讀取圖片：{e}", "error")
            return

        # 確認座標
        if self.cfg["skill_x"] == 0 and self.cfg["skill_y"] == 0:
            self.log("[警告] 技能按鈕位置未設定，將只偵測不點擊", "warn")
        if self.cfg["teleport_x"] == 0 and self.cfg["teleport_y"] == 0:
            self.log("[警告] 傳送術位置未設定，將只偵測不點擊", "warn")

        self.log("[開始] 監控中，按 Ctrl+C 或點停止可終止", "info")
        self.set_status("監控中", "#10b981")

        while not self._stop.is_set():
            ts = time.strftime("%H:%M:%S")
            try:
                screen = self.screenshot_bgr()
                found, score = self.detect_boss(screen, template)
            except Exception as e:
                self.log(f"[{ts}] 截圖失敗：{e}", "warn")
                self._stop.wait(self.cfg["check_interval"])
                continue

            if found:
                self.log(f"[{ts}] ✓ 偵測到頭目（{score:.3f}）", "ok")
            else:
                self.log(f"[{ts}] ✗ 沒有頭目（{score:.3f}）→ 傳送", "warn")
                self.do_teleport()

            self._stop.wait(self.cfg["check_interval"])

        self.set_status("已停止", "#6b7280")
        self.log("[結束] 監控已停止", "info")


# ─── UI ──────────────────────────────────────────────────────────────
class App(tk.Tk):
    BG    = "#1e293b"
    PANEL = "#0f172a"
    ACC   = "#f59e0b"
    TEXT  = "#e2e8f0"
    SUB   = "#94a3b8"
    GREEN = "#10b981"
    RED   = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title("放置天堂 - 自動傳送腳本")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.cfg = load_cfg()
        self._monitor = None
        self._thread  = None
        self._preview = None
        self._build_ui()
        self._load_fields()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _section(self, parent, title):
        tk.Label(parent, text=f"  {title}",
                 bg=self.ACC, fg="#1e293b",
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(10, 4))

    def _build_ui(self):
        # 標題列
        hdr = tk.Frame(self, bg=self.ACC)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚔  放置天堂 自動傳送腳本",
                 bg=self.ACC, fg="#1e293b",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=7)
        self._status_lbl = tk.Label(hdr, text="待機",
                                    bg=self.ACC, fg="#1e293b",
                                    font=("Segoe UI", 10))
        self._status_lbl.pack(side="right", padx=12)

        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", padx=14, pady=10)

        # ── 頭目圖片 ──
        self._section(body, "頭目圖片（用來偵測是否出現頭目）")
        img_row = tk.Frame(body, bg=self.BG)
        img_row.pack(fill="x", pady=3)
        self._tmpl_var = tk.StringVar()
        tk.Entry(img_row, textvariable=self._tmpl_var,
                 bg=self.PANEL, fg=self.TEXT,
                 insertbackground=self.TEXT,
                 relief="flat", font=("Segoe UI", 9), width=30
                 ).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(img_row, text="瀏覽", bg=self.ACC, fg="#1e293b",
                  relief="flat", font=("Segoe UI", 9, "bold"),
                  cursor="hand2", padx=8,
                  command=self._browse_template
                  ).pack(side="left", padx=(6, 0))
        self._preview_lbl = tk.Label(body, bg=self.PANEL,
                                     width=100, height=60,
                                     text="（尚未選擇）", fg=self.SUB,
                                     font=("Segoe UI", 9))
        self._preview_lbl.pack(pady=(4, 0))

        # ── 按鈕座標設定 ──
        self._section(body, "按鈕位置設定（一次性設定，之後自動記憶）")

        coord_info = tk.Label(body,
            text="① 把遊戲畫面顯示出來\n② 點「設定」後，3 秒內將滑鼠移到對應按鈕上\n③ 腳本自動記住位置",
            bg=self.BG, fg=self.SUB, font=("Segoe UI", 8), justify="left")
        coord_info.pack(anchor="w", pady=(0, 6))

        self._coord_vars = {}
        for label, xk, yk in [
            ("技能 分頁",  "skill_x",    "skill_y"),
            ("傳送術 按鈕", "teleport_x", "teleport_y"),
        ]:
            row = tk.Frame(body, bg=self.BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=self.BG, fg=self.TEXT,
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
            xv = tk.IntVar()
            yv = tk.IntVar()
            self._coord_vars[xk] = xv
            self._coord_vars[yk] = yv
            pos_lbl = tk.Label(row, bg=self.PANEL, fg=self.ACC,
                                font=("Consolas", 9), width=14)
            pos_lbl.pack(side="left", padx=(0, 8), ipady=3, ipadx=4)
            tk.Button(row, text="📍 設定位置（3秒）",
                      bg=self.PANEL, fg=self.TEXT,
                      relief="flat", font=("Segoe UI", 9),
                      cursor="hand2", padx=6,
                      command=lambda xv=xv, yv=yv, lbl=pos_lbl: self._capture_coord(xv, yv, lbl)
                      ).pack(side="left")
            # 更新顯示
            def _update_lbl(xv=xv, yv=yv, lbl=pos_lbl):
                lbl.config(text=f"({xv.get()}, {yv.get()})")
            xv.trace_add("write", lambda *_,f=_update_lbl: f())
            yv.trace_add("write", lambda *_,f=_update_lbl: f())

        # ── 偵測設定 ──
        self._section(body, "偵測設定")
        self._vars = {}
        for label, key, lo, hi, step, is_int in [
            ("偵測間隔（秒）",  "check_interval", 1,   60,  1,    True),
            ("相似度門檻",       "threshold",      0.5, 1.0, 0.05, False),
            ("點擊間隔（秒）",  "click_delay",    0.2, 5.0, 0.1,  False),
        ]:
            row = tk.Frame(body, bg=self.BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=self.BG, fg=self.TEXT,
                     font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
            var = tk.IntVar() if is_int else tk.DoubleVar()
            self._vars[key] = var
            tk.Spinbox(row, from_=lo, to=hi, increment=step,
                       textvariable=var, width=8,
                       bg=self.PANEL, fg=self.TEXT,
                       buttonbackground=self.PANEL,
                       insertbackground=self.TEXT,
                       relief="flat", font=("Segoe UI", 9)
                       ).pack(side="left", ipady=4)

        # ── 控制 ──
        btn_row = tk.Frame(body, bg=self.BG)
        btn_row.pack(fill="x", pady=(14, 4))
        self._start_btn = tk.Button(
            btn_row, text="▶  開始監控",
            bg=self.GREEN, fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2", padx=16, pady=8,
            command=self._start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = tk.Button(
            btn_row, text="■  停止",
            bg="#374151", fg=self.SUB, relief="flat",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2", padx=16, pady=8,
            state="disabled", command=self._stop)
        self._stop_btn.pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="💾 儲存",
                  bg=self.PANEL, fg=self.TEXT, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  padx=10, pady=8, command=self._save
                  ).pack(side="left")

        # ── 日誌 ──
        self._section(body, "狀態日誌")
        self._log_box = scrolledtext.ScrolledText(
            body, height=10, bg=self.PANEL, fg=self.TEXT,
            font=("Consolas", 9), relief="flat",
            state="disabled", insertbackground=self.TEXT)
        self._log_box.pack(fill="both", expand=True, pady=(0, 4))
        for tag, color in [("ok","#10b981"),("warn","#f59e0b"),
                            ("error","#ef4444"),("info","#94a3b8"),
                            ("action","#60a5fa")]:
            self._log_box.tag_config(tag, foreground=color)

    # ── 圖片 ────────────────────────────────────────────────────────
    def _browse_template(self):
        path = filedialog.askopenfilename(
            title="選擇頭目圖片",
            filetypes=[("圖片", "*.png;*.jpg;*.jpeg;*.bmp"), ("所有", "*.*")])
        if path:
            self._tmpl_var.set(path)
            self._refresh_preview(path)

    def _refresh_preview(self, path):
        try:
            img = Image.open(path)
            img.thumbnail((100, 60))
            self._preview = ImageTk.PhotoImage(img)
            self._preview_lbl.config(image=self._preview, text="")
        except Exception:
            self._preview_lbl.config(image="", text="（無法載入）")

    # ── 座標捕捉（3 秒倒數）──────────────────────────────────────────
    def _capture_coord(self, xv, yv, lbl):
        def _countdown(n):
            if n > 0:
                lbl.config(text=f"請移至按鈕... {n}")
                self.after(1000, lambda: _countdown(n - 1))
            else:
                x, y = pyautogui.position()
                xv.set(x)
                yv.set(y)
                lbl.config(text=f"({x}, {y})")
                self._save()
                self._append_log(f"已記錄座標 ({x}, {y})", "ok")
        _countdown(3)

    # ── 資料 ────────────────────────────────────────────────────────
    def _load_fields(self):
        self._tmpl_var.set(self.cfg.get("boss_template", ""))
        for k, v in self._vars.items():
            v.set(self.cfg.get(k, DEFAULT[k]))
        for k, v in self._coord_vars.items():
            v.set(self.cfg.get(k, 0))
        if self.cfg.get("boss_template"):
            self._refresh_preview(self.cfg["boss_template"])

    def _collect(self):
        d = self.cfg.copy()
        d["boss_template"] = self._tmpl_var.get()
        for k, v in self._vars.items():
            d[k] = v.get()
        for k, v in self._coord_vars.items():
            d[k] = v.get()
        return d

    def _save(self):
        self.cfg = self._collect()
        save_cfg(self.cfg)

    # ── 日誌 / 狀態 ──────────────────────────────────────────────────
    def _append_log(self, msg, tag="info"):
        def _do():
            self._log_box.config(state="normal")
            self._log_box.insert("end", msg + "\n", tag)
            self._log_box.see("end")
            self._log_box.config(state="disabled")
        self.after(0, _do)

    def _set_status(self, text, color="#e2e8f0"):
        self.after(0, lambda: self._status_lbl.config(text=text, fg=color))

    def _on_monitor_done(self):
        self.after(0, lambda: (
            self._start_btn.config(state="normal", bg=self.GREEN, fg="white"),
            self._stop_btn.config(state="disabled", bg="#374151", fg=self.SUB),
        ))

    # ── 開始 / 停止 ──────────────────────────────────────────────────
    def _start(self):
        self.cfg = self._collect()
        save_cfg(self.cfg)
        self._start_btn.config(state="disabled", bg="#374151", fg=self.SUB)
        self._stop_btn.config(state="normal", bg=self.RED, fg="white")
        self._set_status("監控中", self.GREEN)
        self._append_log("─" * 35, "info")
        self._monitor = Monitor(
            self.cfg, self._append_log, self._set_status, self._on_monitor_done
        )
        self._thread = threading.Thread(target=self._monitor.run, daemon=True)
        self._thread.start()

    def _stop(self):
        if self._monitor:
            self._monitor.stop()
        self._start_btn.config(state="normal", bg=self.GREEN, fg="white")
        self._stop_btn.config(state="disabled", bg="#374151", fg=self.SUB)

    def _on_close(self):
        self._stop()
        self.after(500, self.destroy)


if __name__ == "__main__":
    app = App()
    app.mainloop()
