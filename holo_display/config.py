from __future__ import annotations

import argparse
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
DEFAULT_SMART_RESULT_LIMIT = 100
DEFAULT_TRANSITION_MS = 700
DEFAULT_ROTATION_DEGREES = 0
DEFAULT_BRIGHTNESS = 1.0
DEFAULT_PEOPLE_FILENAME = "people.toml"
PEOPLE_SUBDIR = "people"
BROWSE_USER_CHOICES = frozenset({"main", "phone", "art", "nsfw"})
SEARCH_MODE_CHOICES = frozenset({"person", "smart", "memories", "random"})
ROTATION_DEGREES_CHOICES = {0, 90, 180, 270}
ORIENTATION_CHOICES = {"landscape", "portrait", "any"}
Orientation = Literal["landscape", "portrait", "any"]
CLOCK_OVERLAY_POSITION_CHOICES = frozenset({"bottom_left", "bottom_right", "top_left", "top_right"})
CLOCK_OVERLAY_SPACE_CHOICES = frozenset({"logical", "frame", "screen"})
DEFAULT_CLOCK_OVERLAY_FONT_SIZE = 48
DEFAULT_CLOCK_OVERLAY_MARGIN = 24


@dataclass(frozen=True)
class ImmichUserBlock:
    api_key: str | None
    people_path: Path


@dataclass(frozen=True)
class FileConfig:
    immich_url: str
    active_user: str
    main: ImmichUserBlock
    phone: ImmichUserBlock
    art: ImmichUserBlock
    nsfw: ImmichUserBlock
    pics_dir: Path
    screen_width: int
    screen_height: int
    display_time: int
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
    show_clock_overlay: bool
    clock_overlay_position: str
    clock_overlay_font_size: int
    clock_overlay_margin: int
    clock_overlay_space: str
    clock_overlay_show_background: bool
    clock_overlay_x: int | None
    clock_overlay_y: int | None
    transition_ms: int
    search_size: int
    seen_buffer_size: int
    search_mode: str
    smart_query: str | None
    smart_city: str | None
    smart_result_limit: int
    default_people: tuple[str, ...]
    persons: dict[str, str]
    aliases: dict[str, tuple[str, ...]]
    people_source_path: Path
    orientation: Orientation
    rotation_degrees: int
    immediate_next: bool


def resolve_people_conf_path(config_path: Path, value: str) -> Path:
    """Rutas declaradas en people_conf: relativas al directorio del config; solo nombre de archivo -> subcarpeta people/."""
    raw = Path(value.strip()).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    normalized = raw.as_posix().replace("\\", "/").lstrip("./")
    if normalized.startswith("people/") or normalized == "people":
        return (config_path.parent / raw).resolve()
    return (config_path.parent / PEOPLE_SUBDIR / raw).resolve()


def _normalize_active_user(active_user: str) -> Literal["main", "phone", "art", "nsfw"]:
    if active_user not in BROWSE_USER_CHOICES:
        raise ValueError(
            f"active_user debe ser uno de: {', '.join(sorted(BROWSE_USER_CHOICES))}"
        )
    return active_user  # type: ignore[return-value]


def effective_immich_block(
    file_config: FileConfig,
    *,
    active_user: str,
) -> ImmichUserBlock:
    key = _normalize_active_user(active_user)
    if key == "main":
        return file_config.main
    if key == "phone":
        return file_config.phone
    if key == "art":
        return file_config.art
    return file_config.nsfw


def effective_api_key(
    file_config: FileConfig,
    *,
    active_user: str,
) -> str:
    block = effective_immich_block(file_config, active_user=active_user)
    if not block.api_key or not block.api_key.strip():
        raise ValueError(
            f"Falta api_key en la seccion [{active_user}] para la biblioteca activa"
        )
    return block.api_key.strip()


