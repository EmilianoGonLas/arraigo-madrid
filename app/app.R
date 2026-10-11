# Arraigo residencial en la Comunidad de Madrid, por VUPACI
#
# Dos censos (2001 y 2011), cada uno agregado con su propio seccionado.
# Los datos los prepara R/01_preparar_geometrias.R y R/02_preparar_datos.R.

library(shiny); library(bslib); library(leaflet); library(sf)
library(dplyr); library(tidyr); library(ggplot2); library(DT); library(scales)

ruta <- function(x) file.path("datos", x)
geo <- list(`2001` = readRDS(ruta("vupaci_2001.rds")),
            `2011` = readRDS(ruta("vupaci_2011.rds")))
resumen <- readRDS(ruta("resumen.rds"))
indicadores <- readRDS(ruta("indicadores.rds"))

CENSOS <- sort(unique(resumen$censo))
VARIABLES <- indicadores |> distinct(rama, variable) |> arrange(rama, variable)
opciones_var <- split(VARIABLES$variable, VARIABLES$rama)

# el índice va de 0 a 1: 0 = todos recién llegados, 1 = todos de hace más de 20 años
paleta_indice <- function(x) colorNumeric("YlGnBu", domain = c(0, 1), na.color = "#eeeeee")(x)

ui <- page_sidebar(
  title = "Arraigo residencial en Madrid · censos 2001 y 2011",
  theme = bs_theme(version = 5, preset = "flatly"),
  sidebar = sidebar(
    width = 330,
    radioButtons("vista", "Qué mapear",
                 c("Índice de arraigo" = "indice",
                   "Variación 2001 → 2011" = "variacion",
                   "Una variable del censo" = "variable"),
                 selected = "indice"),
    conditionalPanel(
      "input.vista != 'variacion'",
      selectInput("censo", "Censo", choices = CENSOS, selected = max(CENSOS))),
    conditionalPanel(
      "input.vista == 'variable'",
      selectInput("variable", "Variable", choices = opciones_var,
                  selected = "Año de llegada a la vivienda"),
      selectInput("categoria", "Categoría", choices = NULL),
      helpText("Se mapea el porcentaje que representa esa categoría ",
               "sobre el total del VUPACI.")),
    hr(),
    uiOutput("ficha"),
    hr(),
    helpText(HTML(
      "Fuente: INE, Censos de Población y Viviendas.<br>",
      "Cada censo se agrega con su propio seccionado, así que las cifras ",
      "de 2001 y 2011 son comparables."))
  ),
  layout_columns(
    col_widths = c(7, 5),
    card(full_screen = TRUE, card_header("Mapa"),
         leafletOutput("mapa", height = 620)),
    navset_card_tab(
      nav_panel("Año de llegada", plotOutput("grafico_llegada", height = 290),
                plotOutput("grafico_tramos", height = 260)),
      nav_panel("Composición", plotOutput("grafico_variable", height = 560)),
      nav_panel("Tabla", DTOutput("tabla"))
    )
  )
)

