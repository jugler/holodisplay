import math
import sys
from pathlib import Path

import pygame

# Optional: force 1:1 logical pixels on HiDPI (can look blurry). Prefer using
# screen.get_size() below instead of disabling HiDPI.
# import os
# os.environ.setdefault("SDL_WINDOW_ALLOW_HIGHDPI", "0")

_ROOT = Path(__file__).resolve().parent

pygame.init()
pygame.font.init()

def _load_display_settings(config_path: Path) -> tuple[int, int, str, int]:
    """
    Lee config.toml para obtener:
    - display.screen_width / display.screen_height (físico)
    - display.orientation (landscape/portrait/any)
    - display.rotation_degrees (0/90/180/270)
    """
    try:
        import tomllib  # py3.11+
    except ModuleNotFoundError:
        raise SystemExit("Python >= 3.11 requerido (tomllib).")

    if not config_path.exists():
        # fallback útil para desarrollo
        for fallback in (config_path.with_name("config.frame.toml"), config_path.with_name("config.example.toml")):
            if fallback.exists():
                config_path = fallback
                break

    if config_path.exists():
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        display = data.get("display", {}) if isinstance(data, dict) else {}
        w = display.get("screen_width", 1080)
        h = display.get("screen_height", 1920)
        orientation = display.get("orientation", "landscape")
        rotation = display.get("rotation_degrees", 0)
        if not isinstance(w, int) or not isinstance(h, int):
            w, h = 1080, 1920
        if orientation not in {"landscape", "portrait", "any"}:
            orientation = "landscape"
        if rotation not in {0, 90, 180, 270}:
            rotation = 0
        print(
            f"[splashscreen] config: {config_path} -> {w}x{h}, orientation={orientation}, rotation={rotation}",
            file=sys.stderr,
            flush=True,
        )
        return w, h, orientation, rotation

    print(
        f"[splashscreen] config: no encontrado ({config_path}); usando 1080x1920",
        file=sys.stderr,
        flush=True,
    )
    return 1080, 1920, "portrait", 0


# Resolución/rotación desde config.toml (el surface real puede ser mayor en Retina / HiDPI).
CONFIG_W, CONFIG_H, ORIENTATION, ROTATION_DEG = _load_display_settings(_ROOT / "config.toml")
screen = pygame.display.set_mode((CONFIG_W, CONFIG_H))
pygame.display.set_caption("HoloDisplay Splash")

clock = pygame.time.Clock()

# Surface real (crítico en macOS Retina: suele ser 2× el tamaño lógico).
screen_rect = screen.get_rect()

# Necesitamos rotación solo en modo portrait y con grados válidos
_needs_rotation = ORIENTATION == "portrait" and ROTATION_DEG in {90, 180, 270}

_FONT_PROBE = "HoloDisplay loading"


