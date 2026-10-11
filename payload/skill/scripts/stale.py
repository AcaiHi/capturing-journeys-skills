"""capturing-journeys 的 manifest 工具：登錄依賴、偵測過時、產生清單、找重複、比較差異、標註。

用法（在工作區根目錄）：
    python .claude/skills/capturing-journeys/scripts/stale.py <子命令> [選項]

子命令：record | check | merge | inventory | dups | backup | compare | annotate
只用 Python 3 標準庫；compare 與 annotate 需要 Pillow（pip install pillow）。

常數：
    IMPORT_EXTS      解析 import 時依序嘗試的副檔名
    SKIP_DIRS        展開相依檔案時略過的資料夾
    MAX_FILE_BYTES   超過此大小的檔案不讀（避免誤把打包產物當原始碼）
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

IMPORT_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".json"]
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt"}
MAX_FILE_BYTES = 2_000_000
CODE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte", ".css", ".scss", ".sass", ".less"}

IMPORT_RES = [
    # import type / export type 編譯後會消失，不算依賴
    re.compile(r"""(?:import|export)(?!\s+type\b)\s[^'"`;]*?\sfrom\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""@import\s+(?:url\()?['"]([^'"]+)['"]"""),
]

DEFAULT_COLORS = ["#4C3BCF", "#E8801A", "#2A7DE1", "#5B2A86", "#C2185B", "#B8860B"]


def under(f: Path, base: Path) -> bool:
    try:
        f.relative_to(base)
        return True
    except ValueError:
        return False


def die(msg: str, code: int = 2):
    print(f"錯誤：{msg}", file=sys.stderr)
    sys.exit(code)


def sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def file_hash(p: Path) -> str:
    return sha(p.read_bytes().replace(b"\r\n", b"\n"))


def value_hash(v) -> str:
    return sha(json.dumps(v, ensure_ascii=False, sort_keys=True).encode("utf-8"))


