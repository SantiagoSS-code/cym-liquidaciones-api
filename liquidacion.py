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

# ─────────────────────────────────────────────
CUIT_EMPRESA = "30709066729"
EMPRESA      = "TV CRECER S.R.L."
DIRECCION    = "ESCALADA 1200"
BANCO        = "GALICIA"

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

def generar_txt(empleados, periodo, nro_liquidacion="00001"):
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

    reg1 = f"01{CUIT_EMPRESA}SJ{periodo}M{nro_liq}{dias_base}{cant}"
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

def generar_pdf(empleados, netos, periodo):
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
        txt(ML, y, "Empresa:", bold=True); txt(ML+18*mm, y, EMPRESA)
        txt(MR-60*mm, y, "Direccion:", bold=True); txt(MR-45*mm, y, DIRECCION)
        y -= 5*mm; linea(y); y -= 4*mm
        txt(ML, y, f"Nro C.U.I.T. Empresa:{CUIT_EMPRESA}")
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
        txt(ML, y, f"Banco: {BANCO}"); txt(W/2, y, "Recibí conforme la presente")
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
