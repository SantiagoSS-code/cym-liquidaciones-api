"""
Motor de liquidación + generadores de TXT y PDF
"""
import calendar
import math
import base64
import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Frame
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
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

def calcular_contribuciones_patronales(emp, r, empresa_config, valores_mensuales: dict):
    """
    Calcula las contribuciones patronales (costo empleador) sobre una
    liquidacion ya calculada por liquidar().

    valores_mensuales: dict OBLIGATORIO, sin default. Debe traer las claves
    "inacap" y "ffep" - montos fijos que cambian todos los meses (confirmado
    por el contador) y no pueden asumirse. Si falta cualquiera de las dos
    claves, se lanza error explicito (no hay default de 0).

    empresa_config debe traer:
      - "pyme": bool (default False si no esta) -> alicuota jubilacion patronal
      - "alicuota_art": float (sin default - si falta, se lanza error)
      - "alicuota_asig_familiares": float (sin default - si falta, se lanza error)
    """
    if valores_mensuales is None or "inacap" not in valores_mensuales or "ffep" not in valores_mensuales:
        raise ValueError(
            "valores_mensuales es obligatorio y debe incluir las claves 'inacap' "
            "y 'ffep' - montos que cambian todos los meses. Consultar los "
            "valores vigentes antes de liquidar."
        )
    if "alicuota_art" not in empresa_config:
        raise ValueError(f"Falta 'alicuota_art' en la config de la empresa")
    if "alicuota_asig_familiares" not in empresa_config:
        raise ValueError(f"Falta 'alicuota_asig_familiares' en la config de la empresa")

    if emp.get("fuera_convenio", False):
        return {
            "jubilacion_patronal": 0, "fne": 0, "art": 0, "ffep": 0,
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
    ffep = valores_mensuales["ffep"]
    obra_social_patronal = base * ALICUOTA_OBRA_SOCIAL_PATRONAL
    asignaciones_familiares = base * empresa_config["alicuota_asig_familiares"]
    seguro_la_estrella = base * ALICUOTA_SEGURO_LA_ESTRELLA
    contrib_extraordinaria_osecac = CONTRIB_EXTRAORDINARIA_OSECAC
    inacap = valores_mensuales["inacap"]
    seguro_vida = SEGURO_VIDA_MONTO

    total = (jubilacion_patronal + fne + art + ffep + obra_social_patronal +
             asignaciones_familiares + seguro_la_estrella +
             contrib_extraordinaria_osecac + inacap + seguro_vida)

    return {
        "jubilacion_patronal": jubilacion_patronal, "fne": fne, "art": art, "ffep": ffep,
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

# ─────────────────────────────────────────────────────────────
# generar_pdf_v2 — recibo con tablas reales (reportlab.platypus), siguiendo
# la estructura del Excel modelo oficial de Convenio Comercio (CCT 130/75).
# Adaptado desde el prototipo validado recibo_prototipo_v4.py.
# ─────────────────────────────────────────────────────────────

GRIS_HEADER_V2 = colors.HexColor("#D9D9D9")
GRIS_CLARO_V2 = colors.HexColor("#F2F2F2")
ANCHO_TOTAL_V2 = 180 * mm  # ancho de contenido consistente en todas las tablas del recibo v2


def fmt_pct(n):
    s = f"{n*100:.3f}".rstrip("0").rstrip(".")
    return f"{s}%"


def fmt_fecha(dt):
    if dt is None:
        return ""
    return dt.strftime("%d/%m/%Y")


def _parse_fecha_ddmmaaaa(s):
    """Parsea fecha_ingreso, que llega como string 'DD/MM/YYYY' desde
    enriquecer_empleado()/el mail, a date. Devuelve None si no se puede parsear."""
    if not s:
        return None
    try:
        return datetime.datetime.strptime(str(s), "%d/%m/%Y").date()
    except ValueError:
        return None


def _antiguedad_visual(fecha_ingreso_dt, periodo_dt):
    """Antiguedad en anios/porcentaje SOLO para mostrar en el PDF. No se usa
    para ningun calculo real: el monto de antiguedad que se liquida y paga
    sigue siendo el que ya calcula liquidar() a partir de antiguedad_monto."""
    if fecha_ingreso_dt is None or periodo_dt is None:
        return None, None
    anios = int((periodo_dt - fecha_ingreso_dt).days / 365.25)
    return anios, 0.01 * anios


def _preparar_r_para_recibo_v2(r, periodo_dt, fecha_ingreso_dt):
    r2 = dict(r)
    r2["antiguedad_anios"], r2["antiguedad_pct"] = _antiguedad_visual(fecha_ingreso_dt, periodo_dt)
    no_rem = []
    if r["asig_no_rem"] > 0:
        no_rem.append({"desc": "Asig. No Remunerativa", "monto": r["asig_no_rem"]})
    if r["antiguedad_s_acuerdo"] > 0:
        no_rem.append({"desc": "Antigüedad s/ Acuerdo", "monto": r["antiguedad_s_acuerdo"]})
    if r["presentismo_s_acuerdo"] > 0:
        no_rem.append({"desc": "Presentismo s/ Acuerdo", "monto": r["presentismo_s_acuerdo"]})
    r2["no_remunerativos"] = no_rem
    return r2


def construir_titulo_empresa_v2(empresa_config):
    """Título 'Recibo de Haberes Ley 20.744' + nombre empresa + CUIT."""
    data = [
        ["Recibo de Haberes Ley 20.744"],
        [empresa_config["nombre"]],
        [f"C.U.I.T. EMPRESA: {fmt_cuil(empresa_config.get('cuit', ''))}"],
    ]
    t = Table(data, colWidths=[ANCHO_TOTAL_V2])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, 0), 11),
        ("FONTSIZE", (0, 1), (0, 2), 8),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def construir_fila_periodo_empleado_v2(emp, r, periodo_txt, numero_recibo=""):
    """Fila: Q. | MES/AÑO | APELLIDO Y NOMBRE | N°LEGAJO | SUELDO BRUTO | ANTIGÜEDAD"""
    header = ["Q.", "MES / AÑO", "APELLIDO Y NOMBRE", "N° LEGAJO", "SUELDO BRUTO", "ANTIGÜEDAD"]
    antiguedad_txt = f"{r.get('antiguedad_anios')} años" if r.get("antiguedad_anios") is not None else ""
    valores = [
        numero_recibo,
        periodo_txt,
        emp["nombre"].upper(),
        emp.get("legajo", ""),
        f"$ {fmt_monto(r['base_rem'])}",
        antiguedad_txt,
    ]
    t = Table([header, valores], colWidths=[ANCHO_TOTAL_V2 * w for w in (0.06, 0.14, 0.32, 0.14, 0.20, 0.14)])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HEADER_V2),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_fila_datos_adicionales_v2(emp, empresa_config, periodo_dt, fecha_pago_aportes):
    """Fila: FECHA INGRESO | CATEGORÍA LABORAL | C.U.I.L. | Banco | Período | F.PAGO APORTES"""
    header = ["FECHA INGRESO", "CATEGORÍA LABORAL", "C.U.I.L.", "Banco", "Período", "F.PAGO APORTES"]
    valores = [
        fmt_fecha(emp.get("fecha_ingreso")),
        emp.get("categoria", ""),
        fmt_cuil(emp.get("cuil", "")),
        emp.get("banco", "") or empresa_config.get("banco", ""),
        fmt_fecha(periodo_dt),
        fmt_fecha(fecha_pago_aportes),
    ]
    t = Table([header, valores], colWidths=[ANCHO_TOTAL_V2 * w for w in (0.16, 0.20, 0.18, 0.14, 0.16, 0.16)])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_HEADER_V2),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_barra_titulo_v2(texto, total):
    data = [[texto, f"$ {fmt_monto(total)}"]]
    t = Table(data, colWidths=[ANCHO_TOTAL_V2 * 0.75, ANCHO_TOTAL_V2 * 0.25])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_HEADER_V2),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_tabla_contribuciones_v2(contrib, empresa_config, base_rem):
    header = ["CONCEPTO", "UNIDAD", "BASE", "MONTO"]
    data = [header]

    def fila(desc, unidad, base, monto):
        data.append([desc, unidad, base, fmt_monto(monto)])

    def subtitulo(texto):
        data.append([texto, "", "", ""])

    fila("ART", fmt_pct(empresa_config.get("alicuota_art", 0)), fmt_monto(base_rem), contrib["art"])
    fila("ART - Componente Fijo (FFEP)", "Fijo mensual", "-", contrib.get("ffep", 0))

    fila("Contribución Jubilación (SIPA)",
         fmt_pct(0.1077 if empresa_config.get("pyme") else 0.127),
         fmt_monto(base_rem), contrib["jubilacion_patronal"])
    fila("Fondo Nacional de Empleo", fmt_pct(0.0094), fmt_monto(base_rem), contrib["fne"])
    fila("Asignaciones Familiares", fmt_pct(empresa_config.get("alicuota_asig_familiares", 0)),
         fmt_monto(base_rem), contrib["asignaciones_familiares"])

    fila("Contribución Obra Social", fmt_pct(0.06), fmt_monto(base_rem), contrib["obra_social_patronal"])
    fila("Seguro de Vida Obligatorio", "Fijo", fmt_monto(contrib["seguro_vida"]), contrib["seguro_vida"])

    subtitulo("Costo derivado del CCT")
    fila("Contribución OSECAC", "Fijo por empleado", "-", contrib["contrib_extraordinaria_osecac"])
    fila("Contribución INACAP", "Fijo mensual", "-", contrib["inacap"])
    fila("Seguro de Retiro La Estrella", fmt_pct(0.016), fmt_monto(base_rem), contrib["seguro_la_estrella"])
    if "seguro_vida_cct130" in contrib:
        fila("Seguro de Vida CCT 130/75", "Fijo", "-", contrib["seguro_vida_cct130"])

    t = Table(data, colWidths=[ANCHO_TOTAL_V2 * 0.45, ANCHO_TOTAL_V2 * 0.20, ANCHO_TOTAL_V2 * 0.15, ANCHO_TOTAL_V2 * 0.20])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO_V2),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i, row in enumerate(data):
        if row[0] == "Costo derivado del CCT":
            style.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
            style.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO_V2))
    t.setStyle(TableStyle(style))
    return t