class Ctx:
    def __init__(self, a):
        self.root = Path(a.root).resolve()
        self.ui = (self.root / a.ui).resolve()
        self.manifest_path = self.ui / "manifest.json"
        self.facts_path = self.ui / "facts.json"
        self.screens = self.ui / "screens"
        self.cli_alias = {}
        for item in a.alias or []:
            k, _, v = item.partition("=")
            self.cli_alias[k] = v
        self._alias = None
        self.entries_all = set()

    def load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            die(f"找不到 {self.manifest_path}；先在步驟 2 建立 manifest.json（見 reference/stale.md）")
        try:
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except ValueError as e:
            die(f"manifest.json 不是合法的 JSON：{e}")
        m.setdefault("checkpoints", {})
        m.setdefault("screens", [])
        self.entries_all = {(self.root / s["entry"]).resolve() for s in m["screens"] if s.get("entry")}
        return m

    def save_manifest(self, m: dict):
        self.manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def facts(self) -> dict:
        if not self.facts_path.exists():
            return {}
        try:
            return json.loads(self.facts_path.read_text(encoding="utf-8"))
        except ValueError as e:
            die(f"facts.json 不是合法的 JSON：{e}")

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root).as_posix()

    # ---- 路徑別名 ----
    def aliases(self) -> dict:
        """前綴 -> 絕對目錄。--alias 優先，其次 tsconfig/jsconfig 的 paths。"""
        if self._alias is not None:
            return self._alias
        out = {}
        for name in ("tsconfig.json", "tsconfig.app.json", "jsconfig.json"):
            f = self.root / name
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", text)
            text = re.sub(r",(\s*[}\]])", r"\1", text)
            try:
                opts = json.loads(text).get("compilerOptions", {})
            except ValueError:
                continue
            base = self.root / opts.get("baseUrl", ".")
            for key, targets in (opts.get("paths") or {}).items():
                if key.endswith("/*") and targets and targets[0].endswith("/*"):
                    out.setdefault(key[:-1], (base / targets[0][:-2]).resolve())
        for k, v in self.cli_alias.items():
            out[k if k.endswith("/") else k + "/"] = (self.root / v).resolve()
        self._alias = out
        return out

    def resolve_import(self, spec: str, from_file: Path):
        base = None
        if spec.startswith("."):
            base = (from_file.parent / spec).resolve()
        else:
            for prefix, target in self.aliases().items():
                if spec.startswith(prefix):
                    base = (target / spec[len(prefix):]).resolve()
                    break
        if base is None:
            return None
        cands = [base] + [Path(str(base) + e) for e in IMPORT_EXTS] + [base / ("index" + e) for e in IMPORT_EXTS]
        for c in cands:
            if c.is_file():
                return c
        return None

    def imports_of(self, f: Path) -> list:
        """f 直接 import 的檔案（已解析成絕對路徑）。有快取。"""
        cache = self.__dict__.setdefault("_imports", {})
        if f in cache:
            return cache[f]
        out = []
        if f.suffix.lower() in CODE_SUFFIXES:
            try:
                if f.stat().st_size <= MAX_FILE_BYTES:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    for rx in IMPORT_RES:
                        for spec in rx.findall(text):
                            r = self.resolve_import(spec, f)
                            if r is not None and r not in out:
                                out.append(r)
            except OSError:
                pass
        cache[f] = out
        return out

    def skipped(self, f: Path) -> bool:
        try:
            parts = f.relative_to(self.root).parts
        except ValueError:
            return True
        return any(part in SKIP_DIRS for part in parts) or under(f, self.ui)

    def closure_paths(self, start: Path, stop=frozenset()) -> set:
        """從 start 沿 import 往下展開的所有檔案（含 start）；遇到 stop 裡的檔案（除了 start 自己）就不展開。"""
        seen, stack = set(), [start]
        while stack:
            f = stack.pop()
            if f in seen or not f.is_file() or self.skipped(f) or (f in stop and f != start):
                continue
            seen.add(f)
            stack.extend(self.imports_of(f))
        return seen

    def all_code_files(self) -> list:
        cache = self.__dict__.get("_all")
        if cache is None:
            cache = []
            for dirpath, dirs, files in os.walk(self.root):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not under((Path(dirpath) / d).resolve(), self.ui)]
                for name in files:
                    f = Path(dirpath) / name
                    if f.suffix.lower() in CODE_SUFFIXES:
                        cache.append(f.resolve())
            self._all = cache
        return cache

    def ancestors(self, target: Path) -> set:
        """直接或間接 import target 的所有檔案（渲染它的上層，例如 App、版型）。"""
        rev = self.__dict__.get("_rev")
        if rev is None:
            rev = {}
            for f in self.all_code_files():
                for d in self.imports_of(f):
                    rev.setdefault(d, set()).add(f)
            self._rev = rev
        seen, stack = set(), [target]
        while stack:
            for parent in rev.get(stack.pop(), ()):
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return seen

    def screen_files(self, s: dict) -> dict:
        """這張圖依賴的檔案 -> 雜湊：入口往下展開，加上渲染它的上層（祖先）與祖先帶進來的共用外殼。
        祖先的相依檔案裡，凡是其他圖的入口（別的頁面）都排除，避免改別頁就讓所有圖過時。"""
        if not s.get("entry"):
            return {}
        entry = (self.root / s["entry"]).resolve()
        if not entry.is_file():
            return {}
        files = self.closure_paths(entry)
        ancestors = self.ancestors(entry)
        for a in ancestors:
            if not self.skipped(a):
                files.add(a)
        for a in ancestors:
            if self.skipped(a):
                continue
            for d in self.imports_of(a):
                # 祖先本身、別張圖的入口（別的頁面）都不展開，否則會把整個 app 帶進來，且結果與走訪順序有關
                if d == entry or d in ancestors or d in self.entries_all:
                    continue
                files |= self.closure_paths(d, stop=self.entries_all)
        out = {}
        for f in files:
            try:
                out[self.rel(f)] = file_hash(f)
            except (OSError, ValueError):
                continue
        return out

    def env_hash(self) -> str:
        parts = []
        cfg = self.ui / "playwright.config.ts"
        parts.append(cfg.read_bytes().replace(b"\r\n", b"\n") if cfg.exists() else b"")
        for name in ("_backend.ts", "_story.ts", "_shoot.ts"):  # 共用 mock 與拍攝輔助：改了會影響所有圖
            f = self.ui / "states" / name
            parts.append(f.read_bytes().replace(b"\r\n", b"\n") if f.exists() else b"")
        pkg = self.root / "package.json"
        ver = ""
        if pkg.exists():
            try:
                d = json.loads(pkg.read_text(encoding="utf-8"))
                ver = {**d.get("dependencies", {}), **d.get("devDependencies", {})}.get("@playwright/test", "")
            except ValueError:
                pass
        parts.append(ver.encode())
        return sha(b"\x00".join(parts))

    def compute_inputs(self, s: dict, facts: dict) -> dict:
        files = self.screen_files(s)
        fx = {k: value_hash(facts[k]) for k in s.get("needs", []) if k in facts}
        return {"files": files, "facts": fx, "env": self.env_hash()}


