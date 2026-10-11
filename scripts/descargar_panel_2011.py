# -*- coding: utf-8 -*-
"""
Baja el censo 2011 completo por VUPACI: todas las variables de la lista de
configuración, en formato largo.

Truco que hace esto viable: la selección geográfica se puede **reusar**. Se fija
el VUPACI una vez (unos 10 s de los tres pasos del asistente) y después se piden
las variables una tras otra contra Informe.do, a unos 5 s cada una. Sin eso
habría que rehacer el asistente entero por variable y costaría el triple.

REGLA IMPORTANTE: una sola sesión contra el INE a la vez **en toda la red**. Con
dos procesos simultáneos el servidor devuelve la tabla de otra consulta en
curso, sin avisar y con pinta de dato bueno.

Salida (una fila por VUPACI, variable y categoría):
    datos/censo2011/panel_2011.csv

Se puede cortar y retomar: anota en un archivo aparte los VUPACI terminados.

    python3 descargar_panel_2011.py [--limite N] [--desde V]
"""

import argparse
import csv
import json
import os
import sys
import time

import requests

import ine_censo2011 as ine
from descargar_arraigo import leer_seccionado

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CONFIG = os.path.join(RAIZ, "datos", "config", "variables_2011.json")
DESTINO = os.path.join(RAIZ, "datos", "censo2011")
SALIDA = os.path.join(DESTINO, "panel_2011.csv")
HECHOS = os.path.join(DESTINO, "panel_2011.hechos.txt")

# un VUPACI sólo se da por bueno si volvió al menos esta fracción de las
# variables pedidas. Sin esto, una caída de red marca como "hecho" un VUPACI
# del que no se bajó nada: pasó el 2026-10-09 y se perdieron 220 grupos.
FRACCION_MINIMA = 0.80


def esperar_red(intentos=None):
    """Bloquea hasta que el INE vuelva a responder. Devuelve los minutos esperados."""
    espera, total = 30, 0
    while intentos is None or intentos > 0:
        try:
            requests.get(ine.BASE + "Inicio.do", timeout=30).raise_for_status()
            if total:
                print(f"    red de vuelta tras {total/60:.0f} min", flush=True)
            return total
        except Exception:
            print(f"    sin conexión con el INE, reintento en {espera}s",
                  file=sys.stderr, flush=True)
            time.sleep(espera)
            total += espera
            espera = min(espera * 2, 600)
            if intentos is not None:
                intentos -= 1
    return total


def fijar_geografia(sesion, secciones, muni):
    cods = sorted({s[:5] for s in secciones})
    nombres = {c: muni[c].split(".")[-1].strip("[]")[6:] for c in cods}
    ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso4", "WIZARD": "6",
        "areaOrigen": "municipios-seccionescensales",
        "idComunidad": "", "idProvincia": "", "municipios": "",
        "idMunicipio": [muni[c] for c in cods], "subtipoInfra": "S"})
    r = ine._post(sesion, ine.BASE + "Wizard.do", {
        "reqCode": "paso5", "WIZARD": "6", "areaOrigen": "seccionescensales",
        "idDistrito": "", "idSeccion": "",
        "elementosGeograficosOrigenSeleccionados":
            [ine.clave_seccion(s, nombres[s[:5]]) for s in secciones],
        "desglose": "NO"})
    ine._verificar_ambito(r.text, secciones)
    ine._get(sesion, ine.BASE + "Wizard.do?WIZARD=1&reqCode=paso2")