def construir_barra_subtotal_v2(total):
    return construir_barra_titulo_v2("SUB TOTAL CONTRIBUCIONES EMPLEADOR", total)


def construir_tabla_sueldo_v2(r, emp):
    header = ["CONCEPTO", "UNIDAD", "BASE", "MONTO"]
    data = [header]

    def fila(desc, unidad, base, monto):
        data.append([desc, unidad, base, fmt_monto(monto)])

    def subtitulo(texto):
        data.append([texto, "", "", ""])

    subtitulo("REMUNERATIVO")
    fila("Sueldo Básico", f"{emp.get('dias_trabajados', 30):.0f}", fmt_monto(r["basico_prop"]), r["basico_prop"])
    if r.get("antiguedad", 0) > 0:
        fila("Antigüedad", fmt_pct(r.get("antiguedad_pct") or 0),
             fmt_monto(r["basico_prop"]), r["antiguedad"])
    if r.get("presentismo", 0) > 0:
        fila("Presentismo", fmt_pct(1 / 12), fmt_monto(r["basico_prop"] + r.get("antiguedad", 0)), r["presentismo"])

    if r.get("no_remunerativos"):
        subtitulo("NO REMUNERATIVO")
        for concepto in r["no_remunerativos"]:
            fila(concepto["desc"], concepto.get("unidad", ""), fmt_monto(concepto.get("base", 0)), concepto["monto"])

    subtitulo("DESCUENTOS")
    if r.get("jubilacion", 0) > 0:
        fila("Jubilación", fmt_pct(0.11), fmt_monto(r["base_rem"]), r["jubilacion"])
    if r.get("pami", 0) > 0:
        fila("Ley 19.032 (INSSJP)", fmt_pct(0.03), fmt_monto(r["base_rem"]), r["pami"])
    if r.get("obra_social", 0) > 0:
        fila("Obra Social - OSECAC", fmt_pct(0.03), fmt_monto(r["base_rem"]), r["obra_social"])
    if r.get("sec", 0) > 0:
        fila("Sindicato Empleados de Comercio", fmt_pct(0.02), fmt_monto(r["base_rem"]), r["sec"])
    if r.get("faecys", 0) > 0:
        fila("FAECyS", fmt_pct(0.005), fmt_monto(r["base_rem"]), r["faecys"])
    if r.get("redondeo", 0):
        fila("Redondeo", "-", "-", r["redondeo"])

    t = Table(data, colWidths=[ANCHO_TOTAL_V2 * 0.45, ANCHO_TOTAL_V2 * 0.20, ANCHO_TOTAL_V2 * 0.15, ANCHO_TOTAL_V2 * 0.20])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO_V2),
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
            style.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO_V2))
    t.setStyle(TableStyle(style))
    return t


