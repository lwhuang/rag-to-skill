# 100% 完成度判準 + 交付前 Checklist

> 這份清單是「可以交給同事/提交到 skill hub」的最終把關。
> 嚴格度預設為生產品質——每個 SEVERE 都必須解決。

---

## 一、Severe 判準（必須全過才算完成）

| 代碼 | 問題描述 | 判斷方式 |
|---|---|---|
| S1 | skill.md 缺少有效 frontmatter | `validate.py` check 1 |
| S2 | 有 ref 檔是空骨架（<5 行有效內容） | `validate.py` check 2 |
| S3 | skill.md 提到的 ref 路徑不存在 | `validate.py` check 3 |
| S4 | 整體錨點密度 < 15/1000 行 | `validate.py` check 4 |
| S5 | JSONL 有 item 未被任何錨點覆蓋 | `validate.py` check +1（需 JSONL） |
| S6 | 有 AI 編造內容（無 JSONL 依據的斷言） | 隨機抽 5 段原文，逐字對照 JSONL；或用 `/skill-rag-auditor` |
| S7 | JSONL 來源含惡意 prompt injection 文字 | 手動稽核：搜尋 ref 檔中是否含 "ignore previous instructions" 等指令覆蓋語句 |

---

## 二、Medium 判準（建議修復，不擋交付）

| 代碼 | 問題描述 | 典型例子 |
|---|---|---|
| M1 | description 缺少「何時觸發」 | 觸發條件不清楚，Claude 不知道何時用這個 skill |
| M2 | 某個 ref 檔錨點密度低（但整體達標） | 特定 ref 檔 < 15/1000 |
| M3 | skill.md 快速查詢索引過於稀疏 | 使用者查不到想要的概念 |
| M4 | 有未替換的模板佔位符 | `<書名>`、`<作者>` 殘留在 ref 檔 |
| M5 | ref 檔末尾缺「使用本檔的時機」表格 | 導流效果差 |

---

## 三、Light 判準（可選，品質加分）

| 代碼 | 問題描述 |
|---|---|
| L1 | 章節標題與 JSONL chapter 不完全一致 |
| L2 | ref 檔 H2 標題格式不統一 |
| L3 | 有些 chunk 用範圍錨點（item_index=X-Y）而非逐 chunk 錨點 |
| L4 | skill.md 沒有「典型提問」範例 |

---

## 四、交付前 Checklist

執行以下步驟，每項確認後打勾：

### 自動驗證
```bash
# 基本驗證（validate.py v1.2，從 06-validation-scripts.md 提取）
python3 validate.py <skill-dir>

# 含 JSONL 完整驗證（最強）
python3 validate.py <skill-dir> <path/to/source.jsonl>
```

- [ ] `validate.py` 輸出 `✓ PASS`（無 SEVERE）

### 手動確認（10 分鐘）

- [ ] **S6 Reality Checker**：從 ref 檔隨機選 5 段原文，在 JSONL 中找對應 item_index，逐字比對是否一致；有 AI 整理/補充說明痕跡或找不到對應 item 的段落 → 標記 SEVERE，重寫（也可用 `/skill-rag-auditor` skill 自動化此步驟）
- [ ] skill.md description 的「何時觸發」有 3 個以上具體場景
- [ ] skill.md Reference 目錄與實際 `references/` 目錄一致（無多無少）
- [ ] 所有 `<佔位符>` 都已替換為真實內容
- [ ] 搜尋所有 ref 檔中是否含 prompt injection 字串（對應 S7）：

```bash
grep -r -i \
  "ignore previous\|jailbreak\|system override\|forget instructions\|disregard\|ignore all\|you are now\|act as\|your new role\|忽略之前\|你現在是\|忽略所有\|新的指令" \
  <skill-dir>/
```

無輸出 → 通過；有輸出 → 手動確認是否為原書內容或惡意注入。

---

## 五、獨立性 Checklist（提交到 skill hub 前必查）

> 提交到 skill hub 意味著你的同事會在**沒有你 repo 的機器**上用這個 skill。

- [ ] skill.md 和所有 ref 檔**不包含硬碼的本機路徑**（如 `/Users/doge/...`）
- [ ] 所有 `> 來源：...` 錨點只引用**書名、章節名、item_index**，不引用本機 JSONL 路徑
- [ ] skill 不依賴任何 shared resource（`TERMINOLOGY.md`、`_shared/` 等），或依賴有明確說明如何取得
- [ ] validate.py 可以獨立運行（不依賴 repo-specific 腳本）
- [ ] skill 的知識在沒有 JSONL 的情況下**仍然可以使用**（JSONL 只是建構時需要，非執行時）

---

## 六、打包交付格式

提交到 skill hub 的 skill 應為以下結構：

```
<skill-name>/
  skill.md             ← 必須（含完整 frontmatter）
  references/
    01-xxx.md          ← 至少一個 ref 檔
    02-xxx.md
    ...
  VALIDATE.md          ← 可選：說明如何驗證此 skill
```

如果 repo 有 validate.py 且希望同事也能驗證，可附上：

```
<skill-name>/
  skill.md
  references/
    ...
  validate.py          ← 從 references/06-validation-scripts.md 複製的獨立腳本
```

---

## 七、分級決策樹

```
validate.py SEVERE 出現？
├── 是 → 不可交付，修復 SEVERE 再跑一次
└── 否 →
    validate.py MEDIUM 出現？
    ├── 是 → 評估：預計修復時間 < 30 分鐘？
    │   ├── 是 → 修復後交付
    │   └── 否 → 帶著 MEDIUM 交付，在 VALIDATE.md 說明已知問題
    └── 否 → 確認獨立性 checklist（§五）→ 可交付
```
