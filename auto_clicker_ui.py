"""
放置天堂 - 頭目自動偵測 + 傳送術（UI 版）
使用 Selenium + OpenCV + Tkinter
"""

import os, sys, time, io, json, threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import cv2
import numpy as np
from PIL import Image, ImageTk

# Selenium（由 selenium-manager 自動下載 ChromeDriver，無需手動安裝）
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException

# ─── 設定檔路徑（exe 旁邊的 settings.json）──────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(get_base_dir(), "settings.json")

DEFAULT_SETTINGS = {
    "game_url":        "https://pp771007.github.io/idle-lineage-class/",
    "template_path":   "",
    "check_interval":  5,
    "threshold":       0.75,
    "startup_wait":    15,
    "click_delay":     1.0,
    "skill_tab_text":  "技能",
    "teleport_text":   "傳送術",
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ─── 監控邏輯 ────────────────────────────────────────────────────────
class Monitor:
    def __init__(self, settings: dict, log_fn, status_fn):
        self.s = settings
        self.log = log_fn
        self.set_status = status_fn
        self._stop = threading.Event()
        self.driver = None

    def stop(self):
        self._stop.set()

    def take_screenshot(self):
        png = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def detect_boss(self, screenshot, template):
        best = 0.0
        for scale in [0.7, 0.85, 1.0, 1.15, 1.3]:
            h, w = template.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            if nh > screenshot.shape[0] or nw > screenshot.shape[1]:
                continue
            resized = cv2.resize(template, (nw, nh))
            res = cv2.matchTemplate(screenshot, resized, cv2.TM_CCOEFF_NORMED)
            _, v, _, _ = cv2.minMaxLoc(res)
            if v > best:
                best = v
        return best >= self.s["threshold"], best

    def safe_click(self, text, timeout=5):
        xpaths = [
            f"//*[normalize-space(text())='{text}']",
            f"//*[contains(text(),'{text}')]",
            f"//button[contains(.,'{text}')]",
            f"//span[contains(.,'{text}')]",
        ]
        for xpath in xpaths:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                el.click()
                return True
            except Exception:
                timeout = 1
        return False

    def do_teleport(self):
        skill = self.s["skill_tab_text"]
        tp    = self.s["teleport_text"]
        self.log(f"  → 點擊「{skill}」", "action")
        if not self.safe_click(skill):
            self.log(f"  ✗ 找不到「{skill}」分頁", "warn")
            return
        time.sleep(self.s["click_delay"])
        self.log(f"  → 點擊「{tp}」", "action")
        if self.safe_click(tp):
            self.log(f"  ✓ 傳送術施放完成", "ok")
        else:
            self.log(f"  ✗ 找不到「{tp}」（確認技能是否已學習）", "warn")
        time.sleep(self.s["click_delay"])

    def run(self):
        # 載入模板
        tmpl_path = self.s["template_path"]
        template = cv2.imread(tmpl_path)
        if template is None:
            self.log(f"[錯誤] 找不到頭目圖片：{tmpl_path}", "error")
            self.set_status("錯誤：找不到頭目圖片", "red")
            return

        # 啟動 Chrome
        profile_dir = os.path.join(get_base_dir(), "ChromeProfile")
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")

        self.log("[啟動] 開啟 Chrome...", "info")
        try:
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as e:
            self.log(f"[錯誤] 無法啟動 Chrome：{e}", "error")
            self.set_status("錯誤：無法啟動 Chrome", "red")
            return

        self.driver.maximize_window()
        self.driver.get(self.s["game_url"])

        sw = int(self.s["startup_wait"])
        self.log(f"[等待] 遊戲載入，請在 {sw} 秒內選擇存檔...", "info")
        self.set_status(f"等待存檔載入（{sw}s）...", "#f59e0b")

        for i in range(sw):
            if self._stop.is_set():
                self.driver.quit()
                self.set_status("已停止", "#6b7280")
                return
            remaining = sw - i
            self.set_status(f"等待存檔載入（剩 {remaining}s）...", "#f59e0b")
            time.sleep(1)

        self.log("[開始] 開始偵測頭目...", "info")
        self.set_status("監控中...", "#10b981")

        while not self._stop.is_set():
            ts = time.strftime("%H:%M:%S")
            try:
                shot = self.take_screenshot()
                found, score = self.detect_boss(shot, template)
            except WebDriverException:
                self.log("[停止] 瀏覽器已關閉", "warn")
                break

            if found:
                self.log(f"[{ts}] ✓ 偵測到頭目（{score:.3f}）", "ok")
            else:
                self.log(f"[{ts}] ✗ 未偵測到（{score:.3f}）→ 傳送術", "warn")
                self.do_teleport()

            self._stop.wait(self.s["check_interval"])

        try:
            self.driver.quit()
        except Exception:
            pass
        self.set_status("已停止", "#6b7280")
        self.log("[結束] 監控已停止", "info")


# ─── UI ─────────────────────────────────────────────────────────────
class App(tk.Tk):
    BG        = "#1e293b"
    PANEL_BG  = "#0f172a"
    ACCENT    = "#f59e0b"
    TEXT      = "#e2e8f0"
    SUBTEXT   = "#94a3b8"
    BTN_START = "#10b981"
    BTN_STOP  = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title("放置天堂 - 自動傳送腳本")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.settings = load_settings()
        self._monitor: Monitor | None = None
        self._thread:  threading.Thread | None = None
        self._preview_img = None
        self._build_ui()
        self._load_fields()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 建立 UI ────────────────────────────────────────────────────
    def _build_ui(self):
        pad = dict(padx=12, pady=6)

        # ── 標題列 ──
        hdr = tk.Frame(self, bg=self.ACCENT)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚔  放置天堂 自動傳送腳本",
                 bg=self.ACCENT, fg="#1e293b",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=6)
        self._status_lbl = tk.Label(hdr, text="待機", bg=self.ACCENT,
                                    fg="#1e293b", font=("Segoe UI", 10))
        self._status_lbl.pack(side="right", padx=12)

        # ── 主體分兩欄 ──
        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        left  = tk.Frame(body, bg=self.BG)
        right = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right.pack(side="right", fill="y", padx=(8, 0))

        # ── 左：圖片選擇 ──
        self._section(left, "頭目圖片")
        img_row = tk.Frame(left, bg=self.BG)
        img_row.pack(fill="x", **pad)
        self._tmpl_var = tk.StringVar()
        tk.Entry(img_row, textvariable=self._tmpl_var, width=28,
                 bg=self.PANEL_BG, fg=self.TEXT,
                 insertbackground=self.TEXT, relief="flat",
                 font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(img_row, text="瀏覽", command=self._browse_template,
                  bg=self.ACCENT, fg="#1e293b", relief="flat",
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=8).pack(side="left", padx=(6, 0))

        # 預覽框
        self._preview_lbl = tk.Label(left, bg=self.PANEL_BG,
                                     width=120, height=80,
                                     text="（尚未選擇圖片）",
                                     fg=self.SUBTEXT, font=("Segoe UI", 9))
        self._preview_lbl.pack(padx=12, pady=(0, 8))

        # ── 左：設定 ──
        self._section(left, "偵測設定")
        fields = [
            ("偵測間隔（秒）",  "check_interval", 1, 30,  1,   True),
            ("相似度門檻",       "threshold",      0.5, 1.0, 0.05, False),
            ("啟動等待（秒）",  "startup_wait",   5,  60,  1,   True),
            ("點擊間隔（秒）",  "click_delay",    0.2, 3.0, 0.1, False),
        ]
        self._vars = {}
        for label, key, lo, hi, step, is_int in fields:
            row = tk.Frame(left, bg=self.BG)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=self.BG, fg=self.TEXT,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            var = tk.DoubleVar() if not is_int else tk.IntVar()
            self._vars[key] = var
            spin = tk.Spinbox(row, from_=lo, to=hi, increment=step,
                              textvariable=var, width=7,
                              bg=self.PANEL_BG, fg=self.TEXT,
                              insertbackground=self.TEXT,
                              buttonbackground=self.PANEL_BG,
                              relief="flat", font=("Segoe UI", 9))
            spin.pack(side="left", ipady=3)

        # ── 左：按鈕文字 ──
        self._section(left, "按鈕文字（通常不須修改）")
        btn_fields = [("技能分頁文字", "skill_tab_text"), ("傳送技能文字", "teleport_text")]
        self._text_vars = {}
        for label, key in btn_fields:
            row = tk.Frame(left, bg=self.BG)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=self.BG, fg=self.SUBTEXT,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._text_vars[key] = var
            tk.Entry(row, textvariable=var, width=12,
                     bg=self.PANEL_BG, fg=self.TEXT,
                     insertbackground=self.TEXT,
                     relief="flat", font=("Segoe UI", 9)).pack(side="left", ipady=3)

        # ── 右：控制按鈕 + 狀態 ──
        self._section(right, "控制")
        self._start_btn = tk.Button(
            right, text="▶  開始監控", width=14,
            bg=self.BTN_START, fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            command=self._start, pady=8)
        self._start_btn.pack(padx=12, pady=(4, 6))

        self._stop_btn = tk.Button(
            right, text="■  停止", width=14,
            bg="#374151", fg=self.SUBTEXT, relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2",
            command=self._stop, pady=8, state="disabled")
        self._stop_btn.pack(padx=12, pady=(0, 4))

        tk.Button(right, text="💾  儲存設定", width=14,
                  bg=self.PANEL_BG, fg=self.TEXT, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  command=self._save).pack(padx=12, pady=(12, 2))

        # ── 日誌區 ──
        log_frame = tk.Frame(self, bg=self.BG)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._section(log_frame, "狀態日誌")
        self._log = scrolledtext.ScrolledText(
            log_frame, height=10, bg=self.PANEL_BG, fg=self.TEXT,
            font=("Consolas", 9), relief="flat", state="disabled",
            insertbackground=self.TEXT)
        self._log.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        # 日誌顏色 tag
        self._log.tag_config("ok",     foreground="#10b981")
        self._log.tag_config("warn",   foreground="#f59e0b")
        self._log.tag_config("error",  foreground="#ef4444")
        self._log.tag_config("info",   foreground="#94a3b8")
        self._log.tag_config("action", foreground="#60a5fa")

    def _section(self, parent, title: str):
        tk.Label(parent, text=f"  {title}",
                 bg=self.ACCENT, fg="#1e293b",
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(8, 2))

    # ── 資料載入 ────────────────────────────────────────────────────
    def _load_fields(self):
        self._tmpl_var.set(self.settings.get("template_path", ""))
        for key, var in self._vars.items():
            var.set(self.settings.get(key, DEFAULT_SETTINGS[key]))
        for key, var in self._text_vars.items():
            var.set(self.settings.get(key, DEFAULT_SETTINGS[key]))
        if self.settings.get("template_path"):
            self._refresh_preview(self.settings["template_path"])

    def _collect_settings(self) -> dict:
        s = self.settings.copy()
        s["template_path"] = self._tmpl_var.get()
        for key, var in self._vars.items():
            s[key] = var.get()
        for key, var in self._text_vars.items():
            s[key] = var.get()
        return s

    # ── 圖片瀏覽 / 預覽 ─────────────────────────────────────────────
    def _browse_template(self):
        path = filedialog.askopenfilename(
            title="選擇頭目圖片",
            filetypes=[("圖片", "*.png *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")])
        if path:
            self._tmpl_var.set(path)
            self._refresh_preview(path)

    def _refresh_preview(self, path: str):
        try:
            img = Image.open(path)
            img.thumbnail((120, 80))
            self._preview_img = ImageTk.PhotoImage(img)
            self._preview_lbl.config(image=self._preview_img, text="")
        except Exception:
            self._preview_lbl.config(image="", text="（無法載入圖片）")

    # ── 儲存 ────────────────────────────────────────────────────────
    def _save(self):
        self.settings = self._collect_settings()
        save_settings(self.settings)
        self._append_log("設定已儲存", "info")

    # ── 日誌 ────────────────────────────────────────────────────────
    def _append_log(self, msg: str, tag: str = "info"):
        def _do():
            self._log.config(state="normal")
            self._log.insert("end", msg + "\n", tag)
            self._log.see("end")
            self._log.config(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str, color: str = None):
        def _do():
            self._status_lbl.config(text=text)
            if color:
                self._status_lbl.config(fg=color)
        self.after(0, _do)

    # ── 開始 / 停止 ─────────────────────────────────────────────────
    def _start(self):
        self.settings = self._collect_settings()
        save_settings(self.settings)

        if not self.settings.get("template_path"):
            self._append_log("[錯誤] 請先選擇頭目圖片！", "error")
            return

        self._start_btn.config(state="disabled", bg="#374151", fg=self.SUBTEXT)
        self._stop_btn.config(state="normal",   bg=self.BTN_STOP, fg="white")

        self._monitor = Monitor(self.settings, self._append_log, self._set_status)
        self._thread  = threading.Thread(target=self._monitor.run, daemon=True)
        self._thread.start()
        self._set_status("監控中...", "#10b981")

    def _stop(self):
        if self._monitor:
            self._monitor.stop()
        self._start_btn.config(state="normal", bg=self.BTN_START, fg="white")
        self._stop_btn.config(state="disabled", bg="#374151", fg=self.SUBTEXT)
        self._set_status("已停止", "#6b7280")

    def _on_close(self):
        self._stop()
        self.after(500, self.destroy)


if __name__ == "__main__":
    app = App()
    app.mainloop()
