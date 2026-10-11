# -*- coding: utf-8 -*-
"""
Control independiente de lo descargado, y reparación de lo que no cuadre.

Compara el total de personas de cada VUPACI con la población total de sus
secciones según el fichero masivo de indicadores por sección censal del INE
(tabla t1_1). No tienen por qué coincidir —una cosa es población total y otra
residentes en viviendas principales, y ambas van redondeadas— pero la
diferencia normal es de unas pocas unidades. Una desviación grande delata una
respuesta cruzada del servidor.

    python3 verificar_arraigo.py              # solo informa
    python3 verificar_arraigo.py --reparar    # re-consulta y corrige
"""

import argparse
import os

import pandas as pd

import ine_censo2011 as ine
from descargar_arraigo import COLUMNAS, SALIDA, leer_seccionado

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SECCIONADO = os.path.join(RAIZ, "datos", "originales", "Seccionado VUPACI.xlsx")
INDICADORES = os.path.join(RAIZ, "datos", "ine", "csv", "C2011_ccaa13_Indicadores.csv")


def poblacion_por_vupaci():
    sec = pd.read_excel(SECCIONADO, header=1).iloc[:, 1:3]
    sec.columns = ["VUPACI", "SECCION"]
    sec = sec.dropna(how="any")
    sec["VUPACI"] = sec["VUPACI"].astype(int)
    sec["SECCION"] = sec["SECCION"].astype("int64").astype(str).str.zfill(10)

    ind = pd.read_csv(INDICADORES, dtype=str)
    ind["SECCION"] = (ind["cpro"].str.zfill(2) + ind["cmun"].str.zfill(3)
                      + ind["dist"].str.zfill(2) + ind["secc"].str.zfill(3))
    ind["t1_1"] = pd.to_numeric(ind["t1_1"], errors="coerce")

    return (sec.merge(ind[["SECCION", "t1_1"]], on="SECCION", how="left")
               .groupby("VUPACI")["t1_1"].sum())


def sospechosos(df, umbral):
    pob = poblacion_por_vupaci()
    rel = ((df["Total"] - pob.reindex(df.index)).abs()
           / pob.reindex(df.index) * 100)
    return rel[rel > umbral].sort_values(ascending=False), pob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=float, default=2.0,
                    help="%% de desviación contra el control a partir del cual "
                         "se re-consulta")
    ap.add_argument("--reparar", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(SALIDA).set_index("VUPACI")
    malos, pob = sospechosos(df, args.umbral)
    print(f"{len(df)} VUPACI descargados | {len(malos)} por encima del "
          f"{args.umbral}% de desviación")
    for v, r in malos.items():
        print(f"  VUPACI {v}: total {df.loc[v, 'Total']} vs control "
              f"{int(pob[v])} ({r:+.1f}%)")

    if not args.reparar or malos.empty:
        return

    grupos = leer_seccionado()
    corregidos = 0
    for v in malos.index:
        sesion = ine.nueva_sesion()           # sesión limpia por consulta
        muni = ine.cargar_municipios(sesion, "28")
        cols, filas = ine.consultar(sesion, grupos[v], muni)
        crudos = filas[0][1]
        valores = [ine.a_numero(x) for x in crudos]
        if valores[0] != df.loc[v, "Total"]:
            print(f"  VUPACI {v}: {df.loc[v, 'Total']} -> {valores[0]} (corregido)")
            corregidos += 1
        else:
            print(f"  VUPACI {v}: se confirma {valores[0]} (desviación real)")
        df.loc[v, COLUMNAS] = valores
        df.loc[v, "marcadas"] = "|".join(ine.marcadas(crudos, cols))

    df.reset_index().to_csv(SALIDA, index=False)
    print(f"\n{corregidos} filas corregidas. CSV reescrito.")


if __name__ == "__main__":
    main()
