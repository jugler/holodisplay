from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont


class ImageProcessor:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        year_overlay_font_size: int | None = None,
        info_overlay_font_size: int | None = None,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.year_overlay_font_size = year_overlay_font_size
        self.info_overlay_font_size = info_overlay_font_size

    def prepare(
        self,
        image_bytes: bytes,
        allow_vertical: bool = False,
    ) -> tuple[Image.Image, tuple[int, int]]:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        width, height = image.size

        if height > width and not allow_vertical:
            raise ValueError("vertical_image")

        image = self._compose_background(image, width, height)
        return image, (width, height)

    def add_memory_overlay(
        self,
        image: Image.Image,
        year: str,
        side: str = "right",
    ) -> Image.Image:
        base = image.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._load_overlay_font()
        text = year

        text_box = draw.textbbox((0, 0), text, font=font)
        text_left = text_box[0]
        text_top = text_box[1]
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        padding_x = max(10, self.screen_width // 90)
        padding_y = max(6, self.screen_height // 120)
        panel_height = text_height + (padding_y * 2)
        panel_top = self.screen_height - panel_height - max(24, self.screen_height // 40)
        panel_bottom = panel_top + panel_height
        margin_side = max(20, self.screen_width // 40)
        if side == "left":
            panel_left = margin_side
            panel_right = panel_left + text_width + (padding_x * 2)
        else:
            panel_right = self.screen_width - margin_side
            panel_left = max(
                margin_side,
                panel_right - text_width - (padding_x * 2),
            )

        draw.rounded_rectangle(
            (panel_left, panel_top, panel_right, panel_bottom),
            radius=max(12, self.screen_height // 90),
            fill=(0, 0, 0, 150),
        )
        draw.text(
            (panel_left + padding_x - text_left, panel_top + padding_y - text_top),
            text,
            font=font,
            fill=(255, 255, 255, 255),
        )
        return Image.alpha_composite(base, overlay).convert("RGB")

    def add_person_overlay(
        self,
        image: Image.Image,
        year: str | None,
        people: str | None,
        location: str | None,
        layout: str,
    ) -> Image.Image:
        is_mirrored = layout in {"mirrored", "right"}
        result = image
        if year:
            result = self.add_memory_overlay(
                result,
                year,
                side="left" if is_mirrored else "right",
            )

        info_lines = [line for line in (people, location) if line]
        if not info_lines:
            return result

        base = result.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._load_info_font()
        padding_x = max(14, self.screen_width // 70)
        padding_y = max(10, self.screen_height // 90)
        line_gap = max(12, self.screen_height // 90)
        margin_top = max(56, self.screen_height // 12)
        margin_left = max(20, self.screen_width // 40)

        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in info_lines]
        line_widths = [box[2] - box[0] for box in line_boxes]
        line_heights = [box[3] - box[1] for box in line_boxes]
        panel_width = max(line_widths) + (padding_x * 2)
        panel_height = sum(line_heights) + (padding_y * 2)
        if len(info_lines) > 1:
            panel_height += line_gap * (len(info_lines) - 1)

        if is_mirrored:
            panel_right = self.screen_width - margin_left
            panel_left = panel_right - panel_width
        else:
            panel_left = margin_left
            panel_right = panel_left + panel_width
        panel_top = margin_top
        panel_bottom = panel_top + panel_height

        draw.rounded_rectangle(
            (panel_left, panel_top, panel_right, panel_bottom),
            radius=max(12, self.screen_height // 90),
            fill=(0, 0, 0, 150),
        )

        current_y = panel_top + padding_y
        for line, box, height in zip(info_lines, line_boxes, line_heights):
            draw.text(
                (panel_left + padding_x - box[0], current_y - box[1]),
                line,
                font=font,
                fill=(255, 255, 255, 255),
            )
            current_y += height + line_gap

        return Image.alpha_composite(base, overlay).convert("RGB")

    def _compose_background(
        self, image: Image.Image, width: int, height: int
    ) -> Image.Image:
        img_ratio = width / height
        screen_ratio = self.screen_width / self.screen_height

        if img_ratio > screen_ratio:
            new_width = self.screen_width
            new_height = int(self.screen_width / img_ratio)
        else:
            new_height = self.screen_height
            new_width = int(self.screen_height * img_ratio)

        resized = image.resize((new_width, new_height), Image.LANCZOS)
        background = image.resize(
            (self.screen_width, self.screen_height), Image.LANCZOS
        )
        background = background.filter(ImageFilter.GaussianBlur(25))

        x = (self.screen_width - new_width) // 2
        y = (self.screen_height - new_height) // 2
        background.paste(resized, (x, y))
        return background

    def _load_overlay_font(self) -> ImageFont.ImageFont:
        font_size = self.year_overlay_font_size or max(30, self.screen_height // 18)
        font_candidates = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        )
        for font_path in font_candidates:
            try:
                return ImageFont.truetype(font_path, font_size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _load_info_font(self) -> ImageFont.ImageFont:
        font_size = self.info_overlay_font_size or max(18, self.screen_height // 32)
        font_candidates = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        )
        for font_path in font_candidates:
            try:
                return ImageFont.truetype(font_path, font_size)
            except OSError:
                continue
        return ImageFont.load_default()
