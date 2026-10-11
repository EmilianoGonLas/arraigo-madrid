# Geometrías por VUPACI para los censos 2001 y 2011.
#
# Cada censo tiene su propio seccionado, así que las VUPACI se construyen
# disolviendo las secciones de cada año por separado, con la asignación que
# trae "Seccionado VUPACI 2001 y 2011.xlsx".
#
# Salida: app/datos/vupaci_2001.rds y vupaci_2011.rds (sf, EPSG:4326)

suppressPackageStartupMessages({
  library(sf); library(dplyr); library(readxl)
})

# se ejecuta desde la raíz del proyecto
raiz <- "."
stopifnot(dir.exists(file.path(raiz, "datos")))

carto <- file.path(raiz, "datos", "cartografia", "madrid")
destino <- file.path(raiz, "app", "datos")
dir.create(destino, recursive = TRUE, showWarnings = FALSE)

# --- el seccionado doble -----------------------------------------------------
sec <- read_excel(file.path(raiz, "datos", "originales",
                            "Seccionado VUPACI 2001 y 2011.xlsx"), skip = 1)
names(sec) <- c("sec01", "vup01", "x", "vup11", "sec11")

asig01 <- sec |>
  filter(!is.na(sec01)) |>
  transmute(CUSEC = sprintf("%010.0f", as.numeric(sec01)), VUPACI = as.integer(vup01))
asig11 <- sec |>
  filter(!is.na(sec11)) |>
  transmute(CUSEC = sprintf("%010.0f", as.numeric(sec11)), VUPACI = as.integer(vup11))

message(sprintf("asignación 2001: %d secciones, %d VUPACI",
                nrow(asig01), n_distinct(asig01$VUPACI)))
message(sprintf("asignación 2011: %d secciones, %d VUPACI",
                nrow(asig11), n_distinct(asig11$VUPACI)))

# --- disolver ----------------------------------------------------------------
construir <- function(gpkg, asignacion, etiqueta) {
  g <- st_read(gpkg, quiet = TRUE)
  if (!"CUSEC" %in% names(g)) {            # el de 2001 trae los códigos sueltos
    g <- g |> mutate(CUSEC = paste0(PROVMUN, DISTRITO, SECCION))
  }
  g <- g |> select(CUSEC) |> st_make_valid()

  sin_geo <- setdiff(asignacion$CUSEC, g$CUSEC)
  sin_asig <- setdiff(g$CUSEC, asignacion$CUSEC)
  message(sprintf("%s: %d secciones en la capa | sin geometría: %d | sin VUPACI: %d",
                  etiqueta, nrow(g), length(sin_geo), length(sin_asig)))

  v <- g |>
    inner_join(asignacion, by = "CUSEC") |>
    group_by(VUPACI) |>
    summarise(n_secciones = n(), .groups = "drop") |>
    st_make_valid()

  # aligerar para el mapa sin romper la topología visible
  v <- st_simplify(v, dTolerance = 15, preserveTopology = TRUE) |> st_make_valid()
  message(sprintf("%s: %d VUPACI disueltos", etiqueta, nrow(v)))
  v
}

v01 <- construir(file.path(carto, "secc_2001.gpkg"), asig01, "2001")
v11 <- construir(file.path(carto, "secc_2011.gpkg"), asig11, "2011")

saveRDS(v01, file.path(destino, "vupaci_2001.rds"), compress = "xz")
saveRDS(v11, file.path(destino, "vupaci_2011.rds"), compress = "xz")

message(sprintf("\nguardado en %s", destino))
for (f in list.files(destino, full.names = TRUE)) {
  message(sprintf("  %-22s %6.1f KB", basename(f), file.size(f) / 1024))
}
