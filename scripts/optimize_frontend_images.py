"""Build/check web delivery copies; preserve all original artwork unchanged."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from PIL import __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend/src/assets/theme"
OUTPUT = ROOT / "frontend/src/assets/optimized"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify copies against their recorded sources")
    args = parser.parse_args()
    manifest_path = OUTPUT / "manifest.json"
    if args.check:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in document["files"]:
            source, target = ROOT / row["source"], ROOT / row["output"]
            assert digest(source) == row["source_sha256"], f"Artwork changed: {source.name}"
            assert digest(target) == row["output_sha256"], f"Delivery copy changed: {target.name}"
            with Image.open(target) as image:
                assert list(image.size) == row["dimensions"], target.name
        print(f"Verified {len(document['files'])} web images and unchanged source artwork")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = []
    sources = [SOURCE / f"{name}.png" for name in ("back", "image1", "image2", "image3", "image4")]
    sources.append(ROOT / "frontend/public/favicon.png")
    for source in sources:
        icon = source.name == "favicon.png"
        target = OUTPUT / ("brand-icon.png" if icon else f"{source.stem}.webp")
        with Image.open(source) as image:
            if icon:
                image = image.convert("RGBA")
                image.thumbnail((96, 96), Image.Resampling.LANCZOS)
                image.save(target, format="PNG", optimize=True)
            else:
                image.save(target, format="WEBP", quality=82, method=6)
            dimensions = list(image.size)
        files.append({"source": source.relative_to(ROOT).as_posix(), "source_sha256": digest(source),
                      "output": target.relative_to(ROOT).as_posix(), "output_sha256": digest(target),
                      "source_bytes": source.stat().st_size, "output_bytes": target.stat().st_size,
                      "dimensions": dimensions})
    document = {"schema": 1, "encoder": f"Pillow {pillow_version}",
                "webp": {"quality": 82, "method": 6, "preserve_dimensions": True},
                "icon": {"max_dimensions": [96, 96], "resampling": "LANCZOS"}, "files": files}
    manifest_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_bytes": sum(row["source_bytes"] for row in files),
                      "delivery_bytes": sum(row["output_bytes"] for row in files), "files": len(files)}))


if __name__ == "__main__":
    main()
