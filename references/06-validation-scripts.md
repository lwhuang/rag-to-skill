# 階段 6：獨立驗證腳本（validate.py）

> 本檔包含一個完整的 Python 驗證腳本，可複製到**任何 repo** 使用。
> 不依賴 ziwei 的 CI 腳本。只需 `python3`。

---

## 完整 validate.py 腳本

將以下內容存為 `validate.py`，放在你的 skill 目錄同層或任意路徑：

```python
#!/usr/bin/env python3
"""
rag-to-skill Validator
用法：
  python3 validate.py <skill-dir> <jsonl-path>
  python3 validate.py <skill-dir>   (不驗證 JSONL 覆蓋率，只跑 skill 內部檢查)
"""

import sys, os, re, json, glob

VERSION = "1.2"
ANCHOR_DENSITY_THRESHOLD = 15.0   # per 1000 lines

def load_skill_files(skill_dir):
    files = {}
    main = os.path.join(skill_dir, "skill.md")
    if os.path.exists(main):
        # 防止 skill.md 是指向 skill 目錄外的 symlink
        if os.path.dirname(os.path.realpath(main)) == os.path.realpath(skill_dir):
            files["skill.md"] = open(main, encoding='utf-8').read()
    base = os.path.realpath(os.path.join(skill_dir, "references")) + os.sep
    for f in sorted(glob.glob(os.path.join(skill_dir, "references", "*.md"))):
        real = os.path.realpath(f)
        if not real.startswith(base):
            continue  # symlink 超出目錄邊界，跳過
        # 正規化為正斜線，確保跨平台（Windows 用 \ 時 dict key 不匹配）
        key = os.path.relpath(f, skill_dir).replace(os.sep, '/')
        files[key] = open(f, encoding='utf-8').read()
    return files

def check_frontmatter(skill_md_text):
    issues = []
    if not skill_md_text.startswith("---"):
        issues.append("SEVERE: skill.md 缺少 YAML frontmatter")
        return issues
    end_m = re.search(r'\n---\s*(\n|$)', skill_md_text[3:])
    if end_m is None:
        issues.append("SEVERE: skill.md frontmatter 未閉合")
        return issues
    fm = skill_md_text[3:3 + end_m.start()]
    for field in ["name:", "description:"]:
        if field not in fm:
            issues.append(f"SEVERE: frontmatter 缺少必填欄位 '{field}'")
    # 檢查 description 有沒有觸發條件
    if "何時觸發" not in fm and "trigger" not in fm.lower():
        issues.append("MEDIUM: frontmatter description 建議包含「何時觸發」說明")
    return issues

def check_anchor_density(files, jsonl_provided=False):
    all_lines = 0
    all_anchors = 0
    per_file_issues = []
    for fname, text in files.items():
        if fname == "skill.md":
            continue  # skill.md 本身不要求錨點
        lines = len(text.split('\n'))
        anchors = len(re.findall(r'item_index=\d+', text))
        density = anchors / lines * 1000 if lines > 0 else 0
        all_lines += lines
        all_anchors += anchors
        if density < ANCHOR_DENSITY_THRESHOLD and lines > 50:
            per_file_issues.append(
                f"MEDIUM: {fname} 錨點密度 {density:.1f}/1000 < {ANCHOR_DENSITY_THRESHOLD} "
                f"({anchors} anchors / {lines} lines)"
            )
    total_density = all_anchors / all_lines * 1000 if all_lines > 0 else 0
    print(f"  錨點總覽：{all_anchors} 個錨點 / {all_lines} 行 = {total_density:.1f}/1000")
    # Meta-skill 自動偵測：無 JSONL 來源且錨點極少 → 跳過所有密度判準（per-file 和 overall）
    is_meta_skill = not jsonl_provided and all_anchors < 20
    if is_meta_skill:
        print(f"  ※ 偵測到 meta-skill（無 JSONL 來源、錨點 < 20），跳過所有密度判準")
        return []  # meta-skill 不適用密度要求
    issues = list(per_file_issues)
    if total_density < ANCHOR_DENSITY_THRESHOLD and all_lines > 100:
        issues.append(
            f"SEVERE: 整體錨點密度 {total_density:.1f}/1000 低於最低要求 {ANCHOR_DENSITY_THRESHOLD}/1000"
        )
    return issues

def check_internal_links(skill_dir, files):
    """檢查 skill.md 中提到的 references/ 路徑是否都存在"""
    issues = []
    skill_text = files.get("skill.md", "")
    mentioned = re.findall(r'references/([^\s`\)\"\']+\.md)', skill_text)
    base = os.path.realpath(os.path.join(skill_dir, "references")) + os.sep
    for ref in mentioned:
        path = os.path.realpath(os.path.join(skill_dir, "references", ref))
        if not path.startswith(base):
            issues.append(f"SEVERE: references/{ref} 路徑超出 skill 目錄（路徑穿越）")
            continue
        if not os.path.exists(path):
            issues.append(f"SEVERE: skill.md 提到 references/{ref} 但檔案不存在")
    return issues

