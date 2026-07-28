"""
Motor de liquidación + generadores de TXT y PDF
"""
import calendar
import math
import base64
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF

def fmt_monto(n):
    return f"{abs(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_cuil(cuil_digits):
    """Formatea un CUIL de 11 dígitos sin guiones como XX-XXXXXXXX-X."""
    d = str(cuil_digits or "")
    if len(d) != 11:
        return d
    return f"{d[0:2]}-{d[2:10]}-{d[10]}"

def liquidar(emp):
    bm   = emp["basico_mensual"]
    dias = emp.get("dias_trabajados", 30)
    fer  = emp.get("dias_feriado", 0)

    basico_prop          = bm / 30 * dias
    feriado_no_trabajado = bm / 30 * fer
    antiguedad           = emp.get("antiguedad_monto", 0)
    presentismo          = emp.get("presentismo", 0)
    a_cuenta             = emp.get("a_cuenta_aumentos", 0)
    asig_no_rem          = emp.get("asig_no_rem", 0)
    antiguedad_s_acuerdo = emp.get("antiguedad_s_acuerdo", 0)
    presentismo_s_acuerdo= emp.get("presentismo_s_acuerdo", 0)
    osecac               = emp.get("osecac", 0)
    sec                  = emp.get("sec", 0)
    faecys               = emp.get("faecys", 0)

    if emp.get("fuera_convenio", False):
        osecac = 0
        sec    = 0
        faecys = 0

    base_rem = basico_prop + feriado_no_trabajado + antiguedad + presentismo + a_cuenta
    base_os  = base_rem + asig_no_rem + antiguedad_s_acuerdo + presentismo_s_acuerdo \
               if emp.get("os_sobre_nr", False) else base_rem
    bruto    = base_rem + asig_no_rem + antiguedad_s_acuerdo + presentismo_s_acuerdo

    jubilacion  = 0 if emp.get("fuera_convenio", False) else base_rem * 0.11
    pami        = 0 if emp.get("fuera_convenio", False) else base_rem * 0.03
    obra_social = 0 if emp.get("fuera_convenio", False) else base_os  * 0.03
    total_desc  = jubilacion + pami + obra_social + osecac + sec + faecys

    neto_exacto = bruto - total_desc
    redondeo    = math.ceil(neto_exacto) - neto_exacto
    neto        = math.ceil(neto_exacto)

    return {
        "basico_prop": basico_prop, "feriado_no_trabajado": feriado_no_trabajado,
        "antiguedad": antiguedad, "presentismo": presentismo, "a_cuenta": a_cuenta,
        "asig_no_rem": asig_no_rem, "antiguedad_s_acuerdo": antiguedad_s_acuerdo,
        "presentismo_s_acuerdo": presentismo_s_acuerdo,
        "base_rem": base_rem, "base_os": base_os,
        "jubilacion": jubilacion, "pami": pami, "obra_social": obra_social,
        "osecac": osecac, "sec": sec, "faecys": faecys,
        "total_desc": total_desc, "redondeo": redondeo, "neto": neto,
    }

# ─────────────────────────────────────────────────────────────
# CONTRIBUCIONES PATRONALES
# Valores confirmados por el contador (TV Crecer, Convenio Comercio) el 24/07/2026.
# ART y Asignaciones Familiares son especificos de TV Crecer - otra empresa
# podria tener otros valores, por eso van en empresa_config.
# ─────────────────────────────────────────────────────────────
ALICUOTA_JUBILACION_PATRONAL_PYME = 0.1077
ALICUOTA_JUBILACION_PATRONAL_GENERAL = 0.127  # no confirmado aun, se usa solo si empresa_config["pyme"] es False
ALICUOTA_FNE = 0.0094
ALICUOTA_OBRA_SOCIAL_PATRONAL = 0.06
ALICUOTA_SEGURO_LA_ESTRELLA = 0.016
CONTRIB_EXTRAORDINARIA_OSECAC = 28000.00
SEGURO_VIDA_MONTO = 424.62

