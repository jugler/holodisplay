from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080
DEFAULT_DISPLAY_TIME = 3
DEFAULT_SEARCH_SIZE = 1000
DEFAULT_SEEN_BUFFER_SIZE = 100
DEFAULT_DISPLAY_BACKEND = "framebuffer"
DEFAULT_TRANSITION_MS = 700


@dataclass(frozen=True)
class FileConfig:
    immich_url: str
    api_key: str
    pics_dir: Path
    screen_width: int
    screen_height: int
    display_time: int
    display_backend: str
    grayscale: bool
    show_year_overlay: bool
    show_info_overlay: bool
    overlay_layout: str
    year_overlay_font_size: int | None
    info_overlay_font_size: int | None
    year_overlay_x: int | None
    year_overlay_y: int | None
    info_overlay_x: int | None
    info_overlay_y: int | None
    transition_ms: int
    search_size: int
    seen_buffer_size: int
    search_mode: str
    smart_query: str | None
    smart_city: str | None
    default_people: tuple[str, ...]
    persons: dict[str, str]


@dataclass(frozen=True)
class AppConfig:
    immich_url: str
    api_key: str
    display_time: int
    display_backend: str
    grayscale: bool
    show_year_overlay: bool
    show_info_overlay: bool
    overlay_layout: str
    year_overlay_font_size: int | None
    info_overlay_font_size: int | None
    year_overlay_x: int | None
    year_overlay_y: int | None
    info_overlay_x: int | None
    info_overlay_y: int | None
    pics_dir: Path
    screen_width: int
    screen_height: int
    active_person: str | None = None
    active_people: tuple[str, ...] = ()
    person_id: str | None = None
    person_ids: tuple[str, ...] = ()
    search_mode: str = "person"
    smart_query: str | None = None
    smart_city: str | None = None
    transition_ms: int = DEFAULT_TRANSITION_MS
    search_size: int = DEFAULT_SEARCH_SIZE
    seen_buffer_size: int = DEFAULT_SEEN_BUFFER_SIZE

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key}

    @property
    def image_path(self) -> Path:
        return self.pics_dir / "frame.jpg"

    @property
    def tmp_path(self) -> Path:
        return self.pics_dir / "frame_tmp.jpg"

    @property
    def search_label(self) -> str:
        if self.search_mode == "memories":
            return "Memories"
        if self.search_mode == "random":
            return "Random"
        if self.search_mode == "smart":
            return self.smart_query or "unknown"
        if self.active_people:
            return ", ".join(self.active_people)
        return self.active_person or "unknown"


