"""
CyM Liquidaciones API
FastAPI server con OAuth2 de Gmail para descargar adjuntos directamente.
Endpoints:
  GET  /              → health check
  GET  /auth/login    → inicia flujo OAuth con Google
  GET  /auth/callback → callback OAuth, guarda refresh token
  POST /liquidar      → recibe message_id, descarga Excel, calcula, devuelve PDF+TXT
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import os, base64, json, math, io
import httpx
import pandas as pd
from liquidacion import liquidar, generar_txt, generar_pdf

app = FastAPI(title="CyM Liquidaciones API", version="2.0.0")

# ─── Config OAuth ───────────────────────────────────────────
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI  = "https://web-production-580e0.up.railway.app/auth/callback"
SCOPES        = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_FILE    = "/tmp/gmail_token.json"

def save_token(token_data: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)

def load_token() -> dict | None:
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except:
        return None

async def get_access_token() -> str:
    token = load_token()
    if not token:
        raise HTTPException(401, "No hay token. Visitá /auth/login para autorizar.")
    
    # Refrescar si expiró
    async with httpx.AsyncClient() as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id"     : CLIENT_ID,
            "client_secret" : CLIENT_SECRET,
            "refresh_token" : token["refresh_token"],
            "grant_type"    : "refresh_token",
        })
        data = r.json()
        if "access_token" not in data:
            raise HTTPException(401, f"Error refrescando token: {data}")
        return data["access_token"]

# ─── Endpoints OAuth ────────────────────────────────────────
@app.get("/")
def health():
    token = load_token()
    return {
        "status": "ok",
        "service": "CyM Liquidaciones API",
        "gmail_autorizado": token is not None
    }

@app.get("/auth/login")
def auth_login():
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url)

@app.get("/auth/callback")
async def auth_callback(code: str):
    async with httpx.AsyncClient() as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "code"          : code,
            "client_id"     : CLIENT_ID,
            "client_secret" : CLIENT_SECRET,
            "redirect_uri"  : REDIRECT_URI,
            "grant_type"    : "authorization_code",
        })
        token_data = r.json()
    
    if "refresh_token" not in token_data:
        raise HTTPException(400, f"No se obtuvo refresh_token: {token_data}")
    
    save_token(token_data)
    return {"ok": True, "mensaje": "Gmail autorizado correctamente. Ya podés usar /liquidar."}

# ─── Endpoint principal ─────────────────────────────────────
@app.post("/liquidar")
async def liquidar_endpoint(request: Request):
    body = await request.json()
    message_id = body.get("message_id")
    
    if not message_id:
        raise HTTPException(400, "Se requiere message_id")
    
    access_token = await get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        # 1. Obtener mensaje completo
        r = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full",
            headers=headers
        )
        msg = r.json()
        
        # 2. Encontrar el adjunto Excel
        attachment_id = None
        filename = None
        
        def find_attachment(parts):
            nonlocal attachment_id, filename
            for part in parts:
                if part.get("filename") and part["filename"].endswith((".xls", ".xlsx")):
                    attachment_id = part["body"].get("attachmentId")
                    filename = part["filename"]
                    return
                if part.get("parts"):
                    find_attachment(part["parts"])
        
        payload_parts = msg.get("payload", {}).get("parts", [])
        find_attachment(payload_parts)
        
        if not attachment_id:
            raise HTTPException(400, "No se encontró adjunto Excel en el mensaje")
        
        # 3. Descargar adjunto
        r2 = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
            headers=headers
        )
        att_data = r2.json()
        
        # Gmail usa base64url → convertir a base64 standard
        b64 = att_data["data"].replace("-", "+").replace("_", "/")
        file_bytes = base64.b64decode(b64)
    
    # 4. Procesar Excel
    try:
        engine = "xlrd" if filename.endswith(".xls") else "openpyxl"
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
        hojas = [h for h in xls.sheet_names if "control" not in h.lower() and "solo" not in h.lower()]
        hoja_activa = hojas[0]
        
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=hoja_activa, header=None, engine=engine)
        
        # Extraer período
        periodo_raw = df.iloc[4, 0]
        if hasattr(periodo_raw, "month"):
            periodo = f"{periodo_raw.year}{periodo_raw.month:02d}"
        else:
            partes = str(periodo_raw).split("/")
            periodo = f"20{partes[1]}{partes[0].zfill(2)}"
        
        # Extraer empleados
        empleados_raw = []
        for i in range(10, 20):
            if i >= len(df): break
            row = df.iloc[i]
            nombre = row.iloc[0]
            if pd.isna(nombre) or str(nombre).upper().startswith("TOTAL"): break
            
            def safe(val, default=0):
                return float(val) if pd.notna(val) and val != "" else default
            
            dias_trab = 29 if safe(row.iloc[7]) < safe(row.iloc[6]) and safe(row.iloc[6]) > 0 else 30

            cuil_raw = row.iloc[54] if len(row) > 54 else None
            cuil = str(cuil_raw).replace("-", "").strip() if pd.notna(cuil_raw) else ""

            fecha_ingreso_raw = row.iloc[55] if len(row) > 55 else None
            if hasattr(fecha_ingreso_raw, "strftime"):
                fecha_ingreso = fecha_ingreso_raw.strftime("%d/%m/%Y")
            else:
                fecha_ingreso = str(fecha_ingreso_raw) if pd.notna(fecha_ingreso_raw) else ""

            empleados_raw.append({
                "nombre"               : str(nombre),
                "categoria"            : str(row.iloc[1]) if pd.notna(row.iloc[1]) else "",
                "cuil"                 : cuil,
                "fecha_ingreso"        : fecha_ingreso,
                "basico_mensual"       : safe(row.iloc[6]),
                "dias_trabajados"      : dias_trab,
                "dias_feriado"         : 1 if safe(row.iloc[8]) > 0 else 0,
                "antiguedad_monto"     : safe(row.iloc[10]),
                "presentismo"          : safe(row.iloc[11]),
                "a_cuenta_aumentos"    : safe(row.iloc[12]),
                "asig_no_rem"          : safe(row.iloc[40]),
                "antiguedad_s_acuerdo" : safe(row.iloc[39]),
                "presentismo_s_acuerdo": safe(row.iloc[38]),
                "osecac"               : safe(row.iloc[44]),
                "sec"                  : safe(row.iloc[28]),
                "faecys"               : safe(row.iloc[29]),
                "os_sobre_nr"          : safe(row.iloc[44]) > 0,
            })
        
        # 5. Calcular liquidaciones
        resultados = []
        netos = []
        for emp in empleados_raw:
            r = liquidar(emp)
            netos.append(r["neto"])
            resultados.append({
                "nombre"    : emp["nombre"],
                "categoria" : emp["categoria"],
                "neto"      : r["neto"],
                "base_rem"  : round(r["base_rem"], 2),
                "total_desc": round(r["total_desc"], 2),
            })
        
        # 6. Generar TXT y PDF
        txt_content = generar_txt(empleados_raw, periodo)
        txt_b64 = base64.b64encode(txt_content.encode()).decode()
        
        pdf_bytes = generar_pdf(empleados_raw, netos, periodo)
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
        
        return JSONResponse({
            "ok"        : True,
            "periodo"   : periodo,
            "empleados" : resultados,
            "total_neto": sum(netos),
            "archivos"  : {
                "pdf_filename": f"TV_CRECER_RECIBOS_{periodo}.pdf",
                "pdf_b64"     : pdf_b64,
                "txt_filename": f"TV_CRECER_LSD_{periodo}.txt",
                "txt_b64"     : txt_b64,
            }
        })
    
    except Exception as e:
        raise HTTPException(500, f"Error procesando Excel: {str(e)}")
