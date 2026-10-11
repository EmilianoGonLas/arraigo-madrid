# -*- coding: utf-8 -*-
"""
Libro con los dos censos y **todas las cuentas como fórmulas vivas**.

  Pesos        los cuatro pesos, en celdas editables
  2011         las 11 categorías del INE + tramos + proporciones + índice
  2001         las 12 categorías del INE + tramos + proporciones + índice
  Comparación  los dos índices por VUPACI, buscados con fórmulas, y su variación
  Método       qué hace cada columna

El índice queda en **decimales de 0 a 1**, no en porcentaje: es la media
ponderada de las proporciones, sin multiplicar por 100.

Cada censo se agrega con su propio seccionado (archivo
"Seccionado VUPACI 2001 y 2011.xlsx"), así que no hay aproximaciones.

    python3 excel_formulas_dos_censos.py
"""

import os

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from arraigo_2001_definitivo import (CAT01, CAT11, SEC2001, ARR2011,
                                     leer_seccionado_doble)

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.path.join(RAIZ, "salidas", "Arraigo 2001-2011 - con formulas.xlsx")

NEGRITA = Font(bold=True)
GRIS = Font(color="6B7280", italic=True)
AMBAR_F = Font(color="B45309", bold=True)
AMBAR_R = PatternFill("solid", fgColor="FEF3C7")
CABECERA = PatternFill("solid", fgColor="E5E7EB")

# cuántas columnas ocupa cada tramo en cada año (en el orden de CATxx)
CORTES = {2011: (6, 1, 1, 3), 2001: (6, 1, 1, 4)}


def _hoja_pesos(h):
    h["A1"], h["B1"] = "tramo", "peso"
    h["A1"].font = h["B1"].font = NEGRITA
    filas = [("a — los 6 últimos años del censo", 0.00),
             ("b — los 5 años previos", 0.33),
             ("c — los 10 años previos", 0.66),
             ("d — todo lo anterior", 1.00)]
    for i, (nom, p) in enumerate(filas, start=2):
        h.cell(row=i, column=1, value=nom)
        c = h.cell(row=i, column=2, value=p)
        c.font, c.number_format = NEGRITA, "0.00"
    h["A7"] = ("Cambiá cualquiera de los cuatro y se recalculan las hojas 2011, "
               "2001 y Comparación.")
    h["A7"].font = GRIS
    h["A8"] = ("Los tramos son los mismos en los dos censos, por posición "
               "relativa a la fecha del censo.")
    h["A8"].font = GRIS
    h.column_dimensions["A"].width = 42
    h.column_dimensions["B"].width = 10


