#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 分类管理器 — 本地 Web 服务端

提供 REST API，前端为 cc-switch 风格的现代 Web 界面（web/ 目录）。
双击「技能分类管理器.bat」会启动本服务并自动打开浏览器。

依赖：仅 Python 标准库（http.server / sqlite3 / json），无需任何第三方库。
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import ccswitch_paths

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
CAT_FILE = os.path.join(BASE_DIR, "categories.json")

AGENTS = ccswitch_paths.AGENTS
AGENT_KEYS = ccswitch_paths.AGENT_KEYS
COLUMNS = ccswitch_paths.COLUMNS
APP_DIRS = ccswitch_paths.resolve_agent_skills_dirs()

PORT = 8765

_lock = threading.RLock()
_con = None
_skills = {}     # dir -> {name, desc, **agent_bool}
_pending = {}    # dir -> {agent: bool}
_cats = {}       # cat -> [dirs]
_cat_order = []
_ai_plan = None  # 待确认的 AI 分类方案缓存
# 应用修改的进度状态（后台线程执行，前端轮询）
_apply_state = {"running": False, "done": 0, "total": 0, "errors": [],
                "finished": False, "on": 0, "off": 0}


# ---------- 数据层 ----------

def db_path():
    return ccswitch_paths.resolve_db_path()


def ssot_dir():
    return ccswitch_paths.resolve_ssot_dir()


def connect_db():
    global _con
    _con = sqlite3.connect(db_path(), timeout=15, check_same_thread=False)
    _con.row_factory = sqlite3.Row


def load_categories():
    try:
        with open(CAT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_categories(c):
    """原子写入：先写临时文件再 os.replace，避免中途中断损坏 categories.json。"""
    tmp = CAT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CAT_FILE)


def load_skills():
    cols = ", ".join(COLUMNS[k] for k in AGENT_KEYS)
    rows = _con.execute(f"SELECT directory, name, description, {cols} FROM skills").fetchall()
    out = {}
    for r in rows:
        d = r["directory"]
        out[d] = {"name": (r["name"] or "").strip() or d, "desc": (r["description"] or "").strip()}
        for k in AGENT_KEYS:
            out[d][k] = bool(r[COLUMNS[k]])
    return out


def remove_dest(dest):
    """删除目标路径（仅限 agent skills 目录内的路径，防止误删）。"""
    dest = os.path.abspath(dest)
    # 安全校验：dest 必须位于某个 agent skills 根目录之内
    allowed = [os.path.abspath(p) for p in APP_DIRS.values() if p]
    if not any(dest == root or dest.startswith(root + os.sep) for root in allowed):
        return  # 拒绝删除允许目录之外的路径
    if os.path.islink(dest):
        os.remove(dest)
    elif os.path.isdir(dest):
        shutil.rmtree(dest)
    elif os.path.exists(dest):
        os.remove(dest)


def copy_skill(directory, app):
    src = os.path.join(ssot_dir(), directory)
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        return f"{directory}: SSOT 缺少 SKILL.md"
    dest = os.path.join(APP_DIRS[app], directory)
    os.makedirs(APP_DIRS[app], exist_ok=True)
    remove_dest(dest)
    shutil.copytree(src, dest)
    return None


def cat_of(d):
    for cat, dirs in _cats.items():
        if d in dirs:
            return cat
    return None


def reload_state():
    global _skills, _pending, _cats, _cat_order
    _skills = load_skills()
    _pending = {d: {k: s[k] for k in AGENT_KEYS} for d, s in _skills.items()}
    _cats = load_categories()
    _cat_order = list(_cats.keys())


def state_payload():
    skills_list = []
    for d in sorted(_skills):
        s = _skills[d]
        skills_list.append({
            "dir": d,
            "name": s["name"],
            "desc": s["desc"],
            "cat": cat_of(d),
            "saved": {k: s[k] for k in AGENT_KEYS},
            "pending": {k: _pending[d][k] for k in AGENT_KEYS},
        })
    dirty = any(_pending[d][k] != _skills[d][k] for d in _pending for k in AGENT_KEYS)
    return {
        "agents": [{"key": a["key"], "label": a["label"], "short": a["short"]} for a in AGENTS],
        "categories": _cat_order,
        "uncategorized": [d for d in sorted(_skills) if cat_of(d) is None],
        "skills": skills_list,
        "dirty": dirty,
        "paths": ccswitch_paths.format_report(),
    }


# ---------- 操作 ----------

