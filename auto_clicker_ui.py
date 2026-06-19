"""
放置天堂 - 頭目自動偵測 + 傳送術（DOM 偵測版）
偵測頁面上「頭目」文字標籤，不需要截圖比對
"""

import os, sys, time, json, threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, NoSuchElementException


# ─── 路徑 / 設定 ──────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(get_base_dir(), "settings.json")

DEFAULT = {
    "game_url":       "https://pp771007.github.io/idle-lineage-class/",
    "boss_keyword":   "頭目",        # 頁面上出現此文字 = 有頭目
    "check_interval": 5,             # 偵測間隔（秒）
    "startup_wait":   20,            # 等待載入存檔的秒數
    "click_delay":    1.0,           # 每次點擊後延遲
    "skill_tab":      "技能",
    "teleport_btn":   "傳送術",
}

def load_cfg():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return {**DEFAULT, **json.load(f)}
    except Exception:
        return DEFAULT.copy()

def save_cfg(d):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# ─── 監控執行緒 ──────────────────────────────────────────────────────
class Monitor:
    def __init__(self, cfg, log_fn, status_fn):
        self.cfg = cfg
        self.log = log_fn
        self.set_status = status_fn
        self._stop = threading.Event()
        self.driver = None

    def stop(self):
        self._stop.set()

    def has_boss(self):
        """頁面上是否出現「頭目」文字"""
        try:
            elems = self.driver.find_elements(
                By.XPATH, f"//*[contains(text(), '{self.cfg['boss_keyword']}')]"
            )
            return len(elems) > 0
        except Exception:
            return False

    def safe_click(self, text):
        for xpath in [
            f"//*[normalize-space(text())='{text}']",
            f"//*[contains(text(),'{text}')]",
            f"//button[contains(.,'{text}')]",
            f"//span[contains(.,'{text}')]",
        ]:
            try:
                el = self.driver.find_element(By.XPATH, xpath)
                self.driver.execute_script("arguments[0].click();", el)
                return True
            except NoSuchElementException:
                continue
            except Exception:
                continue
        return False

    def do_teleport(self):
        skill = self.cfg["skill_tab"]
        tp    = self.cfg["teleport_btn"]

        self.log(f"  → 點擊「{skill}」", "action")
        if not self.safe_click(skill):
            self.log(f"  ✗ 找不到「{skill}」", "warn")
            return
        time.sleep(self.cfg["click_delay"])

        self.log(f"  → 點擊「{tp}」", "action")
        if self.safe_click(tp):
            self.log("  ✓ 傳送術施放完成", "ok")
        else:
            self.log(f"  ✗ 找不到「{tp}」（確認技能欄是否顯示）", "warn")
        time.sleep(self.cfg["click_delay"])

    def run(self):
        # ── 啟動 Chrome ──
        profile = os.path.join(get_base_dir(), "ChromeProfile")
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={profile}")
        opts.add_argument("--no-first-run")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-extensions")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.log("[啟動] 正在開啟 Chrome...", "info")
        try:
            self.driver = webdriver.Chrome(options=opts)
        except WebDriverException as e:
            msg = str(e).split("\n")[0]
            self.log(f"[錯誤] Chrome 啟動失敗：{msg}", "error")
            self.set_status("Chrome 啟動失敗", "red")
            messagebox.showerror(
                "Chrome 啟動失敗",
                f"無法開啟 Chrome，請確認已安裝 Google Chrome。\n\n錯誤：{msg}"
            )
            return
        except Exception as e:
            self.log(f"[錯誤] 未知錯誤：{e}", "error")
            self.set_status("錯誤", "red")
            return

        self.driver.maximize_window()
        self.driver.get(self.cfg["game_url"])

        sw = int(self.cfg["startup_wait"])
        self.log(f"[等待] 請在 {sw} 秒內於 Chrome 載入存檔...", "info")
        for i in range(sw):
            if self._stop.is_set():
                self.driver.quit()
                self.set_status("已停止", "#6b7280")
                return
            self.set_status(f"等待載入存檔（剩 {sw-i}s）...", "#f59e0b")
            time.sleep(1)

        self.log("[開始] 開始偵測頭目...", "info")
        self.set_status("監控中", "#10b981")

        while not self._stop.is_set():
            ts = time.strftime("%H:%M:%S")
            try:
                found = self.has_boss()
            except WebDriverException:
                self.log("[停止] 瀏覽器已關閉", "warn")
                break

            if found:
                self.log(f"[{ts}] ✓ 偵測到頭目，等待中...", "ok")
            else:
                self.log(f"[{ts}] ✗ 沒有頭目 → 執行傳送術", "warn")
                self.do_teleport()

            self._stop.wait(self.cfg["check_interval"])

        try:
            self.driver.quit()
        except Exception:
            pass
        self.set_status("已停止", "#6b7280")
        self.log("[結束] 監控已停止", "info")