def _hoja_censo(h, anyo, datos, categorias, extra_total, marcas=None):
    """Escribe un censo con sus fórmulas. Devuelve la letra de la columna índice."""
    n6, n5, n10, nres = CORTES[anyo]
    cabeceras = (["VUPACI", "n secciones"] + categorias + [extra_total]
                 + ["a", "b", "c", "d", "suma tramos",
                    "p_a", "p_b", "p_c", "p_d", "índice"])
    for j, nom in enumerate(cabeceras, start=1):
        c = h.cell(row=1, column=j, value=nom)
        c.font, c.fill = NEGRITA, CABECERA
        c.alignment = Alignment(horizontal="center", wrap_text=True)

    L = get_column_letter
    c0 = 3                                   # primera categoría
    cA1, cA2 = L(c0), L(c0 + n6 - 1)
    cB = L(c0 + n6)
    cC = L(c0 + n6 + n5)
    cD1, cD2 = L(c0 + n6 + n5 + n10), L(c0 + len(categorias) - 1)
    ct = c0 + len(categorias)                # Total publicado
    ca, cb, cc, cd = L(ct + 1), L(ct + 2), L(ct + 3), L(ct + 4)
    cs = L(ct + 5)
    cpa, cpb, cpc, cpd = L(ct + 6), L(ct + 7), L(ct + 8), L(ct + 9)
    cidx = L(ct + 10)

    for i, (v, fila) in enumerate(datos.iterrows(), start=2):
        marcadas = str((marcas or {}).get(v, "") or "").split("|")
        h.cell(row=i, column=1, value=int(v)).font = NEGRITA
        h.cell(row=i, column=2, value=int(fila["n_secciones"]))
        for j, cat in enumerate(categorias, start=c0):
            celda = h.cell(row=i, column=j, value=int(fila[cat]))
            if cat in marcadas:
                celda.font, celda.fill = AMBAR_F, AMBAR_R
        h.cell(row=i, column=ct, value=int(fila["Total"])).font = GRIS

        h[f"{ca}{i}"] = f"=SUM({cA1}{i}:{cA2}{i})"
        h[f"{cb}{i}"] = f"={cB}{i}"
        h[f"{cc}{i}"] = f"={cC}{i}"
        h[f"{cd}{i}"] = f"=SUM({cD1}{i}:{cD2}{i})"
        h[f"{cs}{i}"] = f"=SUM({ca}{i}:{cd}{i})"
        for pc, tc in ((cpa, ca), (cpb, cb), (cpc, cc), (cpd, cd)):
            h[f"{pc}{i}"] = f"=IF({cs}{i}=0,\"\",{tc}{i}/{cs}{i})"
            h[f"{pc}{i}"].number_format = "0.0000"
        h[f"{cidx}{i}"] = (f"=IF({cs}{i}=0,\"\","
                           f"{cpa}{i}*Pesos!$B$2+{cpb}{i}*Pesos!$B$3"
                           f"+{cpc}{i}*Pesos!$B$4+{cpd}{i}*Pesos!$B$5)")
        h[f"{cidx}{i}"].font = NEGRITA
        h[f"{cidx}{i}"].number_format = "0.0000"

    h.column_dimensions["A"].width = 9
    h.column_dimensions["B"].width = 10
    for j in range(c0, len(cabeceras) + 1):
        h.column_dimensions[L(j)].width = 11
    h.column_dimensions[cidx].width = 11
    h.freeze_panes = "C2"
    return cidx, ct, len(datos)


def _hoja_comparacion(h, vupaci, idx11, tot11, n11, idx01, tot01, n01):
    cab = ["VUPACI", "población 2001", "población 2011", "índice 2001",
           "índice 2011", "variación índice", "variación población"]
    for j, nom in enumerate(cab, start=1):
        c = h.cell(row=j and j, column=j, value=nom) if False else h.cell(row=1, column=j, value=nom)
        c.font, c.fill = NEGRITA, CABECERA
        c.alignment = Alignment(horizontal="center", wrap_text=True)

    L = get_column_letter
    t11, t01 = L(tot11), L(tot01)
    for i, v in enumerate(vupaci, start=2):
        h.cell(row=i, column=1, value=int(v)).font = NEGRITA
        busca01 = f"MATCH($A{i},'2001'!$A$2:$A${n01+1},0)"
        busca11 = f"MATCH($A{i},'2011'!$A$2:$A${n11+1},0)"
        h.cell(row=i, column=2,
               value=f"=IFERROR(INDEX('2001'!${t01}$2:${t01}${n01+1},{busca01}),\"\")")
        h.cell(row=i, column=3,
               value=f"=IFERROR(INDEX('2011'!${t11}$2:${t11}${n11+1},{busca11}),\"\")")
        c = h.cell(row=i, column=4,
                   value=f"=IFERROR(INDEX('2001'!${idx01}$2:${idx01}${n01+1},{busca01}),\"\")")
        c.number_format = "0.0000"
        c = h.cell(row=i, column=5,
                   value=f"=IFERROR(INDEX('2011'!${idx11}$2:${idx11}${n11+1},{busca11}),\"\")")
        c.number_format = "0.0000"
        c = h.cell(row=i, column=6, value=f'=IF(OR($D{i}="",$E{i}=""),"",$E{i}-$D{i})')
        c.number_format, c.font = "0.0000", NEGRITA
        h.cell(row=i, column=7, value=f'=IF(OR($B{i}="",$C{i}=""),"",$C{i}-$B{i})')
    for j in range(1, len(cab) + 1):
        h.column_dimensions[L(j)].width = 16
    h.freeze_panes = "B2"