def _log_font(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _try_font_file(path: Path | str, label: str, size: int) -> pygame.font.Font | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        f = pygame.font.Font(str(p), size)
        if f.render(_FONT_PROBE, True, (255, 255, 255)).get_width() <= 0:
            return None
        _log_font(f"[splashscreen] font: {label} -> {p.resolve()}")
        return f
    except (OSError, pygame.error) as exc:
        _log_font(f"[splashscreen] font: skip {p}: {exc}")
        return None


def _load_ui_font(size: int) -> pygame.font.Font:
    """Roboto vía archivo o fontconfig; si no, otras familias; último recurso Font(None)."""
    for fn in ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto.ttf"):
        got = _try_font_file(_ROOT / "assets" / fn, f"bundled assets/{fn}", size)
        if got is not None:
            return got

    for path in (
        "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/roboto/hinted/Roboto-Regular.ttf",
        "/usr/local/share/fonts/Roboto-Regular.ttf",
        Path.home() / ".local/share/fonts/Roboto-Regular.ttf",
        Path.home() / ".fonts/Roboto-Regular.ttf",
    ):
        got = _try_font_file(path, "system path", size)
        if got is not None:
            return got

    for query in (
        "roboto",
        "Roboto-Regular",
        "roboto-regular",
        "Roboto",
        "roboto condensed",
    ):
        matched = pygame.font.match_font(query)
        if matched:
            got = _try_font_file(matched, f"match_font({query!r})", size)
            if got is not None:
                return got

    _log_font(
        "[splashscreen] font: Roboto no encontrada (¿`fc-cache -fv` tras instalar?). "
        "Probando otras familias…"
    )

    for name in (
        "avenir next",
        "avenir",
        "helvetica neue",
        "sf pro text",
        "segoe ui",
        "calibri",
        "noto sans",
        "cantarell",
        "liberation sans",
        "arial",
        "helvetica",
    ):
        matched = pygame.font.match_font(name)
        if matched:
            got = _try_font_file(matched, f"match_font({name!r})", size)
            if got is not None:
                return got

    fallback = pygame.font.SysFont(["Segoe UI", "Arial", "Helvetica"], size)
    if fallback.render(_FONT_PROBE, True, (255, 255, 255)).get_width() > 0:
        _log_font(
            "[splashscreen] font: pygame SysFont (nombre genérico; "
            "SDL puede no exponer la ruta — revisa que Roboto esté en fontconfig)"
        )
        return fallback

    _log_font("[splashscreen] font: fallback -> pygame Font(None) (bitmap básica)")
    return pygame.font.Font(None, size)


font = _load_ui_font(60)

# Spinner procedural (evita wobble de PNGs rotados y se ve más "loading")
SPINNER_DIAMETER = 380
SPINNER_RADIUS = SPINNER_DIAMETER // 2 - 10
SPINNER_THICKNESS = 10
SPINNER_SEGMENTS = 12
SPINNER_TURNS_PER_SEC = 1.0
# Frames pre-render del spinner (más = más suave, pero más RAM/arranque)
SPINNER_CACHED_FRAMES = 48
# Gradiente tipo "neón" (ajusta a gusto)
SPINNER_GRADIENT_START = (0, 210, 255)   # cyan
SPINNER_GRADIENT_END = (255, 60, 180)    # magenta

_spinner_extent = SPINNER_DIAMETER // 2
TEXT_GAP = 28

spinner_surface = pygame.Surface((SPINNER_DIAMETER, SPINNER_DIAMETER), pygame.SRCALPHA).convert_alpha()


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def _draw_capsule(
    dst: pygame.Surface,
    color: tuple[int, int, int, int],
    p1: tuple[float, float],
    p2: tuple[float, float],
    thickness: int,
) -> None:
    """Segmento con extremos redondeados (ovalado)."""
    # Line body
    pygame.draw.line(dst, color, p1, p2, thickness)
    # Round caps
    r = max(1, thickness // 2)
    pygame.draw.circle(dst, color, (int(p1[0]), int(p1[1])), r)
    pygame.draw.circle(dst, color, (int(p2[0]), int(p2[1])), r)


def _draw_spinner(dst: pygame.Surface, phase: float) -> None:
    """Dibuja un spinner con cola (12 marcas con alpha)."""
    dst.fill((0, 0, 0, 0))
    cx = SPINNER_DIAMETER / 2
    cy = SPINNER_DIAMETER / 2

    # phase en radianes; cada segmento está separado por 2π/N
    step = (2 * math.pi) / SPINNER_SEGMENTS
    for i in range(SPINNER_SEGMENTS):
        a = phase - i * step
        # Head brighter, tail fades out
        t = 1.0 - (i / SPINNER_SEGMENTS)
        alpha = max(20, int(255 * (t**2)))
        # Color del gradiente: cabeza más hacia END, cola hacia START
        base = _lerp_color(SPINNER_GRADIENT_START, SPINNER_GRADIENT_END, t)
        color = (*base, alpha)

        x1 = cx + math.cos(a) * (SPINNER_RADIUS * 0.55)
        y1 = cy + math.sin(a) * (SPINNER_RADIUS * 0.55)
        x2 = cx + math.cos(a) * (SPINNER_RADIUS * 1.00)
        y2 = cy + math.sin(a) * (SPINNER_RADIUS * 1.00)

        _draw_capsule(dst, color, (x1, y1), (x2, y2), SPINNER_THICKNESS)

# UI surfaces (spinner + texto). Se rota SOLO este bloque (pequeño) si hace falta.
text = font.render("HoloDisplay loading...", True, (255, 255, 255))
UI_PAD_X = 20
UI_PAD_Y = 12
ui_w = max(SPINNER_DIAMETER, text.get_width()) + UI_PAD_X * 2
ui_h = SPINNER_DIAMETER + TEXT_GAP + text.get_height() + UI_PAD_Y * 2
ui_surface = pygame.Surface((ui_w, ui_h), pygame.SRCALPHA).convert_alpha()
spinner_rect = spinner_surface.get_rect(midtop=(ui_w // 2, UI_PAD_Y))
text_rect = text.get_rect(midtop=(ui_w // 2, spinner_rect.bottom + TEXT_GAP))

def _build_cached_ui_frames() -> list[pygame.Surface]:
    frames: list[pygame.Surface] = []
    for i in range(SPINNER_CACHED_FRAMES):
        phase = (2 * math.pi) * (i / SPINNER_CACHED_FRAMES)
        _draw_spinner(spinner_surface, phase)
        ui_surface.fill((0, 0, 0, 0))
        ui_surface.blit(spinner_surface, spinner_rect)
        ui_surface.blit(text, text_rect)
        base = ui_surface.copy()
        if _needs_rotation:
            base = pygame.transform.rotate(base, ROTATION_DEG)
        # Convertir para blit más rápido (mantener alpha)
        frames.append(base.convert_alpha())
    return frames


cached_frames = _build_cached_ui_frames()
_frame_count = len(cached_frames)
_t = 0.0

running = True
while running:
    dt_ms = clock.tick(60)
    dt = dt_ms / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Fondo negro directo al screen (barato)
    screen.fill((0, 0, 0))

    _t += dt
    idx = int((_t * SPINNER_TURNS_PER_SEC) * _frame_count) % _frame_count
    frame = cached_frames[idx]
    screen.blit(frame, frame.get_rect(center=screen_rect.center))

    pygame.display.flip()

pygame.quit()
sys.exit()