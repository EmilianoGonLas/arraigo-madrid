# Arraigo residencial en la Comunidad de Madrid

Cuánto hace que vive su gente en cada barrio de Madrid, y cómo cambió entre los
censos de **2001** y **2011**. Incluye la aplicación que lo explora en mapa y el
código que reconstruye los datos desde cero.

![estado](https://img.shields.io/badge/datos-2001%20y%202011%20completos-success)
![licencia](https://img.shields.io/badge/licencia-MIT-blue)

## Qué problema resuelve

El INE publica el año de llegada a la vivienda de cada persona, pero sólo se
puede consultar de a una selección por vez, a mano, en un asistente web de 2011.
Para las 489 unidades territoriales de este estudio son unos 20.000 clics.

Este repositorio automatiza esa consulta, la verifica contra fuentes
independientes y deja los datos listos para analizar.

## La unidad de análisis: VUPACI

Las **VUPACI** son 489 agrupaciones de secciones censales de la provincia de
Madrid. No son una división oficial del INE, así que el dato hay que pedirlo
sección por sección y agregarlo.

El detalle que hace viable la comparación intercensal: **el seccionado cambia
entre censos**. Madrid tenía 3.906 secciones en 2001 y 4.272 en 2011, y en los
municipios que crecieron se renumeraron por completo — Alcalá de Henares pasó de
8 distritos a 5. Un código como `2800504007` existe en los dos censos y no es el
mismo territorio.

Por eso cada censo se agrega con **su propio seccionado** (`datos/originales/Seccionado
VUPACI 2001 y 2011.xlsx`), y nunca se reutiliza un código de un año en el otro.

## El índice de arraigo

Media ponderada de la antigüedad de la población, por posición relativa a la
fecha del censo:

| tramo | 2011 | 2001 | peso |
|---|---|---|---|
| a | 2006-2011 (6 años) | 1996-2001 (6 años) | 0 |
| b | 2001-2005 (5 años) | 1991-1995 (5 años) | 0,33 |
| c | 1991-2000 (10 años) | 1981-1990 (10 años) | 0,66 |
| d | antes de 1991 | antes de 1981 | 1 |

`índice = pa·0 + pb·0,33 + pc·0,66 + pd·1`, donde `pX` es la proporción del tramo
sobre el total. Va de **0** (todos llegaron en los últimos seis años) a **1**
(todos llevan más de veinte).

Resultado: índice medio **0,514 en 2001** y **0,486 en 2011**, con correlación
0,69 entre ambos. La provincia perdió arraigo mientras ganaba 971.475 habitantes.

## La aplicación

```bash
R -e 'shiny::runApp("app")'
```

Mapa de las 489 VUPACI con su geometría real de cada año, selector de censo y de
variable, comparación 2001→2011 y, al hacer clic, la distribución de llegada de
ese barrio en los dos censos.

## Cómo se reconstruye todo

```bash
# 1. datos del INE (lento: el asistente responde a ~5 s por consulta)
python3 scripts/descargar_arraigo.py          # año de llegada por VUPACI, 2011
python3 scripts/verificar_arraigo.py --reparar
python3 scripts/descargar_2001_secciones.py   # censo 2001 por sección
python3 scripts/descargar_2001_madrid.py      # Madrid capital, por distritos
python3 scripts/descargar_panel_2011.py       # 83 variables por VUPACI

# 2. cartografía (170 MB, no versionada)
R/00_descargar_cartografia.sh

# 3. preparar los datos de la app
Rscript R/01_preparar_geometrias.R
Rscript R/02_preparar_datos.R
```

Dependencias: Python con `requests`, `beautifulsoup4`, `lxml`, `pandas`,
`openpyxl`; R con `shiny`, `sf`, `leaflet`, `dplyr`, `ggplot2`, `DT`, `bslib`;
y `ogr2ogr` (GDAL).

## Las trampas del asistente del INE

Documentadas porque costaron encontrarlas y cualquiera que repita esto se las va
a cruzar:

- **Es UTF-8**, pese al aspecto de aplicación de 1999. En latin-1 los municipios
  con ñ no casan y la consulta sale vacía.
- **`idFila` vacío rompe la consulta**: responde *"Fallo en sistema"* en vez de
  la tabla. Hay que omitir el campo, no mandarlo vacío.
- **No se puede paralelizar.** Con dos sesiones simultáneas el servidor devuelve
  la tabla de *otra* consulta en curso, en silencio y con pinta de dato bueno.
  Salieron 11 filas mal de 140 antes de detectarlo.
- **Trunca el eco del ámbito** a unos 35 caracteres y se come el paréntesis de
  cierre, así que la verificación por ese lado necesita un patrón tolerante.
- **No dibuja la columna** de una categoría sin datos: la tabla vuelve con menos
  columnas y hay que alinear por nombre.
- **La selección geográfica se puede reusar**: fijarla una vez y pedir variable
  tras variable cuesta 5 s por variable en lugar de 12.

## Verificación

Nada de esto se da por bueno sin un control independiente:

- La población por VUPACI se contrasta con el fichero masivo de indicadores por
  sección censal del INE. Mediana de desviación: **0,027 %**.
- El total de personas debe ser idéntico en todas las variables de un mismo
  VUPACI; si no, la respuesta está cruzada y el grupo se descarta y se repite.
- Las 3.906 secciones del seccionado 2001 coinciden exactamente con las que
  publica el censo 2001, y la población suma 5.394.140, el total provincial.
- El cruce con la base armada a mano por el equipo coincide en 485 de 489 filas;
  las 4 discrepancias resultaron ser secciones mal asignadas en la carga manual.

## Advertencias sobre los datos

- **2011 viene redondeado** a múltiplos de 5 y marca con asterisco las cifras
  bajo el umbral de fiabilidad. **2001 son recuentos exactos.**
- El colectivo no se llama igual: *residentes en viviendas principales* en 2011,
  *residentes en viviendas familiares* en 2001.
- La VUPACI 375 no tiene secciones en 2001: no existía como territorio poblado.
- **2021 queda fuera por ahora.** El censo de 2021 es de registros, no de
  cuestionario, y en la variable de año de llegada a la vivienda el 22 % figura
  como "no consta" y otro 15 % como "no aplicable": el 37 % de la población no
  tiene dato utilizable. Comparar eso con 2001 y 2011 requiere una decisión
  metodológica que todavía no está tomada.

## Fuentes

- INE, [Censos de Población y Viviendas 2011](https://www.ine.es/censos2011/tablas/Inicio.do)
- INE, [Censos de Población y Viviendas 2001](https://www.ine.es/censo/es/inicio.jsp)
- INE, [indicadores por sección censal 2011](https://www.ine.es/censos2011_datos/cen11_datos_resultados_seccen.htm)
- INE, cartografía de secciones censales de 2001, 2011 y 2021

## Licencia

MIT para el código. Los datos son del INE y se rigen por sus condiciones de uso.
