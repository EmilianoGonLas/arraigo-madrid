# -*- coding: utf-8 -*-
"""
Cliente del asistente "Consulta de tablas" del Censo de Población y Viviendas 2011 (INE).

Reproduce, por HTTP, exactamente los mismos pasos que se hacen a mano en
https://www.ine.es/censos2011/tablas/  :

  Paso 1  Crear tablas
  Paso 2  Ámbito geográfico -> Inframunicipal -> municipios -> Secciones
  Paso 3  Colectivo -> Personas / Residentes en viviendas principales
  Paso 4  Columnas -> Año de llegada a la vivienda ; medida -> Personas

Las claves que espera el servidor son miembros MDX, p.ej.

  municipio: [RESIDENCIA].[Todo RESIDENCIA].[Madrid, Comunidad de].[28 Madrid].[28001 Acebeda, La]
  sección:   [RESIDENCIA_INFRA].[Todo RESIDENCIA_INFRA].[28001 Acebeda, La].[Distrito 2800101].[Sección 2800101001]

El nombre del municipio tiene que ser literalmente el del INE, por eso se
cosecha una vez del propio formulario (`cargar_municipios`).
"""

import re
import time
import html
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ine.es/censos2011/tablas/"
ENC = "utf-8"          # el INE sirve y espera UTF-8 (Content-Type: text/html;charset=UTF-8)
UA = "Mozilla/5.0 (X11; Linux x86_64) consulta-academica"

VAR_ANYO_LLEGADA_VIV = "L_[ANYO_LLEGADA_VIV].[DESC_ANYO_LLEGADA_VIV]"
MEDIDA_PERSONAS = "[Measures].[SPERSONASSUM]"


