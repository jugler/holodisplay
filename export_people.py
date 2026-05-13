#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from holo_display.config import credentials_for_people_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga los datos de /people de Immich y genera un TOML (ruta por defecto = people_conf del usuario)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.toml"),
        help="Ruta al config.toml que contiene [immich]",
    )
    parser.add_argument(
        "--user",
        "-u",
        choices=("main", "phone", "art", "nsfw"),
        default="main",
        help="Bloque [main|phone|art|nsfw] para api_key y people_conf (salida por defecto)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Archivo TOML destino (por defecto: people_conf de ese usuario, resuelto como en la app)",
    )
    parser.add_argument(
        "--immich-url",
        type=str,
        help="URL base de Immich (anula el valor de config.toml)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key de Immich (anula el valor de config.toml)",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Incluir personas ocultas (parámetro withHidden)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Cantidad de elementos por página (1–1000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout en segundos para cada llamada HTTP",
    )
    return parser.parse_args()


def fetch_people(
    base_url: str,
    api_key: str,
    include_hidden: bool,
    page_size: int,
    timeout: float,
) -> list[dict]:
    if page_size < 1 or page_size > 1000:
        raise ValueError("page-size debe estar entre 1 y 1000")

    headers = {"x-api-key": api_key}
    endpoint = f"{base_url}/people"
    people: list[dict] = []
    page = 1

    session = requests.Session()
    try:
        while True:
            params = {"page": page, "size": page_size}
            if include_hidden:
                params["withHidden"] = True

            response = session.get(endpoint, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()

            payload = response.json()
            page_items = payload.get("people")
            if not isinstance(page_items, list):
                raise RuntimeError("La respuesta de /people no contiene la lista esperada")

            for person in page_items:
                if isinstance(person, dict):
                    people.append(person)

            has_next = payload.get("hasNextPage")
            if has_next is None:
                if len(page_items) < page_size:
                    break
            elif not has_next:
                break

            page += 1
    finally:
        session.close()

    return people


def build_people_map(people: list[dict]) -> dict[str, str]:
    people_map: dict[str, str] = {}
    for person in people:
        name = person.get("name")
        person_id = person.get("id")
        if not isinstance(name, str) or not isinstance(person_id, str):
            continue
        if name in people_map and people_map[name] != person_id:
            print(
                f"Advertencia: se ignoró otra entrada para {name} ({person_id} vs {people_map[name]})",
                file=sys.stderr,
            )
            continue
        people_map[name] = person_id
    return people_map


def write_people_toml(people_map: dict[str, str], output_path: Path) -> None:
    output_lines = []
    for name in sorted(people_map):
        entry = f"{json.dumps(name)} = {json.dumps(people_map[name])}"
        output_lines.append(entry)
    output_text = "\n".join(output_lines)
    if output_text:
        output_text += "\n"
    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    try:
        base_url, api_key, default_output = credentials_for_people_export(
            args.config,
            args.user,
        )
    except Exception as exc:
        print(f"Error al leer la configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.immich_url:
        base_url = args.immich_url.rstrip("/")
    if args.api_key:
        api_key = args.api_key

    output_path = args.output if args.output is not None else default_output

    try:
        people = fetch_people(
            base_url=base_url,
            api_key=api_key,
            include_hidden=args.include_hidden,
            page_size=args.page_size,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"Error al consultar /people: {exc}", file=sys.stderr)
        sys.exit(1)

    people_map = build_people_map(people)
    write_people_toml(people_map, output_path)

    print(f"Escribí {len(people_map)} entradas en {output_path}")


if __name__ == "__main__":
    main()