def load_file_config(path: str | Path = DEFAULT_CONFIG_PATH) -> FileConfig:
    config_path = Path(path).expanduser()
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontro el archivo de configuracion: {config_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"El archivo de configuracion no es TOML valido: {config_path}: {error}") from error

    immich = _get_table(raw, "immich")
    display = _get_table(raw, "display")
    search = _get_table(raw, "search")
    persons = _get_table(raw, "persons")

    default_people_value = search.get("default_people", ("Jesus",))
    if not isinstance(default_people_value, list | tuple):
        raise ValueError("search.default_people debe ser una lista de nombres")
    default_people = tuple(_ensure_str(name, "search.default_people[]") for name in default_people_value)
    if not default_people:
        raise ValueError("search.default_people no puede estar vacio")

    search_mode = _require_str(search, "mode", "search.mode", "person")
    if search_mode not in {"person", "smart", "memories", "random"}:
        raise ValueError("search.mode debe ser person, smart, memories o random")

    smart_query = _optional_str(search, "smart_query", "search.smart_query")
    if search_mode == "smart" and not smart_query:
        raise ValueError("search.smart_query es obligatorio cuando search.mode es smart")

    unknown_people = [name for name in default_people if name not in persons]
    if unknown_people:
        unknown_list = ", ".join(unknown_people)
        raise ValueError(f"Personas por defecto no definidas en [persons]: {unknown_list}")

    return FileConfig(
        immich_url=_require_str(immich, "url", "immich.url"),
        api_key=_require_str(immich, "api_key", "immich.api_key"),
        pics_dir=Path(_require_str(display, "pics_dir", "display.pics_dir")).expanduser(),
        screen_width=_require_int(display, "screen_width", "display.screen_width", DEFAULT_SCREEN_WIDTH),
        screen_height=_require_int(display, "screen_height", "display.screen_height", DEFAULT_SCREEN_HEIGHT),
        display_time=_require_int(display, "seconds", "display.seconds", DEFAULT_DISPLAY_TIME),
        display_backend=_require_str(
            display,
            "backend",
            "display.backend",
            DEFAULT_DISPLAY_BACKEND,
        ),
        grayscale=_require_bool(
            display,
            "grayscale",
            "display.grayscale",
            False,
        ),
        show_year_overlay=_require_bool(
            display,
            "show_year_overlay",
            "display.show_year_overlay",
            True,
        ),
        show_info_overlay=_require_bool(
            display,
            "show_info_overlay",
            "display.show_info_overlay",
            True,
        ),
        overlay_layout=_require_choice(
            display,
            "overlay_layout",
            "display.overlay_layout",
            {"split", "mirrored", "right"},
            "split",
        ),
        year_overlay_font_size=_optional_positive_int(
            display,
            "year_overlay_font_size",
            "display.year_overlay_font_size",
        ),
        info_overlay_font_size=_optional_positive_int(
            display,
            "info_overlay_font_size",
            "display.info_overlay_font_size",
        ),
        year_overlay_x=_optional_non_negative_int(
            display,
            "year_overlay_x",
            "display.year_overlay_x",
        ),
        year_overlay_y=_optional_non_negative_int(
            display,
            "year_overlay_y",
            "display.year_overlay_y",
        ),
        info_overlay_x=_optional_non_negative_int(
            display,
            "info_overlay_x",
            "display.info_overlay_x",
        ),
        info_overlay_y=_optional_non_negative_int(
            display,
            "info_overlay_y",
            "display.info_overlay_y",
        ),
        transition_ms=_require_int(
            display,
            "transition_ms",
            "display.transition_ms",
            DEFAULT_TRANSITION_MS,
        ),
        search_size=_require_int(search, "search_size", "search.search_size", DEFAULT_SEARCH_SIZE),
        seen_buffer_size=_require_int(
            search,
            "seen_buffer_size",
            "search.seen_buffer_size",
            DEFAULT_SEEN_BUFFER_SIZE,
        ),
        search_mode=search_mode,
        smart_query=smart_query,
        smart_city=_optional_str(search, "smart_city", "search.smart_city"),
        default_people=default_people,
        persons={name: _ensure_str(value, f"persons.{name}") for name, value in persons.items()},
    )


def _get_table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Falta la seccion [{key}] en el archivo de configuracion")
    return value


def _require_str(
    data: dict[str, object],
    key: str,
    label: str,
    default: str | None = None,
) -> str:
    value = data.get(key, default)
    return _ensure_str(value, label)


def _optional_str(data: dict[str, object], key: str, label: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    return _ensure_str(value, label)


def _require_int(
    data: dict[str, object],
    key: str,
    label: str,
    default: int,
) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} debe ser un numero entero")
    return value


def _require_bool(
    data: dict[str, object],
    key: str,
    label: str,
    default: bool,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{label} debe ser true o false")
    return value


def _require_choice(
    data: dict[str, object],
    key: str,
    label: str,
    choices: set[str],
    default: str,
) -> str:
    value = _require_str(data, key, label, default)
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{label} debe ser uno de: {options}")
    return value


def _optional_positive_int(
    data: dict[str, object],
    key: str,
    label: str,
) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} debe ser un numero entero positivo")
    return value


def _optional_non_negative_int(
    data: dict[str, object],
    key: str,
    label: str,
) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} debe ser un numero entero mayor o igual a 0")
    return value


def _ensure_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} debe ser un texto no vacio")
    return value.strip()
