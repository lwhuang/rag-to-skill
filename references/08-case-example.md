# 實戰案例：ziwei 專案 5 個 skill 的建構經驗（2026-04）

> 本案例是 rag-to-skill 方法論的實際來源，濃縮自 ziwei repo 從 v0 到 v1.0.0 的完整建構過程。
> 以下的每個「坑」都是真實踩過的——未來建構時不需要再踩一遍。

---

## 一、專案概況

- **Repo**：`~/Developer/repos/ziwei`
- **JSONL 數量**：5 個，對應 5 本紫微斗數書籍
- **建構的 skill**：5 個主題 skill + 1 個 foundation/路由 skill
- **最終狀態**：v1.0.0，CI 10 階段全綠，619 錨點 99.7% 健康，結構合規 100/100

---

## 二、JSONL Schema（ziwei 格式，作為範例）

每行結構：
```json
{
  "loc": {
    "item_index": 12,
    "chunk_index": 0
  },
  "chapter": "第三章：命宮星曜解讀",
  "text": "紫微坐命的人具有強烈的領導慾望..."
}
```

關鍵點：
- `loc` 是嵌套 dict（不是頂層）— **ziwei 特有 schema，你的 JSONL 可能不同**
- `item_index` 從 4 或 5 開始（前幾個是序章/目錄）— **ziwei 特有，你的 JSONL 可能從 0 或 1 開始**
- 序章/目錄 item 不需要對應 ref，但不能當「孤兒」處理——記錄「跳過，原因：導讀非知識內容」

---

## 三、建構流程的實際決策

### 分組決策（以「慧心齋主談命宮」為例）

```
JSONL: 91 items（包含序章 + 14 主星 × 各 2 chunks + 六吉煞 + 四化 + 乙級星 + 盤性）

分組決定：
  group1-stars.md  → items 10-17  (第一系列 8 主星)
  group2-stars.md  → items 18-23  (第二系列 6 主星)
  auxiliary-stars.md → items 24-31 (祿存、天馬、六吉)
  sha-stars.md     → items 32-37  (六煞)
  hua-stars.md     → items 38-41  (四化星)
  secondary-stars.md → items 43-68 (乙級諸星)
  tutorial.md      → item 7        (導讀/使用教學)
  pan-xing.md      → item 69       ← 最初忘了！導致 S1 Severe
```

**教訓**：做完分組後，用 `04-content-build.md §4.6` 的孤兒檢查腳本——item 69「關於盤性」最初被遺漏，後來發現是因為章節名不在其他分組的預期 chapter 列表裡。

### 因忘了同步 skill.md 造成的 Severe

Phase 5 新增了 `pan-xing.md` 來補 item 69，但忘記：
1. 更新 skill.md `§七 Reference 目錄` 表格
2. 更新 skill.md `§八 快速查詢索引`
3. 在 skill.md 的「盤性」論述段落加「詳見 references/pan-xing.md」

結果 `validate.py` check 3（內部連結）沒問題（沒有斷連結），但 Reality Checker 稽核發現 skill.md 提到盤性但沒有 ref 連結，使用者無從找到。

**規則**：每次新增 ref，立刻同步 skill.md 的 Reference 目錄和查詢索引。不要留到最後一起補。

---

## 四、最常見的三類錯誤

### 錯誤 1：縮寫原文

原書：
> 「紫微星的本質是孤獨的，他需要下屬（眾星拱主），才能感受到存在感。在沒有輔弼的情況下，紫微坐命的人往往過於自我中心，難以接受批評。」

錯誤的 ref 寫法：
> 「紫微星需要輔弼，否則孤獨且自我中心。」

這是 AI 改寫，不是原書。如果要給這種 entity 加錨點，RAG 原文必須完整保留。

**修正**：逐字移植，一字不改。只加標題和錨點。

### 錯誤 2：在 ref 檔自行補充例子

看到原書說「紫微坐命的人適合當主管」，然後自己補：
> 「例如政治家、企業領導者...」（但 JSONL 裡沒有這些例子）

這是 AI 編造。Reality Checker 會標記。

**修正**：原書有的例子才放。原書沒舉例的概念，就不舉例。

### 錯誤 3：「範圍錨點」難以驗證

用 `item_index=10-15` 一個錨點標注六個 item 的內容，validate.py 會回報 `JSONL item 11, 12, 13, 14 未被覆蓋`（因為只 parse 到整數 `10` 和 `15`）。

**修正**：每個 item 各一個錨點，不用範圍。如果六個 item 同屬一個主題，可以在末尾放六行：
```
> 來源：《書名》章節（RAG item_index=10）
> 來源：《書名》章節（RAG item_index=11）
...
```
或逐段放。

---

## 五、validate.py 在 ziwei 的等效物

ziwei 的 `./scripts/ci.sh` 有 10 個步驟，其中跟 rag-to-skill validate.py 等效的是：

| ziwei CI 步驟 | rag-to-skill validate.py 等效 |
|---|---|
| `[1] Link integrity` | check 3（內部連結） |
| `[2] RAG anchor coverage` | check 4（錨點密度）+ check +1（JSONL 覆蓋率） |
| `[6] RAG structural compliance score` | check 2（空骨架）+ check 1（frontmatter） |
| `[9] Anchor parse coverage` | check +1（JSONL 覆蓋率） |

ziwei 額外有（不在 validate.py 範圍）：
- `[3] Sihua consistency`（ziwei 特有，四化一致性）
- `[4-5] Chapter-name / chunk-coverage`（ziwei 特有，錨點精確度）
- `[10] Semantic-diff`（需要 JSONL + eval 腳本）

**結論**：validate.py 覆蓋通用品質，ziwei CI 額外提供 repo-specific 精確度檢查。

---

## 六、從這個專案萃取的核心原則

1. **先掃 JSONL，再規劃，再建目錄**——不要邊建邊改，浪費的 Edit 操作會累積很多
2. **分組後立即做孤兒檢查**——有孤兒 item 就是未來的 Severe
3. **每次新增 ref，立刻同步 skill.md**——不要累積到最後
4. **逐字移植，不精簡**——精簡 = 失去溯源能力
5. **validate.py 是把關，不是進度表**——先把 content 填完再跑，不要每填一個 ref 就跑一次
6. **Reality Checker 比 validate.py 更嚴**——validate.py 不懂語意，Reality Checker 懂。兩者都要跑。

---

## 七、時間估計（供參考）

| 規模 | JSONL items | 預計工時 |
|---|---|---|
| 小（教程類） | < 20 items | 1-2 小時 |
| 中（一般書籍） | 20-100 items | 3-6 小時 |
| 大（工具書/百科） | 100+ items | 1-2 天 |

瓶頸通常在**階段 4（內容填充）**，不在分析或驗證。可以把 Build 工作拆成多個 session，每次填完部分 ref 後 `validate.py` 確認進度。
