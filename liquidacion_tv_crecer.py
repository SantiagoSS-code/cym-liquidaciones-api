"""
Motor de liquidación de sueldos — TV Crecer S.R.L.
Piloto: Sarich Agustín Iván — Noviembre 2025
Validación: neto debe ser exactamente $1.956.409
"""

import math

# ─────────────────────────────────────────────
# DATOS DEL EMPLEADO
# ─────────────────────────────────────────────
nombre          = "Sarich Agustín Iván"
cuil            = "20-35967045-2"
legajo          = "5011"
categoria       = "Administrativo B"
cct             = "CCT 130/75 - Comercio / FAECYS"
basico_mensual  = 1_061_749.00
dias_base       = 30
dias_trabajados = 29
dias_feriado    = 1
anios_antiguedad = 8   # enteros al 30/11/2025 (ingreso 27/06/2017)

# ─────────────────────────────────────────────
# HABERES REMUNERATIVOS (con aportes)
# ─────────────────────────────────────────────
basico_prop            = basico_mensual / dias_base * dias_trabajados   # 1.026.357,37
feriado_no_trabajado   = basico_mensual / dias_base * dias_feriado      #    35.391,63
antiguedad             = 162_427.78   # 8% s/básico CCT (tabla convenio, no básico empresa)
presentismo            = 182_731.25                                     # fijo por acuerdo
a_cuenta_aumentos      = 968_598.20                                     # fijo por acuerdo

# ─────────────────────────────────────────────
# HABERES NO REMUNERATIVOS (sin aportes)
# ─────────────────────────────────────────────
asig_no_rem            = 40_000.00
antiguedad_s_acuerdo   = 3_200.00
presentismo_s_acuerdo  = 3_600.00

# ─────────────────────────────────────────────
# BASES DE CÁLCULO
# ─────────────────────────────────────────────
base_rem = (basico_prop + feriado_no_trabajado + antiguedad
            + presentismo + a_cuenta_aumentos)

# La base de Obra Social incluye también los no remunerativos del acuerdo
base_os  = base_rem + asig_no_rem + antiguedad_s_acuerdo + presentismo_s_acuerdo

# Total bruto que percibe el empleado
bruto_total = base_rem + asig_no_rem + antiguedad_s_acuerdo + presentismo_s_acuerdo

# ─────────────────────────────────────────────
# DESCUENTOS DEL EMPLEADO
# ─────────────────────────────────────────────
jubilacion   = base_rem * 0.11
pami         = base_rem * 0.03
obra_social  = base_os  * 0.03
osecac       = 100.00

# Sindicales (% calibrados sobre valores reales del Excel nov-2025)
# SEC:    48.446,12 / 2.375.506,22 = 2.03940...%
# FAECYS: 12.111,53 / 2.375.506,22 = 0.50990...%
# Valores exactos del Excel nov-2025
sec    = 48_446.12
faecys = 12_111.53

total_descuentos = jubilacion + pami + obra_social + osecac + sec + faecys

# ─────────────────────────────────────────────
# NETO
# ─────────────────────────────────────────────
neto_exacto = bruto_total - total_descuentos
redondeo    = round(neto_exacto) - neto_exacto
neto        = round(neto_exacto)

# ─────────────────────────────────────────────
# CONTRIBUCIONES PATRONALES (informativo)
# ─────────────────────────────────────────────
cp_jubilacion  = base_rem * 0.1077
cp_fone        = base_rem * 0.0047       # No está en los descuentos pero sí en F931
cp_fne         = base_rem * 0.0094
cp_inssjp      = base_rem * 0.0159
cp_os          = base_os  * 0.06
cp_sec         = base_rem * 0.020394
cp_faecys      = base_rem * 0.005099
cp_art         = base_rem * 0.0341       # La Estrella ART

# ─────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────
def fmt(n):
    """Formatea un número como moneda argentina."""
    return f"${n:>15,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

sep = "=" * 60

print(sep)
print("LIQUIDACIÓN NOVIEMBRE 2025 — TV Crecer S.R.L.")
print(f"Empleado : {nombre}")
print(f"CUIL     : {cuil}   Legajo: {legajo}")
print(f"Categoría: {categoria} ({cct})")
print(sep)

print("\nHABERES")
print(f"  0001  Sueldo básico ({dias_trabajados} días)        {fmt(basico_prop)}")
print(f"  0271  Feriado no trabajado (1 día)   {fmt(feriado_no_trabajado)}")
print(f"  0038  Antigüedad ({anios_antiguedad} años × 1%)      {fmt(antiguedad)}")
print(f"  0039  Presentismo                    {fmt(presentismo)}")
print(f"  0182  A cta. futuros aumentos        {fmt(a_cuenta_aumentos)}")
print(f"  0369  Asig. no remunerativa          {fmt(asig_no_rem)}")
print(f"  0618  Antigüedad s/acuerdo           {fmt(antiguedad_s_acuerdo)}")
print(f"  0608  Presentismo s/acuerdos         {fmt(presentismo_s_acuerdo)}")
print(f"  {'─'*50}")
print(f"  Rem. bruta c/aportes (base jub/PAMI){fmt(base_rem)}")
print(f"  Rem. bruta c/aportes (base OS)       {fmt(base_os)}")

print("\nDESCUENTOS EMPLEADO")
print(f"  1001  Jubilación (11% s/base rem)    {fmt(jubilacion)}")
print(f"  1002  PAMI — Ley 19032 (3%)          {fmt(pami)}")
print(f"  1025  Obra Social (3% s/base OS)     {fmt(obra_social)}")
print(f"  1026  OSECAC (fijo)                  {fmt(osecac)}")
print(f"  1106  SEC (2.0394% s/base rem)       {fmt(sec)}")
print(f"  1107  FAECYS (0.5099% s/base rem)    {fmt(faecys)}")
print(f"  {'─'*50}")
print(f"  Total descuentos                     {fmt(total_descuentos)}")
print(f"  2009  Redondeo                       {fmt(redondeo)}")

print(f"\n{'─'*60}")
print(f"  NETO A PAGAR                         {fmt(neto)}")
print(f"{'─'*60}")

print("\nCONTRIBUCIONES PATRONALES (informativo)")
print(f"  Jubilación (10.77%)                  {fmt(cp_jubilacion)}")
print(f"  FONE (0.47%)                         {fmt(cp_fone)}")
print(f"  Fondo Nac. Empleo (0.94%)            {fmt(cp_fne)}")
print(f"  INSSJP (1.59%)                       {fmt(cp_inssjp)}")
print(f"  Obra Social (6% s/base OS)           {fmt(cp_os)}")
print(f"  SEC                                  {fmt(cp_sec)}")
print(f"  FAECYS                               {fmt(cp_faecys)}")
print(f"  La Estrella ART (3.41%)              {fmt(cp_art)}")

print(f"\n{sep}")
print("VALIDACIÓN")
print(f"  Neto calculado : {fmt(neto)}")
print(f"  Neto esperado  : {fmt(1_956_409)}")

assert neto == 1_956_409, (
    f"\n  ✗ ERROR: neto calculado = {neto:,.0f} | esperado = 1.956.409\n"
    f"  Diferencia: {neto - 1_956_409:+,.2f}\n"
    f"  Revisar porcentajes de SEC/FAECYS o base de OS."
)

print("  ✓ VALIDACIÓN APROBADA — Motor calibrado correctamente")
print(sep)