def calcular_contribuciones_patronales(emp, r, empresa_config, inacap_monto):
    """
    Calcula las contribuciones patronales (costo empleador) sobre una
    liquidacion ya calculada por liquidar().

    inacap_monto: OBLIGATORIO, sin default. Este valor cambia todos los
    meses (confirmado por el contador) y no puede asumirse - debe
    consultarse y pasarse explicitamente en cada liquidacion. Pasar 0
    solo si se confirma que no corresponde para esa liquidacion puntual.

    empresa_config debe traer:
      - "pyme": bool (default False si no esta) -> alicuota jubilacion patronal
      - "alicuota_art": float (sin default - si falta, se lanza error)
      - "alicuota_asig_familiares": float (sin default - si falta, se lanza error)
    """
    if inacap_monto is None:
        raise ValueError(
            "inacap_monto es obligatorio y no tiene default porque su valor "
            "cambia todos los meses. Consultar el valor vigente antes de liquidar."
        )
    if "alicuota_art" not in empresa_config:
        raise ValueError(f"Falta 'alicuota_art' en la config de la empresa")
    if "alicuota_asig_familiares" not in empresa_config:
        raise ValueError(f"Falta 'alicuota_asig_familiares' en la config de la empresa")

    if emp.get("fuera_convenio", False):
        return {
            "jubilacion_patronal": 0, "fne": 0, "art": 0,
            "obra_social_patronal": 0, "asignaciones_familiares": 0,
            "seguro_la_estrella": 0, "contrib_extraordinaria_osecac": 0,
            "inacap": 0, "seguro_vida": 0, "total": 0,
        }

    base = r["base_rem"]
    es_pyme = empresa_config.get("pyme", False)
    alicuota_jub = ALICUOTA_JUBILACION_PATRONAL_PYME if es_pyme else ALICUOTA_JUBILACION_PATRONAL_GENERAL

    jubilacion_patronal = base * alicuota_jub
    fne = base * ALICUOTA_FNE
    art = base * empresa_config["alicuota_art"]
    obra_social_patronal = base * ALICUOTA_OBRA_SOCIAL_PATRONAL
    asignaciones_familiares = base * empresa_config["alicuota_asig_familiares"]
    seguro_la_estrella = base * ALICUOTA_SEGURO_LA_ESTRELLA
    contrib_extraordinaria_osecac = CONTRIB_EXTRAORDINARIA_OSECAC
    inacap = inacap_monto
    seguro_vida = SEGURO_VIDA_MONTO

    total = (jubilacion_patronal + fne + art + obra_social_patronal +
             asignaciones_familiares + seguro_la_estrella +
             contrib_extraordinaria_osecac + inacap + seguro_vida)

    return {
        "jubilacion_patronal": jubilacion_patronal, "fne": fne, "art": art,
        "obra_social_patronal": obra_social_patronal,
        "asignaciones_familiares": asignaciones_familiares,
        "seguro_la_estrella": seguro_la_estrella,
        "contrib_extraordinaria_osecac": contrib_extraordinaria_osecac,
        "inacap": inacap, "seguro_vida": seguro_vida, "total": total,
    }

def generar_txt(empleados, periodo, empresa_config, nro_liquidacion="00001"):
    cant = str(len(empleados)).zfill(6)

    if len(periodo) == 6:
        anio_periodo = int(periodo[0:4])
        mes_periodo  = int(periodo[4:6])

        dias_base = str(calendar.monthrange(anio_periodo, mes_periodo)[1]).zfill(2)

        if mes_periodo == 12:
            anio_pago, mes_pago = anio_periodo + 1, 1
        else:
            anio_pago, mes_pago = anio_periodo, mes_periodo + 1
        fecha_pago = f"{anio_pago}{mes_pago:02d}01"
    else:
        dias_base  = "30"
        fecha_pago = "20251201"

    nro_liq = str(nro_liquidacion).zfill(5)[:5]

    reg1 = f"01{empresa_config['cuit']}SJ{periodo}M{nro_liq}{dias_base}{cant}"
    lineas = [reg1]

    for emp in empleados:
        cuil        = emp.get("cuil", "").replace("-", "").replace(" ", "").ljust(11)[:11]
        legajo      = str(emp.get("legajo", "")).ljust(10)[:10]
        dependencia = str(emp.get("dependencia", "")).ljust(50)[:50]
        cbu         = str(emp.get("cbu", "")).ljust(22)[:22]

        reg2 = (
            "02" + cuil + legajo + dependencia + cbu +
            "000" +
            fecha_pago +
            " " * 8 +
            "1"
        )
        lineas.append(reg2)

    return "\r\n".join(lineas)

