---
name: pdf-ocr
description: |
  掃描版 PDF（純圖像，無文字層）→ JSONL，使用 Claude Code 視覺能力逐頁 OCR。
  不需要額外 Anthropic API 費用，消耗當前 session token。
  每次最多處理一個 batch（預設 30 頁），支援 --resume 斷點續跑。
  觸發時機：
  - 使用者說「OCR 這個 PDF」
  - 使用者說「把掃描 PDF 做成 JSONL」
  - 使用者說「/pdf-ocr <path>」
  - 使用者說「用 Claude 辨識這個 PDF 的文字」
  典型呼叫：
  - /pdf-ocr /path/to/book.pdf
  - /pdf-ocr /path/to/book.pdf /path/to/output.jsonl
  - /pdf-ocr /path/to/book.pdf --resume
  - /pdf-ocr /path/to/book.pdf --batch 20 --dpi 120
---

# PDF OCR → JSONL（Claude Code Vision）

> 使用 Claude Code 的 Read tool 視覺能力逐頁辨識掃描 PDF，輸出 rag-to-skill 相容的 JSONL 格式。

---

## 參數解析

從使用者輸入解析以下參數：

| 參數 | 說明 | 預設值 |
|---|---|---|
| `PDF_PATH` | PDF 檔案路徑（必要） | — |
| `OUTPUT_PATH` | 輸出 JSONL 路徑（選用） | PDF 同目錄 + .jsonl |
| `--resume` | 從上次中斷點繼續 | false |
| `--batch N` | 每次最多處理頁數 | 30 |
| `--dpi N` | 圖片渲染解析度 | 100 |

**PROGRESS_FILE** = `OUTPUT_PATH + ".ocr-progress.json"`

---

## 執行流程

### Step 0：前置檢查

1. 確認 `PDF_PATH` 存在
2. 若 `OUTPUT_PATH` 未指定，設為 `PDF_PATH` 同目錄、副檔名換成 `.jsonl`
3. 若 `--resume`：
   - 讀取 `PROGRESS_FILE`
   - 告知使用者「已完成 X / 總頁數 Y 頁，繼續剩餘...」
4. 若非 `--resume`（全新開始）：
   - 初始化進度結構（見下方 §進度結構）

---

### Step 1：提取頁面圖片

執行 extract_pages.py 把 PDF 轉成 PNG 圖片：

```bash
python3 ~/.claude/skills/pdf-ocr/extract_pages.py \
  "<PDF_PATH>" \
  "<PNG_DIR>" \
  --dpi <DPI>
```

- `PNG_DIR` = 若進度中已有 `png_dir` 且目錄存在則沿用，否則用 `/tmp/pdf-ocr-<uuid4前8碼>/`
- 腳本輸出的最後兩行包含 `TOTAL:<n>` 和 `OUT_DIR:<path>`，從中讀取 `TOTAL_PAGES`

---

### Step 2：決定本次 batch 範圍

```
已完成 = PROGRESS.completed_pages（整數 list，0-based）
待處理 = sorted([i for i in range(TOTAL_PAGES) if i not in 已完成])
本次 batch = 待處理[:BATCH_SIZE]
```

若 `本次 batch` 為空 → 跳到 Step 5（全部完成）

告知使用者：「本次處理第 {min+1}–{max+1} 頁（共 {len(batch)} 頁）...」

---

### Step 3：逐頁 OCR

對 `本次 batch` 中的每一頁 `page_idx`（0-based）：

**3a. 讀取圖片**
用 Read tool 讀取：`{PNG_DIR}/page_{page_idx:04d}.png`

**3b. 判斷頁面類型並轉錄**

用以下標準判斷：

| 類型 | 判斷標準 | 處理方式 |
|---|---|---|
| 空白 / 封面 / 純圖片 | 幾乎沒有可辨識的文字 | SKIP，記錄 `skip=true` |
| 章節標題頁 | 有明顯大標題（居中、字體大、第X章 等） | 更新 `current_chapter`，`item_index +1` |
| 一般文字頁 | 有連續文字段落 | 轉錄原文 |

轉錄原則：
- 完整逐字轉錄，保留標點符號
- 若一頁同時有標題和正文，先記錄章節名，再轉錄正文
- 頁碼、書名行等重複性 header/footer 可省略

**3c. 切 chunks**

若有轉錄文字，切成 ≤ 500 字的 chunks（優先在段落 `\n` 或句號 `。` 邊界切割）。

**3d. 建立 records**

```json
{
  "loc": {"item_index": <current_item_index>, "chunk_index": <ci>},
  "chapter": "<current_chapter>",
  "text": "<chunk_text>"
}
```

`ci` 從 `PROGRESS.item_chunk_counts[str(item_index)]` 取得並遞增。

**3e. 更新進度並立即存檔**

更新 `PROGRESS`：
- `completed_pages` 加入 `page_idx`
- `current_chapter` 更新
- `current_item_index` 更新
- `item_chunk_counts` 更新
- `records` 加入新 records

立即寫入 `PROGRESS_FILE`（每頁完成後都要存，確保中斷可恢復）。

---

### Step 4：回報進度

每處理完 5 頁，輸出一行進度：
```
[15/30] 頁 16-20：已完成，累計 87 records，目前章節：第三章：命宮
```

---

### Step 5：寫出 JSONL

本次 batch 全部完成後（或全部頁面完成後），從 `PROGRESS.records` 寫出 JSONL：

```python
import json
records = json.load(open(PROGRESS_FILE))["records"]
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
```

> 每次 batch 完成後都重寫完整 JSONL，確保文件始終是最新的。

---

### Step 6：結束回報

**若還有剩餘頁面**：
```
✅ 本次完成 {len(batch)} 頁（第 {start+1}–{end+1} 頁）
📄 累計 {total_records} records，JSONL 已更新：{OUTPUT_PATH}
📌 剩餘 {remaining} 頁，請執行：
   /pdf-ocr {PDF_PATH} --resume
```

**若全部完成**：
- 刪除 `PROGRESS_FILE` 和 PNG 暫存目錄
```
🎉 OCR 完成！
📄 共 {total_pages} 頁，{total_records} records
💾 輸出：{OUTPUT_PATH}
➡️  下一步：在 Claude Code 輸入「把 {OUTPUT_PATH} 做成 skill」
```

---

## 進度結構（PROGRESS_FILE 格式）

```json
{
  "pdf_path": "/path/to/book.pdf",
  "output_path": "/path/to/output.jsonl",
  "total_pages": 419,
  "png_dir": "/tmp/pdf-ocr-a1b2c3d4",
  "completed_pages": [0, 1, 2, 3],
  "current_chapter": "第一章：命宮",
  "current_item_index": 2,
  "item_chunk_counts": {"0": 3, "1": 2, "2": 1},
  "records": [
    {"loc": {"item_index": 0, "chunk_index": 0}, "chapter": "（前言）", "text": "..."},
    ...
  ]
}
```

---

## 注意事項

- 每次最多處理 BATCH_SIZE 頁（預設 30），超過會因 context 過大影響品質
- PNG 暫存目錄在全部完成後自動刪除；中途 session 結束不影響（下次 --resume 時重新提取）
- 若某頁 Read tool 讀圖失敗，記錄為 `skip=true` 並繼續
- DPI 100 適合一般中文書籍；手寫或模糊頁面建議 --dpi 150
