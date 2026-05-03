# 階段 2-3：架構規劃 + 骨架生成

> 目標：把 entity 清單變成目錄結構。完成後目錄存在，所有 ref 檔為空。

---

## 2.1 分組原則

分組 = 決定「幾個 ref 檔，每個涵蓋哪些 item」。

**好的分組原則（按優先序）**：

1. **原書分章** > 自己命名：JSONL 的 `chapter` 欄位是最天然的分界
2. **3-8 個 ref 檔**：太少（>80 items/檔）難查；太多（<10 items/檔）沒意義
3. **單一語意主題**：「所有星曜現象」 ✓；「第1章＋第3章混在一起」 ✗
4. **size 平衡**：每組 JSONL chars 應在同一數量級（非絕對，但懸殊要問原因）

**特殊情況**：

- 序言/目錄/附錄 item → 不需獨立 ref 檔；可寫入 skill.md 直接段落
- 超長單一章節（>10 個 chunks）→ 可拆成 `01-chX-part1.md` / `01-chX-part2.md`
- 跨章共用概念（如術語表）→ 可建 `00-glossary.md`（數字 00 排序最前）

---

## 2.2 分組決策輔助

把 entity 清單（來自 02-jsonl-scan.md §1.5）填入：

| 分組名稱 | 包含 items | 預計 chars | ref 檔名 |
|---|---|---|---|
| 分組 1 | items 1-5 | ~8000 | `01-intro.md` |
| 分組 2 | items 6-15 | ~25000 | `02-core-concepts.md` |
| ... | ... | ... | ... |
| (跳過) | 序言/目錄 items | — | 寫入 skill.md 直接段落 |

---

## 2.3 生成目錄骨架

確認分組後，執行：

```bash
# 設定變數（請自行修改）
BOOK_TITLE="<書名>"
BOOK_AUTHOR="<作者>"
SKILL_NAME="ebook-<skill-name>" # 強制要求：必須以 ebook- 開頭，以區分電子書與工具
SKILL_DIR="<你的根路徑>/$SKILL_NAME"

# 建立目錄
mkdir -p "$SKILL_DIR/references"

# 防止意外覆寫已存在的 skill.md
[ -f "$SKILL_DIR/skill.md" ] && echo "⚠️  skill.md 已存在，先備份或確認後再執行" && exit 1

# 建立空 ref 檔（依你的分組）
for ref in 01-intro.md 02-core-concepts.md 03-advanced.md; do
    touch "$SKILL_DIR/references/$ref"
    echo "# ${ref%.md}" >> "$SKILL_DIR/references/$ref"
    echo "" >> "$SKILL_DIR/references/$ref"
    echo "> 來源：《$BOOK_TITLE》$BOOK_AUTHOR（RAG 待填）" >> "$SKILL_DIR/references/$ref"
done
```

---

## 2.4 Skill.md 模板（完整版）

建立 `skill.md`，填入以下模板：

```markdown
---
name: ebook-<skill-name>
description: |
  《<書名>》（<年份>）的 <主題> 解讀引擎。
  <一句話說明 skill 的核心功能與價值>
  何時觸發：
  - <最常見使用場景 1>（範例：「問某概念的定義或應用」）
  - <最常見使用場景 2>
  - <最常見使用場景 3>
  適用對象：<使用者類型描述>
  典型提問：「<範例提問 1>」、「<範例提問 2>」、「<範例提問 3>」
---

# <Skill 中文標題>

> 來源：《<書名>》<作者>，<出版社> <出版年>（<ISBN 可選>）
> 本技能已結構化為 AI 可直接執行的解讀規格，無需重讀原書即可掌握方法與判斷原則。

---

## 一、核心概念

<從 JSONL 序言/導讀 item 提取，1-3 段，保留原書語氣>

---

## 二、<主體框架名稱>

<核心方法論/分析框架，來自 JSONL 早期 item>

---

## 三、Reference 目錄

| 檔案 | 內容 | 何時讀 |
|---|---|---|
| `references/01-<group1>.md` | <描述覆蓋範圍> | <使用者提問哪類問題時> |
| `references/02-<group2>.md` | <描述覆蓋範圍> | <使用者提問哪類問題時> |

---

## 四、快速查詢索引

| 使用者提問關鍵字 | 對應 ref 檔 | 核心段落 |
|---|---|---|
| <關鍵字 1> | `references/01-<group1>.md` | §<章節> |
| <關鍵字 2> | `references/02-<group2>.md` | §<章節> |
```

**填寫提示**：
- `description` 的 `何時觸發` 必須具體 — Claude 用這個決定是否啟動此 skill
- `典型提問` 要用使用者真實的說法，不要用術語堆砌
- `三、Reference 目錄` 的「何時讀」要對應使用者的提問動機，不是檔案的結構描述

---

## 2.5 Scaffold 完成確認

```bash
# 確認目錄結構
find "$SKILL_DIR" -type f -name "*.md" | sort

# 確認 skill.md frontmatter 完整
head -20 "$SKILL_DIR/skill.md"
```

產出應類似：
```
<skill-dir>/skill.md
<skill-dir>/references/01-intro.md
<skill-dir>/references/02-core-concepts.md
<skill-dir>/references/03-advanced.md
```

完成條件：
- [ ] skill.md 存在，frontmatter name/description 已填寫
- [ ] 所有規劃的 ref 檔都存在（哪怕是空的）
- [ ] 沒有孤兒 item（每個 item 都有歸屬 ref 檔）
