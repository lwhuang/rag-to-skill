#!/usr/bin/env python3
"""
any_to_jsonl.py：任意格式 → JSONL（透過 markitdown）

支援：PDF、EPUB、DOCX、PPTX、XLSX、HTML、圖片（OCR）等所有 markitdown 支援的格式。
章節邊界自動偵測 Markdown 標題層級，或手動指定。

用法：
  python3 any_to_jsonl.py <input.pdf>
  python3 any_to_jsonl.py <input.epub> <output.jsonl>
  python3 any_to_jsonl.py <input.docx> --chunk-size 800
  python3 any_to_jsonl.py <input.pdf> --heading-level 2   # 手動指定用 H2 分章

輸出 schema 相容 rag-to-skill（item_index / chunk_index / chapter / text）。

依賴：
  pip install markitdown
"""

import sys, json, re, argparse
from pathlib import Path

try:
    from markitdown import MarkItDown
except ImportError:
    sys.exit("缺少 markitdown，請執行：pip install markitdown")


# ── 常數 ──────────────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 500


# ── Markdown 解析 ─────────────────────────────────────────────────────────────

def auto_detect_heading_level(md_text):
    """
    找出最適合作為章節邊界的標題層級。
    策略：從 H1 往下找，第一個出現 ≥ 2 次的層級即為章節層級。
    返回 1-6，找不到返回 None。
    """
    for level in range(1, 6):
        pattern = re.compile(r"^#{" + str(level) + r"} ", re.MULTILINE)
        if len(pattern.findall(md_text)) >= 2:
            return level
    return None


def split_by_heading(md_text, level):
    """
    按指定標題層級切分 Markdown。
    返回 [(section_title, section_body), ...]。
    level 以上的 heading（更大的標題）不切，level 以下的保留在 body 裡。
    """
    heading_pattern = re.compile(
        r"^#{" + str(level) + r"}\s+(.+)$",
        re.MULTILINE
    )

    sections = []
    last_end = 0
    current_title = "（前言）"

    for m in heading_pattern.finditer(md_text):
        body = md_text[last_end:m.start()].strip()
        if body or sections:          # 前言有內容才加；之後的空白也保留邊界
            sections.append((current_title, body))
        current_title = m.group(1).strip()
        last_end = m.end()

    # 最後一節
    body = md_text[last_end:].strip()
    sections.append((current_title, body))

    return [(t, b) for t, b in sections if b]   # 過濾空 body


def md_body_to_paragraphs(body):
    """
    把 Markdown body 轉為段落列表：
    - 移除標題行（子標題保留文字）
    - 移除程式碼區塊
    - 合併換行
    """
    # 移除 fenced code block
    body = re.sub(r"```[\s\S]*?```", "", body)
    # 標題行轉純文字（去掉 # 符號）
    body = re.sub(r"^#{1,6}\s+", "", body, flags=re.MULTILINE)
    # 移除圖片語法 ![...](...)
    body = re.sub(r"!\[.*?\]\(.*?\)", "", body)
    # 移除連結語法，保留文字
    body = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", body)
    # 移除粗體/斜體 markdown 符號
    body = re.sub(r"\*{1,2}([^\*]+)\*{1,2}", r"\1", body)
    body = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", body)

    paragraphs = []
    for para in re.split(r"\n{2,}", body):
        # 段落內換行合併
        para = re.sub(r"(?<=[^\n])\n(?=[^\n])", " ", para)
        para = re.sub(r"\s+", " ", para).strip()
        if para:
            paragraphs.append(para)

    return paragraphs


# ── 切塊 ──────────────────────────────────────────────────────────────────────

def chunk_paragraphs(paragraphs, max_chars):
    """合併段落成 chunks，超長段落按句子邊界切割。"""
    chunks = []
    buf, buf_len = [], 0

    def flush():
        nonlocal buf, buf_len
        t = "\n".join(buf).strip()
        if t:
            chunks.append(t)
        buf.clear()
        buf_len = 0

    for block in paragraphs:
        if len(block) > max_chars:
            if buf:
                flush()
            sentences = re.split(r"(?<=[。！？…\.!?])\s*", block)
            s_buf, s_len = [], 0
            for sent in sentences:
                if s_len + len(sent) > max_chars and s_buf:
                    chunks.append("".join(s_buf).strip())
                    s_buf, s_len = [], 0
                s_buf.append(sent)
                s_len += len(sent)
            if s_buf:
                chunks.append("".join(s_buf).strip())
        else:
            if buf_len + len(block) + 1 > max_chars and buf:
                flush()
            buf.append(block)
            buf_len += len(block) + 1

    if buf:
        flush()

    return [c for c in chunks if c]


# ── 主流程 ────────────────────────────────────────────────────────────────────

def any_to_jsonl(input_path, output_path, chunk_size, heading_level=None, verbose=True):
    md_client = MarkItDown()

    if verbose:
        print(f"轉換中：{input_path} ...")

    result = md_client.convert(str(input_path))
    md_text = result.text_content

    if not md_text.strip():
        sys.exit("markitdown 轉換結果為空，請確認檔案可正常開啟。")

    # 決定章節層級
    if heading_level is None:
        heading_level = auto_detect_heading_level(md_text)

    if heading_level is None:
        if verbose:
            print("未偵測到任何 Markdown 標題，整份文件作為單一 item 切塊。")
        sections = [("（全文）", md_text)]
    else:
        sections = split_by_heading(md_text, heading_level)
        if verbose:
            print(f"偵測到章節標題層級：H{heading_level}，共 {len(sections)} 節")

    total_items  = 0
    total_chunks = 0
    skipped      = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for item_index, (chapter_title, body) in enumerate(sections):
            paragraphs = md_body_to_paragraphs(body)
            if not paragraphs:
                skipped += 1
                continue

            chunks = chunk_paragraphs(paragraphs, chunk_size)
            if not chunks:
                skipped += 1
                continue

            for chunk_index, text in enumerate(chunks):
                record = {
                    "loc": {
                        "item_index": item_index,
                        "chunk_index": chunk_index,
                    },
                    "chapter": chapter_title,
                    "text": text,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_chunks += 1

            total_items += 1

    if verbose:
        print(f"有效 items：{total_items}（跳過空白 {skipped} 個）")
        print(f"總 chunks ：{total_chunks}")
        print(f"輸出      ：{output_path}")

    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="任意格式電子書 → JSONL（透過 markitdown，rag-to-skill 相容）"
    )
    parser.add_argument("input", type=Path, help="輸入檔案（PDF / EPUB / DOCX / PPTX / HTML ...）")
    parser.add_argument(
        "output", type=Path, nargs="?",
        help="輸出 JSONL 路徑（預設：同目錄，副檔名改 .jsonl）"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, metavar="N",
        help=f"每個 chunk 最大字元數（預設 {DEFAULT_CHUNK_SIZE}）"
    )
    parser.add_argument(
        "--heading-level", type=int, choices=range(1, 7), metavar="1-6",
        help="手動指定章節標題層級（預設自動偵測）"
    )
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"找不到檔案：{args.input}")

    output = args.output or args.input.with_suffix(".jsonl")
    any_to_jsonl(args.input, output, args.chunk_size, args.heading_level)


if __name__ == "__main__":
    main()
