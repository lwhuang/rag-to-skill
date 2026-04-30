# 階段 4：內容填充（RAG → Reference）

> 核心原則：**忠實移植**。ref 檔是原書文字的結構化容器，不是摘要。
> 唯一允許的加工：加標題、加 RAG 錨點、加「使用時機」說明表格。

---

## 4.1 提取原文指令

對每個 ref 檔，提取對應 items 的原文：

```bash
python3 << 'EOF'
import json, os, sys

JSONL_PATH = os.environ.get('JSONL', 'RAG/<book>.jsonl')  # 或先 export JSONL="..."
TARGET_ITEMS = {10, 11, 12}             # 換成這個 ref 檔對應的 item_index（set 加速查詢）

# === 依你的 JSONL schema 調整這幾行 ===
def get_index(d):
    _loc = d.get('loc') or {}
    idx = _loc.get('item_index')
    if idx is None: idx = d.get('item_index')
    if idx is None: idx = d.get('id')
    return idx
def get_chunk(d):
    _loc = d.get('loc') or {}
    v = _loc.get('chunk_index')
    if v is None: v = d.get('chunk_index')
    return v if v is not None else 0
def get_text(d):   return d.get('text') or d.get('content') or d.get('body') or ''
def get_chapter(d): return d.get('chapter') or d.get('title') or d.get('section') or ''
# =======================================

with open(JSONL_PATH, encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        idx = get_index(d)
        try:
            idx_key = int(idx) if idx is not None else None
        except (TypeError, ValueError):
            idx_key = idx
        if idx_key in TARGET_ITEMS:
            ch_i = get_chunk(d)
            chap = get_chapter(d)
            text = get_text(d)
            print(f"\n{'='*60}")
            print(f"item_index={idx}  chunk={ch_i}  chapter={chap}")
            print(f"{'='*60}")
            print(text)
EOF
```

---

## 4.2 Reference 檔結構模板

填充每個 ref 檔時，使用以下結構：

```markdown
# <分組標題，對應原書章節名>

> 來源：《<書名>》<作者>（<出版年>）
> 本檔涵蓋 items <X>–<Y>，共 <N> 個主要主題。

---

## 一、<主題/章節名稱 1>

<原文逐字移植。保留原書：>
<- 所有條列項目>
<- 所有小節標題>
<- 所有生活例子/案例>
<- 原書的語氣與措辭>

> 來源：《<書名>》<章節名>（RAG item_index=<X>.<Y>）

---

## 二、<主題/章節名稱 2>

<原文逐字移植...>

> 來源：《<書名>》<章節名>（RAG item_index=<X>.<Y>）

---

## <最後一節>：使用本檔的時機

| 使用者提問 | 對應段落 |
|---|---|
| 「<使用者可能的問法 1>」 | §一 <主題 1> |
| 「<使用者可能的問法 2>」 | §二 <主題 2> |
```

---

## 4.3 忠實度規則（嚴格）

這些事情**絕對不做**：

| 禁止行為 | 原因 |
|---|---|
| 「整理」或「精簡」原文 | 壓縮 = AI 編造的溫床；原文是溯源基礎 |
| 合併兩個原書段落為一段 | 破壞 item 邊界，讓錨點失去意義 |
| 為每個概念「補充例子」 | 補充的內容無 RAG 溯源 → Severe 問題 |
| 改寫原書的判斷或說法 | 你的改寫 ≠ 作者的意圖 |
| 「因為書沒講清楚所以我補充」 | 書沒講 = 這個 ref 檔就不講 |

這些事情**允許做**：

| 允許行為 | 說明 |
|---|---|
| 加 Markdown 標題（`## 一、...`） | 結構化，不改內容 |
| 加 `> 來源：...` 錨點 | 必須 |
| 加「使用本檔的時機」表格 | 導流，內容只引用既有段落 |
| 合理斷行（長段分多行） | 不改語意的排版 |
| 標記術語（加粗 `**`） | 只加強，不改字 |

---

## 4.4 逐 Item 填充循環

對每個 ref 檔，按以下順序執行：

```
for each item in 此 ref 檔的 item 清單:
    1. 執行 4.1 的 python3 指令，取得原文輸出
    2. 複製原文到 ref 檔對應段落
    3. 加 H2 標題（原書章節名或主題名）
    4. 在段落末加 RAG 錨點（見 05-anchor-protocol.md）
    5. 如有多個 chunk（.0 .1 .2 ...），全部包含，逐 chunk 各一錨點
```

> **可以邊填邊加錨點**：不需要等到整個 ref 填完再補錨點。填一個 item 就加一個錨點，中途中斷也不會有未標注段落。

**中途中斷後如何繼續**：執行 §4.6 的孤兒檢查腳本，`Missing item indices` 就是還沒填的 item 清單，直接從那裡繼續。

---

## 4.5 跨檔同步規則

每次新增 ref 檔內容後，必須同步 skill.md：

| 觸發 | 必須同步的地方 |
|---|---|
| 新增 ref 檔或新填充 ref | `skill.md §三 Reference 目錄` 表格 |
| 新增核心概念 | `skill.md §四 快速查詢索引` |
| 新增 ref 但 skill.md 沒提到 | 在 skill.md 對應章節加「詳見 references/xxx.md」 |
| 刪除 ref 或 ref 內容 | 同步刪除 skill.md 對應引用 |

---

## 4.6 完成度自查

每個 ref 檔填完後，用此指令確認沒有孤兒 item：

```bash
python3 << 'EOF'
import json, re, glob, os

JSONL_PATH = os.environ.get('JSONL', 'RAG/<book>.jsonl')  # 或先 export JSONL="..."
SKILL_DIR  = "<skill-dir>"

# 讀取所有 JSONL item_index（用 is None 判斷，item_index=0 不被 falsy 丟棄）
jsonl_items = set()
with open(JSONL_PATH, encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        _loc = d.get('loc') or {}
        idx = _loc.get('item_index')
        if idx is None: idx = d.get('item_index')
        if idx is None: idx = d.get('id')
        if idx is not None:
            jsonl_items.add(str(idx))

# 讀取所有 ref 檔中的錨點 item_index
anchored = set()
for md_file in glob.glob(f"{SKILL_DIR}/references/*.md"):
    text = open(md_file, encoding='utf-8').read()
    for m in re.finditer(r'item_index=(\d+)', text):
        anchored.add(m.group(1))

missing = jsonl_items - anchored
print(f"JSONL items: {len(jsonl_items)}")
print(f"Anchored items: {len(anchored)}")
print(f"Missing (not anchored): {len(missing)}")
if missing:
    print(f"  Missing item indices: {sorted(missing, key=lambda x: (0, int(x)) if x.isdigit() else (1, x))}")
else:
    print("  All items accounted for!")
EOF
```

`Missing = 0` → 可進階段 5（錨點標注）。
`Missing > 0` → 回頭補對應 ref 內容。

**空 item 處理**：若某 item 的 JSONL 文字極短（< 50 字，如圖片頁、空白頁），仍須在 ref 檔中加佔位標注，不可直接跳過——否則 `validate.py` 的 JSONL 覆蓋率檢查無法通過。做法：建一個 H2 小節，加一行說明原因，再接標準 RAG 錨點（`item_index=N`）即可。