def _toggle_skill(data):
    d, agent = data.get("dir"), data.get("agent")
    if d not in _pending or agent not in AGENT_KEYS:
        return {"error": "参数错误"}
    if "on" in data:
        _pending[d][agent] = bool(data["on"])
    else:
        _pending[d][agent] = not _pending[d][agent]
    return state_payload()


def _toggle_category(data):
    cat, agent = data.get("category"), data.get("agent")
    if agent not in AGENT_KEYS:
        return {"error": "参数错误"}
    if cat == "◆ 未分类":
        dirs = [d for d in _skills if cat_of(d) is None]
    elif cat in _cats:
        dirs = [d for d in _cats[cat] if d in _pending]
    else:
        return {"error": "分类不存在"}
    if "on" in data:
        val = bool(data["on"])
    else:
        # 当前是否全开
        val = not (dirs and all(_pending[d][agent] for d in dirs))
    for d in dirs:
        _pending[d][agent] = val
    return state_payload()


def _set_all(data):
    val = bool(data.get("on", True))
    for d in _pending:
        for k in AGENT_KEYS:
            _pending[d][k] = val
    return state_payload()


def _reset():
    _pending.clear()
    _pending.update({d: {k: s[k] for k in AGENT_KEYS} for d, s in _skills.items()})
    return state_payload()


def _scan():
    global _ai_plan
    try:
        _con.close()
    except Exception:
        pass
    connect_db()
    reload_state()
    # 扫描后 _skills 已变化，旧方案可能作用在新数据上，清空待确认方案
    _ai_plan = None
    return state_payload()


def _assign(data):
    d = data.get("dir")
    cat = data.get("category") or ""
    if d not in _skills:
        return {"error": "参数错误"}
    # 先从所有分类移除
    for dirs in _cats.values():
        if d in dirs:
            dirs.remove(d)
    # category 为空表示「移出分类」（回到未分类）；非空则加入该分类
    if cat:
        if cat not in _cats:
            _cats[cat] = []
        _cats[cat].append(d)
    save_categories(_cats)
    _cat_order = list(_cats.keys())
    return state_payload()


def _newcat(data):
    name = (data.get("name") or "").strip()
    if not name:
        return {"error": "名称为空"}
    if name in _cats:
        return {"error": "分类已存在"}
    _cats[name] = []
    save_categories(_cats)
    _cat_order = list(_cats.keys())
    return state_payload()


def _delcat(data):
    """删除分类：将其中的 skill 移回「未分类」，并删除该分类本身。"""
    cat = (data.get("category") or "").strip()
    if not cat:
        return {"error": "分类为空"}
    if cat not in _cats:
        return {"error": "分类不存在"}
    # 直接移除该分类（其中的 skill 自动回到未分类，因为 cat_of 不再匹配）
    del _cats[cat]
    save_categories(_cats)
    _cat_order = list(_cats.keys())
    return state_payload()


# ---------- AI 智能分类 ----------

