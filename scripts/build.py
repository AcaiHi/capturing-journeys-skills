"""把 capturing-journeys skill 連結進前端工作區，並建立 docs/ui-inventory/。

用法：python build.py sync [--workspace DIR]
可重複執行；既有檔案一律不覆蓋，只有 CLAUDE.md / AGENTS.md 裡標記區塊內的規則會依模板刷新。

常數：
    FRAMEWORK_PORTS  依 package.json 相依套件猜測開發伺服器 port（找不到 vite.config 的 port 時使用）
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PAYLOAD = HERE / "payload" / "skill"
TEMPLATES = PAYLOAD / "templates"
SKILL_NAME = "capturing-journeys"

# 範本 -> docs/ui-inventory/ 底下的路徑（已存在就略過）
SKELETON = {
    "playwright.config.ts": "playwright.config.ts",
    "manifest.json": "manifest.json",
    "facts.json": "facts.json",
    "USER_STORY.md": "USER_STORY.md",
    "gitignore": ".gitignore",
    "_shoot.ts": "states/_shoot.ts",
    "_story.ts": "states/_story.ts",
    "_backend.ts": "states/_backend.ts",
}

FRAMEWORK_PORTS = [("vite", 5173), ("@angular/cli", 4200), ("next", 3000), ("nuxt", 3000),
                   ("react-scripts", 3000), ("@vue/cli-service", 8080)]


def is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    if os.name == "nt" and p.exists():
        return bool(os.stat(p, follow_symlinks=False).st_file_attributes & 0x400)  # reparse point
    return False


def make_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def read_pkg(ws: Path):
    f = ws / "package.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None


def git_root(ws: Path):
    for p in [ws, *ws.parents]:
        if (p / ".git").exists():
            return p
    return None


def project_name(ws: Path, pkg) -> str:
    """package.json 的 name（去掉 @scope/）> git 根目錄名 > 資料夾名。"""
    if pkg and isinstance(pkg.get("name"), str) and pkg["name"].strip():
        return pkg["name"].split("/")[-1]
    root = git_root(ws)
    return (root or ws).name


def detect_base_url(ws: Path, pkg) -> str:
    deps = {**(pkg or {}).get("dependencies", {}), **(pkg or {}).get("devDependencies", {})}
    for cfg in ws.glob("vite.config.*"):
        m = re.search(r"port\s*:\s*(\d+)", cfg.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return f"http://localhost:{m.group(1)}"
    for dep, port in FRAMEWORK_PORTS:
        if dep in deps:
            return f"http://localhost:{port}"
    return "http://localhost:3000"


def sync_link(ws: Path, log) -> Path:
    link = ws / ".claude" / "skills" / SKILL_NAME
    if is_link(link):
        if link.resolve() == PAYLOAD.resolve() and (link / "SKILL.md").exists():
            log(f"ok    連結  {link}")
            return link
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
        log(f"已修復 連結  {link}（原本指向過期的位置）")
    elif link.exists():
        bak = link.with_name(f"{SKILL_NAME}.bak-{datetime.date.today()}")
        shutil.move(str(link), str(bak))
        log(f"已把原本的實體資料夾移到 {bak}")
    make_link(link, PAYLOAD)
    log(f"已建立 連結  {link} -> {PAYLOAD}")
    return link


def sync_docs(ws: Path, name: str, base_url: str, log) -> None:
    docs = ws / "docs" / "ui-inventory"
    for sub in ("states", "screens"):
        (docs / sub).mkdir(parents=True, exist_ok=True)
    for src, rel in SKELETON.items():
        f = docs / rel
        if f.exists():
            continue
        text = (TEMPLATES / src).read_text(encoding="utf-8")
        f.write_text(text.replace("{name}", name).replace("{baseURL}", base_url), encoding="utf-8")
        log(f"已建立 {f}")
    log(f"ok    資料夾  {docs}")


BEGIN, END = f"<!-- {SKILL_NAME}:begin -->", f"<!-- {SKILL_NAME}:end -->"
P_BEGIN, P_END = f"<!-- {SKILL_NAME}:pointer:begin -->", f"<!-- {SKILL_NAME}:pointer:end -->"
AGENT_FILES = ("CLAUDE.md", "AGENTS.md")


def upsert_block(f: Path, block: str, begin: str, end: str, log, label: str) -> None:
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    wrapped = f"{begin}\n{block.strip()}\n{end}"
    if begin in text and end in text:
        head, rest = text.split(begin, 1)
        new = head + wrapped + rest.split(end, 1)[1]
        action = "已更新"
    else:
        new = (text.rstrip() + "\n\n" if text.strip() else "") + wrapped + "\n"
        action = "已加入"
    if new == text:
        log(f"ok    {label}  {f}")
        return
    f.write_text(new, encoding="utf-8")
    log(f"{action} {label}  {f}")


def agent_files(folder: Path):
    names = {p.name.upper(): p for p in folder.iterdir() if p.is_file()}
    found = [names[n.upper()] for n in AGENT_FILES if n.upper() in names]
    return found or [folder / "CLAUDE.md"]


def sync_agent_docs(ws: Path, log) -> None:
    block = (TEMPLATES / "agent-block.md").read_text(encoding="utf-8")
    for f in agent_files(ws):
        upsert_block(f, block, BEGIN, END, log, "規則")
    root = git_root(ws)
    if root and root != ws:
        rel = ws.relative_to(root).as_posix()
        pointer = (f"## 畫面截圖（capturing-journeys）\n\n"
                   f"畫面截圖相關工作在 `{rel}/` 進行；開始前先讀 `{rel}/CLAUDE.md` 的 capturing-journeys 規則。")
        for f in agent_files(root):
            upsert_block(f, pointer, P_BEGIN, P_END, log, "根目錄指標")


def check_gitignore(ws: Path, link: Path, log) -> None:
    if not git_root(ws):
        return
    probe = link / "SKILL.md"
    r = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=ws, capture_output=True)
    if r.returncode == 0:
        log("ok    連結已被 .gitignore 排除")
    elif r.returncode == 1:
        rel = link.relative_to(git_root(ws)).as_posix()
        log(f"警告  連結尚未被 git 忽略；Windows 上 git 會把連結指向的內容一起 commit。請在 .gitignore 加入：{rel}/")
    else:
        log("提醒  無法用 git 確認連結是否被忽略，請自行檢查 .gitignore")


def check_playwright(ws: Path, log) -> None:
    pkg = read_pkg(ws)
    if pkg is None:
        log("警告  這裡沒有可讀的 package.json；請在前端專案根目錄（package.json 所在）執行 sync")
        return
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "@playwright/test" in deps:
        log(f"ok    @playwright/test {deps['@playwright/test']}")
    else:
        log("警告  缺少 @playwright/test：npm i -D @playwright/test")
        log("      不想下載瀏覽器的話，不用 npx playwright install；改在 config 的 use 加 channel: 'chrome' 使用本機 Chrome")
    for old in ("capturing-screens",):
        if (ws / ".claude" / "skills" / old).exists():
            log(f"提醒  偵測到舊的 {old} 連結，與本 skill 互相獨立；確定不再使用時再手動移除")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sync"])
    ap.add_argument("--workspace", default=".")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    if not PAYLOAD.is_dir():
        print(f"找不到 payload：{PAYLOAD}", file=sys.stderr)
        return 1
    pkg = read_pkg(ws)
    name, base_url = project_name(ws, pkg), detect_base_url(ws, pkg)
    try:
        link = sync_link(ws, print)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"錯誤：建立連結失敗：{e}；請確認 {ws / '.claude'} 可寫入", file=sys.stderr)
        return 1
    sync_docs(ws, name, base_url, print)
    sync_agent_docs(ws, print)
    check_gitignore(ws, link, print)
    check_playwright(ws, print)
    print(f"\n專案名稱取為「{name}」，baseURL 偵測為 {base_url}。請確認 docs/ui-inventory/playwright.config.ts 的 baseURL、locale、timezoneId。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
