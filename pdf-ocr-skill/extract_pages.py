#!/usr/bin/env python3
"""
extract_pages.py：PDF 頁面 → PNG 圖片（供 pdf-ocr skill 使用）

用法：
  python3 extract_pages.py <pdf_path> <output_dir> [--dpi N]

輸出：
  - 每頁存成 output_dir/page_XXXX.png（4 位數頁碼）
  - 最後一行輸出：TOTAL:<n>
"""

import sys, argparse
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("缺少 PyMuPDF，請執行：pip install pymupdf")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf",     type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--dpi",   type=int, default=100)
    parser.add_argument("--pages", metavar="N-M", default=None,
                        help="只提取指定頁面範圍（1-based）")
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"找不到 PDF：{args.pdf}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(args.pdf))
    total = len(doc)

    page_range = range(total)
    if args.pages:
        import re
        m = re.match(r'^(\d+)-(\d+)$', args.pages)
        if m:
            page_range = range(int(m.group(1)) - 1, min(int(m.group(2)), total))

    mat = fitz.Matrix(args.dpi / 72, args.dpi / 72)
    extracted = 0
    for i in page_range:
        path = args.out_dir / f"page_{i:04d}.png"
        if not path.exists():
            pix = doc[i].get_pixmap(matrix=mat)
            pix.save(str(path))
        extracted += 1

    doc.close()
    print(f"TOTAL:{total}")
    print(f"EXTRACTED:{extracted}")
    print(f"OUT_DIR:{args.out_dir}")


if __name__ == "__main__":
    main()
