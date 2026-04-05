#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass
class Dimensions:
    width: int
    height: int


def load_dimensions(config_path: Path) -> Dimensions:
    if not config_path.exists():
        raise SystemExit(f"No se encontró el archivo de configuración: {config_path}")

    import tomllib

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    display = data.get("display", {})
    width = display.get("screen_width")
    height = display.get("screen_height")
    if not isinstance(width, int) or not isinstance(height, int):
        raise SystemExit("display.screen_width y display.screen_height deben estar definidos como enteros.")
    return Dimensions(width, height)


def run_guide(
    width: int,
    height: int,
    color: tuple[int, int, int],
    thickness: int,
    background: tuple[int, int, int],
    spacing: int,
) -> None:
    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Guía de alineación")
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in {pygame.K_ESCAPE, pygame.K_q}:
                return

        screen.fill(background)

        hw = width // 2
        hh = height // 2

        # crosshair
        pygame.draw.line(screen, color, (0, hh), (width, hh), thickness)
        pygame.draw.line(screen, color, (hw, 0), (hw, height), thickness)

        # borders
        border_thickness = max(thickness, 2)
        pygame.draw.line(screen, color, (0, 0), (width, 0), border_thickness)
        pygame.draw.line(screen, color, (0, height - 1), (width, height - 1), border_thickness)
        pygame.draw.line(screen, color, (0, 0), (0, height), border_thickness)
        pygame.draw.line(screen, color, (width - 1, 0), (width - 1, height), border_thickness)

        # grid
        if spacing > 0:
            for x in range(spacing, width, spacing):
                pygame.draw.line(screen, color, (x, 0), (x, height), 1)

            for y in range(spacing, height, spacing):
                pygame.draw.line(screen, color, (0, y), (width, y), 1)

        pygame.display.flip()
        clock.tick(30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guía simple de líneas horizontales/verticales para centrar un marco.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Ruta al archivo de configuración para leer las dimensiones.",
    )
    parser.add_argument(
        "--color",
        default="255,255,255",
        help="Color de las líneas en formato R,G,B (default blanco).",
    )
    parser.add_argument(
        "--background",
        default="0,0,0",
        help="Color de fondo formato R,G,B (default negro).",
    )
    parser.add_argument(
        "--thickness",
        type=int,
        default=5,
        help="Grosor de las líneas principales.",
    )
    parser.add_argument(
        "--grid-spacing",
        type=int,
        default=50,
        help="Espaciado entre líneas secundarias (en píxeles).",
    )
    return parser.parse_args()


def parse_color(text: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("El color debe tener tres componentes R,G,B.")
    rgb = tuple(int(part) for part in parts)
    if any(not (0 <= value <= 255) for value in rgb):
        raise argparse.ArgumentTypeError("Cada componente RGB debe estar entre 0 y 255.")
    return rgb


def main() -> int:
    args = parse_args()
    color = parse_color(args.color)
    background = parse_color(args.background)
    dims = load_dimensions(args.config)
    run_guide(
        dims.width,
        dims.height,
        color,
        args.thickness,
        background,
        args.grid_spacing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