def _hoja_metodo(h):
    lineas = [
        ("Arraigo por VUPACI, censos 2001 y 2011 — todas las cuentas en fórmulas", True),
        ("", False),
        ("Cada censo se agrega con SU PROPIO seccionado: el lado 2001 del "
         "archivo «Seccionado VUPACI 2001 y 2011.xlsx» asigna VUPACI a las "
         "3.906 secciones de 2001, y el lado 2011 a las 4.271 de 2011. No se "
         "reutiliza ningún código de un año en el otro.", False),
        ("", False),
        ("Los cuatro tramos son los mismos en ambos censos, definidos por "
         "posición relativa a la fecha del censo:", True),
        ("          2011                    2001                 peso", False),
        ("     a    2006-2011 (6 años)      1996-2001 (6 años)     0", False),
        ("     b    2001-2005 (5 años)      1991-1995 (5 años)     0,33", False),
        ("     c    1991-2000 (10 años)     1981-1990 (10 años)    0,66", False),
        ("     d    antes de 1991           antes de 1981          1", False),
        ("", False),
        ("índice = p_a·peso_a + p_b·peso_b + p_c·peso_c + p_d·peso_d", True),
        ("donde p_X es la proporción del tramo sobre la suma de los cuatro.", False),
        ("", False),
        ("Va en decimales de 0 a 1, no en porcentaje: 0 = todos llegaron en los "
         "últimos seis años; 1 = todos llevan más de veinte.", True),
        ("", False),
        ("Los pesos están en la hoja Pesos. Cambiarlos recalcula los dos censos "
         "y la comparación.", False),
        ("", False),
        ("La columna «Total» en gris es la que publica el INE. El denominador "
         "del índice es la suma de los cuatro tramos, no esa: en 2011 difieren "
         "hasta en 15 personas por el redondeo a múltiplos de 5, y así las "
         "proporciones cierran en 1 exacto. En 2001 no hay redondeo y "
         "coinciden.", False),
        ("", False),
        ("En ámbar, las cifras que el INE marca con asterisco en 2011 (por "
         "debajo del umbral de fiabilidad de la muestra). Desaparecen al "
         "agregar los tramos, que es lo que pedía el correo.", False),
        ("", False),
        ("La VUPACI 375 no tiene secciones en 2001: no existía como territorio "
         "poblado. Su fila de comparación queda vacía.", False),
        ("", False),
        ("Dos diferencias entre censos que conviene citar: el colectivo se "
         "llama «residentes en viviendas principales» en 2011 y «residentes en "
         "viviendas familiares» en 2001; y 2001 son recuentos exactos mientras "
         "2011 viene redondeado.", False),
    ]
    for i, (txt, negrita) in enumerate(lineas, start=1):
        c = h.cell(row=i, column=1, value=txt)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if negrita:
            c.font = NEGRITA
    h.column_dimensions["A"].width = 100


def main():
    a, _ = leer_seccionado_doble()
    s01 = pd.read_csv(SEC2001, dtype={"SECCION": str}).set_index("SECCION")
    j = a.join(s01, on="sec01")
    g01 = j.groupby("vup01")[["TOTAL"] + CAT01].sum()
    g01.insert(0, "n_secciones", j.groupby("vup01").size())
    g01 = g01.rename(columns={"TOTAL": "Total"}).sort_index()

    d11 = pd.read_csv(ARR2011).set_index("VUPACI").sort_index()
    marcas11 = d11["marcadas"].to_dict()

    libro = Workbook()
    _hoja_pesos(libro.active)
    libro.active.title = "Pesos"

    h11 = libro.create_sheet("2011")
    idx11, tot11, n11 = _hoja_censo(h11, 2011, d11, CAT11, "Total INE", marcas11)
    h01 = libro.create_sheet("2001")
    idx01, tot01, n01 = _hoja_censo(h01, 2001, g01, CAT01, "Total INE")

    hc = libro.create_sheet("Comparación")
    _hoja_comparacion(hc, list(d11.index), idx11, tot11, n11, idx01, tot01, n01)
    _hoja_metodo(libro.create_sheet("Método"))

    libro.move_sheet("Comparación", offset=-3)
    libro.save(SALIDA)
    print(f"2011: {n11} VUPACI | 2001: {n01} VUPACI | índice en decimales 0-1")
    print("Excel:", SALIDA)


if __name__ == "__main__":
    main()
