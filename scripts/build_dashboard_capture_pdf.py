from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "outputs/APEX_W29_Combined_Dashboard_Long_Capture.png"
    if (ROOT / "outputs/APEX_W29_Combined_Dashboard_Long_Capture.png").is_file()
    else ROOT / "reports/APEX_W29_Combined_Dashboard_Long_Capture.png"
)
DEFAULT_OUTPUT = ROOT / "output/pdf/APEX_W29_Combined_Dashboard_Landscape.pdf"
DEFAULT_QA_DIR = ROOT / "tmp/pdfs/APEX_W29_Combined_Dashboard_Landscape"
PAGE_SIZE = (960, 540)
PAGE_BACKGROUND = "#090909"


def build_pdf(input_path: Path, output_path: Path, qa_dir: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        source = source.convert("RGB")
        source_width, source_height = source.size
        slice_height = round(source_width * PAGE_SIZE[1] / PAGE_SIZE[0])
        page_count = math.ceil(source_height / slice_height)

        pdf = canvas.Canvas(str(output_path), pagesize=PAGE_SIZE, pageCompression=1)
        pdf.setTitle("APEX W29 综合看板网页原样归档")
        pdf.setAuthor("APEX China Community Intelligence")

        for index in range(page_count):
            top = index * slice_height
            bottom = min(source_height, top + slice_height)
            crop = source.crop((0, top, source_width, bottom))
            page_image = Image.new(
                "RGB", (source_width, slice_height), PAGE_BACKGROUND
            )
            page_image.paste(crop, (0, 0))
            qa_path = qa_dir / f"page-{index + 1:02d}.png"
            page_image.save(qa_path, "PNG", optimize=True)
            pdf.drawImage(
                ImageReader(page_image),
                0,
                0,
                width=PAGE_SIZE[0],
                height=PAGE_SIZE[1],
                preserveAspectRatio=False,
                mask="auto",
            )
            pdf.showPage()

        pdf.save()
    return page_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa-dir", type=Path, default=DEFAULT_QA_DIR)
    args = parser.parse_args()
    pages = build_pdf(args.input, args.output, args.qa_dir)
    print(f"created {args.output} with {pages} landscape pages")


if __name__ == "__main__":
    main()
