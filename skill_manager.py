#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_manager.py — 按科研工作流分类批量控制 cc-switch 中 skill 在各 AI Agent 的启用状态

支持的 Agent（与 cc-switch skills 表的 enabled_* 列一一对应）：
  claude(Claude Code)、codex(Codex)、gemini(Gemini CLI)、grokbuild(Grok Build)、
  opencode(OpenCode)、hermes(Hermes)、mcode(MiniMax Code)

原理（与 cc-switch v3.20.4 自身逻辑一致）：
  1. SSOT 仓库:  ~/.cc-switch/skills/<dir>
  2. 启用状态:   ~/.cc-switch/cc-switch.db  skills 表 enabled_<agent>
  3. 文件同步:   copy 方式 —— 启用时把 SSOT 目录复制到各 Agent 的 skills 目录；
                 禁用时从应用目录删除（不动 SSOT 仓库）

用法:
  python skill_manager.py list                 # 查看分类及各类启用统计
  python skill_manager.py status <分类>        # 查看某分类下每个 skill 的开关
  python skill_manager.py on  <分类|all> [-a claude|codex|gemini|grokbuild|opencode|hermes|mcode|both]
  python skill_manager.py off <分类|all> [-a ...]
  python skill_manager.py sync                 # 按数据库标记全量对账文件（修复缺失/多余目录）
  python skill_manager.py check                # 校验分类覆盖是否完整
  python skill_manager.py paths                # 自动探测并打印 cc-switch 相关路径
  python skill_manager.py scan                 # 列出尚未归类的新 skill
  python skill_manager.py assign <skill> <分类> # 把某 skill 归入分类（分类不存在则自动新建）
  python skill_manager.py newcat <分类>        # 新建一个空分类

说明:
  - 分类名可用前缀模糊匹配，如 `on 01` 会匹配 01_文献检索与获取
  - "all" 表示全部 skill
  - 建议先退出 cc-switch 再操作，避免数据库写冲突；操作完再启动它会自动读取新状态
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys

import ccswitch_paths

# 启动时自动探测 cc-switch 相关路径（数据库 / SSOT / 各 Agent 目录），
# 部署到任意电脑均无需手动配置。
_PATHS = ccswitch_paths.detect()
DB_PATH = _PATHS["db_path"]
SSOT = _PATHS["ssot_dir"]
AGENTS = _PATHS["agents"]
AGENT_KEYS = [a["key"] for a in AGENTS]
APP_DIRS = {a["key"]: a["skills_dir"] for a in AGENTS}
COLUMNS = ccswitch_paths.COLUMNS

CAT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.json")


