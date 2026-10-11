# -*- coding: utf-8 -*-
"""
El mismo cuadro que en 2011, pero con el censo 2001: personas por año de
llegada a la vivienda, agregadas por VUPACI, usando la lista de secciones del
seccionado (que es de 2011), y **marcando qué secciones no existen en 2001**.

AVISO IMPORTANTE, y por eso la columna `fiabilidad`:

  que un código de sección exista en los dos censos NO significa que sea el
  mismo territorio. Entre 2001 y 2011 el seccionado se rehízo en los municipios
  que crecieron (Alcalá de Henares pasó de 8 distritos a 5, Madrid capital de
  ~2.300 secciones a 2.409). En esos municipios el código 2800504007 existe en
  ambos años y designa sitios distintos.

  Sólo son exactos los VUPACI marcados como "exacta": aquellos en los que cada
  municipio, o entra entero (y entonces da igual cómo estuviera seccionado por
  dentro), o conservó su seccionado idéntico entre los dos censos.

  Los demás salen calculados, pero son una aproximación cuyo error no se puede
  acotar sin cruzar las cartografías de los dos años.

Salidas:
  salidas/Arraigo 2001 por VUPACI.xlsx
  salidas/secciones_2011_en_2001.csv   una fila por sección, con si aparece o no
"""

import os

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from descargar_arraigo import leer_seccionado

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SEC2001 = os.path.join(RAIZ, "salidas", "censo2001_secciones_madrid.csv")
IND2011 = os.path.join(RAIZ, "datos", "ine", "csv", "C2011_ccaa13_Indicadores.csv")
XLSX = os.path.join(RAIZ, "salidas", "Arraigo 2001 por VUPACI.xlsx")
CSV_SEC = os.path.join(RAIZ, "salidas", "secciones_2011_en_2001.csv")

CAT = ["2001", "2000", "1999", "1998", "1997", "1996", "1991-1995",
       "1981-1990", "1971-1980", "1961-1970", "1941-1960", "Antes de 1941"]

# tramos por posición relativa al censo (los mismos que en 2011, corridos 10 años)
TRAMOS = {"a_ultimos_6": (["2001", "2000", "1999", "1998", "1997", "1996"], 0.00),
          "b_5_previos": (["1991-1995"], 0.33),
          "c_10_previos": (["1981-1990"], 0.66),
          "d_resto": (["1971-1980", "1961-1970", "1941-1960", "Antes de 1941"], 1.00)}


def main():
    grupos = leer_seccionado()
    s01 = pd.read_csv(SEC2001, dtype={"SECCION": str}).set_index("SECCION")
    sec01 = set(s01.index)

    ind = pd.read_csv(IND2011, dtype=str)
    ind["S"] = (ind.cpro.str.zfill(2) + ind.cmun.str.zfill(3)
                + ind.dist.str.zfill(2) + ind.secc.str.zfill(3))
    mun11 = ind.groupby(ind.S.str[:5])["S"].apply(set).to_dict()
    mun01 = {}
    for s in sec01:
        mun01.setdefault(s[:5], set()).add(s)
    identicos = {m for m in mun11 if mun01.get(m) == mun11[m]}

    filas, detalle = [], []
    for v in sorted(grupos):
        secs = grupos[v]
        muns = sorted({x[:5] for x in secs})
        enteros = {m for m in muns if mun11.get(m, set()) <= set(secs)}
        exacta = all(m in enteros or m in identicos for m in muns)

        # para un municipio que entra entero se usan TODAS sus secciones de
        # 2001; para el resto, los códigos tal cual (que es lo aproximado)
        usar, faltan = [], []
        for m in muns:
            if m in enteros:
                usar += sorted(mun01.get(m, set()))
            else:
                for s in (x for x in secs if x.startswith(m)):
                    (usar if s in sec01 else faltan).append(s)
        for s in secs:
            detalle.append({"SECCION": s, "VUPACI": v, "cmun": s[:5],
                            "existe_en_2001": s in sec01,
                            "municipio_entero": s[:5] in enteros,
                            "seccionado_identico": s[:5] in identicos})

        sub = s01.reindex(sorted(set(usar)))
        fila = {"VUPACI": v,
                "fiabilidad": "exacta" if exacta else "aproximada",
                "n_secciones_2011": len(secs),
                "n_encontradas_2001": sum(1 for s in secs if s in sec01),
                "n_no_aparecen": len([s for s in secs if s not in sec01]),
                "secciones_que_faltan": " ".join(sorted(faltan)) or ""}
        fila["Total"] = int(sub["TOTAL"].sum())
        for c in CAT:
            fila[c] = int(sub[c].sum())
        tramos = {k: int(sub[cols].sum().sum()) for k, (cols, _) in TRAMOS.items()}
        fila.update(tramos)
        tot = sum(tramos.values())
        fila["indice_arraigo_2001"] = round(
            sum(tramos[k] / tot * peso
                for k, (_, peso) in TRAMOS.items()) * 100, 2) if tot else None
        filas.append(fila)

    df = pd.DataFrame(filas).set_index("VUPACI")
    pd.DataFrame(detalle).to_csv(CSV_SEC, index=False)

    with pd.ExcelWriter(XLSX, engine="openpyxl") as xls:
        df.reset_index().to_excel(xls, sheet_name="Arraigo 2001", index=False)
        faltan = pd.DataFrame(detalle)
        faltan[~faltan["existe_en_2001"]].to_excel(
            xls, sheet_name="Secciones que no aparecen", index=False)
        _hoja_aviso(xls.book, df)
        _formatear(xls.book, df)

    ex = (df["fiabilidad"] == "exacta").sum()
    print(f"489 VUPACI | exactos: {ex} | aproximados: {len(df) - ex}")
    print(f"secciones que no aparecen en 2001: {int(df['n_no_aparecen'].sum())} "
          f"de {int(df['n_secciones_2011'].sum())}")
    print(f"VUPACI con todas sus secciones presentes: "
          f"{int((df['n_no_aparecen'] == 0).sum())}")
    print(f"\n{XLSX}\n{CSV_SEC}")


