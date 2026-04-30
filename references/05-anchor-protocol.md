# 階段 5：RAG 錨點標注協議

> 錨點 = skill 與原書之間的可驗證連結。沒有錨點的斷言是 AI 編造風險點。
> 本協議適用於任何語言、任何書籍。

---

## 5.1 標準錨點格式

```markdown
> 來源：《<書名>》<章節名>（RAG item_index=<X>.<Y>）
```

| 部件 | 說明 | 範例 |
|---|---|---|
| `《<書名>》` | 書名用書名號，中文全形 | `《紫微攻略》` |
| `<章節名>` | JSONL 的 `chapter` 欄位，原文不改 | `第三章：宮位派解盤法` |
| `item_index=<X>.<Y>` | X = item_index，Y = chunk_index | `item_index=12.3` |

若 chunk_index 為 0（單 chunk item），可只寫 `item_index=<X>`（省略 `.0`）。

---

## 5.2 放置位置規則

| 情況 | 放置位置 |
|---|---|
| 單一概念/原則段落 | 段落末尾，緊接在最後一行之後 |
| 多 chunk 的長篇章節 | 每個 chunk 的原文末尾各一個錨點 |
| 表格（來自原書） | 表格下方一行 |
| 整個 H2 小節的所有內容來自同一 item | H2 開頭 OR 結尾，選一，保持一致 |

**範例：單一段落**

```markdown
## 二、宮位的基本概念

十二宮位是紫微斗數的空間座標，代表人生十二個面向：
命宮（本質）、兄弟宮（手足）、夫妻宮（伴侶）...

> 來源：《紫微攻略》第一章（RAG item_index=5）
```

**範例：多 chunk 長章**

```markdown
## 三、四化的原理

化祿代表流動、增益；化權代表主導、掌控...

> 來源：《紫微斗數新銓》第四章（RAG item_index=15.0）

祿存必須與天馬同宮或對宮才能發揮最大效益...

> 來源：《紫微斗數新銓》第四章（RAG item_index=15.1）
```

---

## 5.3 錨點密度標準

**最低要求**：每 1000 行內容 ≥ 15 個錨點。

計算方式：

```bash
SKILL_DIR="<你的 skill 目錄>"

# 計算所有 ref 檔的總行數和錨點數
python3 << 'EOF'
import glob, re, os

skill_dir = "<你的 skill 目錄>"

total_lines = 0
total_anchors = 0

for md_file in sorted(glob.glob(f"{skill_dir}/references/*.md")):
    text = open(md_file, encoding='utf-8').read()
    lines = len(text.split('\n'))
    anchors = len(re.findall(r'item_index=\d+', text))
    density = anchors / lines * 1000 if lines > 0 else 0
    total_lines += lines
    total_anchors += anchors
    status = "✓" if density >= 15 else "⚠ LOW"
    print(f"{status} {os.path.basename(md_file)}: {lines} lines, {anchors} anchors, {density:.1f}/1000")

print()
total_density = total_anchors / total_lines * 1000 if total_lines > 0 else 0
status = "✓ PASS" if total_density >= 15 else "✗ FAIL"
print(f"{status} TOTAL: {total_lines} lines, {total_anchors} anchors, {total_density:.1f}/1000")
EOF
```

---

## 5.4 常見錨點錯誤

| 錯誤 | 問題 | 修正 |
|---|---|---|
| `(RAG item_index=12)` 放在一段四行原文後 | 不知道是哪行的來源 | 每個概念段落一個錨點 |
| `(RAG item_index=?)` | 不知道 item_index | 回 JSONL 確認 |
| 只寫 item_index 沒寫書名 | 跨 skill 無法追溯 | 完整格式必填書名 |
| `item_index=5-10` 範圍錨點 | 驗證腳本無法 parse | 改成逐 item 各一錨點 |
| 錨點放在說明文字上 | 說明文字不是 RAG 原文 | 只在原文段落加錨點 |

---

## 5.5 不需要加錨點的地方

| 位置 | 原因 |
|---|---|
| skill.md frontmatter（yaml 區塊） | 非內容 |
| skill.md 的 Reference 目錄表格 | 結構索引，非原書內容 |
| 快速查詢索引表格 | 導流，非原書內容 |
| ref 檔的「使用本檔的時機」表格 | 是導流說明，非原書內容 |
| 章節標題行（`## 三、...`） | 標題本身無需錨點 |

---

## 5.6 大量補錨點的策略

如果 ref 檔內容已填完但錨點密度不足，按以下順序補：

1. **找所有無錨點的原文段落**（每兩個換行之間的文字塊）
2. **對照 JSONL 確認 item_index**（用 02-jsonl-scan.md §1.1 的提取指令）
3. **逐段加錨點**，每段末尾一個，精確到 chunk 若可能
4. **重跑密度計算確認 ≥15/1000**

---

**下一步** → `references/06-validation-scripts.md`（執行 validate.py 全量驗證）
