# 快速啟動（指令壓縮版）

> 已熟悉流程的人看這裡。**第一次使用請從 `02-jsonl-scan.md` 開始**（階段 1 SCAN），或直接讀 `skill.md` 看整體流程。
>
> **五步 = 七階段的壓縮版**：Step 1 = 階段 1（SCAN），Step 2 = 階段 2-3（PLAN+SCAFFOLD），Step 3 = 階段 3，Step 4 = 階段 4-5（BUILD+ANCHOR），Step 5 = 階段 6-7（AUDIT+SHIP）。完整七階段流程表格（含輸入/產出/完成條件）見 `skill.md §二`。
>
> **時間提示**：Step 1-3 約 30 分鐘；Step 4 是主要工時，視 JSONL 大小需 1 小時至數天（見 `08-case-example.md §七` 時間估計）。

---

## 前置確認

```bash
# 1. 確認 JSONL 存在且非空
wc -l "<path/to/source.jsonl>"

# 2. 確認 python3 可用
python3 --version
```

---

## 五步完成（最簡情境）

### Step 1：JSONL 快速掃描

```bash
python3 -c "
import json, collections
items = collections.defaultdict(list)
with open('<path/to/source.jsonl>', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        # 嘗試常見 schema 欄位（用 is None 判斷，item_index=0 不被 falsy 丟棄）
        _loc = d.get('loc') or {}
        idx = _loc.get('item_index')
        if idx is None: idx = d.get('item_index')
        if idx is None: idx = d.get('id')
        if idx is None: idx = '?'
        idx = str(idx)
        ch  = d.get('chapter') or d.get('title') or d.get('section') or '?'
        txt = d.get('text') or d.get('content') or d.get('body') or ''
        items[idx].append((ch, len(txt)))
print(f'Total unique items: {len(items)}')
for k,v in list(items.items())[:10]:
    print(f'  item {k}: chapter={v[0][0][:40]} chunks={len(v)} total_chars={sum(x[1] for x in v)}')
print('...(only first 10 shown)')
"
```

產出：知道有多少 item、主要章節名稱。

### Step 2：規劃分組（腦中或紙上，1-2 分鐘）

原則：
- 同一章節 / 主題 → 同一 ref 檔
- 單一 ref 檔建議 30-80 個 item，超過就分兩檔
- 建議 3-8 個 ref 檔（太少 → 檔案過大；太多 → 難查詢）

### Step 3：建立目錄骨架

```bash
SKILL_NAME="ebook-<skill-name>" # 必須以 ebook- 開頭，例如 ebook-acim-text
BOOK_TITLE="<書名>"
BOOK_AUTHOR="<作者>"
SKILL_DIR="$HOME/.agents/skills/$SKILL_NAME"
mkdir -p "$SKILL_DIR/references"

# 建立空的 ref 檔（依你的分組決定）
touch "$SKILL_DIR/references/01-<group1>.md"
touch "$SKILL_DIR/references/02-<group2>.md"
# ...依實際分組加更多

# 建立 skill.md 骨架（使用完整模板，見 03-skill-scaffold.md §2.4）
# 此處省略 inline 模板，避免與 §2.4 版本不同步
touch "$SKILL_DIR/skill.md"
echo "skill.md 已建立，請複製 03-skill-scaffold.md §2.4 的完整模板填入"
```

> skill.md 完整模板在 `references/03-skill-scaffold.md §2.4`，包含四節結構（核心概念、主體框架、Reference 目錄、快速查詢索引）。複製並替換所有 `<佔位符>` 即可。

### Step 4：填充內容（主要工作）

對每個 ref 檔，用此指令提取對應 item 的原文：

```bash
# JSONL 變數已在 §1.1 設好（export JSONL="<path>"）
# 若在新 session 執行，記得先重新 export JSONL="..."
python3 << 'EOF'
import json, os, sys

TARGET_ITEMS = {10, 11, 12, 13}  # 換成你這個 ref 檔對應的 item_index（用 set 加速查詢）

JSONL_PATH = os.environ.get('JSONL')
if not JSONL_PATH:
    sys.exit("錯誤：JSONL 環境變數未設定，請先執行 export JSONL=\"<path>\"")
with open(JSONL_PATH, encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        _loc = d.get('loc') or {}
        idx = _loc.get('item_index')
        if idx is None: idx = d.get('item_index')
        # 同時支援 int 和 str 型別的 item_index
        try:
            idx_key = int(idx) if idx is not None else None
        except (TypeError, ValueError):
            idx_key = idx
        if idx_key in TARGET_ITEMS:
            ch_idx = (d.get('loc') or {}).get('chunk_index', 0)
            print(f'=== item {idx}.{ch_idx} ===')
            print(d.get('text') or d.get('content') or '')
            print()
EOF
```

把輸出的原文**忠實移植**到 ref 檔，加上章節結構與 RAG 錨點（見 Step 5）。

### Step 5：加錨點 + 驗證

每段原文後加錨點：

```markdown
> 來源：《<書名>》<章名>（RAG item_index=<X>.<Y>）
```

驗證：

```bash
# 提取 validate.py（從 06-validation-scripts.md 一鍵取出）
python3 << 'EXTRACT'
import re, os, sys
path = os.path.expanduser('~/.agents/skills/rag-to-skill/references/06-validation-scripts.md')
content = open(path, encoding='utf-8').read()
m = re.search(r'```python\n(.*?)```', content, re.DOTALL)
if not m:
    sys.exit('ERROR: 無法找到 python code block，請確認 06-validation-scripts.md 格式正確')
open('validate.py', 'w', encoding='utf-8').write(m.group(1))
print(f'validate.py 已提取到當前目錄（{len(m.group(1).splitlines())} 行）')
EXTRACT

# 執行驗證（$SKILL_DIR 在 Step 3 設定）
python3 validate.py "$SKILL_DIR"
```

全綠 → 進 references/07-completion-checklist.md 確認後安裝。

---

## 常見陷阱（一行版）

| 陷阱 | 正確做法 |
|---|---|
| 自己「整理」或「精簡」原文 | 逐字移植，保留原書分段與例子 |
| 先寫 skill.md 再建 ref | 先建 ref（有 RAG），再寫 skill.md 引用 |
| 忘記跨檔同步（新增 ref 但沒更新 skill.md §Reference 目錄） | 每次新增/刪除 ref 立刻更新 skill.md |
| 錨點只寫到 item 不寫 chunk | 精確到 `X.Y`，能精確就精確 |
| Skill 名稱太隨意 | 統一以 `ebook-` 開頭（如 `ebook-ziwei`），一眼區別於工具類 skill |
