"""Inspect Office structure and actual rendered PDFs; no model fit or test I/O."""

import argparse
import json
from pathlib import Path
import re
import unicodedata
import zipfile

from docx import Document
from pptx import Presentation
from PIL import Image, ImageDraw
import pymupdf

from beijing_air.midterm_evidence import sha, read

ROOT = Path(__file__).resolve().parents[1]


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace("\u00ad", "")


def doc_text(path):
    d = Document(path)
    text = [p.text for p in d.paragraphs]
    text += [c.text for t in d.tables for row in t.rows for c in row.cells]
    return "\n".join(text), d


def ppt_text(path):
    prs = Presentation(path)
    texts = []
    for slide in prs.slides:
        text = []
        for shape in slide.shapes:
            if shape.has_text_frame: text.append(shape.text)
            if shape.has_table: text += [c.text for row in shape.table.rows for c in row.cells]
        texts.append("\n".join(text))
    return texts, prs


def verify_office(root):
    root = Path(root)
    out = root / "reports/midterm"
    build, e = read(out / "build_manifest.json"), read(out / "evidence.json")
    stem = e["config"]["filename_stem"]
    paths = {ext: out / (stem+"."+ext) for ext in ("docx", "pptx")}
    for info in build["files"]:
        p = root / info["path"]
        assert sha(p) == info["sha256"] and p.stat().st_size == info["bytes"]
        with zipfile.ZipFile(p) as archive: assert archive.testzip() is None
    body, doc = doc_text(paths["docx"])
    slides, prs = ppt_text(paths["pptx"])
    assert len(slides) == build["slides"] == 15
    all_slides = "\n".join(slides)
    for text in (body, all_slides):
        assert "[CẦN BỔ SUNG]" in text and "BẢN NHÁP" in text and "chưa" in text.lower()
        assert "\ufffd" not in text
        for model in e["models"]:
            number = f"{model['MAE']:.6f}".replace(".", ",")
            assert number in text, number
    for slide in prs.slides:
        assert "BẢN NHÁP" in "\n".join(s.text for s in slide.shapes if s.has_text_frame)
        for shape in slide.shapes:
            assert shape.left >= 0 and shape.top >= 0
            assert shape.left+shape.width <= prs.slide_width+100 and shape.top+shape.height <= prs.slide_height+100
        # Images and text must not overlap in this authored layout.
        pictures = [s for s in slide.shapes if s.shape_type == 13]
        for picture in pictures:
            for shape in slide.shapes:
                if not shape.has_text_frame: continue
                x = min(picture.left+picture.width, shape.left+shape.width)-max(picture.left, shape.left)
                y = min(picture.top+picture.height, shape.top+shape.height)-max(picture.top, shape.top)
                assert x <= 0 or y <= 0, "Image/text collision"
    trace = read(out / "traceability.json")
    assert len({t["id"] for t in trace}) == len(trace)
    for item in trace:
        for s in item["sources"]: assert sha(root / s["path"]) == s["sha256"]
        for rid in item["run_ids"]: assert (root / "artifacts/experiments" / rid / "metrics.json").is_file()
    assert sha(root / "experiments/experiment_log.csv") == e["checks"]["ledger_sha256"]
    return e, slides, {"docx_paragraphs": len(doc.paragraphs), "docx_tables": len(doc.tables), "pptx_slides": len(slides),
                       "office_crc": "PASS", "cross_document_MAE_values": "PASS", "placeholder_draft_labels": "PASS",
                       "traceability_sources": "PASS", "ledger_unchanged": True, "model_fit_performed": False, "test_samples_accessed": False}


def render_review(pdf_path, folder, prefix, contact_output):
    folder.mkdir(parents=True, exist_ok=True)
    pages, text_pages, counts = [], [], []
    with pymupdf.open(pdf_path) as pdf:
        for number, page in enumerate(pdf, 1):
            text = page.get_text()
            assert "\ufffd" not in text
            assert len(text.strip()) >= 70, f"Nearly empty rendered page {number}"
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        box = span["bbox"]
                        assert box[0] >= -1 and box[1] >= -1 and box[2] <= page.rect.width+1 and box[3] <= page.rect.height+1, (number, span["text"])
            file = folder / f"{prefix}_{number:02d}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25), alpha=False).save(file)
            pages.append(file); text_pages.append(text); counts.append(len(text))
    contacts = []
    for start in range(0, len(pages), 9):
        landscape = prefix == "slide"
        tw, th = (480, 270) if landscape else (330, 467)
        sheet = Image.new("RGB", (3*(tw+16), 3*(th+36)), "#e7edf2")
        draw = ImageDraw.Draw(sheet)
        for position, p in enumerate(pages[start:start+9]):
            with Image.open(p) as img:
                img.thumbnail((tw, th))
                x, y = (position%3)*(tw+16)+8, (position//3)*(th+36)+28
                sheet.paste(img, (x, y)); draw.text((x, y-19), f"{prefix} {start+position+1}", fill="#14324F")
        target = contact_output / f"{prefix}_contact_{start//9+1}.png"
        sheet.save(target); contacts.append(target)
    return text_pages, {"pages": len(pages), "page_text_lengths": counts, "contacts": [p.name for p in contacts]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--office-only", action="store_true")
    args = p.parse_args()
    e, slide_texts, result = verify_office(ROOT)
    preview = ROOT / "reports/midterm/previews"
    if not args.office_only:
        rendered = read(preview / "render_manifest.json")
        for key, name in (("report_pdf_sha256", "report.pdf"), ("slides_pdf_sha256", "slides.pdf")):
            assert sha(preview / name) == rendered[key]
        docpages, result["docx_render"] = render_review(preview / "report.pdf", ROOT / "artifacts/midterm_review/docx", "page", preview)
        pptpages, result["pptx_render"] = render_review(preview / "slides.pdf", ROOT / "artifacts/midterm_review/pptx", "slide", preview)
        assert len(pptpages) == 15 and len(docpages) == rendered["docx_pages"]
        assert 15 <= len(docpages) <= 24, "Inspect unexpected DOCX pagination"
        for pages in (docpages, pptpages):
            combined = normalized("\n".join(pages))
            assert normalized("CẦN BỔ SUNG") in combined
            for model in e["models"]: assert normalized(f"{model['MAE']:.6f}".replace(".", ",")) in combined
        # Match every visible paragraph/cell from PPTX against its actual PDF page.
        missing = []
        _, prs = ppt_text(ROOT / "reports/midterm" / (e["config"]["filename_stem"]+".pptx"))
        for number, (slide, text) in enumerate(zip(prs.slides, pptpages), 1):
            pieces = []
            for shape in slide.shapes:
                if shape.has_text_frame: pieces += [p.text for p in shape.text_frame.paragraphs]
                if shape.has_table: pieces += [c.text for row in shape.table.rows for c in row.cells]
            actual = normalized(text)
            missing += [{"slide": number, "text": t} for t in pieces if len(t.strip()) > 2 and normalized(t) not in actual]
        assert not missing, missing
        result["rendered_slide_text_complete"] = True
        result["visual_review_required"] = "Inspect contact sheets and full-resolution pages; automatic text checks do not replace visual review."
    result["status"] = "DRAFT_CHECKED"
    (ROOT / "reports/midterm/verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
