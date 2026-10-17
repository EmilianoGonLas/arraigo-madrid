# Arma los datos que consume la Shiny, a partir de todo lo descargado.
#
# Produce dos objetos:
#   resumen.rds      una fila por VUPACI y censo: población, tramos e índice
#   indicadores.rds  formato largo: VUPACI, censo, rama, variable, categoría, personas
#
# El panel de 2011 (83 variables) se está descargando todavía: este script toma
# lo que haya y se puede volver a correr cuando termine.

suppressPackageStartupMessages({
  library(dplyr); library(readr); library(readxl); library(tidyr); library(purrr)
})

raiz <- "."
stopifnot(dir.exists(file.path(raiz, "datos")))
destino <- file.path(raiz, "app", "datos")
dir.create(destino, recursive = TRUE, showWarnings = FALSE)

CAT11 <- c("2011","2010","2009","2008","2007","2006","2001-2005","1991-2000",
           "1981-1990","1971-1980","Antes de 1971")
CAT01 <- c("2001","2000","1999","1998","1997","1996","1991-1995","1981-1990",
           "1971-1980","1961-1970","1941-1960","Antes de 1941")
# los cuatro tramos, por posición relativa a la fecha del censo
TRAMOS <- list(
  `2011` = list(a = CAT11[1:6], b = CAT11[7], c = CAT11[8], d = CAT11[9:11]),
  `2001` = list(a = CAT01[1:6], b = CAT01[7], c = CAT01[8], d = CAT01[9:12]))
PESOS <- c(a = 0, b = 0.33, c = 0.66, d = 1)

indice <- function(df, cats, tramos) {
  t <- imap_dfc(tramos, function(cols, nom) {
    set_names(tibble(rowSums(df[, cols, drop = FALSE], na.rm = TRUE)), nom)
  })
  suma <- rowSums(t)
  tibble(
    a = t$a, b = t$b, c = t$c, d = t$d, suma_tramos = suma,
    indice_arraigo = rowSums(sweep(as.matrix(t), 2, PESOS[names(tramos)], `*`)) / suma)
}

# --- 2011: año de llegada por VUPACI -----------------------------------------
a11 <- read_csv(file.path(raiz, "salidas", "arraigo_por_vupaci.csv"),
                show_col_types = FALSE)
r11 <- bind_cols(
  tibble(VUPACI = a11$VUPACI, censo = 2011L, poblacion = a11$Total,
         n_secciones = a11$n_secciones),
  indice(a11, CAT11, TRAMOS[["2011"]]))

# --- 2001: se agrega desde las secciones con el seccionado de ese año --------
sec <- read_excel(file.path(raiz, "datos", "originales",
                            "Seccionado VUPACI 2001 y 2011.xlsx"), skip = 1)
names(sec) <- c("sec01","vup01","x","vup11","sec11")
asig01 <- sec |> filter(!is.na(sec01)) |>
  transmute(SECCION = sprintf("%010.0f", as.numeric(sec01)),
            VUPACI = as.integer(vup01))
s01 <- read_csv(file.path(raiz, "salidas", "censo2001_secciones_madrid.csv"),
                col_types = cols(SECCION = col_character(), .default = col_double()))
a01 <- asig01 |> inner_join(s01, by = "SECCION") |>
  group_by(VUPACI) |>
  summarise(n_secciones = n(), across(all_of(c("TOTAL", CAT01)), \(x) sum(x, na.rm = TRUE)),
            .groups = "drop")
r01 <- bind_cols(
  tibble(VUPACI = a01$VUPACI, censo = 2001L, poblacion = a01$TOTAL,
         n_secciones = a01$n_secciones),
  indice(a01, CAT01, TRAMOS[["2001"]]))

resumen <- bind_rows(r01, r11) |> arrange(VUPACI, censo)
saveRDS(resumen, file.path(destino, "resumen.rds"), compress = "xz")

# --- indicadores en formato largo --------------------------------------------
largo <- bind_rows(
  a11 |> select(VUPACI, all_of(CAT11)) |>
    pivot_longer(-VUPACI, names_to = "categoria", values_to = "personas") |>
    mutate(censo = 2011L, rama = "Años de llegada",
           variable = "Año de llegada a la vivienda"),
  a01 |> select(VUPACI, all_of(CAT01)) |>
    pivot_longer(-VUPACI, names_to = "categoria", values_to = "personas") |>
    mutate(censo = 2001L, rama = "Años de llegada",
           variable = "Año de llegada a la vivienda"))

# el panel de 2011, si ya hay algo descargado
panel <- file.path(raiz, "datos", "censo2011", "panel_2011.csv")
if (file.exists(panel)) {
  bruto <- read_csv(panel, show_col_types = FALSE)

  # El INE devuelve a veces la tabla truncada: el Total correcto pero sólo
  # parte de las categorías. Eso no se nota en la población total -por eso
  # pasó el control contra el fichero de indicadores- pero el desglose queda
  # mal y mostrarlo sería mentir. Las categorías tienen que sumar el Total,
  # con 5 de margen por categoría por el redondeo del secreto estadístico.
  # El 17/10/2026 esto excluía 2 pares de 24.991: al VUPACI 142 le faltaban
  # 3 de 9 categorías de estudios y al 237 dos tramos de año de construcción.
  control <- bruto |>
    group_by(VUPACI, variable) |>
    summarise(total = sum(personas[categoria == "Total"], na.rm = TRUE),
              suma  = sum(personas[categoria != "Total"], na.rm = TRUE),
              ncat  = sum(categoria != "Total"), .groups = "drop") |>
    mutate(sirve = abs(suma - total) <= 5 * pmax(ncat, 1))

  malas <- control |> filter(!sirve)
  if (nrow(malas)) {
    message(sprintf("panel 2011: excluyo %d desgloses truncados de %d",
                    nrow(malas), nrow(control)))
    for (i in seq_len(nrow(malas)))
      message(sprintf("    VUPACI %d: %s (suman %d, Total %d)",
                      malas$VUPACI[i], malas$variable[i],
                      malas$suma[i], malas$total[i]))
  }

  p <- bruto |>
    semi_join(control |> filter(sirve), by = c("VUPACI", "variable")) |>
    filter(categoria != "Total") |>
    transmute(VUPACI, censo = 2011L, rama, variable, categoria, personas)
  largo <- bind_rows(largo, p)
  message(sprintf("panel 2011: %d VUPACI, %d variables",
                  n_distinct(p$VUPACI), n_distinct(p$variable)))
} else {
  message("panel 2011 todavía no disponible")
}

largo <- largo |> select(VUPACI, censo, rama, variable, categoria, personas)
saveRDS(largo, file.path(destino, "indicadores.rds"), compress = "xz")

message(sprintf("\nresumen    : %d filas (%d VUPACI x censo)", nrow(resumen),
                n_distinct(resumen$VUPACI)))
message(sprintf("indicadores: %d filas, %d variables", nrow(largo),
                n_distinct(largo$variable)))
message(sprintf("índice 2001 medio %.3f | 2011 medio %.3f",
                mean(r01$indice_arraigo, na.rm = TRUE),
                mean(r11$indice_arraigo, na.rm = TRUE)))
for (f in list.files(destino, full.names = TRUE))
  message(sprintf("  %-22s %6.1f KB", basename(f), file.size(f)/1024))