def _read_ccswitch_ai_config():
    """从 cc-switch 数据库读取已配置的 AI 接口（优先 OpenAI 兼容，其次 Anthropic 兼容）。

    返回 {"base_url":..., "api_key":..., "model":..., "auth_style": "openai"|"anthropic",
          "models": [可选模型名列表]}
    或 None（未找到可用配置）。
    """
    try:
        con = sqlite3.connect(db_path(), timeout=10)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, app_type, settings_config, is_current FROM providers").fetchall()
        # 读取 provider_endpoints 表里的实际端点 URL，按 provider_id 关联（优先于硬编码兜底）
        endpoints = {}
        try:
            for ep in con.execute("SELECT provider_id, url FROM provider_endpoints").fetchall():
                endpoints[ep["provider_id"]] = (ep["url"] or "").strip().rstrip("/")
        except Exception:
            pass
        con.close()
    except Exception:
        return None

    # 候选顺序：优先 OpenAI 兼容（codex），其次 Anthropic 兼容（claude-desktop）
    openai_cfg, anthropic_cfg = None, None
    for r in rows:
        try:
            sc = json.loads(r["settings_config"]) if r["settings_config"] else {}
        except Exception:
            sc = {}
        # 按 provider_id 精确取该 provider 记录的实际 URL
        endpoint_url = endpoints.get(r["id"]) or None
        if r["app_type"] == "codex" and sc.get("auth", {}).get("OPENAI_API_KEY"):
            base = None
            model = "deepseek-chat"
            cfg = sc.get("config", "") or ""
            # 尝试从 config 里解析 model / base_url
            for line in cfg.splitlines():
                line = line.strip()
                if line.startswith("model =") and '"' in line:
                    model = line.split('"', 2)[1]
                elif line.startswith("base_url =") and '"' in line:
                    base = line.split('"', 2)[1]
            # 兜底优先级：config 里的 base_url > provider_endpoints 的实际 URL > 默认 DeepSeek
            base = base or endpoint_url or "https://api.deepseek.com"
            # 从 modelCatalog 提取可用模型列表
            models = []
            for m in (sc.get("modelCatalog", {}).get("models") or []):
                if isinstance(m, dict) and m.get("model"):
                    models.append(m["model"])
            if not models:
                models = [model]
            if not openai_cfg:
                openai_cfg = {"base_url": base.rstrip("/"), "api_key": sc["auth"]["OPENAI_API_KEY"],
                              "model": model, "auth_style": "openai", "models": models}
        elif r["app_type"] == "claude-desktop" and sc.get("env", {}).get("ANTHROPIC_AUTH_TOKEN"):
            base = sc["env"].get("ANTHROPIC_BASE_URL") or endpoint_url or "https://api.deepseek.com/anthropic"
            if not anthropic_cfg:
                anthropic_cfg = {"base_url": base.rstrip("/"), "api_key": sc["env"]["ANTHROPIC_AUTH_TOKEN"],
                                 "model": "deepseek-chat", "auth_style": "anthropic",
                                 "models": ["deepseek-chat"]}
    return openai_cfg or anthropic_cfg


def _call_llm(cfg, system, user):
    """调用大模型，返回纯文本回复；失败抛异常。"""
    if cfg["auth_style"] == "anthropic":
        url = cfg["base_url"].rstrip("/") + "/v1/messages"
        body = {
            "model": cfg["model"],
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {"Content-Type": "application/json",
                   "x-api-key": cfg["api_key"],
                   "anthropic-version": "2023-06-01"}
    else:
        url = cfg["base_url"].rstrip("/") + "/v1/chat/completions"
        body = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cfg['api_key']}"}

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if cfg["auth_style"] == "anthropic":
        return data["content"][0]["text"]
    return data["choices"][0]["message"]["content"]


