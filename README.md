# HoloDisplay

Slideshow para mostrar fotos de [Immich](https://immich.app/) en una pantalla, pensado especialmente para una Raspberry Pi o un display dedicado.

El proyecto puede:

- mostrar fotos por persona
- hacer smart search
- mostrar memorias de `on_this_day`
- mostrar fotos random
- pintar overlays con año, personas y ubicacion
- recargar `config.toml` automaticamente sin reiniciar el servicio

## Requisitos

- Python 3.11 o superior
- acceso a una instancia de Immich
- API key de Immich

Dependencias de Python:

- `requests`
- `Pillow`
- `pygame` si vas a usar el backend `pygame`

Dependencias del sistema:

- `fbi` si vas a usar el backend `framebuffer`

## Bajar el proyecto

```bash
git clone git@github.com:jugler/holodisplay.git
cd HoloDisplay
```


## Instalacion

### Opcion simple con `pip`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install requests pillow pygame
```

Si no vas a usar `pygame`, puedes omitirlo:

```bash
pip install requests pillow
```

### Dependencia extra para `framebuffer`

En Raspberry Pi o Linux con framebuffer:

```bash
sudo apt update
sudo apt install fbi
```

## Configuracion

La configuracion real se lee desde `config.toml`, pero ese archivo no debe subirse a git.

Primero crea tu copia local a partir de la plantilla:

```bash
cp config.example.toml config.toml
```

Despues edita `config.toml` con tu URL y tu API key de Immich.

Archivos:

- [`config.example.toml`](/Users/jugler/code/HoloDisplay/config.example.toml): plantilla versionada sin secretos
- `config.toml`: archivo local real, ignorado por git

Ejemplo de `config.toml`:

```toml
[immich]
url = "http://192.168.2.10:2283/api"
api_key = "TU_API_KEY"

[display]
pics_dir = "/home/pi/HoloDisplay/pics"
screen_width = 1920
screen_height = 1080
backend = "pygame"
seconds = 15
show_person_overlay = true
# overlay_layout:
# split = nombres arriba izquierda + ano abajo derecha
# mirrored = nombres arriba derecha + ano abajo izquierda
# right = alias legacy de mirrored
overlay_layout = "split"
transition_ms = 700

[search]
# modes soportados: person, smart, memories, random
mode = "random"
# si mode = "smart", descomenta y ajusta esta linea:
# smart_query = "beach"
default_people = ["Jesus"]
search_size = 1000
seen_buffer_size = 100

[persons]
Jesus = "PERSON_ID_DE_IMMICH"
```

### Campos importantes

`[immich]`

- `url`: URL base del API de Immich. Normalmente termina en `/api`
- `api_key`: API key del usuario

`[display]`

- `pics_dir`: carpeta temporal donde se escriben los JPG que luego se muestran
- `backend`: `pygame` o `framebuffer`
- `seconds`: duracion de cada foto
- `show_person_overlay`: activa overlays para `person` y `random`
- `overlay_layout`: distribucion de overlays
- `transition_ms`: duracion de transicion en `pygame`

`[search]`

- `mode`: `person`, `smart`, `memories` o `random`
- `smart_query`: obligatorio si `mode = "smart"`
- `default_people`: personas por defecto para `person`
- `search_size`: cantidad de resultados por lote
- `seen_buffer_size`: buffer para evitar repetidos en ciertos modos

`[persons]`

- mapa de nombre visible a `personId` de Immich

## Como correrlo

### Usando la configuracion por defecto

```bash
python3 HoloDisplay.py
```

### Usando otro archivo de configuracion

```bash
python3 HoloDisplay.py --config /ruta/a/config.toml
```

## Modos

### `person`

Muestra fotos de una o varias personas configuradas en `[persons]`.

Por config:

```toml
[search]
mode = "person"
default_people = ["Jesus", "Vero"]
```

Por CLI:

```bash
python3 HoloDisplay.py --person Jesus --person Vero
```

### `smart`

Hace smart search textual en Immich.

Por config:

```toml
[search]
mode = "smart"
smart_query = "beach"
```

Por CLI:

```bash
python3 HoloDisplay.py --smart "beach"
```

### `memories`

Consulta `GET /memories` con `type=on_this_day` y la fecha de hoy.

- ordena las fotos de mas nuevas a mas viejas
- hace loop sobre la lista
- permite fotos verticales
- puede mostrar ano y ubicacion

Por config:

```toml
[search]
mode = "memories"
```

Por CLI:

```bash
python3 HoloDisplay.py --memories
```

### `random`

Pide fotos random de toda la libreria.

Por config:

```toml
[search]
mode = "random"
```

Por CLI:

```bash
python3 HoloDisplay.py --random
```

## Overlays

### En `memories`

- ano de la foto
- ubicacion, si el asset la tiene

### En `person` y `random`

- ano de la foto
- personas detectadas
- ubicacion

Si `show_person_overlay = false`, esos overlays se apagan en `person` y `random`.

## Hot reload de configuracion

El proyecto relee `config.toml` automaticamente entre fotos.

Eso significa que puedes cambiar:

- modo
- personas
- `smart_query`
- `seconds`
- overlays
- layout
- backend

y el cambio se aplicara en la siguiente imagen, sin reiniciar el proceso.

## Backends de display

### `pygame`

Recomendado si quieres transiciones suaves.

```toml
[display]
backend = "pygame"
transition_ms = 700
```

Si hace falta, puedes controlar el driver SDL con la variable:

```bash
export IMMICH_SDL_DRIVER=kmsdrm
```

o por ejemplo:

```bash
export IMMICH_SDL_DRIVER=fbcon,x11
```

### `framebuffer`

Usa `fbi` para escribir la imagen al framebuffer.

```toml
[display]
backend = "framebuffer"
```

## Deploy rapido

El repo incluye un script de deploy:

```bash
./deploy.sh
```

Actualmente copia:

- `HoloDisplay.py`
- `config.toml`
- carpeta `holo_display`

El destino por defecto esta definido en [`deploy.sh`](/Users/jugler/code/HoloDisplay/deploy.sh).

## Notas

- `config.toml` contiene datos sensibles como la API key y ahora esta ignorado por git.
- En `memories`, la ubicacion puede requerir una consulta extra por asset porque la respuesta de `/memories` puede venir resumida.
- Los videos no estan soportados como parte del flujo visual actual.

## Ejemplos rapidos

Modo por persona:

```bash
python3 HoloDisplay.py --person Jesus
```

Modo smart:

```bash
python3 HoloDisplay.py --smart "beach"
```

Modo memories:

```bash
python3 HoloDisplay.py --memories
```

Modo random:

```bash
python3 HoloDisplay.py --random
```