def _hoja_aviso(libro, df):
    h = libro.create_sheet("Leer antes de usar", 0)
    ex = (df["fiabilidad"] == "exacta").sum()
    lineas = [
        ("Arraigo 2001 por VUPACI — qué se puede usar y qué no", True),
        ("", False),
        ("El seccionado VUPACI es de 2011. Entre 2001 y 2011 el INE rehízo las "
         "secciones censales de los municipios que crecieron: Alcalá de Henares "
         "pasó de 8 distritos a 5, y Madrid capital de unas 2.300 secciones a "
         "2.409. En esos municipios un código como 2800504007 existe en los dos "
         "censos y NO designa el mismo territorio.", False),
        ("", False),
        (f"Por eso la columna «fiabilidad»:", True),
        (f"· exacta ({ex} VUPACI): cada municipio del grupo o entra entero —y "
         "entonces da igual cómo estuviera seccionado por dentro— o conservó su "
         "seccionado idéntico. Estos son comparables con 2011 sin reservas.", False),
        (f"· aproximada ({len(df)-ex} VUPACI): el grupo parte municipios que se "
         "reseccionaron. La cifra sale calculada, pero mezcla territorio que en "
         "2011 no es el mismo. El error no se puede acotar sin cruzar las "
         "cartografías de los dos años.", False),
        ("", False),
        ("Las columnas n_encontradas_2001, n_no_aparecen y secciones_que_faltan "
         "dicen cuánto del grupo se pudo localizar. Ojo: que una sección "
         "«aparezca» sólo quiere decir que el código existe en 2001, no que sea "
         "el mismo sitio.", False),
        ("", False),
        ("El índice usa los mismos tramos que 2011, por posición relativa al "
         "censo: los seis últimos años (peso 0), los cinco previos (0,33), los "
         "diez previos (0,66) y el resto (1).", False),
        ("", False),
        ("Para tener los 489 bien hay un solo camino: cruzar geométricamente el "
         "seccionado de 2001 con el de 2011 en QGIS. El dato de 2001 por "
         "sección ya está bajado (salidas/censo2001_secciones_madrid.csv).", True),
    ]
    for i, (txt, negrita) in enumerate(lineas, start=1):
        c = h.cell(row=i, column=1, value=txt)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if negrita:
            c.font = Font(bold=True)
    h.column_dimensions["A"].width = 110


def _formatear(libro, df):
    h = libro["Arraigo 2001"]
    negrita = Font(bold=True)
    ambar_f, ambar_r = Font(color="B45309", bold=True), PatternFill("solid", fgColor="FEF3C7")
    verde = Font(color="15803D", bold=True)
    for c in h[1]:
        c.font = negrita
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    cab = [c.value for c in h[1]]
    col_f = cab.index("fiabilidad") + 1
    col_n = cab.index("n_no_aparecen") + 1
    for i in range(2, h.max_row + 1):
        celda = h.cell(row=i, column=col_f)
        if celda.value == "exacta":
            celda.font = verde
        else:
            celda.font, celda.fill = ambar_f, ambar_r
        if (h.cell(row=i, column=col_n).value or 0) > 0:
            h.cell(row=i, column=col_n).font = ambar_f
    for j in range(1, h.max_column + 1):
        h.column_dimensions[get_column_letter(j)].width = 13
    h.column_dimensions[get_column_letter(cab.index("secciones_que_faltan") + 1)].width = 40
    h.freeze_panes = "B2"
    for nombre in ("Secciones que no aparecen",):
        hh = libro[nombre]
        for c in hh[1]:
            c.font = negrita
        for j in range(1, hh.max_column + 1):
            hh.column_dimensions[get_column_letter(j)].width = 17


if __name__ == "__main__":
    main()