server <- function(input, output, session) {

  observeEvent(input$variable, {
    cats <- indicadores |> filter(variable == input$variable) |>
      distinct(categoria) |> pull(categoria)
    updateSelectInput(session, "categoria", choices = cats, selected = cats[1])
  })

  seleccionado <- reactiveVal(NULL)

  # --- qué se pinta -----------------------------------------------------------
  capa <- reactive({
    if (input$vista == "variacion") {
      d <- resumen |> select(VUPACI, censo, indice_arraigo) |>
        pivot_wider(names_from = censo, values_from = indice_arraigo,
                    names_prefix = "i") |>
        mutate(valor = i2011 - i2001)
      g <- geo[["2011"]] |> left_join(d, by = "VUPACI")
      lista <- list(g = g, dominio = max(abs(g$valor), na.rm = TRUE) * c(-1, 1),
                    paleta = "RdBu", etiqueta = "Variación del índice",
                    fmt = function(x) sprintf("%+.3f", x))
    } else if (input$vista == "indice") {
      d <- resumen |> filter(censo == as.integer(input$censo)) |>
        transmute(VUPACI, valor = indice_arraigo)
      g <- geo[[input$censo]] |> left_join(d, by = "VUPACI")
      lista <- list(g = g, dominio = c(0, 1), paleta = "YlGnBu",
                    etiqueta = "Índice de arraigo",
                    fmt = function(x) sprintf("%.3f", x))
    } else {
      tot <- indicadores |> filter(censo == as.integer(input$censo),
                                   variable == input$variable) |>
        group_by(VUPACI) |> summarise(total = sum(personas, na.rm = TRUE),
                                      .groups = "drop")
      d <- indicadores |>
        filter(censo == as.integer(input$censo), variable == input$variable,
               categoria == input$categoria) |>
        group_by(VUPACI) |> summarise(n = sum(personas, na.rm = TRUE),
                                      .groups = "drop") |>
        left_join(tot, by = "VUPACI") |>
        transmute(VUPACI, valor = ifelse(total > 0, 100 * n / total, NA_real_))
      g <- geo[[input$censo]] |> left_join(d, by = "VUPACI")
      lista <- list(g = g, dominio = range(g$valor, na.rm = TRUE),
                    paleta = "YlOrRd", etiqueta = paste0("% ", input$categoria),
                    fmt = function(x) sprintf("%.1f %%", x))
    }
    lista
  })

  output$mapa <- renderLeaflet({
    leaflet() |>
      addProviderTiles(providers$OpenStreetMap.Mapnik,
                       options = providerTileOptions(opacity = 0.55)) |>
      setView(lng = -3.70, lat = 40.42, zoom = 9)
  })

  observe({
    cp <- capa()
    g <- cp$g
    if (all(is.na(g$valor))) {
      leafletProxy("mapa") |> clearShapes() |> clearControls()
      return()
    }
    pal <- colorNumeric(cp$paleta, domain = cp$dominio, na.color = "#e9e9e9",
                        reverse = (cp$paleta == "RdBu"))
    etiquetas <- sprintf(
      "<strong>VUPACI %s</strong><br>%s: %s<br>%s secciones",
      g$VUPACI, cp$etiqueta, cp$fmt(g$valor), g$n_secciones) |>
      lapply(htmltools::HTML)
    leafletProxy("mapa", data = g) |>
      clearShapes() |> clearControls() |>
      addPolygons(
        layerId = ~VUPACI, fillColor = ~pal(valor), fillOpacity = 0.85,
        color = "white", weight = 0.4,
        highlightOptions = highlightOptions(weight = 2, color = "#333",
                                            bringToFront = TRUE),
        label = etiquetas) |>
      addLegend("bottomright", pal = pal, values = cp$dominio,
                title = cp$etiqueta, opacity = 0.9)
  })

  observeEvent(input$mapa_shape_click, seleccionado(input$mapa_shape_click$id))

  # --- panel lateral ----------------------------------------------------------
  output$ficha <- renderUI({
    v <- seleccionado()
    if (is.null(v)) return(helpText("Hacé clic en un VUPACI del mapa."))
    d <- resumen |> filter(VUPACI == v) |> arrange(censo)
    filas <- apply(d, 1, function(r) sprintf(
      "<tr><td>%s</td><td style='text-align:right'>%s</td><td style='text-align:right'>%.3f</td></tr>",
      r[["censo"]], formatC(as.numeric(r[["poblacion"]]), format = "d", big.mark = "."),
      as.numeric(r[["indice_arraigo"]])))
    HTML(paste0(
      "<strong>VUPACI ", v, "</strong>",
      "<table class='table table-sm' style='margin-top:.5rem'>",
      "<thead><tr><th>Censo</th><th style='text-align:right'>Población</th>",
      "<th style='text-align:right'>Índice</th></tr></thead><tbody>",
      paste(filas, collapse = ""), "</tbody></table>"))
  })

  output$grafico_llegada <- renderPlot({
    v <- seleccionado(); req(v)
    d <- indicadores |>
      filter(VUPACI == v, variable == "Año de llegada a la vivienda") |>
      group_by(censo) |> mutate(pct = 100 * personas / sum(personas, na.rm = TRUE)) |>
      ungroup() |> mutate(categoria = factor(categoria, levels = unique(categoria)))
    ggplot(d, aes(categoria, pct, fill = factor(censo))) +
      geom_col(position = "dodge") +
      scale_fill_manual(values = c(`2001` = "#8c6bb1", `2011` = "#238b45"),
                        name = "Censo") +
      labs(title = paste("VUPACI", v, "— año de llegada a la vivienda"),
           x = NULL, y = "% de la población") +
      theme_minimal(base_size = 12) +
      theme(axis.text.x = element_text(angle = 45, hjust = 1),
            legend.position = "top")
  })

  output$grafico_tramos <- renderPlot({
    v <- seleccionado(); req(v)
    d <- resumen |> filter(VUPACI == v) |>
      select(censo, a, b, c, d) |>
      pivot_longer(-censo, names_to = "tramo", values_to = "personas") |>
      group_by(censo) |> mutate(pct = 100 * personas / sum(personas)) |> ungroup() |>
      mutate(tramo = recode(tramo,
        a = "a · últimos 6 años", b = "b · 5 previos",
        c = "c · 10 previos", d = "d · anteriores"))
    ggplot(d, aes(factor(censo), pct, fill = tramo)) +
      geom_col() +
      scale_fill_brewer(palette = "BuPu", name = NULL) +
      labs(title = "Tramos que componen el índice", x = "Censo", y = "%") +
      theme_minimal(base_size = 12) + theme(legend.position = "right")
  })

  output$grafico_variable <- renderPlot({
    v <- seleccionado(); req(v, input$variable)
    d <- indicadores |>
      filter(VUPACI == v, variable == input$variable) |>
      group_by(censo) |> mutate(pct = 100 * personas / sum(personas, na.rm = TRUE)) |>
      ungroup()
    validate(need(nrow(d) > 0, "Esa variable todavía no está descargada para este VUPACI."))
    ggplot(d, aes(reorder(categoria, pct), pct, fill = factor(censo))) +
      geom_col(position = "dodge") + coord_flip() +
      scale_fill_manual(values = c(`2001` = "#8c6bb1", `2011` = "#238b45"),
                        name = "Censo") +
      labs(title = paste("VUPACI", v, "—", input$variable),
           x = NULL, y = "% de la población") +
      theme_minimal(base_size = 12) + theme(legend.position = "top")
  })

  output$tabla <- renderDT({
    resumen |>
      select(VUPACI, censo, n_secciones, poblacion, indice_arraigo) |>
      mutate(indice_arraigo = round(indice_arraigo, 4)) |>
      datatable(rownames = FALSE, filter = "top",
                options = list(pageLength = 15, dom = "tip"),
                colnames = c("VUPACI", "Censo", "Secciones", "Población",
                             "Índice de arraigo"))
  })
}

shinyApp(ui, server)
