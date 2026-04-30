#!/usr/bin/env python3
"""
pdf_ocr_to_jsonl.py：掃描版 PDF（無文字層）→ JSONL（LLM Vision OCR）

對純圖像 PDF 使用 Claude 視覺模型逐頁辨識文字。
輸出 schema 相容 rag-to-skill（item_index / chunk_index / chapter / text）。

用法：
  python3 pdf_ocr_to_jsonl.py <input.pdf>
  python3 pdf_ocr_to_jsonl.py <input.pdf> <output.jsonl>
  python3 pdf_ocr_to_jsonl.py <input.pdf> --dry-run         # 只估算費用，不執行
  python3 pdf_ocr_to_jsonl.py <input.pdf> --resume          # 從中斷點繼續
  python3 pdf_ocr_to_jsonl.py <input.pdf> --dpi 100         # 提高解析度（更準確但費用增加）
  python3 pdf_ocr_to_jsonl.py <input.pdf> --pages 1-10      # 只處理指定頁面（測試用）
  python3 pdf_ocr_to_jsonl.py <input.pdf> --model claude-sonnet-4-6  # 更高品質

依賴：
  pip install pymupdf anthropic

環境變數：
  ANTHROPIC_API_KEY   （必要）
"""

import sys, json, re, argparse, base64, time, math
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("缺少 PyMuPDF，請執行：pip install pymupdf")

try:
    import anthropic
except ImportError:
    sys.exit("缺少 anthropic SDK，請執行：pip install anthropic")


# ── 常數 ──────────────────────────────────────────────────────────────────────

DEFAULT_DPI     = 72     # 省費用；100+ 更清晰但 token 更多
DEFAULT_QUALITY = 75     # JPEG 品質（75 在可辨識度與 token 數量之間取得平衡）
DEFAULT_MODEL   = "claude-haiku-4-5-20251001"  # 最省錢；sonnet 品質更好
DEFAULT_CHUNK   = 500    # 每個 chunk 最大字元數
TILE_SIZE       = 512    # Anthropic tile 邊長（像素）
TOKENS_PER_TILE = 1600   # 每 tile 的 token 數
BASE_TOKENS     = 85     # 每張圖片的基礎 token
DELAY_SECS      = 0.5    # 每頁之間的延遲（避免 rate limit）

# claude-haiku-4-5-20251001 pricing
INPUT_PRICE  = 0.80 / 1_000_000   # $0.80 / M input tokens
OUTPUT_PRICE = 4.00 / 1_000_000   # $4.00 / M output tokens

OCR_PROMPT = """\
請辨識這頁書頁的所有文字，完整逐字轉錄，保留所有標點符號與段落結構。

規則：
1. 若本頁是章節標題頁（有明顯大標題），在輸出**最前一行**加：
   CHAPTER: <章節名稱>
   然後換行繼續本頁正文（若有）
2. 若本頁幾乎無文字（封面、版權頁、空白頁、純圖片）→ 只輸出：SKIP
3. 其他情況：直接輸出原文，不加任何說明或評論

輸出："""


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def estimate_tokens(w: int, h: int) -> int:
    """估算圖片的 input token 數（Anthropic tile-based 計算）"""
    tiles = math.ceil(w / TILE_SIZE) * math.ceil(h / TILE_SIZE)
    return BASE_TOKENS + tiles * TOKENS_PER_TILE


def page_to_jpeg(page, dpi: int, quality: int):
    """將 PDF 頁面轉為 JPEG bytes，返回 (bytes, width, height)"""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    data = pix.tobytes("jpeg", jpg_quality=quality)
    return data, pix.width, pix.height


def is_blank(page) -> bool:
    """快速偵測空白頁（全白）"""
    pix = page.get_pixmap(matrix=fitz.Matrix(0.12, 0.12))
    s = pix.samples
    if not s:
        return True
    return sum(b > 245 for b in s) / len(s) > 0.97


def parse_result(raw: str):
    """
    解析 OCR 結果。
    返回 (skip: bool, new_chapter: str | None, body: str)
    - new_chapter=None  → 章節未變
    - skip=True         → 此頁跳過
    """
    if not raw or raw.strip().upper() == "SKIP":
        return True, None, ""
    m = re.match(r'^CHAPTER:\s*(.+?)$', raw, re.MULTILINE)
    if m:
        chapter = m.group(1).strip()
        body = raw[m.end():].strip()
        return False, chapter, body
    return False, None, raw.strip()


