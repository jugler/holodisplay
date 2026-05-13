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
- `pygame` (render y transiciones en pantalla)

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
active_user = "main"

[main]
api_key = "TU_API_KEY"
people_conf = "main_people.toml"

[phone]
api_key = "TU_API_KEY_PHONE"
people_conf = "phone_people.toml"

[art]
api_key = "TU_API_KEY_ART"
people_conf = "art_people.toml"

[nsfw]
api_key = "TU_API_KEY_NSFW"
people_conf = "nsfw_people.toml"

[display]
pics_dir = "/home/pi/HoloDisplay/pics"
screen_width = 1920
screen_height = 1080
seconds = 15
overlay_layout = "split"
transition_ms = 700

[search]
mode = "random"
default_people = ["Jesus"]
search_size = 1000
seen_buffer_size = 100
```

Los mapas `nombre = personId` van en archivos bajo la carpeta `people/` (p. ej. `people/main_people.toml`).

### Campos importantes

`[immich]`

- `url`: URL base del API de Immich. Normalmente termina en `/api`
- `active_user`: `main`, `phone`, `art` o `nsfw`. Define la biblioteca/API key/people_conf en uso. Se puede sobreescribir con `--user`.

`[main]`, `[phone]`, `[art]`, `[nsfw]`

- `api_key` y `people_conf` por biblioteca; ver arriba y `config.example.toml`. Cuando `active_user` es `art` o `nsfw` se usan la key y el TOML de esa sección y los overlays de personas se apagan.

`[display]`

- `pics_dir`: carpeta temporal donde se escriben los JPG que luego se muestran
- `seconds`: duracion de cada foto
- `show_person_overlay`: activa overlays para `person` y `random`
- `overlay_layout`: distribucion de overlays
- `brightness`: factor de brillo aplicado despues de componer el fondo. Debe ser mayor que 0 (ej. 0.5 para mas oscuro, 1.0 sin cambio, 2.0 mas brillante). Sin limite maximo definido.
- `transition_ms`: duracion de la transicion entre fotos (milisegundos)
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

- Las personas se cargan desde archivos TOML en la carpeta **`people/`** junto al `config.toml` que uses. En `[main]`, `[phone]`, `[art]` y `[nsfw]` el campo **`people_conf`** es el nombre del archivo (p. ej. `main_people.toml` → `people/main_people.toml`). Una ruta que empiece por `people/` se interpreta relativa al directorio del config.
- Genera o actualiza esos archivos con `python3 export_people.py` (por defecto escribe `people/main_people.toml`) o editálos a mano. Contienen pares `"Nombre" = "personId"`.
- `default_people` en `[search]` debe referenciar nombres existentes en el TOML que corresponda al modo activo o fallará al arrancar.
- Puedes definir grupos en `[aliases]` dentro de ese TOML, por ejemplo:

```toml
[aliases]
Amigos = ["Clarisa", "Paola", "Sara"]
Familia = ["Jesus", "Vero"]
```

Los aliases sirven tanto en `default_people` como en `--person`.

## Exportar personas

Para evitar buscar manualmente los IDs de cada persona, se agregó `export_people.py` en la raíz del repo.
Con un `config.toml` válido basta ejecutar:

```bash
python3 export_people.py
```

Eso consulta `GET /people`, incluyendo toda la paginación, y por defecto escribe `people/main_people.toml` con líneas como:

```toml
"Jesus" = "4b2d2c50..."
"Vero" = "a9f7b3..."
```

Opciones relevantes:

1. `--config` / `-c` apunta a otro archivo de configuración antes de llamar a la API.
2. `--output` / `-o` cambia la ruta del archivo (por defecto `people/main_people.toml`).
3. `--include-hidden` incluye personas ocultas (`withHidden=true`).
4. `--immich-url` / `--api-key` permiten usar credenciales distintas.

Usa ese TOML como referencia para tus scripts o copia pares `nombre = id` entre archivos en `people/`.

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

Muestra fotos de una o varias personas configuradas en `[search].default_people` (los IDs vienen del TOML de personas activo, p. ej. `people/main_people.toml`).

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

Puedes usar aliases definidos en el TOML de personas (se aceptan en `default_people` y en `--person`). Si pasas varias personas o aliases, se combinan con OR: basta que cualquier persona aparezca en la foto.

Si Immich devuelve `birthDate` en cada persona del asset, el overlay muestra la edad calculada al momento de la foto: `Vero (34)` y, si es menor a 1 año, en meses: `Bebé (11 meses)`.

Si agregas varias personas, el cliente consulta Immich una vez por cada `personId` y une los resultados (OR). No requiere que aparezcan juntas en la misma foto.

### `smart`

Hace smart search textual en Immich.
Immich devuelve los resultados ordenados por relevancia al query, y el proyecto preserva ese orden (no hace random/shuffle en este modo).

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

### Bibliotecas `art` y `nsfw`

Las bibliotecas `art` y `nsfw` ya no son modos: son valores de `immich.active_user`. Cuando una de ellas está activa se usa la `api_key` y `people_conf` de esa sección y los overlays de personas se desactivan automáticamente.

Por config:

```toml
[immich]
active_user = "art"
```

Por CLI:

```bash
python3 HoloDisplay.py --user art
```

Una vez seleccionada la biblioteca puedes combinarla con cualquier `search.mode` válido (`person`, `smart`, `memories`, `random`).

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

y el cambio se aplicara en la siguiente imagen, sin reiniciar el proceso.

## Display (pygame)

La salida usa pygame (SDL). Ajusta `transition_ms` en `[display]` para la duracion del fundido entre fotos.

Si hace falta, puedes controlar el driver SDL con la variable:

```bash
export IMMICH_SDL_DRIVER=kmsdrm
```

o por ejemplo:

```bash
export IMMICH_SDL_DRIVER=fbcon,x11
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
- `HoloConfigServer.py`
- carpeta `assets`

El destino por defecto esta definido en [`deploy.sh`](/Users/jugler/code/HoloDisplay/deploy.sh).

## Interfaz web de configuración

`HoloConfigServer.py` expone una página responsiva en `http://<tu-pi>:8080` que permite ajustar `config.toml`, cambiar el modo, seleccionar aliases/personas según los TOML en `people/` y forzar la siguiente foto con `[immediate_actions].next`. Es ideal para acceder desde un celular antes de convertirlo en un shortcut/app.

Para ejecutarlo basta con:

```bash
python HoloConfigServer.py
```

La interfaz refresca los valores del archivo y escribe cambios inmediatamente para que el proceso principal los lea sin reiniciar.

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