def _construir_conceptos(emp, r):
    """
    Lista de conceptos de la liquidación (misma lógica que usa generar_pdf()
    internamente), en forma de datos crudos (valores numéricos, no strings
    formateados) para que distintos formatos de recibo puedan renderizarlos
    como quieran.
    """
    conceptos = []
    conceptos.append({"cod":"0001", "concepto":"SUELDO BASICO",
                       "unid":f"{emp.get('dias_trabajados',30):.2f}", "apor":r["basico_prop"]})
    if emp.get("dias_feriado", 0) > 0:
        conceptos.append({"cod":"0271", "concepto":"FERIADO NO TRABAJADO",
                           "unid":f"{emp.get('dias_feriado',0):.2f}", "apor":r["feriado_no_trabajado"]})
    if r["antiguedad"] > 0:
        conceptos.append({"cod":"0038", "concepto":"ANTIGUEDAD", "apor":r["antiguedad"]})
    if r["presentismo"] > 0:
        conceptos.append({"cod":"0039", "concepto":"PRESENTISMO", "apor":r["presentismo"]})
    if r["a_cuenta"] > 0:
        conceptos.append({"cod":"0182", "concepto":"A CTA. FUTUROS AUMENTOS", "apor":r["a_cuenta"]})
    if r["asig_no_rem"] > 0:
        conceptos.append({"cod":"0369", "concepto":"ASIG. NO REMUNERATIVA", "exent":r["asig_no_rem"]})
    if r["antiguedad_s_acuerdo"] > 0:
        conceptos.append({"cod":"0618", "concepto":"ANTIGUEDAD S/ ACUERDO", "exent":r["antiguedad_s_acuerdo"]})
    if r["presentismo_s_acuerdo"] > 0:
        conceptos.append({"cod":"0608", "concepto":"PRESENTISMO S/ ACUERDOS", "exent":r["presentismo_s_acuerdo"]})
    if r["jubilacion"] > 0:
        conceptos.append({"cod":"1001", "concepto":"JUBILACION", "ret":r["jubilacion"]})
    if r["pami"] > 0:
        conceptos.append({"cod":"1002", "concepto":"LEY 19032", "ret":r["pami"]})
    if r["obra_social"] > 0:
        conceptos.append({"cod":"1025", "concepto":"OBRA SOCIAL", "ret":r["obra_social"]})
    if r["osecac"] > 0:
        conceptos.append({"cod":"1026", "concepto":"APORTE OSECAC SEGUN ACUERDO", "ret":r["osecac"]})
    if r["sec"] > 0:
        conceptos.append({"cod":"1106", "concepto":"SEC", "ret":r["sec"]})
    if r["faecys"] > 0:
        conceptos.append({"cod":"1107", "concepto":"FAECYS", "ret":r["faecys"]})
    conceptos.append({"cod":"2009", "concepto":"REDONDEO", "ret":r["redondeo"]})
    return conceptos

