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
import os, base64, json, math, io, re
import httpx
import pandas as pd
from liquidacion import liquidar, generar_txt, generar_pdf
from empresas import EMPRESAS, resolver_empresa, buscar_empleado_por_cuil, buscar_empleado_por_nombre

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
    env_refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
    if env_refresh_token:
        return {"refresh_token": env_refresh_token}
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
    ya_persistido = bool(os.environ.get("GMAIL_REFRESH_TOKEN"))
    return {
        "ok": True,
        "mensaje": "Gmail autorizado correctamente. Ya podés usar /liquidar.",
        "refresh_token": token_data["refresh_token"],
        "accion_requerida": (
            "Ya está configurada la variable GMAIL_REFRESH_TOKEN en Railway — no hace falta nada más."
            if ya_persistido else
            "IMPORTANTE: copiá el valor de 'refresh_token' de esta respuesta y creá la variable de "
            "entorno GMAIL_REFRESH_TOKEN en Railway (Variables → New Variable) con ese valor. "
            "Sin esto, cada redeploy va a volver a pedir autorización."
        ),
    }

def extraer_dominio_remitente_original(cuerpo_mail: str) -> str | None:
    """
    Busca el patrón 'De: Nombre <email@dominio.com>' (o 'From:', con o sin
    nombre antes del email) que los clientes de mail agregan automáticamente
    al reenviar un mail, y devuelve el dominio del email.
    Retorna None si no encuentra el patrón.
    """
    match = re.search(
        r"(?:De|From)\s*:\s*(?:[^<\n]*<)?\s*[\w.+-]+@([\w.-]+\.\w+)\s*>?",
        cuerpo_mail,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None

def extraer_subject(msg: dict) -> str:
    """Extrae el header Subject de un mensaje de Gmail (formato 'full')."""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == "subject":
            return h.get("value", "")
    return ""

def armar_respuesta(empleados_raw: list, periodo: str, empresa_id: str, advertencias_extra: list = None) -> dict:
    """Calcula liquidaciones y genera TXT+PDF. Compartido por /liquidar y /liquidar-texto-libre."""
    empresa_config = EMPRESAS[empresa_id]

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

    txt_content = generar_txt(empleados_raw, periodo, empresa_config)
    txt_b64 = base64.b64encode(txt_content.encode()).decode()

    pdf_bytes = generar_pdf(empleados_raw, netos, periodo, empresa_config)
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    nombre_archivo = empresa_config["nombre"].upper().replace(" ", "_").replace(".", "").replace(",", "")

    return {
        "ok"          : True,
        "periodo"     : periodo,
        "empleados"   : resultados,
        "total_neto"  : sum(netos),
        "advertencias": advertencias_extra or [],
        "archivos"    : {
            "pdf_filename": f"{nombre_archivo}_RECIBOS_{periodo}.pdf",
            "pdf_b64"     : pdf_b64,
            "txt_filename": f"{nombre_archivo}_LSD_{periodo}.txt",
            "txt_b64"     : txt_b64,
        }
    }

# Campos opcionales con su valor por defecto — usado para completar lo que
# falte cuando los empleados llegan armados a mano (endpoint de texto libre)
DEFAULTS_EMPLEADO = {
    "categoria": "", "fuera_convenio": False, "cuil": "", "legajo": "",
    "fecha_ingreso": "", "obra_social_cod": "", "dias_trabajados": 30,
    "dias_feriado": 0, "antiguedad_monto": 0, "presentismo": 0,
    "a_cuenta_aumentos": 0, "asig_no_rem": 0, "antiguedad_s_acuerdo": 0,
    "presentismo_s_acuerdo": 0, "osecac": 0, "sec": 0, "faecys": 0,
    "os_sobre_nr": False,
}

def enriquecer_empleado(empresa_id: str, emp_in: dict) -> tuple[dict, list]:
    """
    Busca al empleado en la base de datos de la empresa y completa campos
    faltantes. Devuelve (empleado_enriquecido, lista_de_advertencias).
    El valor del mail (emp_in) siempre tiene prioridad sobre la base, excepto
    cuando el mail no trae el dato (entonces se usa el de la base).
    """
    advertencias = []
    cuil_mail = str(emp_in.get("cuil", "")).replace("-", "").strip()

    empleado_db = None
    if cuil_mail:
        empleado_db = buscar_empleado_por_cuil(empresa_id, cuil_mail)
    if not empleado_db:
        empleado_db = buscar_empleado_por_nombre(empresa_id, emp_in.get("nombre", ""))

    if not empleado_db:
        # No esta en la base, comportamiento actual sin cambios
        return emp_in, advertencias

    resultado = dict(emp_in)  # copia, no mutar el original

    # Completar campos simples si faltan en el mail
    campos_completar = {
        "legajo": empleado_db.get("legajo", ""),
        "cuil": empleado_db.get("cuil", cuil_mail),
        "categoria": empleado_db.get("categoria_display", ""),
        "fuera_convenio": empleado_db.get("fuera_convenio", False),
        "obra_social_cod": empleado_db.get("obra_social_cod", ""),
        "fecha_ingreso": empleado_db.get("fecha_ingreso", ""),
    }
    for campo, valor_db in campos_completar.items():
        if not resultado.get(campo):
            resultado[campo] = valor_db

    # Logica especial de basico_mensual
    basico_mail = resultado.get("basico_mensual", 0) or 0
    basico_db = empleado_db.get("basico_mensual_actual", 0)

    if basico_mail > 0:
        if basico_db and basico_mail != basico_db:
            advertencias.append(
                f"El basico de \"{empleado_db['nombre_canonico']}\" en este mail "
                f"(${basico_mail:,.0f}) difiere del guardado en la base "
                f"(${basico_db:,.0f}). Verificar si hubo un aumento y actualizar "
                f"empresas.py manualmente si corresponde."
            )
        # resultado["basico_mensual"] ya tiene el valor del mail, no se toca
    else:
        if basico_db:
            resultado["basico_mensual"] = basico_db
        # si no hay basico ni en el mail ni en la base, se deja en 0 -
        # la validacion de mas abajo lo va a rechazar como corresponde

    return resultado, advertencias

# ─── Endpoint principal ─────────────────────────────────────
@app.post("/liquidar")
async def liquidar_endpoint(request: Request):
    body = await request.json()
    message_id = body.get("message_id")
    cuerpo_mail_original = body.get("cuerpo_mail_original")

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

        # 1.5. Identificar empresa (dominio del remitente original, o alias en el asunto)
        asunto = extraer_subject(msg)
        dominio = extraer_dominio_remitente_original(cuerpo_mail_original) if cuerpo_mail_original else None
        empresa_id = resolver_empresa(dominio=dominio, texto_asunto=asunto)
        if not empresa_id:
            raise HTTPException(
                400,
                f"No se pudo identificar la empresa. Dominio detectado: {dominio or 'ninguno'}. Asunto: {asunto or 'no disponible'}"
            )

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

            obra_social_raw = row.iloc[57] if len(row) > 57 else None
            obra_social_cod = str(obra_social_raw).strip() if pd.notna(obra_social_raw) else ""

            # TODO: el Excel de novedades no trae legajo — hasta que ese dato tenga
            # una fuente real (padrón/CRM), se resuelve por CUIL con la tabla de la empresa.
            legajo = EMPRESAS[empresa_id]["legajos"].get(cuil, "")

            categoria_txt = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
            fuera_convenio = "FUERA" in categoria_txt.upper()

            empleados_raw.append({
                "nombre"               : str(nombre),
                "categoria"            : categoria_txt,
                "fuera_convenio"       : fuera_convenio,
                "cuil"                 : cuil,
                "legajo"               : legajo,
                "fecha_ingreso"        : fecha_ingreso,
                "obra_social_cod"      : obra_social_cod,
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

        # 5. Calcular liquidaciones y generar TXT + PDF
        return JSONResponse(armar_respuesta(empleados_raw, periodo, empresa_id))

    except Exception as e:
        raise HTTPException(500, f"Error procesando Excel: {str(e)}")

# ─── Endpoint para novedades sin Excel (texto libre) ────────
@app.post("/liquidar-texto-libre")
async def liquidar_texto_libre(request: Request):
    """
    Recibe novedades ya estructuradas en JSON (parseadas previamente por
    Claude a partir del texto libre del mail) y corre el mismo cálculo y
    generación de PDF/TXT que /liquidar, sin pasar por un Excel.

    Body esperado:
    {
      "periodo": "202511",
      "cuerpo_mail_original": "...",  (opcional, usado para identificar la empresa por dominio)
      "asunto": "...",  (opcional, usado para identificar la empresa por alias si falla el dominio)
      "empleados": [
        {
          "nombre": "...", "basico_mensual": 1000000,
          ... (el resto de los campos es opcional, se completan con default)
        }
      ]
    }
    """
    body = await request.json()
    periodo = body.get("periodo")
    empleados_in = body.get("empleados")
    cuerpo_mail_original = body.get("cuerpo_mail_original")
    asunto = body.get("asunto")

    if not periodo or not empleados_in:
        raise HTTPException(400, "Se requiere 'periodo' y 'empleados' (lista no vacía)")

    dominio = extraer_dominio_remitente_original(cuerpo_mail_original) if cuerpo_mail_original else None
    empresa_id = resolver_empresa(dominio=dominio, texto_asunto=asunto)
    if not empresa_id:
        raise HTTPException(
            400,
            f"No se pudo identificar la empresa. Dominio detectado: {dominio or 'ninguno'}. Asunto: {asunto or 'no disponible'}"
        )

    empleados_raw = []
    todas_las_advertencias = []
    for emp_in in empleados_in:
        if "nombre" not in emp_in or not emp_in.get("nombre"):
            raise HTTPException(400, f"Cada empleado requiere al menos 'nombre': {emp_in}")

        emp_enriquecido, advertencias_emp = enriquecer_empleado(empresa_id, emp_in)
        todas_las_advertencias.extend(advertencias_emp)

        emp = {**DEFAULTS_EMPLEADO, **emp_enriquecido}
        emp["cuil"] = str(emp.get("cuil", "")).replace("-", "").strip()

        if not emp.get("basico_mensual") or emp["basico_mensual"] <= 0:
            raise HTTPException(
                400,
                f"No se pudo determinar 'basico_mensual' para \"{emp['nombre']}\": "
                f"no vino en el mail y no esta en la base de datos de empleados."
            )

        empleados_raw.append(emp)

    try:
        return JSONResponse(armar_respuesta(empleados_raw, periodo, empresa_id, todas_las_advertencias))
    except Exception as e:
        raise HTTPException(500, f"Error generando liquidación desde texto libre: {str(e)}")