def construir_fila_composicion_v2(r):
    no_rem_total = sum(c["monto"] for c in r.get("no_remunerativos", []))
    data = [[f"Remunerativo: $ {fmt_monto(r['base_rem'])}",
             f"No Remunerativo: $ {fmt_monto(no_rem_total)}",
             f"Descuentos: $ {fmt_monto(r['total_desc'])}"]]
    t = Table(data, colWidths=[ANCHO_TOTAL_V2 / 3] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_HEADER_V2),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def construir_fila_recibi_la_suma_v2(lugar, fecha_txt):
    """El Excel modelo usa 'Recibí la suma de: ....' + 'Depositado en:' +
    lugar/fecha + línea de firma (no 'SON PESOS', que pertenecía a la
    referencia incorrecta de Turismo)."""
    data = [["Recibí la suma de: " + "." * 90]]
    t1 = Table(data, colWidths=[ANCHO_TOTAL_V2])
    t1.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    data2 = [["Depositado en: ______________________", ""]]
    t2 = Table(data2, colWidths=[ANCHO_TOTAL_V2 * 0.6, ANCHO_TOTAL_V2 * 0.4])
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7)]))

    data3 = [[f"{lugar}, {fecha_txt}.", "...................................."]]
    t3 = Table(data3, colWidths=[ANCHO_TOTAL_V2 * 0.6, ANCHO_TOTAL_V2 * 0.4])
    t3.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))

    data4 = [["", "Firma del Empleado"]]
    t4 = Table(data4, colWidths=[ANCHO_TOTAL_V2 * 0.6, ANCHO_TOTAL_V2 * 0.4])
    t4.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    return [t1, t2, t3, t4]


