#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 分类管理器 — 图形界面版（v3 深色科技主题）
按科研工作流分类，批量控制 cc-switch 中 skill 在各 AI Agent 的启用状态。

支持的 Agent（与 cc-switch skills 表的 enabled_* 列一一对应）：
  Claude Code、Codex、Gemini CLI、Grok Build、OpenCode、Hermes、MiniMax Code(mcode)

交互亮点：
  - 深色科技风界面：渐变标题栏、卡片化布局、胶囊开关
  - 侧栏每个分类卡片右侧内嵌「一键开关」：整类统一开启/关闭（7 个 Agent），即时流畅
  - 明细区每个 skill 用「芯片按钮」独立控制 7 个 Agent，点击即切换、即时着色
  - 「扫描更新」自动发现新 skill；「新建类别」/下拉框归类即时保存
  - 「路径诊断」展示自动探测到的 cc-switch 相关路径
"""
import json
import os
import queue
import shutil
import sqlite3
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import ccswitch_paths

# 启动时自动探测 cc-switch 相关路径（数据库 / SSOT / 各 Agent 目录），部署无需手动配置。
_PATHS = ccswitch_paths.detect()
DB_PATH = _PATHS["db_path"]
SSOT = _PATHS["ssot_dir"]
AGENTS = _PATHS["agents"]          # 元素含 key / label / short / config_dir / skills_dir
AGENT_KEYS = [a["key"] for a in AGENTS]
APP_DIRS = {a["key"]: a["skills_dir"] for a in AGENTS}
COLUMNS = ccswitch_paths.COLUMNS

CAT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.json")

# 未分类视图的“选择键”
UNCAT = "◆ 未分类"
UNCAT_TITLE = "未分类"

FONT = "Microsoft YaHei UI"

# 深色科技主题配色
PALETTE = {
    "bg": "#0d1117",            # 主背景
    "panel": "#11161d",         # 侧栏面板
    "card": "#161b22",          # 卡片
    "card_hover": "#1b2330",    # 卡片悬停
    "border": "#262d38",        # 边框
    "border_hover": "#3b82f6",  # 悬停边框（强调蓝）
    "ink": "#e6edf3",           # 主文字
    "muted": "#8b949e",         # 次要文字
    "faint": "#6b7480",         # 弱文字
    "accent": "#3b82f6",        # 强调蓝
    "accent_hover": "#2f6fe0",
    "green": "#3fb950",
    "green_hover": "#2ea043",
    "red": "#f85149",
    "warn": "#d29922",
    "chip_on": "#2f6fe0",       # 芯片选中
    "chip_on_hover": "#3b82f6",
    "chip_off": "#21262d",      # 芯片未选
    "chip_off_hover": "#2d333b",
    "track_on": "#3b82f6",
    "track_off": "#3a4149",
    "header_top": "#1d4ed8",
    "header_mid": "#172a63",
    "header_bottom": "#0d1117",
}


# ---------- 底层操作（与 cc-switch 的 copy 同步机制一致） ----------

def load_categories():
    with open(CAT_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_categories(cats):
    with open(CAT_FILE, "w", encoding="utf-8") as f:
        json.dump(cats, f, ensure_ascii=False, indent=2)


def load_skills(con):
    cols = ", ".join(COLUMNS[k] for k in AGENT_KEYS)
    rows = con.execute(
        f"SELECT directory, name, description, {cols} FROM skills"
    ).fetchall()
    out = {}
    for d, name, desc, *flags in rows:
        out[d] = {"name": (name or "").strip() or d, "desc": (desc or "").strip()}
        for k, f in zip(AGENT_KEYS, flags):
            out[d][k] = bool(f)
    return out


def remove_dest(dest):
    if os.path.islink(dest):
        os.remove(dest)
    elif os.path.isdir(dest):
        shutil.rmtree(dest)
    elif os.path.exists(dest):
        os.remove(dest)


def copy_skill(directory, app):
    src = os.path.join(SSOT, directory)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        return f"{directory}: SSOT 缺少 SKILL.md"
    dest = os.path.join(APP_DIRS[app], directory)
    os.makedirs(APP_DIRS[app], exist_ok=True)
    remove_dest(dest)
    shutil.copytree(src, dest)
    return None


# ---------- 自定义控件 ----------

def _hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Switch(tk.Canvas):
    """胶囊形开关控件：开=蓝色轨道+圆点在右，关=灰色轨道+圆点在左。"""

    def __init__(self, parent, state=False, command=None, bg=PALETTE["card"],
                 on_color=PALETTE["track_on"], off_color=PALETTE["track_off"]):
        super().__init__(parent, width=46, height=24, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self._state = bool(state)
        self.command = command
        self.on_color = on_color
        self.off_color = off_color
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _toggle(self, _event=None):
        self.set(not self._state)
        if self.command:
            self.command(self._state)

    def set(self, state):
        self._state = bool(state)
        self._draw()

    def _draw(self):
        self.delete("all")
        w = int(self["width"])
        h = int(self["height"])
        track = self.on_color if self._state else self.off_color
        self.create_oval(1, 1, w - 1, h - 1, fill=track, outline="")
        r = h - 8
        y = (h - r) // 2
        x = w - r - 4 if self._state else 4
        self.create_oval(x, y, x + r, y + r, fill="#ffffff", outline="")


def flat_btn(parent, text, command, bg, fg, hover_bg=None, hover_fg=None,
             padx=14, pady=7, font=(FONT, 9), border=False, bold=False):
    hover_bg = hover_bg or bg
    hover_fg = hover_fg or fg
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                  activebackground=hover_bg, activeforeground=hover_fg,
                  relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 9, "bold") if bold else font,
                  padx=padx, pady=pady, highlightthickness=0)
    if border:
        b.configure(highlightbackground=PALETTE["border"], highlightcolor=PALETTE["border"],
                    highlightthickness=1)
    return b


# ---------- 界面 ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Skill 分类管理器")
        self.geometry("1060x680")
        self.minsize(920, 600)
        self.configure(bg=PALETTE["bg"])

        self.cats = load_categories()
        self.cat_order = list(self.cats.keys())
        self.con = sqlite3.connect(DB_PATH, timeout=15)
        self.skills = load_skills(self.con)
        self.pending = {d: {k: s[k] for k in AGENT_KEYS} for d, s in self.skills.items()}
        self.selected = None

        self.ui_queue = queue.Queue()
        self._build_style()
        self._build_ui()
        self._set_initial_selection()
        self._refresh_all()
        self.after(50, self._poll_queue)

    # ----- 样式 -----

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground="#21262d", background="#21262d",
                        foreground=PALETTE["ink"], arrowcolor=PALETTE["muted"],
                        bordercolor=PALETTE["border"], padding=3,
                        selectbackground="#30363d", selectforeground="#ffffff")
        style.map("TCombobox", fieldbackground=[("readonly", "#21262d")],
                  selectbackground=[("readonly", "#30363d")],
                  selectforeground=[("readonly", "#ffffff")])
        style.configure("Horizontal.TProgressbar", troughcolor="#21262d",
                        background=PALETTE["accent"], bordercolor="#21262d",
                        lightcolor=PALETTE["accent"], darkcolor=PALETTE["accent"])
        style.configure("Vertical.TScrollbar", background="#30363d",
                        troughcolor=PALETTE["panel"], bordercolor=PALETTE["panel"],
                        arrowcolor=PALETTE["muted"])

    # ----- 界面搭建 -----

    def _build_ui(self):
        # 渐变标题栏
        self.header = tk.Canvas(self, height=72, highlightthickness=0, bd=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self._paint_header)

        # 工具栏
        toolbar = tk.Frame(self, bg=PALETTE["panel"])
        toolbar.pack(fill="x")
        tk.Frame(toolbar, height=1, bg=PALETTE["border"]).pack(fill="x")
        tbar = tk.Frame(toolbar, bg=PALETTE["panel"])
        tbar.pack(fill="x", padx=14, pady=10)
        flat_btn(tbar, "↻ 扫描更新", self.on_rescan, PALETTE["accent"], "#ffffff",
                 PALETTE["accent_hover"]).pack(side="left", padx=(0, 6))
        flat_btn(tbar, "＋ 新建类别", self.on_new_category, PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="left", padx=6)
        flat_btn(tbar, "路径诊断", self.show_paths_dialog, PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="left", padx=6)

        self.apply_btn = flat_btn(tbar, "应用修改", self.on_apply, PALETTE["green"], "#ffffff",
                                  PALETTE["green_hover"], bold=True)
        self.apply_btn.pack(side="right", padx=(6, 0))
        flat_btn(tbar, "放弃修改", self.reset_pending, PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="right", padx=6)
        flat_btn(tbar, "全部关闭", lambda: self.set_all(False), PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="right", padx=6)
        flat_btn(tbar, "全部开启", lambda: self.set_all(True), PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="right", padx=6)

        # 主区域
        main = tk.Frame(self, bg=PALETTE["bg"])
        main.pack(fill="both", expand=True, padx=14, pady=12)

        # 左侧分类栏
        side = tk.Frame(main, bg=PALETTE["panel"], width=260, highlightthickness=1,
                        highlightbackground=PALETTE["border"])
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="分 类", bg=PALETTE["panel"], fg=PALETTE["muted"],
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        side_canvas = tk.Canvas(side, bg=PALETTE["panel"], highlightthickness=0, width=258)
        side_scroll = ttk.Scrollbar(side, orient="vertical", command=side_canvas.yview)
        self.side_inner = tk.Frame(side_canvas, bg=PALETTE["panel"])
        self.side_inner.bind("<Configure>",
                             lambda e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))
        side_canvas.create_window((0, 0), window=self.side_inner, anchor="nw")
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side_canvas.pack(side="left", fill="both", expand=True)
        side_scroll.pack(side="right", fill="y")

        # 右侧明细区
        detail = tk.Frame(main, bg=PALETTE["bg"])
        detail.pack(side="left", fill="both", expand=True, padx=(14, 0))

        dhead = tk.Frame(detail, bg=PALETTE["card"], highlightthickness=1,
                         highlightbackground=PALETTE["border"])
        dhead.pack(fill="x", pady=(0, 10))
        dl = tk.Frame(dhead, bg=PALETTE["card"])
        dl.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        self.detail_title = tk.Label(dl, text="", bg=PALETTE["card"], fg=PALETTE["ink"],
                                     font=(FONT, 13, "bold"), anchor="w")
        self.detail_title.pack(anchor="w")
        self.detail_sub = tk.Label(dl, text="", bg=PALETTE["card"], fg=PALETTE["muted"],
                                   font=(FONT, 9), anchor="w")
        self.detail_sub.pack(anchor="w")

        body = tk.Frame(detail, bg=PALETTE["card"], highlightthickness=1,
                        highlightbackground=PALETTE["border"])
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.detail_canvas = tk.Canvas(body, bg=PALETTE["card"], highlightthickness=0)
        dscroll = ttk.Scrollbar(body, orient="vertical", command=self.detail_canvas.yview)
        self.detail_inner = tk.Frame(self.detail_canvas, bg=PALETTE["card"])
        self.detail_inner.bind("<Configure>",
                               lambda e: self.detail_canvas.configure(
                                   scrollregion=self.detail_canvas.bbox("all")))
        self.detail_canvas.create_window((0, 0), window=self.detail_inner, anchor="nw")
        self.detail_canvas.configure(yscrollcommand=dscroll.set)
        self.detail_canvas.grid(row=0, column=0, sticky="nsew")
        dscroll.grid(row=0, column=1, sticky="ns")
        self.detail_canvas.bind_all("<MouseWheel>",
                                    lambda e: self.detail_canvas.yview_scroll(
                                        int(-e.delta / 120), "units"))

        # 状态栏
        self.status = tk.Label(self, text="就绪", anchor="w", bg=PALETTE["bg"],
                               fg=PALETTE["faint"], font=(FONT, 9))
        self.status.pack(fill="x", padx=16, pady=(4, 10))
        self.progress = ttk.Progressbar(self, mode="determinate")

    def _paint_header(self, _event=None):
        w = self.header.winfo_width()
        h = self.header.winfo_height()
        if w <= 1 or h <= 1:
            self.after(50, self._paint_header)
            return
        self.header.delete("all")
        c1 = _hex2rgb(PALETTE["header_top"])
        c2 = _hex2rgb(PALETTE["header_mid"])
        c3 = _hex2rgb(PALETTE["header_bottom"])
        half = w // 2
        for i in range(w):
            if i < half:
                t = i / max(1, half - 1)
                c = tuple(int(c1[j] + (c2[j] - c1[j]) * t) for j in range(3))
            else:
                t = (i - half) / max(1, w - half - 1)
                c = tuple(int(c2[j] + (c3[j] - c2[j]) * t) for j in range(3))
            self.header.create_line(i, 0, i, h, fill=f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
        self.header.create_text(24, 26, anchor="w", text="Skill 分类管理器",
                                fill="#ffffff", font=(FONT, 17, "bold"))
        self.header.create_text(24, 49, anchor="w",
                                text="按科研工作流分类 · 管理 7 个 AI Agent 的 skill 启用状态",
                                fill="#a9c1f0", font=(FONT, 9))

    # ----- 数据辅助 -----

    def cat_dirs(self, cat):
        return [d for d in self.cats.get(cat, []) if d in self.skills]

    def uncategorized(self):
        seen = set()
        for dirs in self.cats.values():
            seen.update(dirs)
        return [d for d in self.skills if d not in seen]

    def _cat_choices(self):
        return ["（选择分类）"] + self.cat_order + ["＋ 新建类别…"]

    def _cat_all_on(self, cat):
        dirs = self.cat_dirs(cat)
        if not dirs:
            return False
        return all(self.pending[d][k] for d in dirs for k in AGENT_KEYS)

    def _set_initial_selection(self):
        uncat = self.uncategorized()
        if uncat:
            self.selected = UNCAT
        elif self.cat_order:
            self.selected = self.cat_order[0]

    def _set_status(self, text):
        self.status.configure(text=text)

    # ----- 渲染 -----

    def _refresh_all(self):
        self._render_sidebar()
        self._render_detail()
        self._set_status(f"共 {len(self.skills)} 个 skill · {len(self.cat_order)} 个分类 · "
                         f"{len(self.uncategorized())} 个未分类")

    def _render_sidebar(self):
        for w in self.side_inner.winfo_children():
            w.destroy()
        uncat = self.uncategorized()
        if uncat:
            self._sidebar_row(UNCAT, f"待归类 · {len(uncat)} 个", special=True)
        for cat in self.cat_order:
            dirs = self.cat_dirs(cat)
            on_n = sum(1 for d in dirs if all(self.pending[d][k] for k in AGENT_KEYS))
            self._sidebar_row(cat, f"{len(dirs)} 个 skill · 全开 {on_n}", special=False)
        add = flat_btn(self.side_inner, "＋ 新建类别", self.on_new_category,
                       PALETTE["card"], PALETTE["accent"], PALETTE["card_hover"],
                       PALETTE["accent"], border=True)
        add.pack(fill="x", padx=12, pady=(12, 8))

    def _sidebar_row(self, key, subtitle, special=False):
        selected = (self.selected == key)
        bg = PALETTE["card"] if selected else PALETTE["panel"]
        card = tk.Frame(self.side_inner, bg=bg, highlightthickness=1,
                        highlightbackground=PALETTE["accent"] if selected else PALETTE["border"],
                        cursor="hand2")
        card.pack(fill="x", padx=10, pady=3)

        bar_color = PALETTE["accent"] if selected else (PALETTE["warn"] if special else PALETTE["border"])
        bar = tk.Frame(card, bg=bar_color, width=3)
        bar.pack(side="left", fill="y")

        txt = tk.Frame(card, bg=bg)
        txt.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=(9, 9))
        title = UNCAT_TITLE if special else key
        name_lbl = tk.Label(txt, text=title, bg=bg, fg=PALETTE["ink"],
                            font=(FONT, 10, "bold"), anchor="w")
        name_lbl.pack(anchor="w")
        sub = tk.Label(txt, text=subtitle, bg=bg, fg=PALETTE["faint"],
                       font=(FONT, 8), anchor="w")
        sub.pack(anchor="w")

        sw = Switch(card, state=self._cat_all_on(key), bg=bg,
                    command=lambda s, k=key: self.toggle_cat_all(k, s))
        sw.pack(side="right", padx=12)

        for w in (card, bar, txt, name_lbl, sub):
            w.bind("<Button-1>", lambda e, k=key: self.select(k))

        def _enter(_e):
            if not selected:
                card.configure(highlightbackground=PALETTE["border_hover"])

        def _leave(_e):
            card.configure(highlightbackground=PALETTE["accent"] if selected else PALETTE["border"])

        card.bind("<Enter>", _enter)
        card.bind("<Leave>", _leave)

    def _render_detail(self):
        for w in self.detail_inner.winfo_children():
            w.destroy()

        key = self.selected
        if key is None:
            self.detail_title.configure(text="Skill 分类管理器")
            self.detail_sub.configure(text="在左侧选择分类，查看并管理其中的 skill")
            tk.Label(self.detail_inner, text="← 在左侧选择一个分类",
                     bg=PALETTE["card"], fg=PALETTE["faint"],
                     font=(FONT, 11)).pack(expand=True, pady=50)
            return

        if key == UNCAT:
            dirs = sorted(self.uncategorized())
            self.detail_title.configure(text="未分类 skill", fg=PALETTE["warn"])
            self.detail_sub.configure(text="以下 skill 尚未归类，请为它们选择类别（也可新建类别）")
        else:
            dirs = sorted(self.cat_dirs(key))
            self.detail_title.configure(text=key, fg=PALETTE["ink"])
            self.detail_sub.configure(text=f"共 {len(dirs)} 个 skill · 点击芯片切换各 Agent · 下拉框调整分类")

        if not dirs:
            tk.Label(self.detail_inner, text="该分类暂无 skill",
                     bg=PALETTE["card"], fg=PALETTE["faint"],
                     font=(FONT, 11)).pack(expand=True, pady=50)
            return

        for d in dirs:
            self._detail_row(d, key)

    def _detail_row(self, d, key):
        meta = self.skills[d]
        card = tk.Frame(self.detail_inner, bg=PALETTE["card"], highlightthickness=1,
                        highlightbackground=PALETTE["border"])
        card.pack(fill="x", padx=4, pady=4)

        top = tk.Frame(card, bg=PALETTE["card"])
        top.pack(fill="x")
        left = tk.Frame(top, bg=PALETTE["card"])
        left.pack(side="left", fill="x", expand=True, padx=(12, 4), pady=(10, 0))
        tk.Label(left, text=meta["name"], bg=PALETTE["card"], fg=PALETTE["ink"],
                 font=(FONT, 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(left, text=d, bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=(FONT, 8), anchor="w").pack(anchor="w")
        if meta["desc"]:
            desc = " ".join(meta["desc"].split())
            if len(desc) > 64:
                desc = desc[:64] + "…"
            tk.Label(left, text=desc, bg=PALETTE["card"], fg=PALETTE["faint"],
                     font=(FONT, 8), anchor="w").pack(anchor="w")

        combo = ttk.Combobox(top, values=self._cat_choices(), state="readonly",
                             width=15, font=(FONT, 9))
        combo.set(UNCAT_TITLE if key == UNCAT else key)
        combo.pack(side="right", padx=10, pady=(10, 0))
        combo.bind("<<ComboboxSelected>>", lambda e, d=d, cb=combo: self.on_assign(d, cb))

        chips = tk.Frame(card, bg=PALETTE["card"])
        chips.pack(fill="x", padx=(12, 4), pady=(4, 12))
        tk.Label(chips, text="Agent:", bg=PALETTE["card"], fg=PALETTE["faint"],
                 font=(FONT, 8)).pack(side="left", padx=(0, 6))
        for agent in AGENTS:
            k = agent["key"]
            on = self.pending[d][k]
            b = tk.Button(chips, text=agent.get("short", agent["label"]),
                          bg=PALETTE["chip_on"] if on else PALETTE["chip_off"],
                          fg="#ffffff" if on else PALETTE["muted"],
                          activebackground=PALETTE["chip_on_hover"] if on else PALETTE["chip_off_hover"],
                          activeforeground="#ffffff" if on else PALETTE["ink"],
                          relief="flat", bd=0, cursor="hand2",
                          font=(FONT, 8), padx=9, pady=2, highlightthickness=0)
            b.configure(command=lambda d=d, k=k, b=b: self._toggle_agent(d, k, b))
            b.pack(side="left", padx=(0, 6))

    # ----- 交互 -----

    def select(self, key):
        self.selected = key
        self._render_sidebar()
        self._render_detail()

    def toggle_cat_all(self, cat, val):
        for d in self.cat_dirs(cat):
            for k in AGENT_KEYS:
                self.pending[d][k] = val
        self._render_sidebar()
        self._render_detail()

    def set_all(self, val):
        for d in self.pending:
            self.pending[d] = {k: val for k in AGENT_KEYS}
        self._render_sidebar()
        self._render_detail()

    def reset_pending(self):
        self.pending = {d: {k: s[k] for k in AGENT_KEYS} for d, s in self.skills.items()}
        self._render_sidebar()
        self._render_detail()

    def _toggle_agent(self, d, key, btn):
        self.pending[d][key] = not self.pending[d][key]
        on = self.pending[d][key]
        btn.configure(bg=PALETTE["chip_on"] if on else PALETTE["chip_off"],
                      fg="#ffffff" if on else PALETTE["muted"],
                      activebackground=PALETTE["chip_on_hover"] if on else PALETTE["chip_off_hover"],
                      activeforeground="#ffffff" if on else PALETTE["ink"])
        self._render_sidebar()

    # ----- 扫描 / 归类 / 新建类别 -----

    def show_paths_dialog(self):
        win = tk.Toplevel(self)
        win.title("cc-switch 路径诊断")
        win.geometry("700x500")
        win.configure(bg=PALETTE["bg"])
        win.transient(self)

        tk.Label(win, text="自动探测到的 cc-switch 相关路径", bg=PALETTE["bg"],
                 fg=PALETTE["ink"], font=(FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(14, 6))

        txt = tk.Text(win, wrap="none", bg=PALETTE["card"], fg=PALETTE["ink"],
                      insertbackground="#ffffff", font=("Consolas", 9), relief="flat",
                      highlightthickness=1, highlightbackground=PALETTE["border"],
                      padx=12, pady=12)
        txt.pack(fill="both", expand=True, padx=14)

        def _refresh():
            info = ccswitch_paths.detect()
            txt.delete("1.0", "end")
            txt.insert("1.0", ccswitch_paths.format_report(info))

        _refresh()

        bar = tk.Frame(win, bg=PALETTE["bg"])
        bar.pack(fill="x", padx=14, pady=12)
        flat_btn(bar, "重新探测", _refresh, PALETTE["accent"], "#ffffff",
                 PALETTE["accent_hover"]).pack(side="left")
        flat_btn(bar, "关闭", win.destroy, PALETTE["card"], PALETTE["muted"],
                 PALETTE["card_hover"], PALETTE["ink"], border=True).pack(side="right")

    def on_rescan(self):
        try:
            self.con.close()
        except Exception:
            pass
        try:
            self.con = sqlite3.connect(DB_PATH, timeout=15)
            self.skills = load_skills(self.con)
        except Exception as e:
            messagebox.showerror("扫描失败",
                                 f"无法读取数据库：{e}\n请确认 cc-switch 已安装且数据库存在。")
            return
        try:
            self.cats = load_categories()
        except Exception as e:
            messagebox.showerror("读取失败", f"categories.json 读取失败：{e}")
            return
        self.cat_order = list(self.cats.keys())
        self.pending = {d: {k: s[k] for k in AGENT_KEYS} for d, s in self.skills.items()}
        if self.selected not in (list(self.cats.keys()) + [UNCAT]):
            self._set_initial_selection()
        self._refresh_all()

    def on_new_category(self):
        name = simpledialog.askstring("新建类别", "请输入新类别名称：", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.cats:
            messagebox.showwarning("已存在", f"类别「{name}」已存在。")
            return
        self.cats[name] = []
        save_categories(self.cats)
        self.cat_order = list(self.cats.keys())
        self._refresh_all()

    def on_assign(self, d, combo):
        val = combo.get()
        if val == "＋ 新建类别…":
            name = simpledialog.askstring("新建类别", "请输入新类别名称：", parent=self)
            if not name or not name.strip():
                return
            name = name.strip()
            if name not in self.cats:
                self.cats[name] = []
            self.assign_skill(d, name)
            return
        if val in ("", "（选择分类）", UNCAT_TITLE):
            return
        self.assign_skill(d, val)

    def assign_skill(self, d, new_cat):
        if new_cat not in self.cats:
            return
        for dirs in self.cats.values():
            if d in dirs:
                dirs.remove(d)
        self.cats[new_cat].append(d)
        save_categories(self.cats)
        self.cat_order = list(self.cats.keys())
        self._refresh_all()

    # ----- 应用修改 -----

    def on_apply(self):
        to_on, to_off = [], []
        for d in self.pending:
            for app in AGENT_KEYS:
                want, have = self.pending[d][app], self.skills[d][app]
                if want and not have:
                    to_on.append((d, app))
                elif not want and have:
                    to_off.append((d, app))
        n = len(to_on) + len(to_off)
        if n == 0:
            messagebox.showinfo("提示", "没有需要修改的项。")
            return
        if not messagebox.askyesno("确认", f"将启用 {len(to_on)} 项、禁用 {len(to_off)} 项，继续？"):
            return
        self.apply_btn.configure(state="disabled")
        self._set_status(f"正在应用… 0/{n}")
        self.progress.pack(fill="x", padx=16, before=self.status)
        self.progress.configure(maximum=n, value=0)

        def work():
            done = 0
            errors = []
            db_updates = []
            for dirs_apps, enabled in ((to_on, True), (to_off, False)):
                for d, app in dirs_apps:
                    try:
                        if enabled:
                            err = copy_skill(d, app)
                            if err:
                                errors.append(err)
                        else:
                            remove_dest(os.path.join(APP_DIRS[app], d))
                        db_updates.append((COLUMNS[app], 1 if enabled else 0, d))
                    except Exception as e:
                        errors.append(f"{d}（{app}）: {e}")
                    done += 1
                    self.ui_queue.put(("tick", done, n))
            self.ui_queue.put(("finish", db_updates, done, errors))

        threading.Thread(target=work, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                if msg[0] == "tick":
                    self._apply_tick(msg[1], msg[2])
                elif msg[0] == "finish":
                    self._apply_finish(msg[1], msg[2], msg[3])
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _apply_tick(self, done, n):
        self.progress.configure(value=done)
        self._set_status(f"正在应用… {done}/{n}")

    def _apply_finish(self, db_updates, done, errors):
        try:
            for col, val, d in db_updates:
                self.con.execute(f"UPDATE skills SET {col} = ? WHERE directory = ?", (val, d))
            self.con.commit()
        except Exception as e:
            errors.append(f"数据库写入失败: {e}（若 cc-switch 正在运行请先退出，再重新点「应用修改」）")
        self.progress.pack_forget()
        self.skills = load_skills(self.con)
        self.pending = {d: {k: s[k] for k in AGENT_KEYS} for d, s in self.skills.items()}
        self.apply_btn.configure(state="normal")
        self._refresh_all()
        if errors:
            self._set_status(f"已处理 {done} 项，其中 {len(errors)} 个失败。")
            messagebox.showwarning(
                "部分失败", "\n".join(errors[:10]) + ("\n…" if len(errors) > 10 else ""))
        else:
            self._set_status(f"完成：已更新 {done} 项。重新打开 cc-switch 可见一致状态。")


if __name__ == "__main__":
    if not os.path.isfile(DB_PATH):
        sys.exit("未找到 cc-switch 数据库: " + DB_PATH)
    app = App()
    app.mainloop()