def pedir(sesion, clave):
    """Una variable en columnas. Devuelve (categorías, valores crudos)."""
    r = ine._post(sesion, ine.BASE + "Informe.do", {
        "reqCode": "iniciar", "jerarquiasSeleccionada": "", "WIZARD": "2",
        "pagina4": "6", "tipoInforme": "LIBRE",
        "idColumna": clave, "medidas": ine.MEDIDA_PERSONAS})
    cols, filas = ine._parsear_tabla(r.text)
    return cols, filas[0][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--pausa", type=float, default=0.2)
    args = ap.parse_args()

    variables = json.load(open(CONFIG, encoding="utf-8"))["incluidas"]
    grupos = leer_seccionado()
    os.makedirs(DESTINO, exist_ok=True)

    hechos = set()
    if os.path.exists(HECHOS):
        hechos = {int(x) for x in open(HECHOS, encoding="utf-8").read().split()}
    pendientes = [v for v in sorted(grupos) if v not in hechos]
    if args.limite:
        pendientes = pendientes[:args.limite]

    print(f"{len(variables)} variables x {len(grupos)} VUPACI | "
          f"{len(hechos)} VUPACI hechos | {len(pendientes)} pendientes",
          flush=True)
    estimado = len(pendientes) * (10 + len(variables) * 4.8) / 3600
    print(f"estimación: {estimado:.1f} horas", flush=True)

    nuevo = not os.path.exists(SALIDA)
    f = open(SALIDA, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if nuevo:
        w.writerow(["VUPACI", "rama", "variable", "categoria", "personas",
                    "marcada"])
        f.flush()
    marcas = open(HECHOS, "a", encoding="utf-8")

    sesion = ine.nueva_sesion()
    muni = ine.cargar_municipios(sesion, "28")
    t_inicio = time.time()

    for i, v in enumerate(pendientes, 1):
        t0 = time.time()
        filas_v, fallos, hechas = [], [], 0

        for vuelta in range(1, 6):          # el VUPACI se reintenta entero
            filas_v, fallos, totales = [], [], set()
            esperar_red()
            try:
                fijar_geografia(sesion, grupos[v], muni)
            except Exception as e:
                print(f"    VUPACI {v}: geografía falló ({e}), vuelta {vuelta}",
                      file=sys.stderr, flush=True)
                esperar_red()
                try:
                    sesion = ine.nueva_sesion()
                    muni = ine.cargar_municipios(sesion, "28")
                except Exception:
                    pass
                continue

            for d in variables:
                try:
                    cols, crudos = pedir(sesion, d["clave"])
                    for cat, val in zip(cols, crudos):
                        if cat == "Total":
                            totales.add(ine.a_numero(val))
                        filas_v.append([v, d["rama"], d["nombre"], cat,
                                        ine.a_numero(val),
                                        "sí" if "*" in (val or "") else ""])
                except Exception:
                    fallos.append(d["nombre"])
                    time.sleep(1)

            hechas = len(variables) - len(fallos)
            # el total de personas tiene que ser el mismo en todas las
            # variables; si no, el INE cruzó respuestas y el grupo no sirve
            if len(totales) > 1:
                print(f"    VUPACI {v}: totales inconsistentes {sorted(totales)}, "
                      f"se descarta y se repite", file=sys.stderr, flush=True)
                sesion = ine.nueva_sesion()
                muni = ine.cargar_municipios(sesion, "28")
                continue
            if hechas >= FRACCION_MINIMA * len(variables):
                break
            print(f"    VUPACI {v}: sólo {hechas}/{len(variables)} variables, "
                  f"vuelta {vuelta}", file=sys.stderr, flush=True)
            esperar_red()
            try:
                sesion = ine.nueva_sesion()
                muni = ine.cargar_municipios(sesion, "28")
            except Exception:
                pass
        else:
            print(f"    VUPACI {v}: NO se pudo bajar, queda pendiente",
                  file=sys.stderr, flush=True)
            continue

        for fila in filas_v:
            w.writerow(fila)
        f.flush()
        marcas.write(f"{v}\n")
        marcas.flush()
        restante = (len(pendientes) - i) * (time.time() - t_inicio) / i / 3600
        print(f"[{i}/{len(pendientes)}] VUPACI {v}: {hechas}/{len(variables)} "
              f"variables en {time.time()-t0:.0f}s | faltan {restante:.1f} h"
              + (f" | fallaron: {fallos[:3]}" if fallos else ""), flush=True)
        time.sleep(args.pausa)

    f.close()
    marcas.close()
    print("\nCSV:", SALIDA)


if __name__ == "__main__":
    main()
