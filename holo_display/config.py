from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomllib

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080
DEFAULT_DISPLAY_TIME = 3
DEFAULT_SEARCH_SIZE = 1000
DEFAULT_SEEN_BUFFER_SIZE = 100
DEFAULT_DISPLAY_BACKEND = "framebuffer"
DEFAULT_TRANSITION_MS = 700
DEFAULT_ROTATION_DEGREES = 0
DEFAULT_BRIGHTNESS = 1.0
DEFAULT_PEOPLE_FILENAME = "people.toml"
ROTATION_DEGREES_CHOICES = {0, 90, 180, 270}
ORIENTATION_CHOICES = {"landscape", "portrait", "any"}
Orientation = Literal["landscape", "portrait", "any"]


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
    brightness: float
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
    aliases: dict[str, tuple[str, ...]]
    orientation: Orientation
    rotation_degrees: int
    art_api_key: str | None
    default_art_mode: bool


@dataclass(frozen=True)
class AppConfig:
    immich_url: str
    api_key: str
    display_time: int
    display_backend: str
    grayscale: bool
    brightness: float
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
    orientation: Orientation = "landscape"
    rotation_degrees: int = DEFAULT_ROTATION_DEGREES
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
    use_art_api_key: bool = False

    @property
    def logical_width(self) -> int:
        if self.orientation == "portrait":
            return self.screen_height
        return self.screen_width

    @property
    def logical_height(self) -> int:
        if self.orientation == "portrait":
            return self.screen_width
        return self.screen_height

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


def load_file_config(path: str | Path = DEFAULT_CONFIG_PATH, people_path: str | Path | None = None) -> FileConfig:
    config_path = Path(path).expanduser()
    resolved_people_path = _resolve_people_path(config_path, people_path)
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontro el archivo de configuracion: {config_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"El archivo de configuracion no es TOML valido: {config_path}: {error}") from error

    immich = _get_table(raw, "immich")
    display = _get_table(raw, "display")
    search = _get_table(raw, "search")
    persons, aliases = _load_people(resolved_people_path)
    art = raw.get("art", {})
    if art is None:
        art_api_key = None
    else:
        if not isinstance(art, dict):
            raise ValueError("La seccion [art] debe ser un objeto")
        art_api_key = _optional_str(art, "api_key", "art.api_key")

    default_people_value = search.get("default_people", ("Jesus",))
    if not isinstance(default_people_value, list | tuple):
        raise ValueError("search.default_people debe ser una lista de nombres")
    default_people = tuple(_ensure_str(name, "search.default_people[]") for name in default_people_value)
    if not default_people:
        raise ValueError("search.default_people no puede estar vacio")

    raw_search_mode = _require_str(search, "mode", "search.mode", "person")
    if raw_search_mode not in {"person", "smart", "memories", "random", "art"}:
        raise ValueError("search.mode debe ser person, smart, memories, random o art")

    default_art_mode = raw_search_mode == "art"
    search_mode = "random" if default_art_mode else raw_search_mode

    smart_query = _optional_str(search, "smart_query", "search.smart_query")
    if search_mode == "smart" and not smart_query:
        raise ValueError("search.smart_query es obligatorio cuando search.mode es smart")

    try:
        _ = _expand_people(default_people, persons, aliases)
    except ValueError as error:
        raise ValueError(f"En default_people: {error}") from error

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
        brightness=_require_positive_number(
            display,
            "brightness",
            "display.brightness",
            DEFAULT_BRIGHTNESS,
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
        orientation=_require_choice(
            display,
            "orientation",
            "display.orientation",
            ORIENTATION_CHOICES,
            "landscape",
        ),
        rotation_degrees=_require_rotation_degrees(
            display,
            "rotation_degrees",
            "display.rotation_degrees",
            DEFAULT_ROTATION_DEGREES,
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
        persons=persons,
        aliases=aliases,
        art_api_key=art_api_key,
        default_art_mode=default_art_mode,
    )


def _resolve_people_path(config_path: Path, people_path: str | Path | None) -> Path:
    if people_path is not None:
        return Path(people_path).expanduser()
    return config_path.with_name(DEFAULT_PEOPLE_FILENAME)


def _load_people(path: Path) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"No se encontro el archivo de personas: {path}. Genera uno con export_people.py"
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"El archivo de personas no es TOML valido: {path}: {error}") from error

    if not isinstance(raw, dict):
        raise ValueError(f"El archivo de personas debe contener un mapa simple de nombre a id: {path}")

    aliases_raw = raw.pop("aliases", None)

    people: dict[str, str] = {}
    for name, value in raw.items():
        person_name = _ensure_str(name, "person name")
        if person_name == "aliases":
            raise ValueError("aliases es una clave reservada en people.toml")
        person_id = _ensure_str(value, f"persons.{person_name}")
        people[person_name] = person_id

    if not people:
        raise ValueError(f"El archivo de personas esta vacio: {path}")

    aliases: dict[str, tuple[str, ...]] = {}
    if aliases_raw is not None:
        if not isinstance(aliases_raw, dict):
            raise ValueError("aliases debe ser un objeto con listas de nombres")
        for alias, names in aliases_raw.items():
            alias_name = _ensure_str(alias, "alias name")
            if alias_name in people:
                raise ValueError(f"El alias {alias_name} choca con una persona existente")
            if not isinstance(names, list | tuple):
                raise ValueError(f"aliases.{alias_name} debe ser una lista de nombres")
            aliases[alias_name] = tuple(_ensure_str(n, f"aliases.{alias_name}[]") for n in names)

    return people, aliases


def _expand_people(
    names: tuple[str, ...],
    persons: dict[str, str],
    aliases: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in persons:
            if name not in seen:
                expanded.append(name)
                seen.add(name)
            continue
        alias_members = aliases.get(name)
        if alias_members is None:
            raise ValueError(f"Persona o alias desconocido: {name}")
        for member in alias_members:
            if member not in persons:
                raise ValueError(f"El alias {name} referencia una persona inexistente: {member}")
            if member not in seen:
                expanded.append(member)
                seen.add(member)
    if not expanded:
        raise ValueError("La lista de personas expandida quedo vacia")
    return tuple(expanded)


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


def _require_positive_number(
    data: dict[str, object],
    key: str,
    label: str,
    default: float,
) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ValueError(f"{label} debe ser un numero mayor que 0")
    return float(value)


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


def _require_rotation_degrees(
    data: dict[str, object],
    key: str,
    label: str,
    default: int,
) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} debe ser un multiplo de 90 entre 0 y 270")
    if value not in ROTATION_DEGREES_CHOICES:
        raise ValueError(f"{label} debe ser 0, 90, 180 o 270")
    return value