def _agrupar_para_detalle_v2(contrib, r):
    costo_sindical_emp = contrib["seguro_la_estrella"] + contrib["inacap"] + contrib.get("seguro_vida_cct130", 0)
    costo_sindical_trab = r.get("sec", 0) + r.get("faecys", 0)

    seg_social_emp = contrib["jubilacion_patronal"] + contrib["fne"] + contrib["asignaciones_familiares"]
    seg_social_trab = r["jubilacion"]

    # PAMI/INSSJP patronal — TODO: no confirmado como concepto separado para
    # TV Crecer, se deja en $0 hasta que el contador lo confirme.
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


ANCHO_DETALLE_V2 = ANCHO_TOTAL_V2 * 0.60
ANCHO_PIE_V2 = ANCHO_TOTAL_V2 * 0.40


def construir_pie_v2(contrib, r, neto):
    g = _agrupar_para_detalle_v2(contrib, r)
    total = neto + contrib["total"]
    valores = [neto, g["seg_social_emp"], g["costo_sindical_emp"], g["obra_social_emp"],
               g["pami_emp"], g["art_emp"], g["scvo_emp"]]
    etiquetas = ["Sueldo Neto", "Seg. Social Empl.", "Costo Sindical", "Obra Social",
                 "PAMI", "ART", "SCVO"]

    d = Drawing(ANCHO_PIE_V2, 45 * mm)
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
    for i, col in enumerate(paleta):
        pie.slices[i].fillColor = col
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


def construir_tabla_detalle_v2(contrib, r):
    g = _agrupar_para_detalle_v2(contrib, r)
    data = [
        ["Total Costo Sindical", "", "Total costo INSSJP (PAMI)", ""],
        ["Empleador", fmt_monto(g["costo_sindical_emp"]), "Empleador", fmt_monto(g["pami_emp"])],
        ["Trabajador", fmt_monto(g["costo_sindical_trab"]), "Trabajador", fmt_monto(g["pami_trab"])],
        ["Total Seguridad Social", "", "Total costo ART", ""],
        ["Empleador", fmt_monto(g["seg_social_emp"]), "Empleador", fmt_monto(g["art_emp"])],
        ["Trabajador", fmt_monto(g["seg_social_trab"]), "", ""],
        ["Total Obra Social", "", "Total Costo SCVO", ""],
        ["Empleador", fmt_monto(g["obra_social_emp"]), "Empleador", fmt_monto(g["scvo_emp"])],
        ["Trabajador", fmt_monto(g["obra_social_trab"]), "", ""],
    ]
    t = Table(data, colWidths=[ANCHO_DETALLE_V2 * 0.25, ANCHO_DETALLE_V2 * 0.20,
                                ANCHO_DETALLE_V2 * 0.34, ANCHO_DETALLE_V2 * 0.21])
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


