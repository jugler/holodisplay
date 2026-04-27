from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps

from holo_display.config import load_file_config
from holo_display.immich_client import ImmichClient


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="debug_orientation.py",
        description="Descarga un asset por id y vuelca EXIF + renders con/sin EXIF transpose.",
    )
    parser.add_argument(
        "asset_id",
        help="Immich asset id (uuid).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Ruta al config TOML (por defecto usa el default del proyecto).",
    )
    parser.add_argument(
        "--out",
        default="debug",
        help="Directorio de salida (default: debug).",
    )
    return parser.parse_args()


def _dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _jsonify_exif_value(value: object) -> object:
    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8")
        except UnicodeDecodeError:
            decoded = value.decode("latin-1", errors="replace")
        return decoded
    if isinstance(value, list):
        return [_jsonify_exif_value(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonify_exif_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonify_exif_value(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Pillow puede devolver tipos como IFDRational, etc.
    return str(value)


def main() -> int:
    args = _parse_args()
    file_config = load_file_config(args.config) if args.config else load_file_config()

    # ImmichClient usa AppConfig, pero aquí solo necesitamos URL + headers.
    class _MiniConfig:
        immich_url = file_config.immich_url
        headers = {"x-api-key": file_config.api_key}
        search_mode = "person"
        orientation = "any"
        search_size = 1
        smart_result_limit = 1
        person_ids: tuple[str, ...] = ()
        smart_query = None
        smart_city = None
        use_art_api_key = False

    client = ImmichClient(_MiniConfig())  # type: ignore[arg-type]
    asset_id: str = args.asset_id

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    details = client.fetch_asset_details(asset_id)
    img_bytes = client.fetch_thumbnail(asset_id)

    original_path = out_dir / f"{asset_id}.original"
    original_path.write_bytes(img_bytes)

    _dump_json(out_dir / f"{asset_id}.asset_details.json", details)

    img = Image.open(original_path)
    exif = img.getexif()
    exif_dict = (
        {str(k): _jsonify_exif_value(exif.get(k)) for k in exif.keys()} if exif is not None else {}
    )
    orientation_value = exif.get(274) if exif is not None else None

    _dump_json(
        out_dir / f"{asset_id}.pil_exif.json",
        {
            "pil_format": img.format,
            "pil_mode": img.mode,
            "pil_size": [img.size[0], img.size[1]],
            "orientation_tag_274": orientation_value,
            "exif": exif_dict,
        },
    )

    # Render sin exif transpose (lo que pasaba antes)
    img_rgb = img.convert("RGB")
    img_rgb.save(out_dir / f"{asset_id}.no_exif_transpose.jpg", format="JPEG", quality=92)

    # Render con exif transpose (lo correcto)
    img_fixed = ImageOps.exif_transpose(img).convert("RGB")
    img_fixed.save(out_dir / f"{asset_id}.with_exif_transpose.jpg", format="JPEG", quality=92)

    print("Guardado en:", out_dir.resolve())
    print("Orientation (EXIF 274):", orientation_value)
    print("Size before:", img.size, "after:", img_fixed.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

