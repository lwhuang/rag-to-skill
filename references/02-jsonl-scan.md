# 階段 1：JSONL 結構探索

> 目標：在 5 分鐘內完全理解這份 JSONL 的 schema、有多少 entity、如何分組。

## 前置：還沒有 JSONL？先轉換

如果手上是 PDF / EPUB / DOCX / PPTX / HTML，用以下工具先轉成 JSONL：

```bash
# 萬用（推薦，任何格式）
pip install markitdown
python3 ~/.claude/skills/rag-to-skill/any_to_jsonl.py <你的檔案>

# PDF 專用（TOC 分章 + header/footer 過濾，品質更高）
pip install pymupdf
python3 ~/.claude/skills/rag-to-skill/pdf_to_jsonl.py <你的.pdf>

# EPUB 專用（spine 順序，章節標題更準確）
pip install ebooklib beautifulsoup4
python3 ~/.claude/skills/rag-to-skill/epub_to_jsonl.py <你的.epub>
```

轉換完成後繼續以下步驟。

---

---

## 1.1 自動 Schema 發現

不要假設 schema。用這段程式碼發現實際欄位：

```bash
# 將下一行換成你的實際 JSONL 路徑（支援含空格、單引號的路徑）
export JSONL="<path/to/source.jsonl>"

python3 << 'EOF'
import json, os

path = os.environ['JSONL']
# 注意：全量載入；大型 JSONL（>1GB）建議改用串流方式
with open(path, encoding='utf-8') as f:
    lines = [json.loads(l) for l in f if l.strip()]

print(f'=== JSONL SCHEMA REPORT ===')
print(f'Total lines: {len(lines)}')
print()

# 找出所有 top-level key
all_keys = set()
for d in lines: all_keys.update(d.keys())
print(f'Top-level keys: {sorted(all_keys)}')
print()

# 嵌套 key 探測（最多兩層）
sample = lines[0]
for k, v in sample.items():
    if isinstance(v, dict):
        print(f'  {k} (dict): {sorted(v.keys())}')
    else:
        print(f'  {k}: {type(v).__name__} = {repr(str(v)[:80])}')
print()

# 嘗試猜 item_index / chapter / text 欄位
def get_field(d, *candidates):
    for c in candidates:
        if c in d: return d[c]
        for v in d.values():
            if isinstance(v, dict) and c in v: return v[c]
    return None

print('=== ENTITY OVERVIEW ===')
items_seen = {}
for d in lines:
    idx   = get_field(d, 'item_index', 'id', 'index', 'chunk_id')
    ch_i  = get_field(d, 'chunk_index', 'chunk', 'sub_index')
    chap  = get_field(d, 'chapter', 'title', 'section', 'heading')
    text  = get_field(d, 'text', 'content', 'body', 'passage')
    key = str(idx)
    if key not in items_seen:
        items_seen[key] = {'chapter': chap, 'chunks': 0, 'chars': 0}
    items_seen[key]['chunks'] += 1
    items_seen[key]['chars'] += len(str(text or ''))

print(f'Unique items: {len(items_seen)}')
print()
def sort_key(k):
    return int(k) if k.isdigit() else k
for k, v in sorted(items_seen.items(), key=lambda x: sort_key(x[0])):
    print(f'  [{k}] ch={str(v["chapter"])[:40]} chunks={v["chunks"]} chars={v["chars"]}')
EOF
```

---

## 1.2 解讀 Schema 報告

Schema 報告完成後，記下以下四個問題的答案：

| 問題 | 範例答案（ziwei 格式） | 你的答案 |
|---|---|---|
| item_index 欄位叫什麼？ | `loc.item_index` | ___ |
| chunk_index 欄位叫什麼？ | `loc.chunk_index` | ___ |
| 章節名稱欄位叫什麼？ | `chapter` | ___ |
| 文字內容欄位叫什麼？ | `text` | ___ |

記下這四個答案，後面 Step 4 提取原文時會用到。

---

## 1.3 章節樹生成

把 entity 按章節分組，找出分組邏輯：

```bash
# JSONL 變數已在 §1.1 設好，直接繼續用
python3 << 'EOF'
import json, os
from collections import OrderedDict

with open(os.environ['JSONL'], encoding='utf-8') as f:
    lines = [json.loads(l) for l in f if l.strip()]

chapters = OrderedDict()
for d in lines:
    # ===== 依你的 schema 調整這兩行 =====
    idx  = d.get('loc', {}).get('item_index', d.get('item_index', '?'))
    chap = d.get('chapter', d.get('title', '?'))
    # =====================================
    if chap not in chapters:
        chapters[chap] = []
    if idx not in chapters[chap]:
        chapters[chap].append(idx)

print('=== CHAPTER TREE ===')
for ch, items in chapters.items():
    print(f'  {str(ch)[:60]}')
    print(f'    items: {items}')
    print()
EOF
```

---

## 1.4 Size Outlier 標記

size outlier = 同類 ref 計畫中某組的 item 總 chars 遠小於其他組（可能有缺漏）。

```bash
python3 << 'EOF'
import json, os

groups = {
    'group1': [10, 11, 12, 13],   # 換成你的分組
    'group2': [20, 21, 22],
    # ...
}

with open(os.environ['JSONL'], encoding='utf-8') as f:
    lines = [json.loads(l) for l in f if l.strip()]

data = {}
for d in lines:
    idx = d.get('loc', {}).get('item_index', d.get('item_index'))
    text = d.get('text', d.get('content', ''))
    if idx not in data: data[idx] = 0
    data[idx] += len(str(text))

print('=== GROUP SIZE CHECK ===')
for gname, items in groups.items():
    total = sum(data.get(i, 0) for i in items)
    print(f'  {gname}: {total} chars ({items})')
EOF
```

平均大小的 20% 以下 → 標記為可能不完整，Phase 2 優先調查。

---

## 1.5 產出：Entity 清單模板

完成 1.1-1.4 後，填寫此表格（手動或讓 Claude 填）：

| item_index | 章節 / 主題名稱 | 字數 | 預計 ref 檔歸屬 | 備註 |
|---|---|---|---|---|
| 1 | 序章 | 800 | (不需 ref) | 前言 |
| 2 | 第一章：... | 3200 | 01-chapter1.md | |
| ... | ... | ... | ... | |
| **孤兒** | 找不到章節的 item | — | **待決定** | Severe 風險 |

這張表格就是整個 Build 流程的路線圖。

---

**下一步** → `references/03-skill-scaffold.md §2.1`（依此表格規劃 ref 檔分組，建立骨架）
