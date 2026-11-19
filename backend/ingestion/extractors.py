"""Source extractors for PDF co-notes, plain text, image assets, and NotebookLM CLI."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DATA_URL_RE = re.compile(
    r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _atomic_write_bytes(path: Path, raw_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(raw_bytes)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _detect_image_ext(raw_bytes: bytes) -> str | None:
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if (
        len(raw_bytes) >= 12
        and raw_bytes[:4] == b"RIFF"
        and raw_bytes[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def extract_pdf_source(
    pdf_path: Path,
    *,
    extract_images_dir: Path | None = None,
    min_image_dim: int = 80,
) -> dict:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "解析 PDF 需要安裝 PyMuPDF：請執行 pip install pymupdf"
        ) from exc

    if not pdf_path.is_file():
        raise FileNotFoundError(f"找不到 PDF 檔案：{pdf_path}")

    pages: list[dict] = []
    text_chunks: list[str] = []
    extracted_images: list[dict] = []
    seen_hashes: dict[str, str] = {}

    if extract_images_dir is not None:
        extract_images_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    try:
        page_count = len(doc)
        for page_idx in range(page_count):
            page = doc[page_idx]
            page_num = page_idx + 1
            text = page.get_text("text").strip()
            pages.append({"page": page_num, "text": text})
            if text:
                text_chunks.append(f"--- Page {page_num} ---\n{text}")

            if extract_images_dir is not None:
                for img_idx, img_info in enumerate(page.get_images(full=True), start=1):
                    xref = img_info[0]
                    info = doc.extract_image(xref)
                    width = int(info.get("width", 0))
                    height = int(info.get("height", 0))
                    raw_bytes = info.get("image", b"")
                    if (
                        width < min_image_dim
                        or height < min_image_dim
                        or not raw_bytes
                    ):
                        continue
                    ext = _detect_image_ext(raw_bytes) or info.get("ext", "png")
                    if ext == "jpeg":
                        ext = "jpg"
                    digest = hashlib.sha256(raw_bytes).hexdigest()
                    if digest in seen_hashes:
                        continue
                    filename = f"p{page_num}_img{img_idx}.{ext}"
                    out_path = extract_images_dir / filename
                    _atomic_write_bytes(out_path, raw_bytes)
                    seen_hashes[digest] = filename
                    extracted_images.append(
                        {
                            "page": page_num,
                            "filename": filename,
                            "path": str(out_path),
                            "width": width,
                            "height": height,
                            "sha256": digest,
                        }
                    )
    finally:
        doc.close()

    return {
        "source": str(pdf_path),
        "pageCount": page_count,
        "pages": pages,
        "fullText": "\n\n".join(text_chunks),
        "images": extracted_images,
    }


def extract_text_source(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"找不到文字／Markdown 檔案：{path}")
    return path.read_text(encoding="utf-8")


def import_image_asset(
    exam_dir: Path,
    source_ref: str,
    *,
    dry_run: bool = False,
) -> str:
    ref = source_ref.strip()
    images_dir = (exam_dir / "images").resolve()

    if ref.startswith("images/"):
        resolved = (exam_dir / ref).resolve()
        if not resolved.is_relative_to(images_dir) or not resolved.is_file():
            raise FileNotFoundError(f"考科圖片不存在：{ref}")
        return ref

    if ref.startswith("data:image/"):
        match = DATA_URL_RE.match(ref)
        if not match:
            raise ValueError("不支援的圖片 Data URL 格式")
        subtype = match.group(1).lower()
        ext = "jpg" if subtype in ("jpeg", "jpg") else subtype
        try:
            raw_bytes = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"圖片 Base64 解碼失敗：{exc}") from exc
        stem = "asset"
    else:
        src_path = Path(ref)
        if not src_path.is_file():
            raise FileNotFoundError(f"找不到圖片來源檔案：{src_path}")
        raw_bytes = src_path.read_bytes()
        detected = _detect_image_ext(raw_bytes)
        if not detected:
            raise ValueError(f"不支援的圖片格式（僅限 JPEG/PNG/WebP）：{src_path}")
        ext = detected
        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", src_path.stem).strip("-") or "image"
        stem = stem[:40]

    if not raw_bytes or len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("圖片大小需介於 1 byte 至 5 MB 之間")

    detected_magic = _detect_image_ext(raw_bytes)
    if not detected_magic:
        raise ValueError("圖片檔頭驗證失敗，非有效的 JPEG/PNG/WebP 檔案")
    ext = detected_magic

    digest = hashlib.sha256(raw_bytes).hexdigest()
    if images_dir.is_dir():
        for existing in sorted(images_dir.iterdir()):
            if (
                existing.is_file()
                and hashlib.sha256(existing.read_bytes()).hexdigest() == digest
            ):
                return f"images/{existing.name}"

    out_name = f"{stem}-{digest[:8]}.{ext}"
    if not dry_run:
        _atomic_write_bytes(images_dir / out_name, raw_bytes)
    return f"images/{out_name}"


def run_nlm_source_list(notebook_id: str) -> list[dict]:
    res = subprocess.run(
        ["nlm", "source", "list", notebook_id, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"nlm source list 失敗：{res.stderr or res.stdout}")
    data = json.loads(res.stdout)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("sources") or data.get("value") or []
    return []


def run_nlm_query(
    notebook_id: str,
    prompt: str,
    *,
    source_ids: str | None = None,
    timeout: int = 180,
) -> str:
    cmd = [
        "nlm",
        "notebook",
        "query",
        notebook_id,
        prompt,
        "--json",
        "--new-conversation",
        "--timeout",
        str(timeout),
    ]
    if source_ids:
        cmd.extend(["--source-ids", source_ids])

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"nlm notebook query 失敗：{res.stderr or res.stdout}")

    raw = res.stdout.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ("answer", "response", "text", "content", "result"):
                if isinstance(parsed.get(key), str):
                    return parsed[key]
    except json.JSONDecodeError:
        pass
    return raw
