# El modelo de Gaphor: definirlo y conectarlo con los datos

Este documento explica cómo cada grupo puede tener **su propio modelo** del
gemelo en Gaphor y que los datos de los sensores aparezcan **dentro de cada
bloque**, sin escribir XML.

## ¿Qué es el archivo `.gaphor`?

Es el archivo donde Gaphor guarda tu modelo. **Es XML** (no HTML) y es un
formato interno: **no se edita a mano**. Se crea/abre con Gaphor o se genera
por código.

## Cómo aparecen los datos en el bloque

Los datos vivos se muestran como **value properties** de SysML, en el
compartimento "values" del bloque:

```
┌───────────────────────────┐
│      «block»              │
│   BME280 (Aula A)         │
├─ values ──────────────────┤
│  Temperatura: °C = 23.4   │
│  Humedad relativa: % = 55 │
│  Presión: hPa = 1013      │
│  Actualizado: hora = 12:00│
└───────────────────────────┘
```

El **bridge crea automáticamente** esas propiedades (una por métrica), les pone
el valor y activa el compartimento. Tú solo tienes que asegurar el **nombre del
bloque** (ver "Contrato de nombres"). La nota del bloque queda para la
descripción estática del sensor.

> Modo configurable: `gaphor.display` en `config.yaml` puede ser `values`
> (por defecto, lo anterior), `note` (todo en la Nota) o `both`.

## Opciones para definir tu modelo (ninguna requiere XML)

| Opción | Cómo | Para quién |
|--------|------|-----------|
| **1. Gaphor (GUI)** | Dibujar el diagrama en la app de Gaphor. Genera el `.gaphor` solo. | Recomendado, **cero código**. |
| **2. `config.yaml` + `init-model`** | Declarar aulas/sensores en YAML y correr `uv run gemelo -c config.yaml init-model`. El código genera el `.gaphor` ya conforme. | El más simple, sin programar. |
| **3. Python (API de Gaphor)** | Un script con `ElementFactory` + `storage.save` que crea bloques/propiedades. Ver `server/gemelo/model_builder.py` como ejemplo. | Grupos que quieran generarlo por código. |
| **4. XML a mano** | Editar el `.gaphor` directo. | **Desaconsejado** (frágil). |

En las cuatro vías, lo único **obligatorio** para que lleguen los datos es que
el **nombre del bloque** coincida con lo que el bridge busca.

## Contrato de nombres (lo único que debes acertar)

El bridge empareja cada `(aula, sensor)` con un bloque **por su nombre**,
calculado desde `config.yaml → naming`.

**Nombre de bloque por defecto** (`template: "{model} ({aula_name})"`):

| Sensor (topic) | Modelo | Bloque esperado (aula-A / aula-B) |
|---|---|---|
| `inmp441`  | INMP441 | `INMP441 (Aula A)` / `INMP441 (Aula B)` |
| `mhz19b`   | MH-Z19B | `MH-Z19B (Aula A)` / `MH-Z19B (Aula B)` |
| `bme280`   | BME280 | `BME280 (Aula A)` / `BME280 (Aula B)` |
| `bh1750`   | BH1750 (GY-302) | `BH1750 (GY-302) (Aula A)` / … |
| `mlx90640` | MLX90640 32x24 | `MLX90640 32x24 (Aula A)` / … |

Si tu diagrama usa otros nombres, tienes dos formas de alinearlo (ver
`docs/GUIA_DE_USO.md`, "Parte C-bis"):
- **`naming.template`** si sigues un patrón (variables `{model}`, `{aula_name}`,
  `{aula_id}`, `{sensor}`).
- **`naming.overrides`** para mapear un `(aula, sensor)` a un nombre exacto.

## Qué value properties crea el bridge por sensor

No necesitas crearlas tú: el bridge las genera. Esta es la lista (nombre →
unidad) que aparecerá dentro de cada bloque:

| Sensor | Value properties (nombre : unidad) |
|--------|-------------------------------------|
| INMP441 | Nivel de presión sonora : dB |
| MH-Z19B | CO2 : ppm |
| BME280 | Temperatura : °C · Humedad relativa : % · Presión : hPa |
| BH1750 | Iluminancia : lux |
| MLX90640 | Temperatura mínima : °C · Temperatura máxima : °C · Temperatura media : °C · Ocupación estimada : personas |
| (todos) | Actualizado : hora (marca de tiempo de la última lectura) |

## Flujo recomendado para un grupo con diagrama propio

1. Dibuja en Gaphor un bloque por sensor (y por aula), nombrándolos según el
   contrato (o ajusta `naming` en `config.yaml`).
2. Apunta `model_path` en `config.yaml` a tu archivo `.gaphor`.
3. Arranca el bridge (`uv run gemelo -c config.yaml run`).
4. El bridge **crea las value properties, las rellena y activa el compartimento**
   automáticamente en cada bloque que encuentre por nombre.

> **Atajo:** `uv run gemelo -c config.yaml init-model` genera un `.gaphor` de
> arranque ya conforme (bloques + value properties), que luego puedes
> reorganizar en Gaphor.

## Nota sobre "en vivo"

Gaphor **no recarga solo** un archivo que cambia por debajo: para ver los
valores nuevos, **reabre el modelo**. Para monitoreo continuo (auto-refresco),
usa el **dashboard web** (`uv run gemelo -c config.yaml dashboard`). Gaphor es
la vista de diseño/estructura; el dashboard, la vista operativa en vivo.
