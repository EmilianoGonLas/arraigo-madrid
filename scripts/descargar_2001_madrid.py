# -*- coding: utf-8 -*-
"""
Madrid capital (28079) aparte: tiene ~2.300 secciones en 2001 y la consulta de
municipio entero no devuelve tabla. Se pide distrito por distrito (21) y se
añade al mismo CSV que el resto de la provincia.

    python3 descargar_2001_madrid.py
"""

import csv
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

import ine_censo2001 as c01
from descargar_2001_secciones import CAT, SALIDA, municipios_provincia

CMUN = "28079"


def secciones_del_distrito(sesion, cdist):
    base = [("select_comunidad", "13"), ("select_provincia", "28"),
            ("select_municipio", ""), ("municipios", CMUN),
            ("subtipoInfra", "D"), ("fType", "5"), ("_IDIOMA", "es")]
    c01._post(sesion, c01.BASE + "seleccion_infra_elec_sec_dist.jsp", base)
    c01._post(sesion, c01.BASE + "seleccion_colectivo.jsp",
              base + [("distritos_secciones", cdist)])
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
        raise RuntimeError(f"{cdist}: no se encontró la tabla")

    columnas, filas = [], {}
    for tr in tabla.find_all("tr"):
        cel = [c.get_text(" ", strip=True).replace("\xa0", " ").strip()
               for c in tr.find_all(["td", "th"])]
        if not columnas and "TOTAL" in cel:
            columnas = cel[cel.index("TOTAL"):]
            continue
        m = re.match(r"^Secci[óo]n\s+(\d{10})$", cel[0] if cel else "")
        if m and columnas and len(cel) >= len(columnas):
            por_nombre = dict(zip(columnas, cel[-len(columnas):]))
            filas[m.group(1)] = [por_nombre.get(c, "0") for c in CAT]
    if not filas:
        raise RuntimeError(f"{cdist}: la tabla no traía secciones")
    return filas


def main():
    hechos = set()
    with open(SALIDA, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if fila["SECCION"].startswith(CMUN):
                hechos.add(fila["SECCION"][:7])

    sesion = requests.Session()
    sesion.headers["User-Agent"] = c01.UA
    municipios_provincia(sesion)
    base = [("select_comunidad", "13"), ("select_provincia", "28"),
            ("select_municipio", ""), ("municipios", CMUN),
            ("subtipoInfra", "D"), ("fType", "5"), ("_IDIOMA", "es")]
    r = c01._post(sesion, c01.BASE + "seleccion_infra_elec_sec_dist.jsp", base)
    distritos = sorted(set(re.findall(r'<OPTION\s+VALUE="(%s\d{2})"' % CMUN,
                                      r.text, re.I)))
    pendientes = [d for d in distritos if d not in hechos]
    print(f"{len(distritos)} distritos | {len(pendientes)} pendientes", flush=True)

    f = open(SALIDA, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    errores = []
    for i, d in enumerate(pendientes, 1):
        for intento in (1, 2, 3):
            try:
                secs = secciones_del_distrito(sesion, d)
                for s in sorted(secs):
                    w.writerow([s] + [c01.a_numero(x) for x in secs[s]])
                f.flush()
                print(f"[{i}/{len(pendientes)}] {d}: {len(secs)} secciones",
                      flush=True)
                break
            except Exception as e:
                print(f"    {d}: fallo {intento}/3 -> {e}",
                      file=sys.stderr, flush=True)
                time.sleep(3 * intento)
                sesion = requests.Session()
                sesion.headers["User-Agent"] = c01.UA
                municipios_provincia(sesion)
        else:
            errores.append(d)
        time.sleep(0.4)
    f.close()
    if errores:
        print(f"\ndistritos sin bajar: {errores}")


if __name__ == "__main__":
    main()