def load_file_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    people_path: str | Path | None = None,
    argv: list[str] | None = None,
    *,
    resolve_people_context: str | None = None,
) -> FileConfig:
    config_path = Path(path).expanduser()
    argv = list(argv if argv is not None else [])
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontro el archivo de configuracion: {config_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"El archivo de configuracion no es TOML valido: {config_path}: {error}") from error

    immich = _get_table(raw, "immich")
    display = _get_table(raw, "display")
    search = _get_table(raw, "search")

    file_active_user = _require_str(immich, "active_user", "immich.active_user", "main")
    if file_active_user not in BROWSE_USER_CHOICES:
        raise ValueError(
            f"immich.active_user debe ser uno de: {', '.join(sorted(BROWSE_USER_CHOICES))}"
        )

    main_block, phone_block, art_block, nsfw_block = _parse_immich_user_blocks(
        raw,
        config_path,
        immich,
        people_path_override=people_path,
    )

    raw_search_mode = _require_str(search, "mode", "search.mode", "person")
    if raw_search_mode in {"art", "nsfw"}:
        raise ValueError(
            "search.mode ya no acepta 'art' ni 'nsfw'. Mueve esa eleccion a "
            "immich.active_user y deja search.mode en person/smart/memories/random."
        )
    if raw_search_mode not in SEARCH_MODE_CHOICES:
        raise ValueError(
            f"search.mode debe ser uno de: {', '.join(sorted(SEARCH_MODE_CHOICES))}"
        )
    search_mode = raw_search_mode

    if resolve_people_context is not None:
        if resolve_people_context not in BROWSE_USER_CHOICES:
            raise ValueError(
                "resolve_people_context: active_user debe ser uno de "
                f"{', '.join(sorted(BROWSE_USER_CHOICES))}"
            )
        peek_active = resolve_people_context
    else:
        peek_active = _peek_active_user(argv, file_active_user)
    if peek_active not in BROWSE_USER_CHOICES:
        raise ValueError(
            f"active_user (--user) debe ser uno de: {', '.join(sorted(BROWSE_USER_CHOICES))}"
        )

    people_source = _people_path_for_context(
        main_block,
        phone_block,
        art_block,
        nsfw_block,
        browse_context=peek_active,  # type: ignore[arg-type]
    )
    persons, aliases = _load_people(people_source)

    default_people_value = search.get("default_people", ("Jesus",))
    if not isinstance(default_people_value, list | tuple):
        raise ValueError("search.default_people debe ser una lista de nombres")
    default_people = tuple(_ensure_str(name, "search.default_people[]") for name in default_people_value)
    if not default_people:
        raise ValueError("search.default_people no puede estar vacio")

    smart_query = _optional_str(search, "smart_query", "search.smart_query")
    if search_mode == "smart" and not smart_query:
        raise ValueError("search.smart_query es obligatorio cuando search.mode es smart")

    if search_mode == "person":
        try:
            _ = _expand_people(default_people, persons, aliases)
        except ValueError as error:
            raise ValueError(
                f"En default_people para la biblioteca activa: {error}"
            ) from error

    active_block = {
        "main": main_block,
        "phone": phone_block,
        "art": art_block,
        "nsfw": nsfw_block,
    }[peek_active]
    if not active_block.api_key:
        raise ValueError(
            f"La biblioteca activa '{peek_active}' no tiene api_key configurada en [{peek_active}]"
        )

    immediate_actions = raw.get("immediate_actions", {})
    immediate_next = False
    if immediate_actions is not None:
        if not isinstance(immediate_actions, dict):
            raise ValueError("La seccion [immediate_actions] debe ser un objeto")
        immediate_next_value = immediate_actions.get("next", 0)
        if isinstance(immediate_next_value, bool) or not isinstance(immediate_next_value, int):
            raise ValueError("immediate_actions.next debe ser 0 o 1")
        immediate_next = bool(immediate_next_value)

    clock_overlay_font_size = _require_int(
        display,
        "clock_overlay_font_size",
        "display.clock_overlay_font_size",
        DEFAULT_CLOCK_OVERLAY_FONT_SIZE,
    )
    if clock_overlay_font_size < 1:
        raise ValueError("display.clock_overlay_font_size debe ser un entero mayor o igual a 1")
    clock_overlay_margin = _require_int(
        display,
        "clock_overlay_margin",
        "display.clock_overlay_margin",
        DEFAULT_CLOCK_OVERLAY_MARGIN,
    )
    if clock_overlay_margin < 0:
        raise ValueError("display.clock_overlay_margin debe ser un entero mayor o igual a 0")

    clock_overlay_x = _optional_non_negative_int(display, "clock_overlay_x", "display.clock_overlay_x")
    clock_overlay_y = _optional_non_negative_int(display, "clock_overlay_y", "display.clock_overlay_y")
    if (clock_overlay_x is None) != (clock_overlay_y is None):
        raise ValueError(
            "display.clock_overlay_x y clock_overlay_y deben definirse los dos o omitirse los dos"
        )

    return FileConfig(
        immich_url=_require_str(immich, "url", "immich.url"),
        active_user=file_active_user,
        main=main_block,
        phone=phone_block,
        art=art_block,
        nsfw=nsfw_block,
        pics_dir=Path(_require_str(display, "pics_dir", "display.pics_dir")).expanduser(),
        screen_width=_require_int(display, "screen_width", "display.screen_width", DEFAULT_SCREEN_WIDTH),
        screen_height=_require_int(display, "screen_height", "display.screen_height", DEFAULT_SCREEN_HEIGHT),
        display_time=_require_int(display, "seconds", "display.seconds", DEFAULT_DISPLAY_TIME),
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
        show_clock_overlay=_require_bool(
            display,
            "show_clock_overlay",
            "display.show_clock_overlay",
            False,
        ),
        clock_overlay_position=_require_choice(
            display,
            "clock_overlay_position",
            "display.clock_overlay_position",
            CLOCK_OVERLAY_POSITION_CHOICES,
            "bottom_left",
        ),
        clock_overlay_font_size=clock_overlay_font_size,
        clock_overlay_margin=clock_overlay_margin,
        clock_overlay_space=_require_choice(
            display,
            "clock_overlay_space",
            "display.clock_overlay_space",
            CLOCK_OVERLAY_SPACE_CHOICES,
            "frame",
        ),
        clock_overlay_show_background=_require_bool(
            display,
            "clock_overlay_show_background",
            "display.clock_overlay_show_background",
            True,
        ),
        clock_overlay_x=clock_overlay_x,
        clock_overlay_y=clock_overlay_y,
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
        smart_result_limit=_optional_non_negative_int(
            search,
            "smart_result_limit",
            "search.smart_result_limit",
        )
        or DEFAULT_SMART_RESULT_LIMIT,
        search_mode=search_mode,
        smart_query=smart_query,
        smart_city=_optional_str(search, "smart_city", "search.smart_city"),
        default_people=default_people,
        persons=persons,
        aliases=aliases,
        people_source_path=people_source,
        immediate_next=immediate_next,
    )


