"""
CyM Liquidaciones API
FastAPI server que recibe un Excel con novedades y devuelve:
- JSON con los netós calculados
- PDF de recibos (base64)
- TXT para ARCA (base64)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import math
import base64
import io
import tempfile
import os
from datetime import datetime

# Importar generadores
from liquidacion import liquidar, generar_txt, generar_pdf

app = FastAPI(title="CyM Liquidaciones API", version="1.0.0")

@app.get("/")
def health():
    return {"status": "ok", "service": "CyM Liquidaciones API"}

@app.post("/liquidar")
async def liquidar_endpoint(file: UploadFile = File(...)):
    """
    Recibe un Excel con novedades del mes y devuelve la liquidación completa.
    """
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(400, "El archivo debe ser .xls o .xlsx")

    contents = await file.read()

    try:
        # Leer Excel y extraer novedades
        engine = 'xlrd' if file.filename.endswith('.xls') else 'openpyxl'
        
        # Detectar la hoja más reciente (primer hoja que no sea control)
        xls = pd.ExcelFile(io.BytesIO(contents), engine=engine)
        hojas = [h for h in xls.sheet_names if 'control' not in h.lower() and 'solo' not in h.lower()]
        hoja_activa = hojas[0]  # la más reciente

        df = pd.read_excel(io.BytesIO(contents), sheet_name=hoja_activa, 
                          header=None, engine=engine)

        # Extraer período del excel (fila 4, col 0)
        periodo_raw = df.iloc[4, 0]  # ej: "11/25"
        if hasattr(periodo_raw, 'month'):
            periodo = f"{periodo_raw.year}{periodo_raw.month:02d}"
        else:
            partes = str(periodo_raw).split('/')
            periodo = f"20{partes[1]}{partes[0].zfill(2)}"

        # Extraer empleados (filas 10 en adelante hasta totales)
        empleados_raw = []
        for i in range(10, 20):
            if i >= len(df):
                break
            row = df.iloc[i]
            nombre = row.iloc[0]
            if pd.isna(nombre) or str(nombre).upper().startswith('TOTAL'):
                break
            
            def safe(val, default=0):
                return float(val) if pd.notna(val) and val != '' else default

            empleados_raw.append({
                "nombre"               : str(nombre),
                "categoria"            : str(row.iloc[1]) if pd.notna(row.iloc[1]) else "",
                "basico_mensual"       : safe(row.iloc[6]),
                "dias_trabajados"      : int(safe(row.iloc[7]) / safe(row.iloc[6]) * 30) if safe(row.iloc[6]) > 0 and safe(row.iloc[7]) < safe(row.iloc[6]) else 30,
                "dias_feriado"         : 1 if pd.notna(row.iloc[8]) and safe(row.iloc[8]) > 0 else 0,
                "antiguedad_monto"     : safe(row.iloc[10]),
                "presentismo"          : safe(row.iloc[11]),
                "a_cuenta_aumentos"    : safe(row.iloc[12]),
                "asig_no_rem"          : safe(row.iloc[40]),
                "antiguedad_s_acuerdo" : safe(row.iloc[39]),
                "presentismo_s_acuerdo": safe(row.iloc[38]),
                "osecac"               : safe(row.iloc[44]),
                "sec"                  : safe(row.iloc[28]),
                "faecys"               : safe(row.iloc[29]),
                "os_sobre_nr"          : safe(row.iloc[44]) > 0,  # tiene OSECAC
            })

        # Calcular liquidaciones
        resultados = []
        for emp in empleados_raw:
            r = liquidar(emp)
            resultados.append({
                "nombre"        : emp["nombre"],
                "categoria"     : emp["categoria"],
                "basico_mensual": emp["basico_mensual"],
                "base_rem"      : round(r["base_rem"], 2),
                "base_os"       : round(r["base_os"], 2),
                "jubilacion"    : round(r["jubilacion"], 2),
                "pami"          : round(r["pami"], 2),
                "obra_social"   : round(r["obra_social"], 2),
                "osecac"        : r["osecac"],
                "sec"           : r["sec"],
                "faecys"        : r["faecys"],
                "total_desc"    : round(r["total_desc"], 2),
                "neto"          : r["neto"],
            })

        # Generar TXT para ARCA
        txt_content = generar_txt(empleados_raw, periodo)
        txt_b64 = base64.b64encode(txt_content.encode()).decode()

        # Generar PDF de recibos
        pdf_bytes = generar_pdf(empleados_raw, [r["neto"] for r in [liquidar(e) for e in empleados_raw]], periodo)
        pdf_b64 = base64.b64encode(pdf_bytes).decode()

        return JSONResponse({
            "ok"       : True,
            "periodo"  : periodo,
            "hoja"     : hoja_activa,
            "empleados": resultados,
            "total_neto": sum(r["neto"] for r in resultados),
            "archivos" : {
                "txt_filename": f"TV_CRECER_LSD_{periodo}.txt",
                "txt_b64"     : txt_b64,
                "pdf_filename": f"TV_CRECER_RECIBOS_{periodo}.pdf",
                "pdf_b64"     : pdf_b64,
            }
        })

    except Exception as e:
        raise HTTPException(500, f"Error procesando el Excel: {str(e)}")