def text_to_chunks(text: str, max_chars: int):
    """將長文字切成 ≤max_chars 的 chunks，優先在段落/句子邊界切割"""
    chunks = []
    while len(text) > max_chars:
        cut = max(
            text.rfind('\n', 0, max_chars),
            text.rfind('。', 0, max_chars),
            text.rfind('！', 0, max_chars),
            text.rfind('？', 0, max_chars),
        )
        if cut < max_chars // 2:
            cut = max_chars
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return [c for c in chunks if c]


def ocr_page(client, model: str, img_bytes: bytes, retries: int = 3):
    """呼叫 Claude API 辨識單頁，自動重試。返回 (text, in_tokens, out_tokens)"""
    b64 = base64.standard_b64encode(img_bytes).decode()
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                        },
                        {"type": "text", "text": OCR_PROMPT},
                    ],
                }],
            )
            return resp.content[0].text.strip(), resp.usage.input_tokens, resp.usage.output_tokens
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f" [rate limit，等待 {wait}s]", end="", flush=True)
            time.sleep(wait)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
            else:
                return f"ERROR:{e}", 0, 0
    return "", 0, 0


# ── 主流程 ────────────────────────────────────────────────────────────────────

def pdf_ocr_to_jsonl(
    pdf_path: Path,
    output_path: Path,
    dpi: int = DEFAULT_DPI,
    quality: int = DEFAULT_QUALITY,
    model: str = DEFAULT_MODEL,
    chunk_size: int = DEFAULT_CHUNK,
    dry_run: bool = False,
    resume: bool = False,
    page_range=None,   # (start_0, end_0) inclusive，0-indexed
    verbose: bool = True,
):
    doc = fitz.open(str(pdf_path))
    all_pages = list(range(len(doc)))

    if page_range:
        all_pages = [i for i in all_pages if page_range[0] <= i <= page_range[1]]

    # 偵測空白頁
    if verbose:
        print(f"掃描 {len(all_pages)} 頁...", flush=True)
    valid_pages = [i for i in all_pages if not is_blank(doc[i])]
    blank_count = len(all_pages) - len(valid_pages)

    # 用第一個有效頁估算 token 數
    sample_idx = valid_pages[0] if valid_pages else all_pages[0]
    _, sw, sh = page_to_jpeg(doc[sample_idx], dpi, quality)
    per_page_in  = estimate_tokens(sw, sh)
    per_page_out = 400   # 每頁平均輸出 token 估算
    est_in       = per_page_in  * len(valid_pages)
    est_out      = per_page_out * len(valid_pages)
    est_usd      = est_in * INPUT_PRICE + est_out * OUTPUT_PRICE

    if verbose:
        print(f"有效頁面：{len(valid_pages)}（空白 {blank_count} 頁跳過）")
        print(f"圖片尺寸：{sw}×{sh}px @ {dpi} DPI（每頁 ≈ {per_page_in} input tokens）")
        print(f"估算費用：≈ USD ${est_usd:.2f}（誤差 ±50%，實際依 API 回傳計算）")
        print(f"模型：{model}")

    if dry_run:
        print("\n[dry-run — 未執行 OCR]")
        doc.close()
        return

    # ── 載入進度（resume 模式）──────────────────────────────────────────────
    progress_file = Path(str(output_path) + ".progress.json")
    completed: dict[int, dict] = {}

    if resume and progress_file.exists():
        with open(progress_file, encoding='utf-8') as f:
            raw_prog = json.load(f)
        completed = {int(k): v for k, v in raw_prog.items()}
        if verbose:
            print(f"\n續跑：已完成 {len(completed)} 頁，繼續剩餘...")

    client = anthropic.Anthropic()
    to_process = [i for i in valid_pages if i not in completed]
    total_in   = sum(v.get("in_tok",  0) for v in completed.values())
    total_out  = sum(v.get("out_tok", 0) for v in completed.values())

    if verbose and to_process:
        print(f"\n開始 OCR（共 {len(to_process)} 頁）\n")

    # ── OCR 主迴圈 ──────────────────────────────────────────────────────────
    for seq, page_idx in enumerate(to_process):
        img_bytes, _, _ = page_to_jpeg(doc[page_idx], dpi, quality)

        if verbose:
            print(f"  [{seq+1:3d}/{len(to_process)}] 頁 {page_idx+1:3d}...", end=" ", flush=True)

        raw, in_tok, out_tok = ocr_page(client, model, img_bytes)
        total_in  += in_tok
        total_out += out_tok
        cost = total_in * INPUT_PRICE + total_out * OUTPUT_PRICE

        completed[page_idx] = {"raw": raw, "in_tok": in_tok, "out_tok": out_tok}

        # 每頁都存進度，確保中斷可恢復
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(completed, f, ensure_ascii=False)

        if verbose:
            skip, ch, body = parse_result(raw)
            if raw.startswith("ERROR"):
                status = "ERROR"
            elif skip:
                status = "SKIP"
            elif ch:
                status = f"CH:{ch[:22]}"
            else:
                status = f"{len(body)} 字"
            print(f"{status:28s} | 累計 ${cost:.4f}", flush=True)

        time.sleep(DELAY_SECS)

    doc.close()

    # ── 後處理：生成最終 JSONL ───────────────────────────────────────────────
    current_chapter  = "（前言）"
    item_index       = 0
    item_chunk_count: dict[int, int] = {}
    records = []

    for page_idx in sorted(completed):
        raw = completed[page_idx].get("raw", "")
        if not raw or raw.startswith("ERROR"):
            continue
        skip, ch, body = parse_result(raw)

        if ch and ch != current_chapter:
            current_chapter = ch
            item_index += 1
            item_chunk_count[item_index] = 0

        if skip or not body:
            continue

        if item_index not in item_chunk_count:
            item_chunk_count[item_index] = 0

        for chunk_text in text_to_chunks(body, chunk_size):
            ci = item_chunk_count[item_index]
            records.append({
                "loc": {"item_index": item_index, "chunk_index": ci},
                "chapter": current_chapter,
                "text": chunk_text,
            })
            item_chunk_count[item_index] += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 成功完成，刪除進度檔
    if progress_file.exists():
        progress_file.unlink()

    cost = total_in * INPUT_PRICE + total_out * OUTPUT_PRICE
    if verbose:
        print(f"\n完成！")
        print(f"輸出：{output_path}")
        print(f"JSONL 行數（chunks）：{len(records)}")
        print(f"實際費用：USD ${cost:.4f}")

    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="掃描版 PDF（無文字層）→ JSONL（LLM Vision OCR，rag-to-skill 相容）"
    )
    parser.add_argument("pdf",    type=Path, help="輸入 PDF 路徑")
    parser.add_argument("output", type=Path, nargs="?",
                        help="輸出 JSONL 路徑（預設：同目錄，副檔名改 .jsonl）")
    parser.add_argument(
        "--dpi", type=int, default=DEFAULT_DPI, metavar="N",
        help=f"渲染解析度（預設 {DEFAULT_DPI}；100 更清晰但費用增加）",
    )
    parser.add_argument(
        "--quality", type=int, default=DEFAULT_QUALITY, metavar="N",
        help=f"JPEG 品質 1-95（預設 {DEFAULT_QUALITY}）",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude 模型（預設 {DEFAULT_MODEL}；sonnet 品質更高）",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK, metavar="N",
        help=f"每個 chunk 最大字元數（預設 {DEFAULT_CHUNK}）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只估算費用，不執行 OCR",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="從上次中斷點繼續（需要 .progress.json 存在）",
    )
    parser.add_argument(
        "--pages", metavar="N-M",
        help="只處理指定頁面範圍（1-based，例：1-20）",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"找不到檔案：{args.pdf}")

    page_range = None
    if args.pages:
        m = re.match(r'^(\d+)-(\d+)$', args.pages)
        if not m:
            sys.exit("--pages 格式錯誤，應為 N-M（例：1-20）")
        page_range = (int(m.group(1)) - 1, int(m.group(2)) - 1)

    output = args.output or args.pdf.with_suffix(".jsonl")
    pdf_ocr_to_jsonl(
        args.pdf, output,
        dpi=args.dpi, quality=args.quality, model=args.model,
        chunk_size=args.chunk_size,
        dry_run=args.dry_run, resume=args.resume,
        page_range=page_range,
    )


if __name__ == "__main__":
    main()