def load_categories():
    with open(CAT_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_categories(cats):
    with open(CAT_FILE, "w", encoding="utf-8") as f:
        json.dump(cats, f, ensure_ascii=False, indent=2)


def load_skills(con):
    cols = ", ".join(COLUMNS[k] for k in AGENT_KEYS)
    rows = con.execute(f"SELECT directory, {cols} FROM skills").fetchall()
    out = {}
    for d, *flags in rows:
        out[d] = {k: bool(f) for k, f in zip(AGENT_KEYS, flags)}
    return out


def load_skills_meta(con):
    rows = con.execute(
        "SELECT directory, name, description FROM skills ORDER BY directory").fetchall()
    return {d: (n or d, (de or "").strip()) for d, n, de in rows}


def uncategorized_dirs(cats, skills):
    seen = set()
    for dirs in cats.values():
        seen.update(dirs)
    return sorted(set(skills) - seen)


def match_category(name, cats):
    if name == "all":
        return name
    keys = [k for k in cats if k.startswith(name)]
    if len(keys) == 1:
        return keys[0]
    if not keys:
        raise SystemExit(f"未找到分类: {name}\n可用分类: " + "、".join(cats))
    raise SystemExit(f"分类前缀不唯一 ({'、'.join(keys)})，请更精确一些")


def resolve_dirs(cat_key, cats, all_dirs):
    if cat_key == "all":
        return list(all_dirs)
    dirs = cats[cat_key]
    unknown = [d for d in dirs if d not in all_dirs]
    if unknown:
        print(f"[警告] 分类 {cat_key} 中有 {len(unknown)} 个 skill 不在数据库: {unknown}")
    return [d for d in dirs if d in all_dirs]


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
        return f"{directory}: SSOT 缺少 SKILL.md，跳过"
    dest = os.path.join(APP_DIRS[app], directory)
    os.makedirs(APP_DIRS[app], exist_ok=True)
    remove_dest(dest)
    shutil.copytree(src, dest)
    return None


def set_enabled(dirs, apps, enabled, con, skills):
    for d in dirs:
        for app in apps:
            err = None
            if enabled:
                err = copy_skill(d, app)
            else:
                remove_dest(os.path.join(APP_DIRS[app], d))
            if err:
                print(f"  [失败] {err}")
                continue
            skills[d][app] = enabled
            con.execute(f"UPDATE skills SET {COLUMNS[app]} = ? WHERE directory = ?",
                        (1 if enabled else 0, d))
    con.commit()


def cmd_list(cats, skills):
    labels = [a.get("short", a["label"]) for a in AGENTS]
    print(f"{'分类':<36} {'数量':>4} " + " ".join(f"{l:>8}" for l in labels))
    print("-" * (36 + 4 + 1 + 9 * len(AGENTS)))
    totals = {k: 0 for k in AGENT_KEYS}
    for cat, dirs in cats.items():
        have = [d for d in dirs if d in skills]
        cells = [f"{sum(skills[d][k] for d in have):>8}" for k in AGENT_KEYS]
        for k in AGENT_KEYS:
            totals[k] += sum(skills[d][k] for d in have)
        print(f"{cat:<36} {len(have):>4} " + " ".join(cells))
    print("-" * (36 + 4 + 1 + 9 * len(AGENTS)))
    n = len(skills)
    cells = [f"{totals[k]:>8}" for k in AGENT_KEYS]
    print(f"{'合计':<36} {n:>4} " + " ".join(cells))


def cmd_status(cat_key, cats, skills):
    dirs = resolve_dirs(cat_key, cats, skills) if cat_key else None
    if dirs is None:
        return cmd_list(cats, skills)
    labels = [a.get("short", a["label"]) for a in AGENTS]
    print(f"{'skill':<40}" + " ".join(f"{l:>8}" for l in labels))
    for d in sorted(dirs):
        s = skills[d]
        cells = [f"{('✔' if s[k] else '✘'):>8}" for k in AGENT_KEYS]
        print(f"{d:<40}" + " ".join(cells))


def main():
    p = argparse.ArgumentParser(description="按科研分类控制 cc-switch skill 启用状态")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("status"); sp.add_argument("category", nargs="?")
    for name in ("on", "off"):
        sp = sub.add_parser(name); sp.add_argument("category"); sp.add_argument(
            "-a", "--app", choices=AGENT_KEYS + ["both"], default="both")
    sub.add_parser("sync")
    sub.add_parser("check")
    sub.add_parser("paths")
    sp = sub.add_parser("scan")
    sp = sub.add_parser("assign"); sp.add_argument("skill"); sp.add_argument("category")
    sp = sub.add_parser("newcat"); sp.add_argument("name")
    args = p.parse_args()

    if args.cmd == "paths":
        print(ccswitch_paths.format_report())
        return

    cats = load_categories()
    con = sqlite3.connect(DB_PATH, timeout=15)
    skills = load_skills(con)

    if args.cmd == "list":
        cmd_list(cats, skills)
    elif args.cmd == "status":
        cmd_status(match_category(args.category, cats) if args.category else None, cats, skills)
    elif args.cmd in ("on", "off"):
        cat_key = match_category(args.category, cats)
        apps = AGENT_KEYS if args.app == "both" else [args.app]
        dirs = resolve_dirs(cat_key, cats, skills)
        print(f"{'启用' if args.cmd == 'on' else '禁用'} [{cat_key}] 的 {len(dirs)} 个 skill "
              f"→ {' + '.join(apps)}")
        set_enabled(dirs, apps, args.cmd == "on", con, skills)
        print("完成。")
    elif args.cmd == "sync":
        fixed = 0
        for d, s in skills.items():
            for app, on in s.items():
                dest = os.path.join(APP_DIRS[app], d)
                if on and not os.path.isdir(dest):
                    copy_skill(d, app); fixed += 1
                elif not on and os.path.isdir(dest):
                    remove_dest(dest); fixed += 1
        print(f"对账完成，修复 {fixed} 处。")
    elif args.cmd == "check":
        seen = [d for dirs in cats.values() for d in dirs]
        dupes = {d for d in seen if seen.count(d) > 1}
        uncategorized = sorted(set(skills) - set(seen))
        stale = sorted(set(seen) - set(skills))
        print(f"数据库 {len(skills)} 个 skill；分类覆盖 {len(set(seen) & set(skills))} 个")
        if dupes: print("重复出现在多个分类:", sorted(dupes))
        if uncategorized: print("未分类:", uncategorized)
        if stale: print("分类中已不存在于数据库:", stale)
        if not (dupes or uncategorized or stale): print("覆盖完整，无重复、无遗漏。")
    elif args.cmd == "scan":
        meta = load_skills_meta(con)
        uncat = uncategorized_dirs(cats, meta)
        if not uncat:
            print("没有未分类的 skill。")
        else:
            print(f"未分类 skill 共 {len(uncat)} 个：")
            for d in uncat:
                name, desc = meta[d]
                print(f"  {d:<40} {name}")
    elif args.cmd == "assign":
        skill = args.skill
        if skill not in skills:
            raise SystemExit(f"数据库中不存在 skill: {skill}")
        if args.category not in cats:
            cats[args.category] = []
            print(f"[新建分类] {args.category}")
        for dirs in cats.values():
            if skill in dirs:
                dirs.remove(skill)
        cats[args.category].append(skill)
        save_categories(cats)
        print(f"已把 {skill} 归入分类「{args.category}」。")
    elif args.cmd == "newcat":
        if args.name in cats:
            raise SystemExit(f"分类已存在: {args.name}")
        cats[args.name] = []
        save_categories(cats)
        print(f"已新建分类「{args.name}」。")
    con.close()


if __name__ == "__main__":
    main()
