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
- `brightness`: factor de brillo aplicado despues de componer el fondo. Debe ser mayor que 0 (ej. 0.5 para mas oscuro, 1.0 sin cambio, 2.0 mas brillante). Sin limite maximo definido.
- `transition_ms`: duracion de transicion en `pygame`
- `orientation`: `landscape` (por defecto), `portrait` o `any` para filtrar fotos verticales o horizontales.
- `rotation_degrees`: entero entre 0, 90, 180 y 270; si `orientation = "portrait"` el render rotado antes de enviarlo al display físico.
- El overlay de ubicación divide ciudad y país en líneas separadas (acortando `United States of America` a `USA`) solo cuando el modo no es `landscape`; en `landscape` se mantiene como una sola línea tipo `Berlin, Germany`.
- cuando `orientation = "portrait"`, el render se arma como si el área fuera 90º rotada y el resultado final se gira 270º antes de enviarlo al display para que los overlays sigan alineados con la pantalla físicamente rotada.

`[search]`

- `mode`: `person`, `smart`, `memories`, `random` o `art`
- `smart_query`: obligatorio si `mode = "smart"`
- `default_people`: personas por defecto para `person`
- `search_size`: cantidad de resultados por lote
- `seen_buffer_size`: buffer para evitar repetidos en ciertos modos

Personas

- Las personas ya no viven en `[persons]` del `config.toml`. Ahora se leen desde un archivo `people.toml` ubicado junto al config que uses (por ejemplo `config.toml` → `people.toml`, `config.holothot.toml` → `people.toml`).
- Genera ese archivo con `python3 export_people.py` o mantenlo a mano. Contiene pares `"Nombre" = "personId"`.
- `default_people` en `[search]` debe referenciar nombres existentes en ese `people.toml` o fallará al arrancar.
- Puedes definir grupos en `[aliases]` dentro de `people.toml`, por ejemplo:

```toml
[aliases]
Amigos = ["Clarisa", "Paola", "Sara"]
Familia = ["Jesus", "Vero"]
```

Los aliases sirven tanto en `default_people` como en `--person`.

`[art]`

- `api_key`: API key del usuario art; se usa cuando `search.mode = "art"` o `--art`. En ese modo los overlays se apagan automáticamente.

## Exportar personas

Para evitar buscar manualmente los IDs de cada persona, se agregó `export_people.py` en la raíz del repo.
Con un `config.toml` válido basta ejecutar:

```bash
python3 export_people.py
```

Eso consulta `GET /people`, incluyendo toda la paginación, y genera `people.toml` con líneas como:

```toml
"Jesus" = "4b2d2c50..."
"Vero" = "a9f7b3..."
```

Opciones relevantes:

1. `--config` / `-c` apunta a otro archivo de configuración antes de llamar a la API.
2. `--output` / `-o` cambia la ruta del `people.toml`.
3. `--include-hidden` incluye personas ocultas (`withHidden=true`).
4. `--immich-url` / `--api-key` permiten usar credenciales distintas.

Usa ese `people.toml` para copiar los pares `nombre = id` dentro de `[persons]` o para tus scripts.

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

Muestra fotos de una o varias personas configuradas en `[search].default_people` (los IDs vienen de `people.toml`).

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

Puedes usar aliases definidos en `people.toml` (se aceptan en `default_people` y en `--person`). Si pasas varias personas o aliases, se combinan con OR: basta que cualquier persona aparezca en la foto.

Si Immich devuelve `birthDate` en cada persona del asset, el overlay muestra la edad calculada al momento de la foto: `Vero (34)` y, si es menor a 1 año, en meses: `Bebé (11 meses)`.

Si agregas varias personas, el cliente consulta Immich una vez por cada `personId` y une los resultados (OR). No requiere que aparezcan juntas en la misma foto.

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

### `art`

Usa el nuevo usuario “art” con su propia API key en el mismo servidor. El modo se comporta como un `random` específico para ese usuario.

Por config:

```toml
[search]
mode = "art"
```

Por CLI:

```bash
python3 HoloDisplay.py --art
```

En modo `art` los overlays se desactivan automáticamente aunque estén habilitados en la configuración, de modo que las imágenes se muestran sin texto adicional.

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
- Para centrar un marco puedes usar `./center_guide.py` (requiere `pygame`). Se dibujará un cruzado y bordes horizontales/verticales que coinciden con las dimensiones de `config.toml`.
## Guía de alineación

Si necesitas centrar la pantalla dentro de un marco físico, ejecuta `./center_guide.py`. El script abre una ventana con una cuadrícula de líneas y bordes que coinciden con `screen_width` / `screen_height` de `config.toml`. Ajusta color (`--color R,G,B`), fondo (`--background R,G,B`), grosor (`--thickness`), y separación de la cuadrícula (`--grid-spacing`). Pulsa `Esc` o `q` para salir.

```bash
pip install pygame
python3 center_guide.py --config config.holodisplay.toml --color 255,0,0 --thickness 3
```

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