def by_chapter(screens):
    groups = {}
    for s in screens:
        groups.setdefault(str(s.get("chapter", "?")), []).append(s)
    return groups


# ---------------------------------------------------------------- record
def cmd_record(c: Ctx, a):
    m = c.load_manifest()
    facts = c.facts()
    known = {s["id"]: s for s in m["screens"]}
    wanted = set(a.ids.split(",")) if a.ids else None
    n = 0
    for meta_f in sorted(c.screens.glob("*.meta.json")):
        sid = meta_f.name[: -len(".meta.json")]
        if wanted is not None and sid not in wanted:
            continue
        if sid not in known:
            print(f"警告：{sid} 有 meta 但不在 manifest，先把它加進 manifest 再 record")
            continue
        s = known[sid]
        if a.chapter and str(s.get("chapter")) != str(a.chapter):
            continue
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        stamp = s.get("recordedAt")
        fresh = stamp is None or meta_f.stat().st_mtime > datetime.datetime.fromisoformat(stamp).timestamp()
        if wanted is None and not a.chapter and not fresh:
            continue
        s["textHash"] = meta.get("textHash")
        if meta.get("boxes"):
            s["boxes"] = meta["boxes"]
        else:
            s.pop("boxes", None)
        s["inputs"] = c.compute_inputs(s, facts)
        s["recordedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
        if not s.get("entry"):
            print(f"提醒：{sid} 沒有 entry，程式碼變更偵測不到")
        n += 1
    c.save_manifest(m)
    print(f"已登錄 {n} 張圖")
    if n == 0:
        print("沒有需要登錄的圖：重拍時要帶 --update-snapshots 才會更新 meta；或用 --ids / --chapter 指定")


# ----------------------------------------------------------------- check
def stale_reasons(c: Ctx, s: dict, facts: dict) -> list:
    rec = s.get("inputs")
    if not rec:
        return ["尚未登錄（拍完要執行 record）"]
    reasons = []
    cur_files = c.screen_files(s)
    for p, h in rec.get("files", {}).items():
        if p not in cur_files:
            fp = (c.root / p).resolve()
            if fp in c.entries_all and fp.is_file() and file_hash(fp) == h:
                continue  # 該檔現在是別張圖的入口（別頁），依規則排除出外殼；內容沒變，不算過時
            reasons.append(f"檔案已移除或不再被引用: {p}")
        elif cur_files[p] != h:
            reasons.append(f"檔案變更: {p}")
    for p in cur_files:
        if p not in rec.get("files", {}):
            reasons.append(f"新增相依檔案: {p}")
    for k, h in rec.get("facts", {}).items():
        if k not in facts:
            reasons.append(f"事實已移除: {k}")
        elif value_hash(facts[k]) != h:
            reasons.append(f"事實變更: {k}")
    for k in s.get("needs", []):
        if k in facts and k not in rec.get("facts", {}):
            reasons.append(f"新增事實依賴: {k}")
    if rec.get("env") != c.env_hash():
        reasons.append("環境變更（config、Playwright 版本，或共用的 _backend/_story/_shoot）")
    return reasons


def lint_needs(m: dict, facts: dict) -> list:
    problems = []
    cps = m.get("checkpoints", {})
    chapter, made = None, set()
    for s in m["screens"]:
        ch = s.get("chapter")
        if ch != chapter:
            chapter, made = ch, set()
        cp = s.get("checkpoint")
        if cp and cp not in cps:
            problems.append((s["id"], f"檢查點未宣告: {cp}"))
        avail = set(facts) | set(cps.get(cp, {}).get("provides", [])) | made
        for need in s.get("needs", []):
            if need not in avail:
                problems.append((s["id"], f"前提無來源: {need}"))
        made |= set(s.get("makes", []))
    return problems


def cmd_check(c: Ctx, a):
    m = c.load_manifest()
    facts = c.facts()
    shown = [s for s in m["screens"] if not a.chapter or str(s.get("chapter")) == str(a.chapter)]
    stale = {}
    for s in shown:
        if s.get("kind") == "manual":
            continue
        r = stale_reasons(c, s, facts)
        if r:
            stale[s["id"]] = r
    # 連動：同一 chain 的圖只能整條重拍；derivedFrom 的來源圖過時時，引用它的圖也要重新核對。
    direct = set(stale)
    for s in m["screens"]:
        if s.get("kind") == "manual":
            continue
        sid = s["id"]
        if s.get("chain"):
            mates = [t["id"] for t in m["screens"] if t.get("chain") == s["chain"] and t["id"] in direct and t["id"] != sid]
            if mates:
                stale.setdefault(sid, []).append(f"同一 chain（{s['chain']}）的圖過時: {', '.join(mates)}，這條只能整條重拍")
        src = [d for d in s.get("derivedFrom", []) if d in direct]
        if src:
            stale.setdefault(sid, []).append(f"引用的圖過時，說明裡的數字或文字要重新核對: {', '.join(src)}")
    if not stale:
        print("沒有偵測到過時的圖。")
    else:
        for ch, group in by_chapter(shown).items():
            hit = [s for s in group if s["id"] in stale]
            if not hit:
                continue
            print(f"第 {ch} 章：{len(hit)}/{len(group)} 張可能過時")
            for s in hit:
                tag = "  [volatile，重拍後須人工過目]" if s.get("stability") == "volatile" else ""
                print(f"  {s['id']}{tag}")
                for r in stale[s["id"]][: a.max_reasons]:
                    print(f"    - {r}")
                if not s.get("entry"):
                    print("    - 沒有 entry，程式碼變更偵測不到")
        print(f"\n共 {len(stale)} 張可能過時。check 是預測，沒列出的圖仍可偶爾整套跑一次把關。")
    problems = [p for p in lint_needs(m, facts) if not a.chapter or any(p[0] == s["id"] for s in shown)]
    if problems:
        print("\n前提檢查：")
        for sid, msg in problems:
            print(f"  {sid}: {msg}")
    vol = [s["id"] for s in shown if s.get("stability") == "volatile"]
    if vol:
        print(f"\nvolatile 的圖（{len(vol)} 張）：重拍後請使用者人工確認，並核對引用其數字或文字的說明：")
        print("  " + ", ".join(vol))


# ----------------------------------------------------------------- merge
def cmd_merge(c: Ctx, a):
    m = c.load_manifest()
    known = {s["id"] for s in m["screens"]}
    added, skipped = [], []
    for f in sorted((c.ui / "_parts").glob("*.manifest.json")):
        try:
            part = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            die(f"{f.name} 不是合法的 JSON：{e}")
        for s in part["screens"] if isinstance(part, dict) else part:
            if s.get("id") in known:
                skipped.append(s.get("id"))
                continue
            m["screens"].append(s)
            known.add(s["id"])
            added.append(s["id"])

    def chapter_key(s):
        ch = str(s.get("chapter", ""))
        return (0, int(ch)) if ch.isdigit() else (1, ch)

    m["screens"].sort(key=chapter_key)  # 穩定排序：同一章內維持原本順序，新的接在後面
    c.save_manifest(m)
    print(f"已合併 {len(added)} 張圖：{', '.join(added) or '無'}")
    if skipped:
        print(f"略過 {len(skipped)} 張（id 已在 manifest）：{', '.join(skipped)}")
    print("合併後請執行 record，並確認草稿沒有重複或衝突的 id。")


# ------------------------------------------------------------- inventory
def cmd_inventory(c: Ctx, a):
    m = c.load_manifest()
    title = m.get("title") or c.root.name
    out = [f"# 畫面清單 — {title}", "", "由 manifest.json 產生，請勿手動編輯；要改請改 manifest 後重新執行 `stale.py inventory`。", ""]
    extra = 0
    for ch, group in by_chapter(m["screens"]).items():
        name = next((s.get("chapterTitle") for s in group if s.get("chapterTitle")), "")
        out += [f"## 第 {ch} 章 {name}".rstrip(), ""]
        for s in group:
            kind = s.get("kind", "main")
            if kind in ("setup", "extra"):
                extra += kind == "extra"
                continue
            out.append(f"### {s.get('caption', s['id'])}")
            if kind == "manual":
                out.append(f"（需手動截圖：{s.get('manualReason', '無法自動截圖')}）")
            else:
                ann = c.screens / f"{s['id']}.annotated.png"
                img = ann.name if ann.exists() else f"{s['id']}.png"
                out.append(f"![{s.get('caption', s['id'])}](screens/{img})")
            if s.get("desc"):
                out.append(s["desc"])
            if s.get("warn"):
                out.append(f"警告：{s['warn']}")
            if s.get("stability") == "volatile":
                out.append(f"註：此圖重拍可能不同（{', '.join(s.get('volatileBy', [])) or 'volatile'}）。")
            out.append("")
    if extra:
        out += [f"另有 {extra} 張「只拍不放」的圖，見 manifest.json。", ""]
    (c.ui / "inventory.md").write_text("\n".join(out), encoding="utf-8")
    print(f"已產生 {c.ui / 'inventory.md'}")


# ------------------------------------------------------------------ dups
def cmd_dups(c: Ctx, a):
    groups = {}
    for p in sorted(c.screens.glob("*.png")):
        if p.name.endswith(".annotated.png"):
            continue
        groups.setdefault(sha(p.read_bytes()), []).append(p.name)
    dup = [g for g in groups.values() if len(g) > 1]
    if not dup:
        print("沒有像素完全相同的圖。")
        return
    for g in dup:
        print("完全相同: " + ", ".join(g))
    print("確認這些是否拍到了同一個畫面（可能是重複，或其中一張拍錯頁）。")


# --------------------------------------------------------- backup/compare
def _pngs(d: Path):
    return {p.name: p for p in sorted(d.glob("*.png")) if not p.name.endswith(".annotated.png")}


def cmd_backup(c: Ctx, a):
    dst = c.ui / ".before"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    n = 0
    for name, p in _pngs(c.screens).items():
        shutil.copy2(p, dst / name)
        n += 1
    print(f"已備份 {n} 張圖到 {dst}")


def _need_pillow():
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: F401
        return Image, ImageChops, ImageDraw, ImageFont
    except ImportError:
        die("需要 Pillow：pip install pillow")


def cmd_compare(c: Ctx, a):
    Image, ImageChops, _, _ = _need_pillow()
    before_dir = c.ui / ".before"
    if not before_dir.exists():
        die("找不到 .before/，重拍前先執行 stale.py backup")
    m = c.load_manifest()
    vol = {s["id"] for s in m["screens"] if s.get("stability") == "volatile"}
    before, after = _pngs(before_dir), _pngs(c.screens)
    rows = []
    for name, p in after.items():
        sid = name[:-4]
        if name not in before:
            rows.append((1.0, sid, "新增"))
            continue
        a_img, b_img = Image.open(before[name]).convert("RGB"), Image.open(p).convert("RGB")
        if a_img.size != b_img.size:
            rows.append((1.0, sid, "尺寸不同"))
            continue
        diff = ImageChops.difference(a_img, b_img).convert("L")
        changed = diff.point(lambda v: 255 if v else 0).histogram()[255]
        rows.append((changed / (a_img.width * a_img.height), sid, ""))
    rows.sort(reverse=True)
    print(f"{'差異比例':>8}  id")
    for ratio, sid, note in rows:
        flag = "  [volatile，須人工過目]" if sid in vol else ""
        print(f"{ratio * 100:7.3f}%  {sid} {note}{flag}")
    zero = sum(1 for r in rows if r[0] == 0)
    print(f"\n共 {len(rows)} 張，其中 {zero} 張完全沒變。差異大的與 volatile 的請使用者過目。")


# -------------------------------------------------------------- annotate
def _font(size: int):
    _, _, _, ImageFont = _need_pillow()
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _color_index(key: str) -> int:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper()) - 65
    if key.isdigit():
        return int(key) - 1
    return int(sha(key.encode()), 16)


