from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SplashStyle:
    spinner_diameter: int = 340
    spinner_thickness: int = 10
    spinner_segments: int = 12
    turns_per_sec: float = 1.0
    cached_frames: int = 32
    gradient_start: tuple[int, int, int] = (0, 210, 255)  # cyan
    gradient_end: tuple[int, int, int] = (255, 60, 180)  # magenta
    text: str = "HoloDisplay loading..."
    text_gap: int = 24
    pad_x: int = 20
    pad_y: int = 12


class SplashRenderer:
    """
    Renderer ligero para splashscreen.

    - No abre ventanas ni inicializa pygame: usa el pygame/screen ya inicializado por el Display.
    - Pre-renderiza N frames (y opcionalmente su versión rotada) para minimizar CPU en Raspberry Pi 3B.
    """

    def __init__(
        self,
        pygame,
        *,
        screen_size: tuple[int, int],
        orientation: str = "landscape",
        rotation_degrees: int = 0,
        font,
        style: SplashStyle | None = None,
    ) -> None:
        self.pygame = pygame
        self.screen_w, self.screen_h = screen_size
        self.orientation = orientation
        self.rotation_degrees = rotation_degrees
        self.font = font
        self.style = style or SplashStyle()

        self._needs_rotation = self.orientation == "portrait" and self.rotation_degrees in {90, 180, 270}
        self._frames = self._build_cached_frames()
        self._frame_count = len(self._frames)
        self._start = time.monotonic()

    def draw(self, screen_surface) -> None:
        """Blitea el frame actual centrado (no hace flip)."""
        elapsed = time.monotonic() - self._start
        idx = int((elapsed * self.style.turns_per_sec) * self._frame_count) % self._frame_count
        frame = self._frames[idx]
        screen_surface.blit(frame, frame.get_rect(center=screen_surface.get_rect().center))

    def _build_cached_frames(self):
        pygame = self.pygame
        s = self.style

        spinner_d = s.spinner_diameter
        spinner_r = spinner_d // 2 - 10
        spinner_surface = pygame.Surface((spinner_d, spinner_d), pygame.SRCALPHA).convert_alpha()

        text_surface = self.font.render(s.text, True, (255, 255, 255))
        ui_w = max(spinner_d, text_surface.get_width()) + s.pad_x * 2
        ui_h = spinner_d + s.text_gap + text_surface.get_height() + s.pad_y * 2
        ui_surface = pygame.Surface((ui_w, ui_h), pygame.SRCALPHA).convert_alpha()

        spinner_rect = spinner_surface.get_rect(midtop=(ui_w // 2, s.pad_y))
        text_rect = text_surface.get_rect(midtop=(ui_w // 2, spinner_rect.bottom + s.text_gap))

        frames = []
        for i in range(max(1, int(s.cached_frames))):
            phase = (2 * math.pi) * (i / max(1, int(s.cached_frames)))
            self._draw_spinner(
                spinner_surface,
                phase,
                pygame=pygame,
                spinner_r=spinner_r,
                thickness=s.spinner_thickness,
                segments=s.spinner_segments,
                grad_start=s.gradient_start,
                grad_end=s.gradient_end,
            )

            ui_surface.fill((0, 0, 0, 0))
            ui_surface.blit(spinner_surface, spinner_rect)
            ui_surface.blit(text_surface, text_rect)

            frame = ui_surface.copy()
            if self._needs_rotation:
                frame = pygame.transform.rotate(frame, self.rotation_degrees)
            frames.append(frame.convert_alpha())

        return frames

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    @classmethod
    def _lerp_color(
        cls,
        c1: tuple[int, int, int],
        c2: tuple[int, int, int],
        t: float,
    ) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        return (
            int(cls._lerp(c1[0], c2[0], t)),
            int(cls._lerp(c1[1], c2[1], t)),
            int(cls._lerp(c1[2], c2[2], t)),
        )

    @staticmethod
    def _draw_capsule(pygame, dst, color, p1, p2, thickness: int) -> None:
        pygame.draw.line(dst, color, p1, p2, thickness)
        r = max(1, thickness // 2)
        pygame.draw.circle(dst, color, (int(p1[0]), int(p1[1])), r)
        pygame.draw.circle(dst, color, (int(p2[0]), int(p2[1])), r)

    @classmethod
    def _draw_spinner(
        cls,
        dst,
        phase: float,
        *,
        pygame,
        spinner_r: int,
        thickness: int,
        segments: int,
        grad_start: tuple[int, int, int],
        grad_end: tuple[int, int, int],
    ) -> None:
        dst.fill((0, 0, 0, 0))
        cx = dst.get_width() / 2
        cy = dst.get_height() / 2
        step = (2 * math.pi) / max(1, segments)

        for i in range(max(1, segments)):
            a = phase - i * step
            t = 1.0 - (i / max(1, segments))
            alpha = max(18, int(255 * (t**2)))
            base = cls._lerp_color(grad_start, grad_end, t)
            color = (*base, alpha)

            x1 = cx + math.cos(a) * (spinner_r * 0.55)
            y1 = cy + math.sin(a) * (spinner_r * 0.55)
            x2 = cx + math.cos(a) * (spinner_r * 1.00)
            y2 = cy + math.sin(a) * (spinner_r * 1.00)

            cls._draw_capsule(pygame, dst, color, (x1, y1), (x2, y2), thickness)