def _ai_classify(data):
    """AI 智能分类（第一步·生成方案）：调用大模型给出分类方案，**不写入任何数据**。

    返回 preview 字段：每个 skill 的目录名 → 目标分类，供前端预览。
    方案缓存在 _ai_plan 中，待用户确认后由 _ai_apply 落地。

    入参：
      instruction : 用户写的一行分类意图（可空）
      scope       : "uncategorized" | "all" | "current" | "selected"
      category    : scope="current" 时的单个分类名
      categories  : scope="selected" 时的分类名列表（多选）
      model       : 指定模型名（可空，缺省用配置里的默认模型）
    """
    global _cats, _cat_order, _ai_plan
    instruction = (data.get("instruction") or "").strip()
    scope = data.get("scope") or "uncategorized"
    model = (data.get("model") or "").strip()

    cfg = _read_ccswitch_ai_config()
    if not cfg:
        return {"error": "未在 cc-switch 中找到可用的 AI 接口配置。请先在 cc-switch 里配置一个 OpenAI/Anthropic 兼容的 Provider（如 DeepSeek）。"}

    # 指定模型（若在可用列表内）
    if model and model in cfg.get("models", []):
        cfg["model"] = model

    # 确定待分类范围
    if scope == "all":
        targets = sorted(_skills)
    elif scope == "uncategorized":
        targets = [d for d in sorted(_skills) if cat_of(d) is None]
    elif scope == "current":
        cat = (data.get("category") or "").strip()
        targets = [d for d in (_cats.get(cat) or []) if d in _skills]
    elif scope == "selected":
        cats = data.get("categories") or []
        if not isinstance(cats, list):
            return {"error": "categories 参数应为列表"}
        targets = []
        for c in cats:
            for d in (_cats.get(c) or []):
                if d in _skills and d not in targets:
                    targets.append(d)
        targets.sort()
    elif scope in _cats:
        targets = [d for d in _cats[scope] if d in _skills]
    else:
        return {"error": "无效的分类范围"}

    if not targets:
        return {"error": "该范围内没有可分类的 skill"}

    # 构建 skill 清单（目录名 + 描述）
    skill_desc = []
    for d in targets:
        s = _skills[d]
        desc = (s.get("desc") or "").strip()
        skill_desc.append(f"- {d}" + (f"：{desc}" if desc else ""))
    skill_text = "\n".join(skill_desc)

    existing_cats = "\n".join(_cat_order) if _cat_order else "（当前还没有任何分类）"

    system = (
        "你是半导体/科研工作流的 skill 分类助手。请把给定的 skill（每个是一行「目录名：描述」）"
        "归入合适的分类。你可以使用已有的分类，也可以提出新分类。"
        "分类应简洁、有编号前缀（如 07_其他）。"
    )
    user = (
        f"现有分类：\n{existing_cats}\n\n"
        f"待分类的 skill：\n{skill_text}\n\n"
    )
    if instruction:
        user += f"用户希望的分类方式：{instruction}\n\n"
    user += (
        "请只输出一个 JSON 对象，格式为 {\"分类名\": [\"skill目录名\", ...]}，"
        "把所有 skill 都归入某个分类，不要输出任何 JSON 以外的文字、解释或代码块标记。"
    )

    try:
        raw = _call_llm(cfg, system, user)
    except Exception as e:
        return {"error": f"调用大模型失败：{e}"}

    # 解析 JSON（容忍代码块包裹）
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        result = json.loads(raw)
    except Exception:
        return {"error": f"大模型返回的内容无法解析为 JSON：{raw[:500]}", "raw": raw}

    if not isinstance(result, dict):
        return {"error": "大模型返回格式不正确（应为对象）", "raw": raw}

    # 生成预览方案（dir -> 目标分类），不写入数据
    plan = {}
    created = []
    for cat, dirs in result.items():
        cat = (cat or "").strip()
        if not cat:
            continue
        if cat not in _cats:
            created.append(cat)
        if not isinstance(dirs, list):
            continue
        for d in dirs:
            if d not in _skills:
                continue
            plan[d] = cat

    if not plan:
        return {"error": "大模型未返回任何可用的归类结果", "raw": raw}

    # 缓存方案（含新建分类清单），等待用户确认
    _ai_plan = {"plan": plan, "created": created, "scope": scope, "model": cfg["model"]}

    return {
        "preview": [{"dir": d, "name": _skills[d]["name"], "to": plan[d],
                     "from": cat_of(d)} for d in targets if d in plan],
        "created_categories": created,
        "applied": len(plan),
        "model": cfg["model"],
        "scope": scope,
    }


def _ai_apply(data):
    """AI 智能分类（第二步·确认落地）：把缓存方案真正写入 categories.json。"""
    global _cats, _cat_order, _ai_plan
    if not _ai_plan:
        return {"error": "没有待确认的 AI 分类方案，请先执行一次「AI 智能分类」"}

    plan = _ai_plan["plan"]
    created = _ai_plan["created"]

    # 新建分类（空分类）
    for cat in created:
        if cat not in _cats:
            _cats[cat] = []

    # 归入：先把每个 dir 从所有分类移除，再加入目标分类
    for d, cat in plan.items():
        for existing_dirs in _cats.values():
            if d in existing_dirs:
                existing_dirs.remove(d)
        # 防御：目标分类若因边界情况（大小写/全半角差异、方案生成后分类被改动）不存在，则补建
        if cat not in _cats:
            _cats[cat] = []
            if cat not in created:
                created.append(cat)
        _cats[cat].append(d)

    save_categories(_cats)
    _cat_order = list(_cats.keys())

    payload = state_payload()
    payload["ai"] = {"applied": len(plan), "created_categories": created,
                     "scope": _ai_plan["scope"], "model": _ai_plan["model"]}
    _ai_plan = None
    return payload


def _ai_config_info():
    """返回当前可用的 AI 接口信息（脱敏），供前端展示。"""
    cfg = _read_ccswitch_ai_config()
    if not cfg:
        return {"available": False}
    return {"available": True, "model": cfg["model"], "models": cfg.get("models", [cfg["model"]]),
            "auth_style": cfg["auth_style"], "base_url": cfg["base_url"]}


