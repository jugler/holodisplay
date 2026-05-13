from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Protocol, Callable

_CLOCK_FONT_CANDIDATES = ["Roboto", "DejaVu Sans", "Arial", "Helvetica"]


def _clock_12h_parts(now: datetime) -> tuple[int, int]:
    """Hora 1-12 y minutos (sin am/pm)."""
    h24 = now.hour
    minute = now.minute
    h12 = h24 % 12
    if h12 == 0:
        h12 = 12
    return h12, minute


def _format_clock_12h(now: datetime) -> str:
    """12 h sin sufijo (p. ej. 00:27 -> 12:27)."""
    h12, minute = _clock_12h_parts(now)
    return f"{h12}:{minute:02d}"


def _compose_clock_tight(
    pygame,
    font,
    color: tuple[int, int, int],
    h12: int,
    minute: int,
) -> object:
    """Hora + ':' + minutos, con kerning reducido alrededor del ':'."""
    pieces = (str(h12), ":", f"{minute:02d}")
    surfs = [font.render(p, False, color) for p in pieces]
    # Acercar ':' a los digitos (las monoespaciadas dejan mucho aire).
    kern = -max(2, min(6, font.get_height() // 8))
    x = 0
    xs: list[int] = []
    for i, s in enumerate(surfs):
        xs.append(x)
        x += s.get_width()
        if i < 2:
            x += kern
    tw = max(x, 1)
    th = max(s.get_height() for s in surfs)
    out = pygame.Surface((tw, th), pygame.SRCALPHA)
    out.fill((0, 0, 0, 0))
    for s, px in zip(surfs, xs):
        out.blit(s, (px, (th - s.get_height()) // 2))
    return out


# Sans primero: ':' mas estrecho que en mono; mono como respaldo.
_CLOCK_TTF_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


class DisplayBackend(Protocol):
    def show_image(
        self,
        path: Path,
        display_time: int,
        stop_event: Event | None = None,
        *,
        show_clock_overlay: bool = False,
        clock_overlay_position: str = "bottom_left",
        clock_overlay_font_size: int = 48,
        clock_overlay_margin: int = 24,
        clock_overlay_x: int | None = None,
        clock_overlay_y: int | None = None,
        clock_overlay_space: str = "frame",
        clock_overlay_show_background: bool = True,
        display_orientation: str = "landscape",
        display_rotation_degrees: int = 0,
    ) -> None:
        """clock_overlay_space: frame = mismas coords que year_overlay_* sobre el JPEG; screen = SDL."""
        ...


class PygameDisplay:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        transition_ms: int,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.transition_ms = transition_ms
        self._pygame = None
        self._screen = None
        self._clock = None
        self._current_surface = None
        self._selected_driver = None
        self._clock_font = None
        self._clock_font_size: int | None = None
        self._clock_layout_logged = False

    def show_image(
        self,
        path: Path,
        display_time: int,
        stop_event: Event | None = None,
        *,
        show_clock_overlay: bool = False,
        clock_overlay_position: str = "bottom_left",
        clock_overlay_font_size: int = 48,
        clock_overlay_margin: int = 24,
        clock_overlay_x: int | None = None,
        clock_overlay_y: int | None = None,
        clock_overlay_space: str = "frame",
        clock_overlay_show_background: bool = True,
        display_orientation: str = "landscape",
        display_rotation_degrees: int = 0,
    ) -> None:
        pygame = self._init_pygame()
        target_width, target_height = self._screen.get_size()
        next_surface = pygame.image.load(str(path)).convert()
        orig_w, orig_h = next_surface.get_size()
        if orig_w != target_width or orig_h != target_height:
            # `smoothscale` reduce aliasing/pixelado al escalar (mejor que `scale`).
            next_surface = pygame.transform.smoothscale(next_surface, (target_width, target_height))

        clock_display_x: int | None = None
        clock_display_y: int | None = None
        if show_clock_overlay and clock_overlay_x is not None and clock_overlay_y is not None:
            if clock_overlay_space == "frame":
                if orig_w > 0 and orig_h > 0:
                    clock_display_x = int(round(clock_overlay_x * target_width / orig_w))
                    clock_display_y = int(round(clock_overlay_y * target_height / orig_h))
            else:
                clock_display_x, clock_display_y = clock_overlay_x, clock_overlay_y

        if show_clock_overlay and not self._clock_layout_logged:
            self._clock_layout_logged = True
            print(
                "Reloj pygame:",
                f"JPEG={orig_w}x{orig_h}",
                f"SDL={target_width}x{target_height}",
                f"coords_sdl={clock_display_x},{clock_display_y}"
                if clock_display_x is not None
                else f"ancla={clock_overlay_position}",
                f"(frame_cfg x={clock_overlay_x} y={clock_overlay_y} space={clock_overlay_space})",
                f"orient={display_orientation} rot={display_rotation_degrees}",
            )

        transition_seconds = min(display_time, self.transition_ms / 1000)
        transition_elapsed = self._run_transition(
            next_surface,
            transition_seconds,
            stop_event,
            show_clock_overlay=show_clock_overlay,
            clock_overlay_position=clock_overlay_position,
            clock_overlay_font_size=clock_overlay_font_size,
            clock_overlay_margin=clock_overlay_margin,
            clock_display_x=clock_display_x,
            clock_display_y=clock_display_y,
            display_orientation=display_orientation,
            display_rotation_degrees=display_rotation_degrees,
            clock_overlay_show_background=clock_overlay_show_background,
        )
        hold_seconds = max(0, display_time - transition_elapsed)

        self._screen.blit(next_surface, (0, 0))
        self._draw_clock_overlay(
            show_clock_overlay=show_clock_overlay,
            clock_overlay_position=clock_overlay_position,
            clock_overlay_font_size=clock_overlay_font_size,
            clock_overlay_margin=clock_overlay_margin,
            clock_display_x=clock_display_x,
            clock_display_y=clock_display_y,
            display_orientation=display_orientation,
            display_rotation_degrees=display_rotation_degrees,
            clock_overlay_show_background=clock_overlay_show_background,
        )
        pygame.display.flip()
        self._current_surface = next_surface
        self._wait(
            hold_seconds,
            stop_event,
            next_surface,
            show_clock_overlay=show_clock_overlay,
            clock_overlay_position=clock_overlay_position,
            clock_overlay_font_size=clock_overlay_font_size,
            clock_overlay_margin=clock_overlay_margin,
            clock_display_x=clock_display_x,
            clock_display_y=clock_display_y,
            display_orientation=display_orientation,
            display_rotation_degrees=display_rotation_degrees,
            clock_overlay_show_background=clock_overlay_show_background,
        )

    def show_splash_until(
        self,
        predicate: Callable[[], bool],
        *,
        text: str = "HoloDisplay loading...",
        orientation: str = "landscape",
        rotation_degrees: int = 0,
        fps: int = 30,
        cached_frames: int = 24,
    ) -> None:
        """
        Muestra un splash animado hasta que `predicate()` sea True.

        Usa el mismo `pygame`/screen que el display para evitar conflictos SDL.
        """
        pygame = self._init_pygame()
        from .splash import SplashRenderer, SplashStyle

        w, h = self._screen.get_size()

        # Fuente simple: intentamos Roboto si está disponible por fontconfig
        font = pygame.font.SysFont(["Roboto", "DejaVu Sans", "Arial", "Helvetica"], 54)

        # Pi 3B: reducir trabajo por frame con menos frames cacheados.
        effective_cached = max(12, min(int(cached_frames), 48))
        if os.uname().machine.startswith(("arm", "aarch64")):
            effective_cached = min(effective_cached, 24)

        style = SplashStyle(text=text, cached_frames=effective_cached)
        renderer = SplashRenderer(
            pygame,
            screen_size=(w, h),
            orientation=orientation,
            rotation_degrees=rotation_degrees,
            font=font,
            style=style,
        )

        while True:
            self._pump_events()
            if predicate():
                return
            self._screen.fill((0, 0, 0))
            renderer.draw(self._screen)
            pygame.display.flip()
            self._clock.tick(max(1, fps))

    def _init_pygame(self):
        if self._pygame is not None:
            return self._pygame

        try:
            import pygame
        except ImportError as error:
            raise RuntimeError(
                "HoloDisplay requiere instalar pygame en el dispositivo."
            ) from error

        driver_candidates = self._candidate_drivers()
        errors: list[str] = []

        for driver in driver_candidates:
            try:
                self._initialize_with_driver(pygame, driver)
                break
            except pygame.error as error:
                errors.append(f"{driver}: {error}")
                pygame.quit()
        else:
            joined_errors = " | ".join(errors) if errors else "sin detalles"
            raise RuntimeError(
                f"No se pudo iniciar pygame con ningun driver SDL. {joined_errors}"
            )

        self._pygame = pygame
        detected_width, detected_height = self._screen.get_size()
        print(
            "Pygame display detectado:",
            f"{detected_width}x{detected_height}",
        )
        print("SDL video driver:", self._selected_driver)
        # El patrón de prueba es útil para calibración, pero molesta en arranque normal.
        # Se puede reactivar con HOLODISPLAY_STARTUP_PATTERN=1
        if os.environ.get("HOLODISPLAY_STARTUP_PATTERN") == "1":
            self._draw_startup_test_pattern()
        return pygame

    def _candidate_drivers(self) -> list[str]:
        configured = os.environ.get("IMMICH_SDL_DRIVER")
        if configured:
            return [item.strip() for item in configured.split(",") if item.strip()]
        return ["kmsdrm", "fbcon", "x11"]

    def _initialize_with_driver(self, pygame, driver: str) -> None:
        os.environ["SDL_VIDEODRIVER"] = driver
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        if driver == "fbcon":
            os.environ.setdefault("SDL_FBDEV", "/dev/fb0")

        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("HoloDisplay")
        pygame.mouse.set_visible(False)
        self._screen = pygame.display.set_mode(
            (0, 0),
            pygame.FULLSCREEN | pygame.NOFRAME,
        )
        self._clock = pygame.time.Clock()
        self._selected_driver = pygame.display.get_driver()
        print(f"Intentando SDL_VIDEODRIVER={driver} -> OK")

    def _draw_startup_test_pattern(self) -> None:
        pygame = self._pygame
        width, height = self._screen.get_size()
        self._screen.fill((20, 20, 20))
        pygame.draw.rect(self._screen, (220, 40, 40), (0, 0, width // 2, height // 2))
        pygame.draw.rect(
            self._screen,
            (40, 180, 60),
            (width // 2, 0, width // 2, height // 2),
        )
        pygame.draw.rect(
            self._screen,
            (40, 90, 220),
            (0, height // 2, width // 2, height // 2),
        )
        pygame.draw.rect(
            self._screen,
            (230, 200, 40),
            (width // 2, height // 2, width // 2, height // 2),
        )
        pygame.display.flip()
        time.sleep(1)

    def _run_transition(
        self,
        next_surface,
        duration_seconds: float,
        stop_event: Event | None = None,
        *,
        show_clock_overlay: bool = False,
        clock_overlay_position: str = "bottom_left",
        clock_overlay_font_size: int = 48,
        clock_overlay_margin: int = 24,
        clock_display_x: int | None = None,
        clock_display_y: int | None = None,
        display_orientation: str = "landscape",
        display_rotation_degrees: int = 0,
        clock_overlay_show_background: bool = True,
    ) -> float:
        pygame = self._pygame
        if self._current_surface is None or duration_seconds <= 0:
            self._screen.blit(next_surface, (0, 0))
            self._draw_clock_overlay(
                show_clock_overlay=show_clock_overlay,
                clock_overlay_position=clock_overlay_position,
                clock_overlay_font_size=clock_overlay_font_size,
                clock_overlay_margin=clock_overlay_margin,
                clock_display_x=clock_display_x,
                clock_display_y=clock_display_y,
                display_orientation=display_orientation,
                display_rotation_degrees=display_rotation_degrees,
                clock_overlay_show_background=clock_overlay_show_background,
            )
            pygame.display.flip()
            return 0.0

        start = time.monotonic()
        next_surface.set_alpha(0)
        while True:
            self._pump_events()
            if stop_event is not None and stop_event.is_set():
                break
            elapsed = time.monotonic() - start
            if elapsed >= duration_seconds:
                break

            progress = elapsed / duration_seconds

            self._screen.blit(self._current_surface, (0, 0))
            next_surface.set_alpha(int(progress * 255))
            self._screen.blit(next_surface, (0, 0))
            self._draw_clock_overlay(
                show_clock_overlay=show_clock_overlay,
                clock_overlay_position=clock_overlay_position,
                clock_overlay_font_size=clock_overlay_font_size,
                clock_overlay_margin=clock_overlay_margin,
                clock_display_x=clock_display_x,
                clock_display_y=clock_display_y,
                display_orientation=display_orientation,
                display_rotation_degrees=display_rotation_degrees,
                clock_overlay_show_background=clock_overlay_show_background,
            )
            pygame.display.flip()
            self._clock.tick(30)
        next_surface.set_alpha(None)
        return time.monotonic() - start

    def _wait(
        self,
        seconds: float,
        stop_event: Event | None,
        base_surface,
        *,
        show_clock_overlay: bool = False,
        clock_overlay_position: str = "bottom_left",
        clock_overlay_font_size: int = 48,
        clock_overlay_margin: int = 24,
        clock_display_x: int | None = None,
        clock_display_y: int | None = None,
        display_orientation: str = "landscape",
        display_rotation_degrees: int = 0,
        clock_overlay_show_background: bool = True,
    ) -> None:
        pygame = self._pygame
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if stop_event is not None and stop_event.is_set():
                break
            if show_clock_overlay:
                self._screen.blit(base_surface, (0, 0))
                self._draw_clock_overlay(
                    show_clock_overlay=True,
                    clock_overlay_position=clock_overlay_position,
                    clock_overlay_font_size=clock_overlay_font_size,
                    clock_overlay_margin=clock_overlay_margin,
                    clock_display_x=clock_display_x,
                    clock_display_y=clock_display_y,
                    display_orientation=display_orientation,
                    display_rotation_degrees=display_rotation_degrees,
                    clock_overlay_show_background=clock_overlay_show_background,
                )
                pygame.display.flip()
            self._pump_events()
            self._clock.tick(30)

    def _load_clock_font(self, pygame, size: int):
        """SysFont falla a menudo en Pi sin escritorio; probamos TTF del sistema y la fuente bitmap."""
        for path in _CLOCK_TTF_CANDIDATES:
            try:
                font = pygame.font.Font(path, size)
                if self._clock_font_probe_ok(font):
                    return font
            except OSError:
                continue
        try:
            font = pygame.font.SysFont(_CLOCK_FONT_CANDIDATES, size, bold=True)
            if self._clock_font_probe_ok(font):
                return font
        except Exception:
            pass
        return pygame.font.Font(None, max(size, 20))

    @staticmethod
    def _clock_font_probe_ok(font) -> bool:
        try:
            surf = font.render("12:59", False, (255, 255, 255))
        except Exception:
            return False
        return surf.get_width() >= 12 and surf.get_height() >= 8

    def _draw_clock_overlay(
        self,
        *,
        show_clock_overlay: bool,
        clock_overlay_position: str,
        clock_overlay_font_size: int,
        clock_overlay_margin: int,
        clock_display_x: int | None,
        clock_display_y: int | None,
        display_orientation: str = "landscape",
        display_rotation_degrees: int = 0,
        clock_overlay_show_background: bool = True,
    ) -> None:
        if not show_clock_overlay:
            return
        pygame = self._pygame
        if clock_overlay_font_size != self._clock_font_size:
            self._clock_font = self._load_clock_font(pygame, clock_overlay_font_size)
            self._clock_font_size = clock_overlay_font_size
        assert self._clock_font is not None
        now = datetime.now()
        h12, minute = _clock_12h_parts(now)
        # Sin antialias; piezas con kerning para que no parezca "12 : 56" (espacio alrededor del ':').
        fg = _compose_clock_tight(pygame, self._clock_font, (250, 250, 250), h12, minute)
        shadow_rgb = (40, 40, 40) if clock_overlay_show_background else (0, 0, 0)
        shadow = _compose_clock_tight(pygame, self._clock_font, shadow_rgb, h12, minute)
        tw, th = fg.get_size()
        sw, sh = self._screen.get_size()
        pad = max(6, clock_overlay_font_size // 8)
        if clock_display_x is not None and clock_display_y is not None:
            # Coordenadas fijas: no clamp a [0, sw-tw] (saturaba el reloj en un borde si x era grande).
            x, y = clock_display_x, clock_display_y
        else:
            x, y = self._clock_text_origin((tw, th), clock_overlay_position, clock_overlay_margin)
            if tw < sw:
                x = max(0, min(x, sw - tw))
            else:
                x = 0
            if th < sh:
                y = max(0, min(y, sh - th))
            else:
                y = 0
        bg_rect = pygame.Rect(x - pad, y - pad, tw + pad * 2, th + pad * 2)
        sdx, sdy = (1, 1) if clock_overlay_show_background else (2, 2)
        if clock_overlay_show_background:
            surf = pygame.Surface((bg_rect.width, bg_rect.height))
            surf.fill((28, 28, 28))
            pygame.draw.rect(surf, (120, 120, 120), surf.get_rect(), width=1)
        else:
            surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 0))
        surf.blit(shadow, (pad + sdx, pad + sdy))
        surf.blit(fg, (pad, pad))

        rot = (display_rotation_degrees % 360) != 0 and display_orientation == "portrait"
        if rot:
            rotated = pygame.transform.rotate(surf, display_rotation_degrees)
            self._screen.blit(rotated, rotated.get_rect(center=bg_rect.center))
            if os.environ.get("HOLODISPLAY_DEBUG_CLOCK") == "1":
                dbg = rotated.get_rect(center=bg_rect.center)
                pygame.draw.rect(self._screen, (255, 0, 0), dbg, width=2)
        else:
            self._screen.blit(surf, bg_rect.topleft)
            if os.environ.get("HOLODISPLAY_DEBUG_CLOCK") == "1":
                pygame.draw.rect(self._screen, (255, 0, 0), bg_rect, width=2)

    def _clock_text_origin(
        self,
        text_size: tuple[int, int],
        position: str,
        margin: int,
    ) -> tuple[int, int]:
        sw, sh = self._screen.get_size()
        tw, th = text_size
        if position == "bottom_left":
            return margin, sh - th - margin
        if position == "bottom_right":
            return sw - tw - margin, sh - th - margin
        if position == "top_left":
            return margin, margin
        return sw - tw - margin, margin

    def _pump_events(self) -> None:
        for event in self._pygame.event.get():
            if event.type == self._pygame.QUIT:
                raise SystemExit(0)