def cmd_annotate(c: Ctx, a):
    Image, _, ImageDraw, _ = _need_pillow()
    m = c.load_manifest()
    style = {"width": 7, "font": 23, "colors": DEFAULT_COLORS}
    sf = c.ui / "annotate.style.json"
    if sf.exists():
        style.update(json.loads(sf.read_text(encoding="utf-8")))
    cfg = (c.ui / "playwright.config.ts").read_text(encoding="utf-8") if (c.ui / "playwright.config.ts").exists() else ""
    vm = re.search(r"VIEWPORT\s*=\s*\{\s*width:\s*(\d+)", cfg)
    vw = int(vm.group(1)) if vm else None
    wanted = set(a.ids.split(",")) if a.ids else None
    n = 0
    for s in m["screens"]:
        if wanted is not None and s["id"] not in wanted:
            continue
        boxes = s.get("boxes")
        src = c.screens / f"{s['id']}.png"
        if not boxes or not src.exists():
            continue
        img = Image.open(src).convert("RGB")
        scale = img.width / vw if vw else 1
        d = ImageDraw.Draw(img)
        font, w = _font(style["font"]), style["width"]
        for key in sorted(boxes):
            b = boxes[key]
            col = style["colors"][_color_index(key) % len(style["colors"])]
            x0, y0 = b["x"] * scale, b["y"] * scale
            x1, y1 = x0 + b["width"] * scale, y0 + b["height"] * scale
            d.rectangle([x0, y0, x1, y1], outline=col, width=w)
            tb = d.textbbox((0, 0), key, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            pad = 8
            lw, lh = tw + pad * 2, th + pad * 2
            ly = y0 - lh if y0 - lh >= 0 else y0
            d.rectangle([x0, ly, x0 + lw, ly + lh], fill=col)
            d.text((x0 + pad - tb[0], ly + pad - tb[1]), key, fill="white", font=font)
        img.save(c.screens / f"{s['id']}.annotated.png")
        n += 1
    print(f"已產生 {n} 張標註圖")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["record", "check", "merge", "inventory", "dups", "backup", "compare", "annotate"])
    ap.add_argument("--ui", default="docs/ui-inventory", help="ui-inventory 資料夾（相對於 --root）")
    ap.add_argument("--root", default=".", help="原始碼根目錄（package.json 所在）")
    ap.add_argument("--alias", action="append", help="路徑別名，例如 @=src（可重複）")
    ap.add_argument("--ids", help="只處理這些 id（逗號分隔）")
    ap.add_argument("--chapter", help="只處理這一章")
    ap.add_argument("--max-reasons", type=int, default=6, help="check 每張圖最多列幾條原因")
    a = ap.parse_args()
    c = Ctx(a)
    {"record": cmd_record, "check": cmd_check, "merge": cmd_merge, "inventory": cmd_inventory, "dups": cmd_dups,
     "backup": cmd_backup, "compare": cmd_compare, "annotate": cmd_annotate}[a.cmd](c, a)


if __name__ == "__main__":
    main()