# ─── UI ──────────────────────────────────────────────────────────────
class App(tk.Tk):
    BG       = "#1e293b"
    PANEL    = "#0f172a"
    ACCENT   = "#f59e0b"
    TEXT     = "#e2e8f0"
    SUB      = "#94a3b8"
    GREEN    = "#10b981"
    RED      = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title("放置天堂 - 自動傳送腳本")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.cfg = load_cfg()
        self._monitor = None
        self._thread  = None
        self._build_ui()
        self._load_fields()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 建 UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        # 標題列
        hdr = tk.Frame(self, bg=self.ACCENT)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚔  放置天堂 自動傳送腳本",
                 bg=self.ACCENT, fg="#1e293b",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=7)
        self._status_lbl = tk.Label(hdr, text="待機",
                                    bg=self.ACCENT, fg="#1e293b",
                                    font=("Segoe UI", 10))
        self._status_lbl.pack(side="right", padx=12)

        # 主體
        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", padx=14, pady=10)

        # ── 設定欄位 ──
        self._section(body, "偵測設定")
        spin_fields = [
            ("偵測間隔（秒）",   "check_interval", 1,   60,  1,    True),
            ("啟動等待（秒）",   "startup_wait",   5,   120, 1,    True),
            ("點擊間隔（秒）",   "click_delay",    0.2, 5.0, 0.1,  False),
        ]
        self._vars = {}
        for label, key, lo, hi, step, is_int in spin_fields:
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

        self._section(body, "按鈕文字（通常不須修改）")
        text_fields = [
            ("技能分頁文字", "skill_tab"),
            ("傳送技能文字", "teleport_btn"),
            ("頭目偵測關鍵字", "boss_keyword"),
        ]
        self._txt = {}
        for label, key in text_fields:
            row = tk.Frame(body, bg=self.BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=self.BG, fg=self.SUB,
                     font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._txt[key] = var
            tk.Entry(row, textvariable=var, width=14,
                     bg=self.PANEL, fg=self.TEXT,
                     insertbackground=self.TEXT,
                     relief="flat", font=("Segoe UI", 9)
                     ).pack(side="left", ipady=4)

        # ── 控制按鈕 ──
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
                  padx=10, pady=8,
                  command=self._save).pack(side="left")

        # ── 日誌 ──
        self._section(body, "狀態日誌")
        self._log_box = scrolledtext.ScrolledText(
            body, height=12,
            bg=self.PANEL, fg=self.TEXT,
            font=("Consolas", 9), relief="flat",
            state="disabled", insertbackground=self.TEXT)
        self._log_box.pack(fill="both", expand=True, pady=(0, 4))
        self._log_box.tag_config("ok",     foreground="#10b981")
        self._log_box.tag_config("warn",   foreground="#f59e0b")
        self._log_box.tag_config("error",  foreground="#ef4444")
        self._log_box.tag_config("info",   foreground="#94a3b8")
        self._log_box.tag_config("action", foreground="#60a5fa")

    def _section(self, parent, title):
        tk.Label(parent, text=f"  {title}",
                 bg=self.ACCENT, fg="#1e293b",
                 font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(10, 4))

    # ── 資料 ────────────────────────────────────────────────────────
    def _load_fields(self):
        for k, v in self._vars.items():
            v.set(self.cfg.get(k, DEFAULT[k]))
        for k, v in self._txt.items():
            v.set(self.cfg.get(k, DEFAULT[k]))

    def _collect(self):
        d = self.cfg.copy()
        for k, v in self._vars.items():
            d[k] = v.get()
        for k, v in self._txt.items():
            d[k] = v.get()
        return d

    def _save(self):
        self.cfg = self._collect()
        save_cfg(self.cfg)
        self._append_log("設定已儲存", "info")

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

    # ── 開始 / 停止 ──────────────────────────────────────────────────
    def _start(self):
        self.cfg = self._collect()
        save_cfg(self.cfg)
        self._start_btn.config(state="disabled", bg="#374151", fg=self.SUB)
        self._stop_btn.config(state="normal",   bg=self.RED,  fg="white")
        self._set_status("啟動中...", self.ACCENT)
        self._monitor = Monitor(self.cfg, self._append_log, self._set_status)
        self._thread  = threading.Thread(target=self._monitor.run, daemon=True)
        self._thread.start()

    def _stop(self):
        if self._monitor:
            self._monitor.stop()
        self._start_btn.config(state="normal", bg=self.GREEN, fg="white")
        self._stop_btn.config(state="disabled", bg="#374151", fg=self.SUB)

    def _on_close(self):
        self._stop()
        self.after(600, self.destroy)


if __name__ == "__main__":
    app = App()
    app.mainloop()