def _people_path_for_context(
    main: ImmichUserBlock,
    phone: ImmichUserBlock,
    art: ImmichUserBlock,
    nsfw: ImmichUserBlock,
    *,
    browse_context: Literal["main", "phone", "art", "nsfw"],
) -> Path:
    if browse_context == "nsfw":
        return nsfw.people_path
    if browse_context == "art":
        return art.people_path
    if browse_context == "phone":
        return phone.people_path
    return main.people_path


def _peek_active_user(argv: list[str], file_default: str) -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--user", "--active-user", dest="browse_user", default=None)
    known, _ = parser.parse_known_args(argv)
    if known.browse_user is not None and str(known.browse_user).strip():
        return _ensure_str(known.browse_user, "--user / --active-user")
    return file_default


def _parse_immich_user_blocks(
    raw: dict[str, object],
    config_path: Path,
    immich: dict[str, object],
    *,
    people_path_override: str | Path | None,
) -> tuple[ImmichUserBlock, ImmichUserBlock, ImmichUserBlock, ImmichUserBlock]:
    main_raw = raw.get("main")
    legacy_key = _optional_str(immich, "api_key", "immich.api_key")

    if isinstance(main_raw, dict) and _optional_str(main_raw, "api_key", "[main].api_key"):
        main_people_conf = _require_str(main_raw, "people_conf", "[main].people_conf")
        main = ImmichUserBlock(
            api_key=_require_str(main_raw, "api_key", "[main].api_key"),
            people_path=resolve_people_conf_path(config_path, main_people_conf),
        )
    elif legacy_key:
        if people_path_override is not None:
            legacy_raw = Path(people_path_override).expanduser()
            legacy_people = (
                legacy_raw.resolve()
                if legacy_raw.is_absolute()
                else resolve_people_conf_path(config_path, str(people_path_override))
            )
        else:
            legacy_people = (config_path.parent / PEOPLE_SUBDIR / DEFAULT_PEOPLE_FILENAME).resolve()
        main = ImmichUserBlock(api_key=legacy_key.strip(), people_path=legacy_people)
    else:
        raise ValueError(
            "Define [main] con api_key y people_conf, o bien immich.api_key (legacy) y "
            f"{PEOPLE_SUBDIR}/{DEFAULT_PEOPLE_FILENAME} junto al config"
        )

    phone_raw = raw.get("phone")
    if isinstance(phone_raw, dict) and _optional_str(phone_raw, "api_key", "[phone].api_key"):
        phone_people_conf = _require_str(phone_raw, "people_conf", "[phone].people_conf")
        phone = ImmichUserBlock(
            api_key=_require_str(phone_raw, "api_key", "[phone].api_key"),
            people_path=resolve_people_conf_path(config_path, phone_people_conf),
        )
    else:
        phone = ImmichUserBlock(api_key=None, people_path=main.people_path)

    art_raw = raw.get("art")
    if art_raw is None:
        art_raw = {}
    if not isinstance(art_raw, dict):
        raise ValueError("La seccion [art] debe ser un objeto")
    art_people_conf_s = _optional_str(art_raw, "people_conf", "[art].people_conf")
    art_people_path = (
        resolve_people_conf_path(config_path, art_people_conf_s)
        if art_people_conf_s
        else main.people_path
    )
    art = ImmichUserBlock(
        api_key=_optional_str(art_raw, "api_key", "[art].api_key"),
        people_path=art_people_path,
    )

    nsfw_raw = raw.get("nsfw")
    if nsfw_raw is None:
        nsfw_raw = {}
    if not isinstance(nsfw_raw, dict):
        raise ValueError("La seccion [nsfw] debe ser un objeto")
    nsfw_people_conf_s = _optional_str(nsfw_raw, "people_conf", "[nsfw].people_conf")
    nsfw_people_path = (
        resolve_people_conf_path(config_path, nsfw_people_conf_s)
        if nsfw_people_conf_s
        else main.people_path
    )
    nsfw = ImmichUserBlock(
        api_key=_optional_str(nsfw_raw, "api_key", "[nsfw].api_key"),
        people_path=nsfw_people_path,
    )

    return main, phone, art, nsfw


