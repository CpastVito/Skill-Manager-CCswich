#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ccswitch_paths.py — 自动探测 cc-switch 相关路径（部署到任意电脑均无需手动配置）

解析规则与 cc-switch 官方源码保持一致：
  - config.rs             get_app_config_dir()   → 环境变量 CC_SWITCH_CONFIG_DIR 优先，否则 ~/.cc-switch
  - services/skill.rs     get_ssot_dir()         → skillStorageLocation=unified 时用 ~/.agents/skills，否则 <config>/skills
  - services/skill.rs     get_app_skills_dir()   → 各 Agent 的 <config_dir>/skills，支持 settings.json override
  - settings.rs           AppSettings 各 xxxConfigDir 字段（camelCase）
  - mcode_config.rs       data_dir()             → MINIMAX_DATA_DIR / MAVIS_DATA_DIR / 默认 ~/.minimax
  - hermes_config.rs      get_hermes_dir()       → Windows 用 %LOCALAPPDATA%\\hermes，否则 ~/.hermes

对外接口：
  detect()                     -> 返回完整的路径探测报告（dict）
  format_report(info)          -> 把报告格式化为可读文本
  AGENTS / AGENT_KEYS / COLUMNS -> Agent 元信息与数据库列名映射
"""
import json
import os


def _home():
    return os.path.expanduser("~")


def _hermes_default_dir():
    # Hermes：Windows 用 %LOCALAPPDATA%\hermes，其它平台用 ~/.hermes
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(_home(), "AppData", "Local")
        return os.path.join(base, "hermes")
    return os.path.join(_home(), ".hermes")


def _mcode_default_dir():
    # MiniMax Code：MINIMAX_DATA_DIR 优先，MAVIS_DATA_DIR 备选，默认 ~/.minimax
    d = os.environ.get("MINIMAX_DATA_DIR") or os.environ.get("MAVIS_DATA_DIR")
    return d.strip() if d and d.strip() else os.path.join(_home(), ".minimax")


# Agent 元信息：key 与 skills 表的 enabled_<key> 列名一一对应
#   label       : 完整名称（用于诊断报告 / README）
#   short       : 简短名称（用于界面勾选框等紧凑场景）
#   default_dir : 无 override 时的“配置目录”（skills 目录 = default_dir/skills）
#   override    : settings.json 中对应的自定义目录字段名（camelCase，None 表示无）
AGENTS = [
    {"key": "claude",    "label": "Claude Code",  "short": "Claude",   "default_dir": os.path.join(_home(), ".claude"),           "override": "claudeConfigDir"},
    {"key": "codex",     "label": "Codex",        "short": "Codex",    "default_dir": os.path.join(_home(), ".codex"),            "override": "codexConfigDir"},
    {"key": "gemini",    "label": "Gemini CLI",   "short": "Gemini",   "default_dir": os.path.join(_home(), ".gemini"),           "override": "geminiConfigDir"},
    {"key": "grokbuild", "label": "Grok Build",   "short": "Grok",     "default_dir": os.path.join(_home(), ".grok"),             "override": "grokConfigDir"},
    {"key": "opencode",  "label": "OpenCode",     "short": "OpenCode", "default_dir": os.path.join(_home(), ".config", "opencode"), "override": "opencodeConfigDir"},
    {"key": "hermes",    "label": "Hermes",       "short": "Hermes",   "default_dir": _hermes_default_dir(),                      "override": "hermesConfigDir"},
    {"key": "mcode",     "label": "MiniMax Code", "short": "MiniMax",  "default_dir": _mcode_default_dir(),                       "override": None},
]
AGENT_KEYS = [a["key"] for a in AGENTS]
COLUMNS = {a["key"]: f"enabled_{a['key']}" for a in AGENTS}


def _expand(path):
    """展开 override 路径中的 ~ 为用户主目录（与 cc-switch resolve_override_path 一致）。"""
    if not path:
        return path
    path = path.strip()
    if path == "~":
        return _home()
    if path.startswith("~/"):
        return os.path.join(_home(), path[2:])
    if path.startswith("~\\"):
        return os.path.join(_home(), path[2:])
    return path


def resolve_config_dir():
    """cc-switch 中央配置目录（SSOT 根）：CC_SWITCH_CONFIG_DIR 优先，否则 ~/.cc-switch。"""
    d = os.environ.get("CC_SWITCH_CONFIG_DIR")
    if d and d.strip():
        return _expand(d.strip())
    return os.path.join(_home(), ".cc-switch")


def load_settings(config_dir=None):
    """读取 <config_dir>/settings.json，失败返回空 dict。"""
    config_dir = config_dir or resolve_config_dir()
    path = os.path.join(config_dir, "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_db_path(config_dir=None):
    return os.path.join(config_dir or resolve_config_dir(), "cc-switch.db")


def resolve_ssot_dir(settings=None, config_dir=None):
    """SSOT（skill 仓库）目录：skillStorageLocation=unified → ~/.agents/skills，否则 <config>/skills。"""
    settings = settings if settings is not None else load_settings(config_dir)
    config_dir = config_dir or resolve_config_dir()
    if str(settings.get("skillStorageLocation", "")).lower() == "unified":
        return os.path.join(_home(), ".agents", "skills")
    return os.path.join(config_dir, "skills")


def resolve_sync_method(settings=None):
    settings = settings if settings is not None else load_settings()
    return str(settings.get("skillSyncMethod", "copy")).lower() or "copy"


def resolve_agent_dirs(settings=None):
    """各 Agent 的“配置目录”：优先 settings.json 的 override，否则默认目录。"""
    settings = settings if settings is not None else load_settings()
    out = {}
    for a in AGENTS:
        d = None
        if a["override"]:
            ov = settings.get(a["override"])
            if ov and str(ov).strip():
                d = _expand(str(ov).strip())
        out[a["key"]] = d if d else a["default_dir"]
    return out


def resolve_agent_skills_dirs(settings=None):
    dirs = resolve_agent_dirs(settings)
    return {k: os.path.join(v, "skills") for k, v in dirs.items()}


def detect():
    """一次性探测全部路径，返回结构化报告。"""
    config_dir = resolve_config_dir()
    settings = load_settings(config_dir)
    db_path = resolve_db_path(config_dir)
    ssot_dir = resolve_ssot_dir(settings, config_dir)
    sync_method = resolve_sync_method(settings)
    agent_dirs = resolve_agent_dirs(settings)
    agent_skills = resolve_agent_skills_dirs(settings)

    agents = []
    for a in AGENTS:
        k = a["key"]
        agents.append({
            "key": k,
            "label": a["label"],
            "short": a.get("short", a["label"]),
            "override_field": a["override"],
            "config_dir": agent_dirs[k],
            "skills_dir": agent_skills[k],
        })

    return {
        "config_dir": config_dir,
        "settings_path": os.path.join(config_dir, "settings.json"),
        "db_path": db_path,
        "ssot_dir": ssot_dir,
        "sync_method": sync_method,
        "storage_location": str(settings.get("skillStorageLocation", "cc_switch")).lower(),
        "env_config_dir": os.environ.get("CC_SWITCH_CONFIG_DIR") or None,
        "agents": agents,
    }


def _exists(path):
    return "存在" if os.path.exists(path) else "缺失"


def format_report(info=None):
    """把探测报告格式化为可读文本（供 GUI 诊断窗口 / CLI paths 命令使用）。"""
    info = info or detect()
    lines = []
    lines.append("cc-switch 路径探测报告")
    lines.append("=" * 46)
    lines.append(f"中央配置目录 : {info['config_dir']}")
    lines.append(f"  环境变量 CC_SWITCH_CONFIG_DIR : {info['env_config_dir'] or '（未设置，使用默认）'}")
    lines.append(f"数据库文件   : {info['db_path']}   [{_exists(info['db_path'])}]")
    lines.append(f"settings.json: {info['settings_path']}   [{_exists(info['settings_path'])}]")
    lines.append(f"SSOT 仓库    : {info['ssot_dir']}   [{_exists(info['ssot_dir'])}]")
    lines.append(f"  存储位置 skillStorageLocation : {info['storage_location']}")
    lines.append(f"  同步方式 skillSyncMethod      : {info['sync_method']}")
    lines.append("")
    lines.append("各 Agent 的 skills 目录：")
    for a in info["agents"]:
        tag = f"[{'✓' if os.path.exists(a['skills_dir']) else '✗'}]"
        lines.append(f"  {a['label']:<13} {tag} {a['skills_dir']}")
    lines.append("")
    lines.append("说明：若目录标 [✗] 表示该 Agent 尚未安装或未初始化；")
    lines.append("启用某 Agent 的 skill 时会自动创建对应 skills 目录。")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report())