def _start_apply():
    """启动后台应用线程，立即返回；前端通过 /api/apply_status 轮询进度。"""
    global _apply_state
    with _lock:
        if _apply_state["running"]:
            return {"started": False, "message": "应用正在进行中"}
        to_on, to_off = [], []
        for d in _pending:
            for k in AGENT_KEYS:
                want, have = _pending[d][k], _skills[d][k]
                if want and not have:
                    to_on.append((d, k))
                elif not want and have:
                    to_off.append((d, k))
        if not to_on and not to_off:
            return {"started": False, "message": "没有需要修改的项"}
        _apply_state = {"running": True, "done": 0, "total": len(to_on) + len(to_off),
                        "errors": [], "finished": False, "on": len(to_on), "off": len(to_off)}
    threading.Thread(target=_apply_worker, args=(to_on, to_off), daemon=True).start()
    return {"started": True, "total": len(to_on) + len(to_off),
            "on": len(to_on), "off": len(to_off)}


def _apply_worker(to_on, to_off):
    global _apply_state
    errors = []
    db_on, db_off = [], []
    done = 0
    for d, k in to_on:
        err = copy_skill(d, k)
        if err:
            errors.append(err)
        else:
            db_on.append((d, k))
        done += 1
        with _lock:
            _apply_state["done"] = done
    for d, k in to_off:
        remove_dest(os.path.join(APP_DIRS[k], d))
        db_off.append((d, k))
        done += 1
        with _lock:
            _apply_state["done"] = done
    with _lock:
        for d, k in db_on:
            _con.execute(f"UPDATE skills SET {COLUMNS[k]} = 1 WHERE directory = ?", (d,))
        for d, k in db_off:
            _con.execute(f"UPDATE skills SET {COLUMNS[k]} = 0 WHERE directory = ?", (d,))
        try:
            _con.commit()
        except Exception as e:
            errors.append(f"数据库写入失败: {e}（若 cc-switch 正在运行请先退出）")
        _skills.clear()
        _skills.update(load_skills())
        _pending.clear()
        _pending.update({d: {k: s[k] for k in AGENT_KEYS} for d, s in _skills.items()})
        _apply_state.update({"running": False, "finished": True, "errors": errors,
                             "on": len(db_on), "off": len(db_off)})


def apply_status():
    with _lock:
        return dict(_apply_state)


# ---------- HTTP 处理 ----------

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _serve_file(self, rel):
        if rel in ("/", "/index.html"):
            path = os.path.join(WEB_DIR, "index.html")
            ctype = "text/html; charset=utf-8"
        else:
            name = os.path.basename(rel)
            path = os.path.join(WEB_DIR, name)
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            ctype = {"css": "text/css; charset=utf-8", "js": "application/javascript; charset=utf-8",
                     "html": "text/html; charset=utf-8"}.get(ext, "application/octet-stream")
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        with _lock:
            if path == "/api/state":
                self._json(state_payload())
            elif path == "/api/paths":
                self._json({"report": ccswitch_paths.format_report()})
            elif path == "/api/apply_status":
                self._json(apply_status())
            elif path == "/api/ai_config":
                self._json(_ai_config_info())
            else:
                self._serve_file(path)

    def do_POST(self):
        path = urlparse(self.path).path
        with _lock:
            data = self._read_json()
            handlers = {
                "/api/toggle_skill": lambda: _toggle_skill(data),
                "/api/toggle_category": lambda: _toggle_category(data),
                "/api/set_all": lambda: _set_all(data),
                "/api/reset": _reset,
                "/api/scan": _scan,
                "/api/assign": lambda: _assign(data),
                "/api/newcat": lambda: _newcat(data),
                "/api/delcat": lambda: _delcat(data),
                "/api/ai_classify": lambda: _ai_classify(data),
                "/api/ai_apply": lambda: _ai_apply(data),
                "/api/apply": _start_apply,
            }
            fn = handlers.get(path)
            if fn:
                self._json(fn())
            else:
                self._json({"error": "not found"}, 404)

    def log_message(self, *_args):
        pass


def _kill_port_owner(port):
    """杀掉监听指定端口的进程（用于端口被残留服务占用时自愈）。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             timeout=5).stdout
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=5)
    except Exception:
        pass


def main():
    global _skills, _pending, _cats, _cat_order
    connect_db()
    reload_state()

    url = f"http://127.0.0.1:{PORT}/"
    server = None
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # 端口被残留进程占用：杀掉后重试一次
        _kill_port_owner(PORT)
        time.sleep(1)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError:
            print("无法启动服务：端口 8765 被占用且无法释放。")
            print("请手动关闭占用该端口的程序，或编辑 server.py 中的 PORT 后重试。")
            input("按回车键退出…")
            return

    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    print(f"Skill 分类管理器已启动：{url}")
    print("关闭本窗口即可停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
