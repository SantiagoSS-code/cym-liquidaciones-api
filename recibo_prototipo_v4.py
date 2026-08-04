"""
Prototipo v4 del recibo de sueldo - reportlab Platypus (tablas reales).

Cambios vs v3:
- Encabezado reescrito siguiendo la estructura REAL del Excel modelo oficial
  (Recibo_sueldo_EDITABLE_Anexo_III_decreto_407_art_140_LCT_ignacio_online.xlsx),
  no la referencia vieja de Turismo/Hotelería.
- Se saca "SON PESOS" y la dependencia de num2words (pertenecía a la fuente
  incorrecta). Se reemplaza por "Recibí la suma de: ..." + "Depositado en:",
  tal como aparece en el Excel modelo.
- Contribuciones patronales: se mantienen las 3 alícuotas desglosadas
  (Jubilación / FNE / Asignaciones Familiares) y ART/FFEP separados —así
  seguimos usando los valores reales confirmados por el contador— pero se
  agrupan visualmente bajo el mismo orden y títulos de sección que el Excel
  (ART+FFEP primero, después el bloque de Jubilación/SIPA, luego Obra Social,
  Seguro de Vida Obligatorio, subtítulo "Costo derivado del CCT", y ahí
  OSECAC/INACAP/La Estrella/Seguro Vida CCT 130-75).
- Sueldo bruto: se agregan subtítulos REMUNERATIVO / NO REMUNERATIVO /
  DESCUENTOS dentro de la misma tabla, como en el Excel.
- Detalle de composición salarial + torta: se agrega PAMI (Total costo
  INSSJP) como categoría propia, separada de Obra Social, siguiendo el Excel.

TODOs marcados explícitamente en el código (ver comentarios "# TODO"):
- Confirmar si calcular_contribuciones_patronales() real ya separa ART y
  FFEP en dos campos del dict `contrib`, o si hay que separarlos ahí.
- PAMI/INSSJP patronal: no confirmado como concepto separado para TV Crecer.
  Se deja en $0 con esta nota, NO se inventa un valor.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Frame
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend

GRIS_HEADER = colors.HexColor("#D9D9D9")
GRIS_CLARO = colors.HexColor("#F2F2F2")
ANCHO_TOTAL = 180 * mm  # ancho de contenido consistente en TODAS las tablas


def fmt(n):
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(n):
    s = f"{n*100:.3f}".rstrip("0").rstrip(".")
    return f"{s}%"


def fmt_cuil(cuil_digits):
    d = str(cuil_digits or "")
    if len(d) != 11:
        return d
    return f"{d[0:2]}-{d[2:10]}-{d[10]}"


def fmt_fecha(dt):
    if dt is None:
        return ""
    return dt.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# ENCABEZADO — reescrito siguiendo la estructura real del Excel modelo
# ---------------------------------------------------------------------------

def construir_titulo_empresa(empresa_config):
    """Título 'Recibo de Haberes Ley 20.744' + nombre empresa + CUIT."""
    data = [
        ["Recibo de Haberes Ley 20.744"],
        [empresa_config["nombre"]],
        [f"C.U.I.T. EMPRESA: {empresa_config.get('cuit', '')}"],
    ]
    t = Table(data, colWidths=[ANCHO_TOTAL])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, 0), 11),
        ("FONTSIZE", (0, 1), (0, 2), 8),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def construir_fila_periodo_empleado(emp, r, periodo_txt, numero_recibo=""):
    """Fila: Q. | MES/AÑO | APELLIDO Y NOMBRE | N°LEGAJO | SUELDO BRUTO | ANTIGÜEDAD"""
    header = ["Q.", "MES / AÑO", "APELLIDO Y NOMBRE", "N° LEGAJO", "SUELDO BRUTO", "ANTIGÜEDAD"]
    antiguedad_txt = f"{r.get('antiguedad_anios', 0)} años" if r.get("antiguedad_anios") is not None else ""
    valores = [
        numero_recibo,
        periodo_txt,
        emp["nombre"].upper(),
        emp.get("legajo", ""),
        f"$ {fmt(r['base_rem'])}",
        antiguedad_txt,
    ]
    t = Table([header, valores], colWidths=[ANCHO_TOTAL * w for w in (0.06, 0.14, 0.32, 0.14, 0.20, 0.14)])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HEADER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_fila_datos_adicionales(emp, empresa_config, periodo_dt, fecha_pago_aportes):
    """Fila: FECHA INGRESO | CATEGORÍA LABORAL | C.U.I.L. | Banco | Período | F.PAGO APORTES"""
    header = ["FECHA INGRESO", "CATEGORÍA LABORAL", "C.U.I.L.", "Banco", "Período", "F.PAGO APORTES"]
    valores = [
        fmt_fecha(emp.get("fecha_ingreso")),
        emp.get("categoria", ""),
        fmt_cuil(emp.get("cuil", "")),
        emp.get("banco", "") or empresa_config.get("medio_pago", "Transf. Bancaria"),
        fmt_fecha(periodo_dt),
        fmt_fecha(fecha_pago_aportes),
    ]
    t = Table([header, valores], colWidths=[ANCHO_TOTAL * w for w in (0.16, 0.20, 0.18, 0.14, 0.16, 0.16)])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HEADER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_barra_titulo(texto, total):
    data = [[texto, f"$ {fmt(total)}"]]
    t = Table(data, colWidths=[ANCHO_TOTAL * 0.75, ANCHO_TOTAL * 0.25])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_HEADER),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# ---------------------------------------------------------------------------
# COSTO TOTAL EMPLEADOR — mismo orden/títulos de sección que el Excel,
# pero con ART/FFEP y Jubilación/FNE/Asig.Familiares desglosados
# ---------------------------------------------------------------------------

def construir_tabla_contribuciones(contrib, empresa_config, base_rem):
    header = ["CONCEPTO", "UNIDAD", "BASE", "MONTO"]
    data = [header]

    def fila(desc, unidad, base, monto):
        data.append([desc, unidad, base, fmt(monto)])

    def subtitulo(texto):
        data.append([texto, "", "", ""])

    # --- Bloque ART + FFEP (Excel los junta en una línea; nosotros los
    #     mantenemos separados porque tenemos los valores reales) ---
    fila("ART", fmt_pct(empresa_config.get("alicuota_art", 0)), fmt(base_rem), contrib["art"])
    # TODO: confirmar si calcular_contribuciones_patronales() real ya trae
    # "ffep" como campo separado de "art". Acá se asume que sí.
    fila("ART - Componente Fijo (FFEP)", "Fijo mensual", "-", contrib.get("ffep", 0))

    # --- Bloque Jubilación/SIPA (Excel lo junta en una línea; nosotros lo
    #     mantenemos separado: Jubilación patronal, FNE, Asig. Familiares) ---
    fila("Contribución Jubilación (SIPA)",
         fmt_pct(0.1077 if empresa_config.get("pyme") else 0.127),
         fmt(base_rem), contrib["jubilacion_patronal"])
    fila("Fondo Nacional de Empleo", fmt_pct(0.0094), fmt(base_rem), contrib["fne"])
    fila("Asignaciones Familiares", fmt_pct(empresa_config.get("alicuota_asig_familiares", 0)),
         fmt(base_rem), contrib["asignaciones_familiares"])

    fila("Contribución Obra Social", fmt_pct(0.06), fmt(base_rem), contrib["obra_social_patronal"])
    fila("Seguro de Vida Obligatorio", "Fijo", fmt(contrib["seguro_vida"]), contrib["seguro_vida"])

    subtitulo("Costo derivado del CCT")
    fila("Contribución OSECAC", "Fijo por empleado", "-", contrib["contrib_extraordinaria_osecac"])
    fila("Contribución INACAP", "Fijo mensual", "-", contrib["inacap"])
    fila("Seguro de Retiro La Estrella", fmt_pct(0.016), fmt(base_rem), contrib["seguro_la_estrella"])
    if "seguro_vida_cct130" in contrib:
        fila("Seguro de Vida CCT 130/75", "Fijo", "-", contrib["seguro_vida_cct130"])

    t = Table(data, colWidths=[ANCHO_TOTAL * 0.45, ANCHO_TOTAL * 0.20, ANCHO_TOTAL * 0.15, ANCHO_TOTAL * 0.20])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    # Resaltar la fila de subtítulo "Costo derivado del CCT"
    for i, row in enumerate(data):
        if row[0] == "Costo derivado del CCT":
            style.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
            style.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO))
    t.setStyle(TableStyle(style))
    return t


def construir_barra_subtotal(total):
    return construir_barra_titulo("SUB TOTAL CONTRIBUCIONES EMPLEADOR", total)


# ---------------------------------------------------------------------------
# SUELDO BRUTO — con subtítulos REMUNERATIVO / NO REMUNERATIVO / DESCUENTOS
# como en el Excel
# ---------------------------------------------------------------------------

def construir_tabla_sueldo(r, emp):
    header = ["CONCEPTO", "UNIDAD", "BASE", "MONTO"]
    data = [header]

    def fila(desc, unidad, base, monto):
        data.append([desc, unidad, base, fmt(monto)])

    def subtitulo(texto):
        data.append([texto, "", "", ""])

    subtitulo("REMUNERATIVO")
    fila("Sueldo Básico", f"{emp.get('dias_trabajados', 30):.0f}", fmt(r["basico_prop"]), r["basico_prop"])
    if r.get("antiguedad", 0) > 0:
        fila("Antigüedad", fmt_pct(r.get("antiguedad_pct", 0.01 * r.get("antiguedad_anios", 0))),
             fmt(r["basico_prop"]), r["antiguedad"])
    if r.get("presentismo", 0) > 0:
        fila("Presentismo", fmt_pct(1 / 12), fmt(r["basico_prop"] + r.get("antiguedad", 0)), r["presentismo"])

    if r.get("no_remunerativos"):
        subtitulo("NO REMUNERATIVO")
        for concepto in r["no_remunerativos"]:
            fila(concepto["desc"], concepto.get("unidad", ""), fmt(concepto.get("base", 0)), concepto["monto"])

    subtitulo("DESCUENTOS")
    if r.get("jubilacion", 0) > 0:
        fila("Jubilación", fmt_pct(0.11), fmt(r["base_rem"]), r["jubilacion"])
    if r.get("pami", 0) > 0:
        fila("Ley 19.032 (INSSJP)", fmt_pct(0.03), fmt(r["base_rem"]), r["pami"])
    if r.get("obra_social", 0) > 0:
        fila("Obra Social - OSECAC", fmt_pct(0.03), fmt(r["base_rem"]), r["obra_social"])
    if r.get("sec", 0) > 0:
        fila("Sindicato Empleados de Comercio", fmt_pct(0.02), fmt(r["base_rem"]), r["sec"])
    if r.get("faecys", 0) > 0:
        fila("FAECyS", fmt_pct(0.005), fmt(r["base_rem"]), r["faecys"])
    if r.get("redondeo", 0):
        fila("Redondeo", "-", "-", r["redondeo"])

    t = Table(data, colWidths=[ANCHO_TOTAL * 0.45, ANCHO_TOTAL * 0.20, ANCHO_TOTAL * 0.15, ANCHO_TOTAL * 0.20])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i, row in enumerate(data):
        if row[0] in ("REMUNERATIVO", "NO REMUNERATIVO", "DESCUENTOS"):
            style.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
            style.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO))
    t.setStyle(TableStyle(style))
    return t


def construir_fila_composicion(r):
    no_rem_total = sum(c["monto"] for c in r.get("no_remunerativos", []))
    data = [[f"Remunerativo: $ {fmt(r['base_rem'])}",
             f"No Remunerativo: $ {fmt(no_rem_total)}",
             f"Descuentos: $ {fmt(r['total_desc'])}"]]
    t = Table(data, colWidths=[ANCHO_TOTAL / 3] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_HEADER),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_fila_recibi_la_suma(lugar, fecha_txt):
    """Reemplaza a 'SON PESOS' (esa fila pertenecía a la referencia
    incorrecta de Turismo). El Excel modelo usa 'Recibí la suma de: ....'
    + 'Depositado en:' + lugar/fecha + línea de firma."""
    data = [["Recibí la suma de: " + "." * 90]]
    t1 = Table(data, colWidths=[ANCHO_TOTAL])
    t1.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    data2 = [["Depositado en: ______________________", ""]]
    t2 = Table(data2, colWidths=[ANCHO_TOTAL * 0.6, ANCHO_TOTAL * 0.4])
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7)]))

    data3 = [[f"{lugar}, {fecha_txt}.", "...................................."]]
    t3 = Table(data3, colWidths=[ANCHO_TOTAL * 0.6, ANCHO_TOTAL * 0.4])
    t3.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))

    data4 = [["", "Firma del Empleado"]]
    t4 = Table(data4, colWidths=[ANCHO_TOTAL * 0.6, ANCHO_TOTAL * 0.4])
    t4.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    return [t1, t2, t3, t4]


# ---------------------------------------------------------------------------
# Detalle de composición salarial + torta — con PAMI como bucket propio
# ---------------------------------------------------------------------------

def _agrupar_para_detalle(contrib, r):
    costo_sindical_emp = contrib["seguro_la_estrella"] + contrib["inacap"] + contrib.get("seguro_vida_cct130", 0)
    costo_sindical_trab = r.get("sec", 0) + r.get("faecys", 0)

    # Seg. Social Empl. = Jubilación + FNE + Asig.Familiares (así lo define
    # el Excel en su nota: "incluye SIPA, Fondo Nacional de Empleo y
    # Asignaciones Familiares"). Ya están desglosados arriba en la tabla de
    # contribuciones; acá los sumamos solo para el bucket del detalle/torta.
    seg_social_emp = contrib["jubilacion_patronal"] + contrib["fne"] + contrib["asignaciones_familiares"]
    seg_social_trab = r["jubilacion"]

    # PAMI/INSSJP como categoría propia (Excel: "Total costo INSSJP")
    # TODO: el lado empleador no está confirmado como concepto separado
    # para TV Crecer — se deja en 0 hasta confirmar con el contador si
    # corresponde desglosarlo del 10,77% de jubilación patronal o si es
    # un concepto aparte.
    pami_emp = contrib.get("inssjp_patronal", 0)
    pami_trab = r.get("pami", 0)

    obra_social_emp = contrib["obra_social_patronal"] + contrib["contrib_extraordinaria_osecac"]
    obra_social_trab = r["obra_social"]
    art_emp = contrib["art"] + contrib.get("ffep", 0)
    scvo_emp = contrib["seguro_vida"]

    return {
        "costo_sindical_emp": costo_sindical_emp, "costo_sindical_trab": costo_sindical_trab,
        "seg_social_emp": seg_social_emp, "seg_social_trab": seg_social_trab,
        "pami_emp": pami_emp, "pami_trab": pami_trab,
        "obra_social_emp": obra_social_emp, "obra_social_trab": obra_social_trab,
        "art_emp": art_emp, "scvo_emp": scvo_emp,
    }


ANCHO_DETALLE = ANCHO_TOTAL * 0.60
ANCHO_PIE = ANCHO_TOTAL * 0.40


def construir_pie(contrib, r, neto):
    g = _agrupar_para_detalle(contrib, r)
    total = neto + contrib["total"]
    valores = [neto, g["seg_social_emp"], g["costo_sindical_emp"], g["obra_social_emp"],
               g["pami_emp"], g["art_emp"], g["scvo_emp"]]
    etiquetas = ["Sueldo Neto", "Seg. Social Empl.", "Costo Sindical", "Obra Social",
                 "PAMI", "ART", "SCVO"]

    d = Drawing(ANCHO_PIE, 45 * mm)
    pie = Pie()
    pie.x = 2 * mm
    pie.y = 2 * mm
    pie.width = 34 * mm
    pie.height = 34 * mm
    pie.data = valores
    pie.labels = None
    pie.slices.strokeWidth = 0.5
    paleta = [colors.HexColor("#2E5FA3"), colors.HexColor("#C0392B"), colors.HexColor("#27AE60"),
              colors.HexColor("#8E44AD"), colors.HexColor("#3498DB"), colors.HexColor("#F39C12"),
              colors.HexColor("#BDC3C7")]
    for i, c in enumerate(paleta):
        pie.slices[i].fillColor = c
    d.add(pie)

    legend = Legend()
    legend.x = 38 * mm
    legend.y = 38 * mm
    legend.dx = 6
    legend.dy = 6
    legend.fontSize = 6
    legend.alignment = "left"
    legend.colorNamePairs = [(paleta[i], f"{etiquetas[i]} ({valores[i]/total*100:.1f}%)") for i in range(len(valores))]
    d.add(legend)
    return d


def construir_tabla_detalle(contrib, r):
    g = _agrupar_para_detalle(contrib, r)
    data = [
        ["Total Costo Sindical", "", "Total costo INSSJP (PAMI)", ""],
        ["Empleador", fmt(g["costo_sindical_emp"]), "Empleador", fmt(g["pami_emp"])],
        ["Trabajador", fmt(g["costo_sindical_trab"]), "Trabajador", fmt(g["pami_trab"])],
        ["Total Seguridad Social", "", "Total costo ART", ""],
        ["Empleador", fmt(g["seg_social_emp"]), "Empleador", fmt(g["art_emp"])],
        ["Trabajador", fmt(g["seg_social_trab"]), "", ""],
        ["Total Obra Social", "", "Total Costo SCVO", ""],
        ["Empleador", fmt(g["obra_social_emp"]), "Empleador", fmt(g["scvo_emp"])],
        ["Trabajador", fmt(g["obra_social_trab"]), "", ""],
    ]
    # Fracciones relativas AL ANCHO_DETALLE (no a ANCHO_TOTAL) — deben sumar 1,
    # porque esta tabla ocupa la celda izquierda de la tabla combinada
    # [[detalle, pie]], que le asigna exactamente ANCHO_DETALLE de ancho.
    t = Table(data, colWidths=[ANCHO_DETALLE * 0.25, ANCHO_DETALLE * 0.20,
                                ANCHO_DETALLE * 0.34, ANCHO_DETALLE * 0.21])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
    ]
    for fila_titulo in (0, 3, 6):
        style.append(("FONTNAME", (0, fila_titulo), (0, fila_titulo), "Helvetica-Bold"))
        style.append(("FONTNAME", (2, fila_titulo), (2, fila_titulo), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def construir_titulo_detalle():
    data = [["Detalle de la composición salarial", "Costo total empleador"]]
    t = Table(data, colWidths=[ANCHO_DETALLE, ANCHO_PIE])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------

def generar_recibo(empresa_config, emp, r, contrib, neto, periodo_txt, periodo_dt, fecha_pago_aportes,
                    lugar="Buenos Aires", fecha_firma_txt=""):
    elementos = []
    elementos.append(construir_titulo_empresa(empresa_config))
    elementos.append(construir_fila_periodo_empleado(emp, r, periodo_txt))
    elementos.append(construir_fila_datos_adicionales(emp, empresa_config, periodo_dt, fecha_pago_aportes))

    elementos.append(construir_barra_titulo("COSTO TOTAL EMPLEADOR", contrib["total"]))
    elementos.append(construir_tabla_contribuciones(contrib, empresa_config, r["base_rem"]))
    elementos.append(construir_barra_subtotal(contrib["total"]))

    elementos.append(construir_barra_titulo("SUELDO BRUTO", r["base_rem"]))
    elementos.append(construir_tabla_sueldo(r, emp))
    elementos.append(construir_fila_composicion(r))
    elementos.append(construir_barra_titulo("SUELDO NETO $", neto))

    elementos.extend(construir_fila_recibi_la_suma(lugar, fecha_firma_txt))

    elementos.append(construir_titulo_detalle())
    detalle = construir_tabla_detalle(contrib, r)
    pie = construir_pie(contrib, r, neto)
    combinado = Table([[detalle, pie]], colWidths=[ANCHO_DETALLE, ANCHO_PIE])
    combinado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elementos.append(combinado)

    return elementos


if __name__ == "__main__":
    import datetime

    empresa_config = {
        "nombre": "TV CRECER S.R.L.",
        "cuit": "30-00000000-0",  # TODO: completar CUIT real de TV Crecer
        "pyme": True,
        "alicuota_art": 0.04430,
        "alicuota_asig_familiares": 0.0470,
        "medio_pago": "Transf. Bancaria",
    }
    emp = {
        "nombre": "Sarich", "legajo": "005011", "cuil": "20359670452",
        "categoria": "Administrativo B", "fecha_ingreso": datetime.date(2015, 12, 10),
        "banco": "", "dias_trabajados": 30,
    }
    r = {
        "basico_prop": 1061749, "antiguedad": 0, "antiguedad_anios": 0, "presentismo": 0,
        "jubilacion": 116792.39, "pami": 31852.47, "obra_social": 31852.47, "redondeo": 0.33,
        "base_rem": 1061749, "total_desc": 180497.66, "sec": 0, "faecys": 0,
        "no_remunerativos": [],
    }
    contrib = {
        "jubilacion_patronal": 114350.37, "fne": 9980.44, "art": 47035.48, "ffep": 0,
        "obra_social_patronal": 63704.94, "asignaciones_familiares": 49902.20,
        "seguro_la_estrella": 16987.98, "contrib_extraordinaria_osecac": 28000.00,
        "inacap": 5567.94, "seguro_vida": 424.62, "total": 335953.98,
    }
    neto = 881252.00

    W, H = A4
    c = canvas.Canvas("recibo_prototipo_v4.pdf", pagesize=A4)
    frame = Frame(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm, showBoundary=0)
    elementos = generar_recibo(empresa_config, emp, r, contrib, neto, "AGOSTO 2026",
                                datetime.date(2026, 8, 1), datetime.date(2026, 9, 1),
                                fecha_firma_txt="01 de SEPTIEMBRE 2026")
    sobrante = frame.addFromList(elementos, c)
    if sobrante:
        print(f"AVISO: quedaron {len(sobrante)} elementos sin entrar en la pagina 1")
    c.save()
    print("PDF generado: recibo_prototipo_v4.pdf")