def generar_pdf(empleados, netos, periodo, empresa_config):
    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    ML = 15 * mm
    MR = W - 15 * mm

    mes_nombre = {
        "01":"ENERO","02":"FEBRERO","03":"MARZO","04":"ABRIL",
        "05":"MAYO","06":"JUNIO","07":"JULIO","08":"AGOSTO",
        "09":"SEPTIEMBRE","10":"OCTUBRE","11":"NOVIEMBRE","12":"DICIEMBRE"
    }
    mm_str = periodo[4:6] if len(periodo) == 6 else "11"
    aa_str = periodo[2:4] if len(periodo) == 6 else "25"
    periodo_txt = f"{mes_nombre.get(mm_str,'?')} 20{aa_str}"
    mes_num = int(mm_str)
    anio_num = 2000 + int(aa_str)
    if mes_num == 12:
        mes_pago_num, anio_pago_num = 1, anio_num + 1
    else:
        mes_pago_num, anio_pago_num = mes_num + 1, anio_num
    fecha_pago = f"1/{mes_pago_num}/{anio_pago_num}"

    def txt(x, y, texto, size=7, bold=False, align="left"):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "right":   c.drawRightString(x, y, str(texto))
        elif align == "center": c.drawCentredString(x, y, str(texto))
        else:                  c.drawString(x, y, str(texto))

    def linea(y):
        c.setLineWidth(0.5)
        c.line(ML, y, MR, y)

    def recibo(emp, r, neto, y_start, copia):
        y = y_start
        txt(ML, y, "Empresa:", bold=True); txt(ML+18*mm, y, empresa_config["nombre"])
        txt(MR-60*mm, y, "Direccion:", bold=True); txt(MR-45*mm, y, empresa_config["direccion"])
        y -= 5*mm; linea(y); y -= 4*mm
        txt(ML, y, f"Nro C.U.I.T. Empresa:{empresa_config['cuit']}")
        txt(W/2, y, f"Nro C.U.I.L. Empleado: {fmt_cuil(emp.get('cuil',''))}")
        y -= 4*mm
        txt(ML, y, "Apellido y Nombre", bold=True)
        txt(MR-40*mm, y, "Legajo Nro", bold=True)
        txt(MR-15*mm, y, "Fecha de Ingreso", bold=True)
        y -= 4*mm
        txt(ML, y, emp["nombre"].upper(), bold=True)
        txt(MR-38*mm, y, emp.get("legajo",""))
        txt(MR-12*mm, y, emp.get("fecha_ingreso",""))
        y -= 4*mm; linea(y); y -= 4*mm
        txt(ML, y, "Período de Pago", bold=True)
        txt(ML+45*mm, y, "Tarea Desempeñada", bold=True)
        txt(W/2+20*mm, y, "Categoría", bold=True)
        txt(MR-20*mm, y, "Remuneración Básica", bold=True)
        y -= 4*mm
        txt(ML, y, periodo_txt)
        txt(ML+45*mm, y, emp.get("tarea",""))
        txt(W/2+20*mm, y, emp.get("categoria",""))
        txt(MR, y, fmt_monto(emp["basico_mensual"]), align="right")
        y -= 4*mm; linea(y); y -= 4*mm

        # Encabezado columnas
        txt(ML, y, "COD.", 6, bold=True)
        txt(ML+13*mm, y, "CONCEPTO", 6, bold=True)
        txt(ML+90*mm, y, "UNIDADES", 6, bold=True)
        txt(ML+122*mm, y, "APORTES CON RET.", 6, bold=True, align="right")
        txt(ML+148*mm, y, "REMUN. EXENTAS", 6, bold=True, align="right")
        txt(MR, y, "RETENCIONES", 6, bold=True, align="right")
        y -= 3*mm; linea(y); y -= 4*mm

        def fila(cod, concepto, unid="", apor="", exent="", ret=""):
            nonlocal y
            txt(ML, y, cod, 6); txt(ML+13*mm, y, concepto, 6)
            if unid:  txt(ML+102*mm, y, unid, 6, align="right")
            if apor:  txt(ML+122*mm, y, apor, 6, align="right")
            if exent: txt(ML+148*mm, y, exent, 6, align="right")
            if ret:   txt(MR, y, ret, 6, align="right")
            y -= 3.8*mm

        conceptos = []
        conceptos.append({"cod":"0001", "concepto":"SUELDO BASICO",
                           "unid":f"{emp.get('dias_trabajados',30):.2f}", "apor":fmt_monto(r["basico_prop"])})
        if emp.get("dias_feriado", 0) > 0:
            conceptos.append({"cod":"0271", "concepto":"FERIADO NO TRABAJADO",
                               "unid":f"{emp.get('dias_feriado',0):.2f}", "apor":fmt_monto(r["feriado_no_trabajado"])})
        if r["antiguedad"] > 0:
            conceptos.append({"cod":"0038", "concepto":"ANTIGUEDAD", "apor":fmt_monto(r["antiguedad"])})
        if r["presentismo"] > 0:
            conceptos.append({"cod":"0039", "concepto":"PRESENTISMO", "apor":fmt_monto(r["presentismo"])})
        if r["a_cuenta"] > 0:
            conceptos.append({"cod":"0182", "concepto":"A CTA. FUTUROS AUMENTOS", "apor":fmt_monto(r["a_cuenta"])})
        if r["asig_no_rem"] > 0:
            conceptos.append({"cod":"0369", "concepto":"ASIG. NO REMUNERATIVA", "exent":fmt_monto(r["asig_no_rem"])})
        if r["antiguedad_s_acuerdo"] > 0:
            conceptos.append({"cod":"0618", "concepto":"ANTIGUEDAD S/ ACUERDO", "exent":fmt_monto(r["antiguedad_s_acuerdo"])})
        if r["presentismo_s_acuerdo"] > 0:
            conceptos.append({"cod":"0608", "concepto":"PRESENTISMO S/ ACUERDOS", "exent":fmt_monto(r["presentismo_s_acuerdo"])})
        if r["jubilacion"] > 0:
            conceptos.append({"cod":"1001", "concepto":"JUBILACION", "ret":fmt_monto(r["jubilacion"])})
        if r["pami"] > 0:
            conceptos.append({"cod":"1002", "concepto":"LEY 19032", "ret":fmt_monto(r["pami"])})
        if r["obra_social"] > 0:
            conceptos.append({"cod":"1025", "concepto":"OBRA SOCIAL", "ret":fmt_monto(r["obra_social"])})
        if r["osecac"] > 0:
            conceptos.append({"cod":"1026", "concepto":"APORTE OSECAC SEGUN ACUERDO", "ret":fmt_monto(r["osecac"])})
        if r["sec"] > 0:
            conceptos.append({"cod":"1106", "concepto":"SEC", "ret":fmt_monto(r["sec"])})
        if r["faecys"] > 0:
            conceptos.append({"cod":"1107", "concepto":"FAECYS", "ret":fmt_monto(r["faecys"])})
        conceptos.append({"cod":"2009", "concepto":"REDONDEO", "ret":fmt_monto(r["redondeo"])})

        for concepto in conceptos:
            fila(**concepto)

        y -= 2*mm; linea(y); y -= 4*mm
        txt(ML, y, "REMUNERACION BRUTA:", bold=True)
        txt(ML+122*mm, y, fmt_monto(r["base_rem"]), align="right")
        y -= 5*mm; linea(y); y -= 4*mm
        txt(ML, y, f"Lugar y Fecha de Pago: BS. AS."); txt(ML+55*mm, y, fecha_pago)
        txt(W/2+5*mm, y, "Reingreso: / /")
        txt(MR-30*mm, y, "TOTAL NETO", bold=True)
        txt(MR, y, fmt_monto(neto), bold=True, align="right")
        y -= 5*mm
        txt(ML, y, f"Son: $ {fmt_monto(neto)}", 7)
        y -= 6*mm; linea(y); y -= 4*mm
        txt(ML, y, f"Banco: {empresa_config['banco']}"); txt(W/2, y, "Recibí conforme la presente")
        y -= 4*mm
        txt(ML, y, f"Obra Social: {emp.get('obra_social_cod','')}"); txt(W/2, y, "liquidacion de haberes")
        y -= 4*mm; txt(ML, y, "Forma de pago:")
        y -= 4*mm; txt(ML, y, "Nº de Cta:"); txt(MR-40*mm, y, "Devolver este recibo una vez firmado")
        y -= 4*mm; txt(ML, y, "ART:"); txt(MR, y, f"Firma {copia}", align="right")
        y -= 4*mm; txt(MR, y, f"Copia para {copia}", align="right")
        y -= 3*mm; linea(y)
        return y

    for i, emp in enumerate(empleados):
        r    = liquidar(emp)
        neto = netos[i]
        mitad = H / 2
        recibo(emp, r, neto, H - 10*mm, "el empleador")
        c.setDash(4, 4); c.setLineWidth(0.3); c.line(ML, mitad, MR, mitad); c.setDash()
        recibo(emp, r, neto, mitad - 3*mm, "el empleado")
        c.showPage()

    c.save()
    return buffer.getvalue()

