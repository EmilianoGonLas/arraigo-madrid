# -*- coding: utf-8 -*-
"""
Baja el censo 2001 a nivel de sección para toda la provincia de Madrid:
personas residentes en viviendas familiares por año de llegada a la vivienda.

Una consulta por municipio (el sistema de 2001 sólo deja elegir secciones si se
selecciona un único municipio), con la variable "Sección" en filas. Las cifras
vienen exactas, sin redondeo ni asteriscos.

Sirve para dos cosas:
  - tener el dato de 2001 por sección;
  - y, sobre todo, saber **cuál era el seccionado de 2001**, para poder decir en
    qué municipios los códigos de 2011 siguen designando lo mismo.

Guarda incrementalmente, así que se puede cortar y retomar.

    python3 descargar_2001_secciones.py [--limite N]
"""

import argparse
import csv
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

import ine_censo2001 as c01

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.path.join(RAIZ, "salidas", "censo2001_secciones_madrid.csv")

CAT = ["TOTAL", "2001", "2000", "1999", "1998", "1997", "1996", "1991-1995",
       "1981-1990", "1971-1980", "1961-1970", "1941-1960", "Antes de 1941"]


def municipios_provincia(sesion, cprov="28", ccaa="13"):
    c01._get(sesion, c01.BASE + "inicio.jsp", 60)
    c01._get(sesion, c01.BASE + "seleccion_ambito.jsp", 60)
    c01._get(sesion, c01.BASE + "seleccion_inframunicipal.jsp", 60)
    r = c01._post(sesion, c01.BASE + "seleccion_inframunicipal.jsp",
                  {"select_comunidad": ccaa, "select_provincia": cprov,
                   "select_municipio": "", "municipios": "",
                   "fType": "5", "_IDIOMA": "es"})
    return sorted({m for m in re.findall(r'<OPTION\s+VALUE="(%s\d{3})"' % cprov,
                                         r.text, re.I)})


def secciones_de(sesion, cmun, cprov="28", ccaa="13"):
    """{codigo_seccion_10: [valores]} para un municipio, censo 2001."""
    base = [("select_comunidad", ccaa), ("select_provincia", cprov),
            ("select_municipio", ""), ("municipios", cmun),
            ("subtipoInfra", "D"), ("fType", "5"), ("_IDIOMA", "es")]
    r = c01._post(sesion, c01.BASE + "seleccion_infra_elec_sec_dist.jsp", base)
    distritos = re.findall(r'<OPTION\s+VALUE="(%s\d{2})"' % cmun, r.text, re.I)
    if not distritos:
        raise RuntimeError(f"{cmun}: el INE no listó distritos")

    datos = base + [("distritos_secciones", d) for d in distritos]
    c01._post(sesion, c01.BASE + "seleccion_colectivo.jsp", datos)
    c01._get(sesion, c01.BASE + f"estructura.jsp?k={c01.COLECTIVO_PERSONAS_VIV_FAM}")
    r = c01._post(sesion, c01.BASE + "consulta.jsp",
                  [("k", c01.COLECTIVO_PERSONAS_VIV_FAM), ("_IDIOMA", "ES"),
                   ("s", "1"), ("m", "SPERSONAS"), ("r", "SECCION"),
                   ("c", "ANYO_LLEGADA_VIV")], timeout=600)

    soup = BeautifulSoup(r.text, "lxml")
    tabla = None
    for t in soup.find_all("table"):
        if "Sección" in t.get_text() and len(t.find_all("tr")) > 3:
            tabla = t
    if tabla is None:
        raise RuntimeError(f"{cmun}: no se encontró la tabla")

    # el INE no dibuja la columna de una categoría sin ningún dato, así que
    # hay que leer las cabeceras y alinear por nombre, rellenando con 0.
    columnas = []
    filas = {}
    for tr in tabla.find_all("tr"):
        cel = [c.get_text(" ", strip=True).replace("\xa0", " ").strip()
               for c in tr.find_all(["td", "th"])]
        if not columnas and "TOTAL" in cel:
            columnas = cel[cel.index("TOTAL"):]
            continue
        m = re.match(r"^Secci[óo]n\s+(\d{10})$", cel[0] if cel else "")
        if m and len(cel) >= len(columnas) and columnas:
            por_nombre = dict(zip(columnas, cel[-len(columnas):]))
            raras = [c for c in columnas if c not in CAT]
            if raras:
                raise RuntimeError(f"{cmun}: columnas inesperadas {raras}")
            filas[m.group(1)] = [por_nombre.get(c, "0") for c in CAT]
    if not filas:
        raise RuntimeError(f"{cmun}: la tabla no traía secciones")
    return filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--pausa", type=float, default=0.5)
    args = ap.parse_args()

    hechos = set()
    if os.path.exists(SALIDA):
        with open(SALIDA, newline="", encoding="utf-8") as f:
            hechos = {fila["SECCION"][:5] for fila in csv.DictReader(f)}

    sesion = requests.Session()
    sesion.headers["User-Agent"] = c01.UA
    muni = municipios_provincia(sesion)
    pendientes = [m for m in muni if m not in hechos]
    if args.limite:
        pendientes = pendientes[:args.limite]
    print(f"{len(muni)} municipios | {len(hechos)} hechos | "
          f"{len(pendientes)} pendientes", flush=True)

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    nuevo = not os.path.exists(SALIDA)
    f = open(SALIDA, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if nuevo:
        w.writerow(["SECCION"] + CAT)
        f.flush()

    errores = []
    for i, cmun in enumerate(pendientes, 1):
        for intento in (1, 2, 3):
            try:
                secs = secciones_de(sesion, cmun)
                for s in sorted(secs):
                    w.writerow([s] + [c01.a_numero(x) for x in secs[s]])
                f.flush()
                print(f"[{i}/{len(pendientes)}] {cmun}: {len(secs)} secciones",
                      flush=True)
                break
            except Exception as e:
                print(f"    {cmun}: fallo {intento}/3 -> {e}",
                      file=sys.stderr, flush=True)
                time.sleep(3 * intento)
                sesion = requests.Session()
                sesion.headers["User-Agent"] = c01.UA
                municipios_provincia(sesion)
        else:
            errores.append(cmun)
        time.sleep(args.pausa)

    f.close()
    if errores:
        print(f"\nmunicipios sin bajar: {errores}")
    print(f"\nCSV: {SALIDA}")


if __name__ == "__main__":
    main()