def credentials_for_people_export(
    config_path: str | Path,
    user: Literal["main", "phone", "art", "nsfw"],
    *,
    people_path_override: str | Path | None = None,
) -> tuple[str, str, Path]:
    """URL base de Immich (sin barra final), API key y ruta resuelta de people_conf para export_people."""
    path = Path(config_path).expanduser()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontro el archivo de configuracion: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"El archivo de configuracion no es TOML valido: {path}: {error}") from error

    immich = _get_table(raw, "immich")
    url = _require_str(immich, "url", "immich.url").rstrip("/")

    main_block, phone_block, art_block, nsfw_block = _parse_immich_user_blocks(
        raw,
        path,
        immich,
        people_path_override=people_path_override,
    )

    if user == "main":
        block = main_block
    elif user == "phone":
        block = phone_block
    elif user == "art":
        block = art_block
    else:
        block = nsfw_block

    if not block.api_key or not block.api_key.strip():
        raise ValueError(
            f"Falta o esta vacia la api_key en la seccion [{user}] "
            "(o la configuracion legacy no define credenciales para ese usuario)"
        )

    return url, block.api_key.strip(), block.people_path


def _load_people(path: Path) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"No se encontro el archivo de personas: {path}. Coloca los *.toml en la carpeta people/ "
            "junto al config o ejecuta export_people.py -o people/main_people.toml"
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


@dataclass(frozen=True)
class AppConfig:
    immich_url: str
    api_key: str
    display_time: int
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
    smart_result_limit: int = DEFAULT_SMART_RESULT_LIMIT
    transition_ms: int = DEFAULT_TRANSITION_MS
    search_size: int = DEFAULT_SEARCH_SIZE
    seen_buffer_size: int = DEFAULT_SEEN_BUFFER_SIZE
    active_user: str = "main"
    people_source_path: Path = DEFAULT_CONFIG_PATH
    immediate_next: bool = False
    show_clock_overlay: bool = False
    clock_overlay_position: str = "bottom_left"
    clock_overlay_font_size: int = DEFAULT_CLOCK_OVERLAY_FONT_SIZE
    clock_overlay_margin: int = DEFAULT_CLOCK_OVERLAY_MARGIN
    clock_overlay_space: str = "frame"
    clock_overlay_show_background: bool = True
    clock_overlay_x: int | None = None
    clock_overlay_y: int | None = None
    config_path: Path = DEFAULT_CONFIG_PATH

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