def generar_pdf_v2(empleados, netos, periodo, empresa_config, inacap_monto):
    """
    Formato de recibo alternativo (costo total empleador + contribuciones
    patronales + composición salarial + gráfico de torta). Misma firma que
    generar_pdf() para ser intercambiable, pero completamente independiente:
    no modifica ni reutiliza el código de dibujo de generar_pdf().
    """
    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    ML = 15 * mm
    MR = W - 15 * mm

    mes_nombre = {
        "01":"ENERO","02":"FEBRERO","03":"MARZO","04":"ABRIL",
        "05":"MAYO","06":"JUNIO","07":"JULIO","08":"AGOSTO",
        "09":"SEPTIEMBRE","10":"OCTUBRE","11":"NOVIEMBRE","12":"DICIEMBRE"
    }
    mm_str = periodo[4:6] if len(periodo) == 6 else "11"
    aa_str = periodo[2:4] if len(periodo) == 6 else "25"
    periodo_txt = f"{mes_nombre.get(mm_str,'?')} 20{aa_str}"
    mes_num = int(mm_str)
    anio_num = 2000 + int(aa_str)
    if mes_num == 12:
        mes_pago_num, anio_pago_num = 1, anio_num + 1
    else:
        mes_pago_num, anio_pago_num = mes_num + 1, anio_num
    fecha_pago = f"1/{mes_pago_num}/{anio_pago_num}"

    def txt(x, y, texto, size=6, bold=False, align="left"):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "right":   c.drawRightString(x, y, str(texto))
        elif align == "center": c.drawCentredString(x, y, str(texto))
        else:                  c.drawString(x, y, str(texto))

    def linea(y):
        c.setLineWidth(0.4)
        c.line(ML, y, MR, y)

    COLORES_TORTA = [
        colors.HexColor("#2b6cb0"), colors.HexColor("#38a169"),
        colors.HexColor("#d69e2e"), colors.HexColor("#c53030"),
        colors.HexColor("#805ad5"),
    ]

    def dibujar_pie(x, y_top, categorias):
        """categorias: lista de (nombre, valor) > 0. Torta + referencias a texto."""
        if not categorias:
            return y_top
        total = sum(v for _, v in categorias) or 1
        d = Drawing(30 * mm, 22 * mm)
        pie = Pie()
        pie.x = 2 * mm
        pie.y = 1 * mm
        pie.width = 20 * mm
        pie.height = 20 * mm
        pie.data = [v for _, v in categorias]
        pie.labels = None
        pie.simpleLabels = 0
        pie.sideLabels = 0
        for i in range(len(categorias)):
            pie.slices[i].fillColor = COLORES_TORTA[i % len(COLORES_TORTA)]
            pie.slices[i].strokeColor = colors.white
            pie.slices[i].strokeWidth = 0.5
        d.add(pie)
        renderPDF.draw(d, c, x, y_top - 22 * mm)

        ly = y_top - 3 * mm
        lx = x + 24 * mm
        for i, (nombre, valor) in enumerate(categorias):
            pct = valor / total * 100
            c.setFillColor(COLORES_TORTA[i % len(COLORES_TORTA)])
            c.rect(lx, ly - 2, 2.2 * mm, 2.2 * mm, fill=1, stroke=0)
            c.setFillColor(colors.black)
            txt(lx + 3.5 * mm, ly - 2, f"{nombre}: {pct:.1f}%", 5.5)
            ly -= 3.6 * mm
        return y_top - 24 * mm

    def recibo_v2(emp, r, contrib, neto, y_start, copia):
        y = y_start

        # Encabezado
        txt(ML, y, f"Obra Social: {emp.get('obra_social_cod','')}", bold=True)
        txt(W/2, y, f"Periodo Abonado: {periodo_txt}", bold=True)
        y -= 3.6*mm
        txt(ML, y, f"Lugar de Pago: {empresa_config['nombre']}")
        txt(W/2, y, f"F. Pago Aportes: {fecha_pago}")
        y -= 3*mm; linea(y); y -= 3.5*mm

        txt(ML, y, emp["nombre"].upper(), bold=True, size=7)
        txt(MR-45*mm, y, f"Legajo: {emp.get('legajo','')}", size=5.5)
        txt(MR-15*mm, y, f"CUIL: {fmt_cuil(emp.get('cuil',''))}", size=5.5)
        y -= 3.5*mm; linea(y); y -= 3.5*mm

        # Bloque 1 — Costo Total Empleador
        txt(ML, y, f"COSTO TOTAL EMPLEADOR: $ {fmt_monto(contrib['total'])}", bold=True, size=7)
        y -= 3.5*mm
        txt(ML, y, "COD.", 5.5, bold=True); txt(ML+13*mm, y, "DESCRIPCION", 5.5, bold=True)
        txt(ML+95*mm, y, "UNIDADES", 5.5, bold=True, align="right")
        txt(ML+120*mm, y, "V. UNITARIO", 5.5, bold=True, align="right")
        txt(MR, y, "CONTRIBUCIONES", 5.5, bold=True, align="right")
        y -= 3*mm

        filas_contrib = [
            ("5010", "Jubilacion", contrib["jubilacion_patronal"]),
            ("5020", "Fondo Nacional de Empleo", contrib["fne"]),
            ("5030", "ART", contrib["art"]),
            ("5040", "Obra Social", contrib["obra_social_patronal"]),
            ("5050", "Asignaciones Familiares", contrib["asignaciones_familiares"]),
            ("5060", "Seguro La Estrella", contrib["seguro_la_estrella"]),
            ("5070", "Contribucion Extraordinaria OSECAC", contrib["contrib_extraordinaria_osecac"]),
            ("5080", "INACAP", contrib["inacap"]),
            ("5090", "Seguro de vida y sepelio", contrib["seguro_vida"]),
        ]
        for cod, desc, val in filas_contrib:
            txt(ML, y, cod, 5.5); txt(ML+13*mm, y, desc, 5.5)
            txt(MR, y, fmt_monto(val), 5.5, align="right")
            y -= 3*mm
        linea(y); y -= 3.2*mm
        txt(ML, y, "SUBTOTAL CONTRIBUCIONES EMPLEADOR:", bold=True, size=6)
        txt(MR, y, fmt_monto(contrib["total"]), bold=True, size=6, align="right")
        y -= 3.5*mm; linea(y); y -= 3.5*mm

        # Bloque 2 — Sueldo Bruto
        txt(ML, y, f"SUELDO BRUTO: $ {fmt_monto(r['base_rem'])}", bold=True, size=7)
        y -= 3.5*mm
        txt(ML, y, "COD.", 5.5, bold=True); txt(ML+13*mm, y, "DESCRIPCION", 5.5, bold=True)
        txt(ML+78*mm, y, "UNIDADES", 5.5, bold=True, align="right")
        txt(ML+95*mm, y, "V.UNIT.", 5.5, bold=True, align="right")
        txt(ML+118*mm, y, "REMUN.", 5.5, bold=True, align="right")
        txt(ML+142*mm, y, "NO REMUN.", 5.5, bold=True, align="right")
        txt(MR, y, "DESCUENTOS", 5.5, bold=True, align="right")
        y -= 3*mm

        for cpt in _construir_conceptos(emp, r):
            txt(ML, y, cpt["cod"], 5.5); txt(ML+13*mm, y, cpt["concepto"], 5.5)
            if cpt.get("unid"): txt(ML+78*mm, y, cpt["unid"], 5.5, align="right")
            if "apor" in cpt:   txt(ML+118*mm, y, fmt_monto(cpt["apor"]), 5.5, align="right")
            if "exent" in cpt:  txt(ML+142*mm, y, fmt_monto(cpt["exent"]), 5.5, align="right")
            if "ret" in cpt:    txt(MR, y, fmt_monto(cpt["ret"]), 5.5, align="right")
            y -= 2.9*mm
        linea(y); y -= 3.2*mm

        # Resumen final
        remunerativo    = r["base_rem"]
        no_remunerativo = r["asig_no_rem"] + r["antiguedad_s_acuerdo"] + r["presentismo_s_acuerdo"]
        descuentos      = r["total_desc"] + r["redondeo"]
        txt(ML, y, "COMPOSICION SALARIAL:", bold=True, size=6)
        y -= 3*mm
        txt(ML, y, f"Remunerativo: $ {fmt_monto(remunerativo)}", size=5.5)
        txt(ML+55*mm, y, f"No Remunerativo: $ {fmt_monto(no_remunerativo)}", size=5.5)
        txt(ML+115*mm, y, f"Descuentos: $ {fmt_monto(descuentos)}", size=5.5)
        y -= 3.5*mm; linea(y); y -= 3.2*mm

        txt(ML, y, f"Son pesos: $ {fmt_monto(neto)}", size=6)
        txt(MR-35*mm, y, "SUELDO NETO:", bold=True, size=7)
        txt(MR, y, fmt_monto(neto), bold=True, size=7, align="right")
        y -= 3.5*mm; linea(y); y -= 3.5*mm

        # Detalle de composición salarial (empleador / trabajador)
        txt(ML, y, "DETALLE COMPOSICION SALARIAL", bold=True, size=6)
        y -= 3*mm
        costo_sindical_empleador = (contrib["seguro_la_estrella"]
                                     + contrib["contrib_extraordinaria_osecac"]
                                     + contrib["inacap"])
        detalle = [
            ("Total Costo Sindical", costo_sindical_empleador,
             r["osecac"] + r["sec"] + r["faecys"]),
            ("Total Seguridad Social", contrib["jubilacion_patronal"] + contrib["fne"],
             r["jubilacion"] + r["pami"]),
            ("Total Obra Social", contrib["obra_social_patronal"], r["obra_social"]),
            ("Total Asignaciones Familiares", contrib["asignaciones_familiares"], None),
            ("Total ART", contrib["art"], None),
        ]
        for nombre, emp_val, trab_val in detalle:
            linea_txt = f"{nombre} - Empleador: $ {fmt_monto(emp_val)}"
            if trab_val is not None:
                linea_txt += f"  /  Trabajador: $ {fmt_monto(trab_val)}"
            txt(ML, y, linea_txt, size=5.5)
            y -= 2.8*mm
        y -= 0.5*mm

        # Grafico de torta — Costo Total Empleador
        categorias = [
            ("Sueldo Neto", neto),
            ("Seguridad Social", contrib["jubilacion_patronal"] + r["jubilacion"] + r["pami"] + contrib["fne"]),
            ("Costo Sindical", costo_sindical_empleador + r["osecac"] + r["sec"] + r["faecys"]),
            ("Obra Social", contrib["obra_social_patronal"] + r["obra_social"]),
            ("ART", contrib["art"]),
        ]
        categorias = [(n, v) for n, v in categorias if v > 0]
        y = dibujar_pie(ML, y, categorias)

        y -= 1*mm; linea(y); y -= 3.5*mm
        txt(ML, y, f"Lugar y Fecha de Pago: BS. AS.  {fecha_pago}", size=5.5)
        y -= 3*mm
        txt(MR-40*mm, y, f"Firma {copia}", size=5.5, align="right")
        y -= 3*mm
        txt(MR-40*mm, y, f"Copia para {copia}", size=5.5, align="right")
        y -= 2.5*mm; linea(y)
        return y

    for i, emp in enumerate(empleados):
        r       = liquidar(emp)
        contrib = calcular_contribuciones_patronales(emp, r, empresa_config, inacap_monto)
        neto    = netos[i]
        mitad   = H / 2
        recibo_v2(emp, r, contrib, neto, H - 10*mm, "el empleador")
        c.setDash(4, 4); c.setLineWidth(0.3); c.line(ML, mitad, MR, mitad); c.setDash()
        recibo_v2(emp, r, contrib, neto, mitad - 3*mm, "el empleado")
        c.showPage()

    c.save()
    return buffer.getvalue()