def check_jsonl_coverage(skill_dir, jsonl_path, files):
    """檢查 JSONL 中的 item_index 是否都有對應錨點"""
    issues = []

    # 讀取 JSONL item_index（用 is None 判斷，item_index=0 不被 falsy 丟棄）
    jsonl_items = set()
    try:
        with open(jsonl_path, encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                idx = None
                if 'loc' in d and isinstance(d['loc'], dict):
                    idx = d['loc'].get('item_index')
                if idx is None:
                    idx = d.get('item_index')
                if idx is None:
                    idx = d.get('id')
                if idx is None:
                    idx = d.get('index')
                if idx is not None:
                    jsonl_items.add(str(idx))
    except Exception as e:
        issues.append(f"WARNING: 無法讀取 JSONL ({e})，跳過覆蓋率檢查")
        return issues

    # 讀取 ref 檔中的錨點 item_index（排除 skill.md，其說明性文字可能含 item_index）
    anchored = set()
    for fname, text in files.items():
        if fname == "skill.md":
            continue
        for m in re.finditer(r'item_index=(\d+)', text):
            anchored.add(m.group(1))

    missing = jsonl_items - anchored
    covered = jsonl_items & anchored
    coverage = (len(covered) / len(jsonl_items) * 100) if jsonl_items else 0

    print(f"  覆蓋率：{len(covered)}/{len(jsonl_items)} items = {coverage:.1f}%")

    if missing:
        # (0, int) 排數字；(1, str) 排非數字；同型別可比較，不會 TypeError
        missing_sorted = sorted(missing, key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
        issues.append(
            f"SEVERE: {len(missing)} 個 JSONL item 未被任何錨點覆蓋：{missing_sorted}"
        )

    return issues

def check_no_placeholder(files):
    """找出還沒替換的模板佔位符（跳過 fenced code block、inline code、blockquote 中的範例字串）"""
    issues = []
    placeholders = ['<書名>', '<作者>', '<skill-name>', '<skill_name>', 'TODO', 'FIXME', '<待填>']
    fence = '\x60' * 3  # 用 \x60 組成三反引號，避免截斷 markdown code fence
    for fname, text in files.items():
        clean = re.sub(fence + r'[\s\S]*?' + fence, '', text)   # 去除 fenced code block
        clean = re.sub(r'\x60[^\x60\n]+\x60', '', clean)        # 去除 inline code
        clean = re.sub(r'^>.*$', '', clean, flags=re.MULTILINE)  # 去除 blockquote 行
        for ph in placeholders:
            if ph in clean:
                issues.append(f"MEDIUM: {fname} 包含未替換的佔位符 '{ph}'")
    return issues

def check_ref_not_empty(files):
    """找出過短的 ref 檔（可能是空骨架）"""
    issues = []
    for fname, text in files.items():
        if fname == "skill.md":
            continue
        lines = [l for l in text.split('\n') if l.strip()]
        if len(lines) < 5:
            issues.append(f"SEVERE: {fname} 內容過少（只有 {len(lines)} 行有效內容），可能是空骨架")
    return issues

def main():
    if len(sys.argv) < 2:
        print("用法：python3 validate.py <skill-dir> [<jsonl-path>]")
        sys.exit(1)

    skill_dir  = sys.argv[1]
    jsonl_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isdir(skill_dir):
        print(f"錯誤：找不到目錄 {skill_dir}")
        sys.exit(1)

    if not os.path.exists(os.path.join(skill_dir, "skill.md")):
        print(f"警告：{skill_dir} 中找不到 skill.md，請確認這是一個 skill 目錄")
        print("（如果 skill.md 還未建立，可先跑 03-skill-scaffold.md §2.3 建立骨架）")

    print(f"\n{'='*60}")
    print(f" rag-to-skill Validator")
    print(f" Skill:  {skill_dir}")
    print(f" JSONL:  {jsonl_path or '(未提供，跳過 JSONL 覆蓋率檢查)'}")
    print(f"{'='*60}\n")

    files = load_skill_files(skill_dir)
    print(f"讀取到 {len(files)} 個 Markdown 檔：{list(files.keys())}\n")

    all_issues = []

    print("--- [1/5] Frontmatter 完整性 ---")
    skill_text = files.get("skill.md", "")
    issues = check_frontmatter(skill_text)
    all_issues.extend(issues)
    print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    print("--- [2/5] 空骨架檢查 ---")
    issues = check_ref_not_empty(files)
    all_issues.extend(issues)
    print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    print("--- [3/5] 內部連結 ---")
    issues = check_internal_links(skill_dir, files)
    all_issues.extend(issues)
    print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    print("--- [4/5] RAG 錨點密度 ---")
    issues = check_anchor_density(files, jsonl_provided=jsonl_path is not None)
    all_issues.extend(issues)
    print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    print("--- [5/5] 佔位符殘留 ---")
    issues = check_no_placeholder(files)
    all_issues.extend(issues)
    print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    if jsonl_path:
        print("--- [+1] JSONL item 覆蓋率 ---")
        issues = check_jsonl_coverage(skill_dir, jsonl_path, files)
        all_issues.extend(issues)
        print(f"  {'✓' if not issues else f'✗ {len(issues)} 個問題'}")

    # 分級彙整
    severe  = [i for i in all_issues if i.startswith("SEVERE")]
    medium  = [i for i in all_issues if i.startswith("MEDIUM")]
    warning = [i for i in all_issues if i.startswith("WARNING")]

    print(f"\n{'='*60}")
    if not severe and not medium:
        print(" ✓ PASS — 所有關鍵檢查通過")
    else:
        print(f" ✗ FAIL — {len(severe)} Severe, {len(medium)} Medium, {len(warning)} Warning")

    if severe:
        print("\nSEVERE（必須修復）:")
        for i in severe: print(f"  • {i}")

    if medium:
        print("\nMEDIUM（建議修復）:")
        for i in medium: print(f"  • {i}")

    if warning:
        print("\nWARNING（注意）:")
        for i in warning: print(f"  • {i}")

    print(f"{'='*60}\n")
    sys.exit(1 if severe else 0)

if __name__ == "__main__":
    main()
```

---

## 使用方式

### 步驟 0：從本檔提取 validate.py

```bash
python3 << 'EXTRACT'
import re, os, sys
path = os.path.expanduser('~/.claude/skills/rag-to-skill/references/06-validation-scripts.md')
content = open(path, encoding='utf-8').read()
m = re.search(r'```python\n(.*?)```', content, re.DOTALL)
if not m:
    sys.exit('ERROR: 無法找到 python code block，請確認 06-validation-scripts.md 格式正確')
open('validate.py', 'w', encoding='utf-8').write(m.group(1))
print(f'validate.py 已提取到當前目錄（{len(m.group(1).splitlines())} 行）')
EXTRACT
```

### 執行驗證

```bash
# 基本驗證（不需要 JSONL）
python3 validate.py path/to/my-skill/

# 含 JSONL 覆蓋率驗證（完整驗證）
python3 validate.py path/to/my-skill/ path/to/source.jsonl

# 範例（ziwei 格式）
python3 validate.py ~/.claude/skills/紫微攻略/ ~/Developer/repos/ziwei/RAG/紫微攻略.jsonl
```

---

## 輸出解讀

| 輸出 | 意義 | 行動 |
|---|---|---|
| `✓ PASS` | 所有關鍵檢查通過 | 可進交付流程 |
| `SEVERE` | 必須修復才能交付 | 對照 07-completion-checklist.md |
| `MEDIUM` | 建議修復，不擋交付 | 評估修復成本 |
| `WARNING` | 注意事項，不計 fail | 可選擇性處理 |

---

## 腳本限制（已知）

| 限制 | 說明 |
|---|---|
| 不做語意稽核 | 無法判斷「content 是否忠實原書」，只驗證結構 |
| JSONL schema 假設 | 嘗試多種常見欄位名稱，非標準 schema 需手動調整 |
| 不驗證錨點的 item_index 是否真實存在於 JSONL | 只查 skill 中的數字是否匹配 JSONL 的 index 列表 |

---

**下一步** → validate.py 輸出 `✓ PASS` 後，進 `references/07-completion-checklist.md` 執行交付前 checklist（含手動 S6/S7 稽核）
