#!/usr/bin/env python3
"""
epub-to-jsonl：EPUB 電子書轉 JSONL

用法：
  python3 epub_to_jsonl.py <input.epub>
  python3 epub_to_jsonl.py <input.epub> <output.jsonl>
  python3 epub_to_jsonl.py <input.epub> --chunk-size 800

輸出 schema 相容 rag-to-skill（item_index / chunk_index / chapter / text）。

依賴：
  pip install ebooklib beautifulsoup4
"""

import sys, json, re, argparse
from pathlib import Path

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    sys.exit("缺少 ebooklib，請執行：pip install ebooklib")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("缺少 beautifulsoup4，請執行：pip install beautifulsoup4")


# ── 預設切塊大小 ─────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 500   # 字元數（中文約 250 字 / 英文約 80-100 字）


# ── HTML → 段落 ───────────────────────────────────────────────────────────────

def html_to_paragraphs(html_bytes):
    """將 HTML bytes 轉為 (soup, [段落文字]) 。"""
    html = html_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # 移除不需要的節點
    for tag in soup(["script", "style", "img", "nav", "head", "figure"]):
        tag.decompose()

    # 優先嘗試尋找本文容器，若無則用 body 或整個 soup
    container = soup.find("body") or soup

    # 使用 \n 作為分隔符提取所有文字，能有效處理 <br/> 或 <div> 換行
    raw_text = container.get_text(separator="\n", strip=True)
    
    # 切分行並過濾空白行
    blocks = []
    for line in raw_text.splitlines():
        text = line.strip()
        if text:
            blocks.append(text)

    return soup, blocks


def extract_chapter_title(item, soup):
    """從 HTML 擷取標題，優先 h1 → h2 → h3 → item.title → 無標題。"""
    for tag in ["h1", "h2", "h3"]:
        el = soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t:
                return t
    title = getattr(item, "title", "") or ""
    return title.strip() or "（無標題）"


# ── 切塊 ──────────────────────────────────────────────────────────────────────

def chunk_blocks(blocks, max_chars):
    """
    把段落列表合併成 chunks，每個 chunk ≤ max_chars。
    單一段落超長時按句子邊界拆開。
    """
    chunks = []
    buf, buf_len = [], 0

    def flush():
        nonlocal buf, buf_len
        text = "\n".join(buf).strip()
        if text:
            chunks.append(text)
        buf, buf_len = [], 0

    for block in blocks:
        if len(block) > max_chars:
            # 先 flush 現有緩衝
            if buf:
                flush()
            # 按句子邊界切超長段落
            sentences = re.split(r"(?<=[。！？.!?])\s*", block)
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
            # 加入緩衝
            if buf_len + len(block) + 1 > max_chars and buf:
                flush()
            buf.append(block)
            buf_len += len(block) + 1

    if buf:
        flush()

    return [c for c in chunks if c]


# ── 主轉換邏輯 ────────────────────────────────────────────────────────────────

def epub_to_jsonl(epub_path, output_path, chunk_size, verbose=True):
    book = epub.read_epub(str(epub_path))

    # 書名
    meta_title = book.get_metadata("DC", "title")
    book_title = meta_title[0][0].strip() if meta_title else epub_path.stem

    # 依 spine 順序取 DOCUMENT items（保證閱讀順序）
    spine_items = []
    for spine_id, _linear in book.spine:
        item = book.get_item_with_id(spine_id)
        if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
            spine_items.append(item)

    # fallback：無 spine 資訊時直接取全部文件
    if not spine_items:
        spine_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

    total_items = 0
    total_chunks = 0
    skipped = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for item_index, item in enumerate(spine_items):
            soup, blocks = html_to_paragraphs(item.get_content())

            if not blocks:
                skipped += 1
                continue

            chapter = extract_chapter_title(item, soup)
            chunks = chunk_blocks(blocks, chunk_size)

            if not chunks:
                skipped += 1
                continue

            for chunk_index, text in enumerate(chunks):
                record = {
                    "loc": {
                        "item_index": item_index,
                        "chunk_index": chunk_index,
                    },
                    "chapter": chapter,
                    "text": text,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_chunks += 1

            total_items += 1

    if verbose:
        print(f"書名     ：{book_title}")
        print(f"spine 項目：{len(spine_items)}（跳過空白 {skipped} 個）")
        print(f"有效章節  ：{total_items}")
        print(f"總 chunks ：{total_chunks}")
        print(f"輸出      ：{output_path}")

    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EPUB → JSONL（rag-to-skill 相容格式）"
    )
    parser.add_argument("epub", type=Path, help="輸入 EPUB 檔案路徑")
    parser.add_argument(
        "output", type=Path, nargs="?", help="輸出 JSONL 路徑（預設：同目錄，副檔名改 .jsonl）"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        metavar="N", help=f"每個 chunk 最大字元數（預設 {DEFAULT_CHUNK_SIZE}）"
    )
    args = parser.parse_args()

    if not args.epub.exists():
        sys.exit(f"找不到檔案：{args.epub}")
    if args.epub.suffix.lower() != ".epub":
        sys.exit(f"不支援的檔案格式（需要 .epub）：{args.epub}")

    output = args.output or args.epub.with_suffix(".jsonl")
    epub_to_jsonl(args.epub, output, args.chunk_size)


if __name__ == "__main__":
    main()