def construir_titulo_detalle_v2():
    data = [["Detalle de la composición salarial", "Costo total empleador"]]
    t = Table(data, colWidths=[ANCHO_DETALLE_V2, ANCHO_PIE_V2])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def generar_recibo_v2(empresa_config, emp, r, contrib, neto, periodo_txt, periodo_dt, fecha_pago_aportes,
                       lugar="Buenos Aires", fecha_firma_txt=""):
    elementos = []
    elementos.append(construir_titulo_empresa_v2(empresa_config))
    elementos.append(construir_fila_periodo_empleado_v2(emp, r, periodo_txt))
    elementos.append(construir_fila_datos_adicionales_v2(emp, empresa_config, periodo_dt, fecha_pago_aportes))

    elementos.append(construir_barra_titulo_v2("COSTO TOTAL EMPLEADOR", contrib["total"]))
    elementos.append(construir_tabla_contribuciones_v2(contrib, empresa_config, r["base_rem"]))
    elementos.append(construir_barra_subtotal_v2(contrib["total"]))

    elementos.append(construir_barra_titulo_v2("SUELDO BRUTO", r["base_rem"]))
    elementos.append(construir_tabla_sueldo_v2(r, emp))
    elementos.append(construir_fila_composicion_v2(r))
    elementos.append(construir_barra_titulo_v2("SUELDO NETO $", neto))

    elementos.extend(construir_fila_recibi_la_suma_v2(lugar, fecha_firma_txt))

    elementos.append(construir_titulo_detalle_v2())
    detalle = construir_tabla_detalle_v2(contrib, r)
    pie = construir_pie_v2(contrib, r, neto)
    combinado = Table([[detalle, pie]], colWidths=[ANCHO_DETALLE_V2, ANCHO_PIE_V2])
    combinado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elementos.append(combinado)

    return elementos


def generar_pdf_v2(empleados, netos, periodo, empresa_config, valores_mensuales):
    """
    Formato de recibo con tablas reales (reportlab.platypus), siguiendo la
    estructura del Excel modelo oficial de Convenio Comercio (CCT 130/75).
    Costo total empleador + contribuciones patronales + composición salarial
    + gráfico de torta. Una copia por página completa (no dos por hoja).

    valores_mensuales: dict OBLIGATORIO con "inacap" y "ffep" — se propaga
    tal cual a calcular_contribuciones_patronales().
    """
    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    mes_nombre = {
        "01": "ENERO", "02": "FEBRERO", "03": "MARZO", "04": "ABRIL",
        "05": "MAYO", "06": "JUNIO", "07": "JULIO", "08": "AGOSTO",
        "09": "SEPTIEMBRE", "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE"
    }
    mm_str = periodo[4:6] if len(periodo) == 6 else "11"
    aa_str = periodo[2:4] if len(periodo) == 6 else "25"
    mes_num = int(mm_str)
    anio_num = 2000 + int(aa_str)
    periodo_dt = datetime.date(anio_num, mes_num, 1)
    periodo_txt = f"{mes_nombre.get(mm_str,'?')} {anio_num}"
    if mes_num == 12:
        mes_pago_num, anio_pago_num = 1, anio_num + 1
    else:
        mes_pago_num, anio_pago_num = mes_num + 1, anio_num
    fecha_pago_aportes = datetime.date(anio_pago_num, mes_pago_num, 1)
    fecha_firma_txt = f"{fecha_pago_aportes.day:02d} de {mes_nombre[f'{mes_pago_num:02d}']} de {anio_pago_num}"

    for i, emp in enumerate(empleados):
        r = liquidar(emp)
        contrib = calcular_contribuciones_patronales(emp, r, empresa_config, valores_mensuales)
        neto = netos[i]

        fecha_ingreso_dt = _parse_fecha_ddmmaaaa(emp.get("fecha_ingreso"))
        emp2 = dict(emp)
        emp2["fecha_ingreso"] = fecha_ingreso_dt
        r2 = _preparar_r_para_recibo_v2(r, periodo_dt, fecha_ingreso_dt)

        elementos = generar_recibo_v2(empresa_config, emp2, r2, contrib, neto, periodo_txt,
                                       periodo_dt, fecha_pago_aportes, fecha_firma_txt=fecha_firma_txt)
        frame = Frame(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm, showBoundary=0)
        sobrante = frame.addFromList(elementos, c)
        if sobrante:
            raise ValueError(
                f"El recibo de {emp.get('nombre','?')} no entro en una pagina "
                f"({len(sobrante)} elementos sobrantes) - revisar tamanos/fuentes."
            )
        c.showPage()

    c.save()
    return buffer.getvalue()
