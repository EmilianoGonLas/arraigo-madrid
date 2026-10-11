# -*- coding: utf-8 -*-
"""
Baja del censo 2011, por VUPACI, el cruce de una variable demográfica con el
año de llegada a la vivienda.

El secreto estadístico del INE sólo deja cruzar con «año de llegada» las
variables exentas —sexo, edad en grandes grupos y tamaño de municipio—, además
de las de referencia geográfica. Cualquier otra se rechaza, así que el resto de
variables hay que pedirlas sueltas.

No paralelizar: con varias sesiones el INE devuelve la tabla de otra consulta
(ver descargar_arraigo.py).

    python3 descargar_cruce_2011.py --variable edad
    python3 descargar_cruce_2011.py --variable sexo
"""

import argparse
import csv
import os
import re
import sys
import time

import ine_censo2011 as ine
from descargar_arraigo import leer_seccionado

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATOS = os.path.join(RAIZ, "datos", "censo2011")

COLUMNAS = ["Total", "2011", "2010", "2009", "2008", "2007", "2006",
            "2001-2005", "1991-2000", "1981-1990", "1971-1980", "Antes de 1971"]

VARIABLES = {
    "edad": ("Edad en grandes grupos", "L_[EDAD_GRUPO].[DESC_EDAD_GRUPO]"),
    "sexo": ("Sexo", "L_[SEXO].[DESC_SEXO]"),
}


def clave_variable(sesion, etiqueta):
    """Busca en el árbol del paso 4 la clave MDX de una variable por su nombre."""
    r = ine._get(sesion, ine.BASE + "Wizard.do?WIZARD=1&reqCode=paso2")
    pares = dict(re.findall(r'text:"([^"]+)", value:"(L_\[[^"]+)"', r.text))
    if etiqueta not in pares:
        raise RuntimeError(f"no está la variable {etiqueta!r} en el árbol")
    return pares[etiqueta]


def consultar(sesion, secciones, muni, clave_fila):
    """Devuelve [(categoría, [valores...]), ...] con una fila por categoría."""
    cods = sorted({s[:5] for s in secciones})
    nombres = {c: muni[c].split(".")[-1].strip("[]")[6:] for c in cods}
    ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso4", "WIZARD": "6",
        "areaOrigen": "municipios-seccionescensales",
        "idComunidad": "", "idProvincia": "", "municipios": "",
        "idMunicipio": [muni[c] for c in cods], "subtipoInfra": "S"})
    ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso5", "WIZARD": "6", "areaOrigen": "seccionescensales",
        "idDistrito": "", "idSeccion": "",
        "elementosGeograficosOrigenSeleccionados":
            [ine.clave_seccion(s, nombres[s[:5]]) for s in secciones],
        "desglose": "NO"})
    ine._get(sesion, ine.BASE + "Wizard.do?WIZARD=1&reqCode=paso2")
    r = ine._post(sesion, ine.BASE + "Informe.do", {
        "reqCode": "iniciar", "jerarquiasSeleccionada": "", "WIZARD": "2",
        "pagina4": "6", "tipoInforme": "LIBRE",
        "idFila": clave_fila, "idColumna": ine.VAR_ANYO_LLEGADA_VIV,
        "medidas": ine.MEDIDA_PERSONAS})
    ine._verificar_ambito(r.text, secciones)
    cols, filas = ine._parsear_tabla(r.text)
    desconocidas = [c for c in cols if c not in COLUMNAS]
    if desconocidas:
        raise RuntimeError(f"columnas inesperadas: {desconocidas}")
    salida = []
    for etiqueta, crudos in filas:
        por_nombre = dict(zip(cols, crudos))
        ordenados = [por_nombre.get(c, "0") for c in COLUMNAS]
        salida.append((etiqueta or "Total",
                       [ine.a_numero(x) for x in ordenados],
                       "|".join(ine.marcadas(ordenados, COLUMNAS)),
                       "|".join(c for c in COLUMNAS if c not in por_nombre)))
    return salida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variable", required=True, choices=sorted(VARIABLES))
    ap.add_argument("--pausa", type=float, default=0.3)
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args()

    etiqueta, _ = VARIABLES[args.variable]
    os.makedirs(DATOS, exist_ok=True)
    salida = os.path.join(DATOS, f"anyo_llegada_x_{args.variable}.csv")

    hechos = set()
    if os.path.exists(salida):
        with open(salida, newline="", encoding="utf-8") as f:
            hechos = {int(x["VUPACI"]) for x in csv.DictReader(f)}

    grupos = leer_seccionado()
    pendientes = [v for v in sorted(grupos) if v not in hechos]
    if args.limite:
        pendientes = pendientes[:args.limite]
    print(f"{len(grupos)} VUPACI | {len(hechos)} hechos | "
          f"{len(pendientes)} pendientes | variable: {etiqueta}", flush=True)

    sesion = ine.nueva_sesion()
    muni = ine.cargar_municipios(sesion, "28")
    clave = clave_variable(sesion, etiqueta)
    print("clave MDX:", clave, flush=True)

    nuevo = not os.path.exists(salida)
    f = open(salida, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if nuevo:
        w.writerow(["VUPACI", "categoria"] + COLUMNAS + ["marcadas", "ausentes"])
        f.flush()

    errores = []
    for i, v in enumerate(pendientes, 1):
        for intento in (1, 2, 3):
            try:
                for cat, vals, marc, aus in consultar(sesion, grupos[v], muni, clave):
                    w.writerow([v, cat] + vals + [marc, aus])
                f.flush()
                print(f"[{i}/{len(pendientes)}] VUPACI {v}", flush=True)
                break
            except Exception as e:
                print(f"    VUPACI {v}: fallo {intento}/3 -> {e}",
                      file=sys.stderr, flush=True)
                time.sleep(2 * intento)
                sesion = ine.nueva_sesion()
                muni = ine.cargar_municipios(sesion, "28")
                clave = clave_variable(sesion, etiqueta)
        else:
            errores.append(v)
        time.sleep(args.pausa)
    f.close()
    if errores:
        print(f"\nVUPACI sin bajar: {errores}")
    print("\nCSV:", salida)


if __name__ == "__main__":
    main()
