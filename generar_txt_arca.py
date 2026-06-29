"""
Generador de TXT para ARCA — Libro de Sueldos Digital (LSD)
TV Crecer S.R.L. — CUIT 30-70906672-9
Noviembre 2025

Estructura según especificación AFIP:
  Registro 1 (cabecera): 35 caracteres — 1 línea por archivo
  Registro 2 (empleados): 115 caracteres — 1 línea por empleado

Solo se informan empleados bajo relación de dependencia con aportes
al F931. Diego Montes de Oca (socio gerente / fuera de convenio)
se incluye también en el F931.
"""

# ─────────────────────────────────────────────────────────────
# DATOS DE LA EMPRESA
# ─────────────────────────────────────────────────────────────
CUIT_EMPRESA   = "30709066729"   # sin guiones
PERIODO        = "202511"        # AAAAMM
TIPO_LIQ       = "M"            # M = mensual
NRO_LIQUIDACION = "00003"       # número de liquidación del período
DIAS_BASE      = "30"
FECHA_PAGO     = "20251201"     # 1/12/2025 — formato AAAAMMDD

# ─────────────────────────────────────────────────────────────
# EMPLEADOS A INFORMAR EN EL F931
# Incluye los 3 empleados de TV Crecer
# ─────────────────────────────────────────────────────────────
empleados = [
    {
        "nombre"      : "Montes de Oca Diego",
        "cuil"        : "20186092555",   # sin guiones
        "legajo"      : "",
        "dependencia" : "",
        "cbu"         : "",
        "dias_prop"   : "000",           # 0 = no proporciona tope
        "forma_pago"  : "1",             # 1 = efectivo/acreditación directa
    },
    {
        "nombre"      : "Sarich Agustín Iván",
        "cuil"        : "20359670452",
        "legajo"      : "",
        "dependencia" : "",
        "cbu"         : "",
        "dias_prop"   : "000",
        "forma_pago"  : "1",
    },
    {
        "nombre"      : "Arzeno Lucas Agustín",
        "cuil"        : "20398771940",
        "legajo"      : "",
        "dependencia" : "",
        "cbu"         : "",
        "dias_prop"   : "000",
        "forma_pago"  : "1",
    },
]

CANT_EMPLEADOS = str(len(empleados)).zfill(6)   # 000003

# ─────────────────────────────────────────────────────────────
# GENERACIÓN REGISTRO 1 — CABECERA (35 chars)
# ─────────────────────────────────────────────────────────────
# Estructura:
#  [0:2]   "01"              — identificador fijo
#  [2:13]  CUIT empleador    — 11 dígitos sin guiones
#  [13:15] "SJ"              — identifica liquidación SyJ
#  [15:21] periodo AAAAMM    — 6 dígitos
#  [21:22] tipo liquidación  — M/Q/D/H
#  [22:27] nro liquidación   — 5 dígitos con ceros
#  [27:29] días base         — "30"
#  [29:35] cant. reg tipo 04 — 6 dígitos con ceros

def generar_registro1():
    r = (
        "01"
        + CUIT_EMPRESA
        + "SJ"
        + PERIODO
        + TIPO_LIQ
        + NRO_LIQUIDACION
        + DIAS_BASE
        + CANT_EMPLEADOS
    )
    assert len(r) == 35, f"Registro 1 largo incorrecto: {len(r)} (esperado 35)"
    return r

# ─────────────────────────────────────────────────────────────
# GENERACIÓN REGISTRO 2 — POR EMPLEADO (115 chars)
# ─────────────────────────────────────────────────────────────
# Estructura:
#  [0:2]    "02"             — identificador fijo
#  [2:13]   CUIL empleado    — 11 dígitos sin guiones
#  [13:18]  legajo           — 5 chars, espacios si vacío
#  [18:23]  dependencia      — 5 chars, espacios si vacío
#  [23:45]  CBU              — 22 chars, espacios si vacío (solo si forma_pago=3)
#  [45:95]  espacios         — 50 chars reservados
#  [95:98]  días proporcionar tope — 3 dígitos ("000" si no aplica)
#  [98:106] fecha de pago    — AAAAMMDD
#  [106:114] fecha rúbrica   — 8 chars espacios (no se completa)
#  [114:115] forma de pago   — 1 char (1=efectivo, 2=cheque, 3=acreditación)

def generar_registro2(emp):
    cuil        = emp["cuil"].ljust(11)[:11]
    legajo      = emp["legajo"].ljust(5)[:5]
    dependencia = emp["dependencia"].ljust(5)[:5]
    cbu         = emp["cbu"].ljust(22)[:22]
    reservado   = " " * 50
    dias_prop   = emp["dias_prop"].zfill(3)[:3]
    fecha_pago  = FECHA_PAGO
    rubrica     = " " * 8
    forma_pago  = emp["forma_pago"]

    r = (
        "02"
        + cuil
        + legajo
        + dependencia
        + cbu
        + reservado
        + dias_prop
        + fecha_pago
        + rubrica
        + forma_pago
    )
    assert len(r) == 115, (
        f"Registro 2 largo incorrecto para {emp['nombre']}: {len(r)} (esperado 115)"
    )
    return r

# ─────────────────────────────────────────────────────────────
# GENERAR ARCHIVO TXT
# ─────────────────────────────────────────────────────────────
def generar_txt(nombre_archivo="TV_CRECER_LSD_202511.txt"):
    lineas = []

    reg1 = generar_registro1()
    lineas.append(reg1)

    for emp in empleados:
        reg2 = generar_registro2(emp)
        lineas.append(reg2)

    contenido = "\r\n".join(lineas)   # CRLF — requerido por ARCA

    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write(contenido)

    return lineas, nombre_archivo

# ─────────────────────────────────────────────────────────────
# OUTPUT Y VALIDACIÓN
# ─────────────────────────────────────────────────────────────
SEP = "=" * 62

lineas, archivo = generar_txt()

print(SEP)
print("GENERADOR TXT — LIBRO DE SUELDOS DIGITAL (ARCA)")
print(f"Empresa  : TV Crecer S.R.L.  CUIT: {CUIT_EMPRESA}")
print(f"Período  : {PERIODO}   Tipo: {TIPO_LIQ}   Liq Nro: {NRO_LIQUIDACION}")
print(f"Empleados: {len(empleados)}")
print(SEP)

print(f"\nREGISTRO 1 — Cabecera")
print(f"  {lineas[0]}")
print(f"  Largo: {len(lineas[0])} ✓" if len(lineas[0]) == 35 else f"  Largo: {len(lineas[0])} ✗ ERROR")

print(f"\nREGISTROS 2 — Empleados")
for i, emp in enumerate(empleados):
    reg = lineas[i + 1]
    estado = "✓" if len(reg) == 115 else "✗ ERROR"
    print(f"  {emp['nombre']:<28} largo: {len(reg)} {estado}")
    print(f"  {reg}")
    print()

print(f"\n{SEP}")
print(f"VALIDACIONES")
assert len(lineas[0]) == 35,  "✗ Registro 1: largo incorrecto"
print(f"  ✓ Registro 1: 35 caracteres")
for i, emp in enumerate(empleados):
    assert len(lineas[i+1]) == 115, f"✗ Registro 2 {emp['nombre']}: largo incorrecto"
print(f"  ✓ Registros 2: 115 caracteres c/u")
print(f"  ✓ Archivo generado: {archivo}")
print(SEP)

print(f"\nCONTENIDO DEL ARCHIVO (para verificar en bloc de notas):")
print(f"{'─'*62}")
for l in lineas:
    print(l)
print(f"{'─'*62}")