def _post(sesion, url, params):
    """POST con el cuerpo codificado en UTF-8, que es lo que espera el INE."""
    cuerpo = urlencode(params, doseq=True, encoding=ENC)
    r = sesion.post(
        url, data=cuerpo,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    r.raise_for_status()
    r.encoding = ENC
    return r


def _get(sesion, url):
    r = sesion.get(url, timeout=60)
    r.raise_for_status()
    r.encoding = ENC
    return r


def nueva_sesion():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    _get(s, BASE + "Inicio.do")
    return s


def cargar_municipios(sesion, cprov="28"):
    """Devuelve {codigo_municipio: clave_MDX} para una provincia."""
    _get(sesion, BASE + "Wizard.do?WIZARD=1&reqCode=paso1")
    r = _get(sesion, BASE + "Wizard.do?WIZARD=5&reqCode=paso4")
    opciones = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', r.text)
    muni = {}
    for valor, texto in opciones:
        valor = html.unescape(valor)
        texto = html.unescape(texto).strip()
        if valor.startswith("[RESIDENCIA].") and re.match(r"^%s\d{3}\s" % cprov, texto):
            muni[texto[:5]] = valor
    if not muni:
        raise RuntimeError("no se pudieron leer los municipios del formulario")
    return muni


def clave_seccion(cod10, nombre_municipio):
    """cod10 = 2800101001 -> clave MDX de la sección."""
    cmun, cdist = cod10[:5], cod10[:7]
    return ("[RESIDENCIA_INFRA].[Todo RESIDENCIA_INFRA]."
            f"[{cmun} {nombre_municipio}].[Distrito {cdist}].[Sección {cod10}]")


def consultar(sesion, secciones, muni_mdx, desglose="NO",
              variable=VAR_ANYO_LLEGADA_VIV, medida=MEDIDA_PERSONAS):
    """
    secciones: lista de códigos de 10 dígitos.
    desglose : "NO" -> una sola fila agregada ; "SI" -> una fila por sección.
    Devuelve (cabeceras, filas) tal cual los publica el INE.
    """
    cods_muni = sorted({s[:5] for s in secciones})
    nombres = {c: muni_mdx[c].split(".")[-1].strip("[]")[6:] for c in cods_muni}

    # Paso 2a: municipios -> "Secciones"
    _post(sesion, BASE + "Wizard.do", {
        "reqCode": "paso4", "WIZARD": "6",
        "areaOrigen": "municipios-seccionescensales",
        "idComunidad": "", "idProvincia": "", "municipios": "",
        "idMunicipio": [muni_mdx[c] for c in cods_muni],
        "subtipoInfra": "S",
    })

    # Paso 2b: secciones concretas + desglose
    _post(sesion, BASE + "Wizard.do", {
        "reqCode": "paso5", "WIZARD": "6",
        "areaOrigen": "seccionescensales",
        "idDistrito": "", "idSeccion": "",
        "elementosGeograficosOrigenSeleccionados":
            [clave_seccion(s, nombres[s[:5]]) for s in secciones],
        "desglose": desglose,
    })

    # Paso 3: colectivo Personas / residentes en viviendas principales
    _get(sesion, BASE + "Wizard.do?WIZARD=1&reqCode=paso2")

    # Paso 4: tabla
    r = _post(sesion, BASE + "Informe.do", {
        "reqCode": "iniciar", "jerarquiasSeleccionada": "",
        "WIZARD": "2", "pagina4": "6", "tipoInforme": "LIBRE",
        # ojo: NO se manda idFila. Si se manda vacío el INE responde
        # "Fallo en sistema" en vez de la tabla.
        "idColumna": variable, "medidas": medida,
    })
    _verificar_ambito(r.text, secciones)
    return _parsear_tabla(r.text)


def _verificar_ambito(texto, secciones):
    """
    El informe repite el ámbito geográfico usado, en forma
    "-(28001-Acebeda, La) (Sección 01-001)". Si el INE se hubiera comido alguna
    sección de las enviadas, el número no cuadraría y el total saldría corto
    sin avisar. Mejor que reviente aquí.
    """
    # ojo: el INE trunca los nombres largos a unos 35 caracteres y se come el
    # paréntesis de cierre -> "-(28063-Gargantilla del Lozoya y Pini) (Sección 01-001"
    # así que el patrón no puede exigir paréntesis balanceados.
    incluidas = re.findall(r"-\((\d{5})-[^(]*\(Sección (\d{2})-(\d{3})", texto)
    if not incluidas:
        return                      # con una sola sección el INE no lista detalle
    obtenidas = {m + d + sec for m, d, sec in incluidas}
    faltan = set(secciones) - obtenidas
    if faltan:
        raise RuntimeError(f"el INE no incluyó {len(faltan)} secciones: "
                           f"{sorted(faltan)[:5]}")


def _parsear_tabla(texto):
    """
    Saca la tabla de resultados del HTML del INE.

    La tabla es <table class="OLAPMainTable">; las cabeceras de columna llevan
    class="OLAPTableColumnHeader" y los datos class="dat". Las cabeceras traen
    pegado el menú desplegable entero ("2011 Profundizar por--> ..."), así que
    hay que quedarse con la primera línea.

    Devuelve (columnas, filas):
      columnas -> ['Total', '2011', ..., 'Antes de 1971']
      filas    -> [(etiqueta_fila, [valores...]), ...]
    """
    soup = BeautifulSoup(texto, "lxml")
    if "Fallo en sistema" in soup.get_text():
        raise RuntimeError("el INE devolvió 'Fallo en sistema' (sesión perdida "
                           "o parámetros inválidos)")

    tabla = None
    for t in soup.find_all("table"):
        if t.find("td", class_="dat") or t.find("th", class_="dat"):
            tabla = t
    if tabla is None:
        raise RuntimeError("no se encontró la tabla de resultados en la respuesta")

    def limpia(celda):
        txt = celda.get_text("|", strip=True)
        return txt.split("|")[0].strip()

    columnas = []
    for tr in tabla.find_all("tr"):
        cab = tr.find_all(["td", "th"], class_="OLAPTableColumnHeader", recursive=False)
        if len(cab) > 2:                       # la fila de años, no la de medidas
            etiquetas = [limpia(c) for c in cab]
            if "Total" in etiquetas:
                columnas = etiquetas[etiquetas.index("Total"):]
                break

    filas = []
    for tr in tabla.find_all("tr"):
        datos = tr.find_all(["td", "th"], class_="dat", recursive=False)
        if not datos:
            continue
        cab_fila = tr.find(["td", "th"], class_="OLAPTableRowHeader", recursive=False)
        filas.append((limpia(cab_fila) if cab_fila else "",
                      [limpia(d) for d in datos]))

    if not filas:
        raise RuntimeError("la tabla no traía filas de datos")
    return columnas, filas


def a_numero(txt):
    """
    '1.100' -> 1100 ; '30*' -> 30 ; '' o '.' -> None.

    El asterisco lo pone el INE en las cifras que quedan por debajo del umbral
    de fiabilidad/confidencialidad. El valor se conserva; que venía marcado se
    anota aparte con `marcadas()`.
    """
    txt = (txt or "").strip().replace("*", "").replace(".", "").replace(",", ".")
    if txt in ("", "-", "..", "."):
        return None
    try:
        return int(float(txt))
    except ValueError:
        return None


def marcadas(valores, columnas):
    """Nombres de las columnas cuyo valor venía con asterisco."""
    return [c for c, v in zip(columnas, valores) if "*" in (v or "")]
