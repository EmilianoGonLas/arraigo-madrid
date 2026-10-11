# -*- coding: utf-8 -*-
"""
Cliente del sistema de consulta del Censo de Población y Viviendas 2001 (INE).

Es otra aplicación que la de 2011: JSP, ISO-8859-1, y los pasos son
  inicio.jsp -> seleccion_ambito.jsp -> seleccion_<ambito>.jsp
             -> seleccion_colectivo.jsp -> estructura.jsp?k=<colectivo>
             -> consulta.jsp

Diferencias con 2011 que importan:
  - las cifras NO vienen redondeadas a múltiplos de 5 ni marcadas con asterisco:
    son recuentos exactos, así que se pueden sumar sin perder nada;
  - las categorías del año de llegada son otras (el censo es de 2001);
  - a nivel inframunicipal sólo se pueden elegir secciones concretas si se
    selecciona UN único municipio; con varios devuelve todo.
"""

import re

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ine.es/censo/es/"
ENC = "iso-8859-1"
UA = "Mozilla/5.0 (X11; Linux x86_64) consulta-academica"

COLECTIVO_PERSONAS_VIV_FAM = "MDDB.COLECTIVO_P2M"   # Residentes en viviendas familiares
VAR_ANYO_LLEGADA_VIV = "ANYO_LLEGADA_VIV"
VAR_MUNICIPIO = "MUNICIPIO"
MEDIDA_PERSONAS = "SPERSONAS"


def _get(s, url, timeout=180):
    r = s.get(url, timeout=timeout)
    r.raise_for_status()
    r.encoding = ENC
    return r


def _post(s, url, datos, timeout=420):
    r = s.post(url, data=datos, timeout=timeout)
    r.raise_for_status()
    r.encoding = ENC
    return r


def tabla_provincial(cprov="28", ccaa="13",
                     variable=VAR_ANYO_LLEGADA_VIV,
                     colectivo=COLECTIVO_PERSONAS_VIV_FAM):
    """
    Una sola consulta: filas = municipios de la provincia, columnas = la
    variable pedida. Devuelve (columnas, {codigo_municipio: [valores]}).

    Se usa el ámbito provincial con la variable "Municipio de residencia" en
    filas porque el ámbito municipal no admite más de 52 municipios a la vez.
    """
    s = requests.Session()
    s.headers["User-Agent"] = UA
    _get(s, BASE + "inicio.jsp", timeout=60)
    _get(s, BASE + "seleccion_ambito.jsp", timeout=60)
    _get(s, BASE + "seleccion_provincia.jsp", timeout=60)
    _post(s, BASE + "seleccion_colectivo.jsp",
          [("select_comunidades", ccaa), ("select_provincia", cprov),
           ("provincias", cprov), ("fType", "3"), ("_IDIOMA", "es")])
    _get(s, BASE + f"estructura.jsp?k={colectivo}")
    r = _post(s, BASE + "consulta.jsp",
              [("k", colectivo), ("_IDIOMA", "ES"), ("s", "1"),
               ("m", MEDIDA_PERSONAS), ("r", VAR_MUNICIPIO), ("c", variable)])
    return _parsear(r.text)


def _parsear(texto):
    soup = BeautifulSoup(texto, "lxml")
    tabla = None
    for t in soup.find_all("table"):
        # la tabla buena es la que trae una fila por municipio ("28001-...")
        if re.search(r"\d{5}-\D", t.get_text(" ")) and len(t.find_all("tr")) > 10:
            tabla = t
    if tabla is None:
        raise RuntimeError("no se encontró la tabla de resultados")

    columnas, filas = [], {}
    for tr in tabla.find_all("tr"):
        cel = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cel = [c.replace("\xa0", " ").strip() for c in cel]
        if not any(cel):
            continue
        if not columnas and "TOTAL" in cel:
            columnas = cel[cel.index("TOTAL"):]
            continue
        m = re.match(r"^(\d{5})-", cel[0])
        if m and len(cel) >= len(columnas):
            filas[m.group(1)] = cel[-len(columnas):]
    if not filas:
        raise RuntimeError("la tabla no traía filas de municipio")
    return columnas, filas


def a_numero(txt):
    """'5.394.140' -> 5394140. El censo 2001 no usa asteriscos."""
    t = (txt or "").strip().replace(".", "").replace(",", ".")
    if t in ("", "-", "..", "."):
        return None
    try:
        return int(float(t))
    except ValueError:
        return None
