"""
Configuración de empresas cliente.
Cada empresa se identifica por el dominio de mail de sus RRHH/contacto
(el remitente ORIGINAL de las novedades, no el mail del contador que reenvía),
o como respaldo, por un alias de nombre presente en el asunto del mail.
"""

import unicodedata

EMPRESAS = {
    "tv_crecer": {
        "nombre": "TV CRECER S.R.L.",
        "cuit": "30709066729",
        "direccion": "ESCALADA 1200",
        "banco": "GALICIA",
        "dominios": ["tvcrecer.com"],  # completar con el/los dominios reales del cliente
        "alias": ["TV Crecer", "TVCrecer"],
        "pyme": True,
        "alicuota_art": 0.04430,
        "alicuota_asig_familiares": 0.0470,
        "inacap_monto_mensual": 5567.94,  # actualizar cada vez que cambie el acuerdo INACAP
        "inacap_actualizado_al": "2026-07",  # mes/año en que se confirmo este valor por ultima vez - fuente: institutocap.org.ar/inacap/acuerdos_salariales
        "ffep_monto_mensual": 1827.00,  # componente fijo del ART - actualizar cada vez que cambie
        "ffep_actualizado_al": "2026-06",  # mes/año en que se confirmo este valor por ultima vez - fuente: el contador
        "legajos": {
            "20186092555": "005001",
            "20359670452": "005011",
            # Nota: Lucas Arzeno (CUIL 20398771940, legajo 005013) fue desvinculado.
            # Sacado de la nomina activa a partir de agosto 2026. Pendiente confirmar
            # con el contador si ya se liquido su liquidacion final.
        },
        "empleados": {
            "20186092555": {
                "nombre_canonico": "Diego Montes de Oca",
                "legajo": "005001",
                "categoria_afip": "999999 - SIN CATEGORIAS",
                "categoria_display": "Fuera de convenio",
                "convenio": "9999/99 - EXCLUIDO DE CONVENIO",
                "fuera_convenio": True,
                "fecha_ingreso": "2007-11-05",
                "obra_social_cod": "000000",
                "puesto": "1210 - DIRECTORES GENERALES Y GERENTES GENERALES DE EMPRESA",
                "basico_mensual_actual": 2500000,
                "basico_actualizado_al": "2026-07",
            },
            "20359670452": {
                "nombre_canonico": "Agustín Sarich",
                "legajo": "005011",
                "categoria_afip": "004332 - AYUDANTE - PERSONAL ADMINISTRATIVO",
                "categoria_display": "ADM B",
                "convenio": "0130/75 - COMERCIO",
                "fuera_convenio": False,
                "fecha_ingreso": "2017-06-27",
                "obra_social_cod": "126205",
                "puesto": "4190 - OTROS OFICINISTAS",
                "basico_mensual_actual": 1061749,
                "basico_actualizado_al": "2025-11",
            },
        },
    },
    # Se agregan nuevas empresas acá con la misma estructura
}

def _normalizar(texto: str) -> str:
    """Sin acentos, minúsculas, espacios extremos recortados."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()

def resolver_empresa_por_dominio(dominio: str) -> str | None:
    """Devuelve el id de empresa (key de EMPRESAS) para un dominio dado, o None si no matchea ninguna."""
    dominio = dominio.lower().strip()
    for empresa_id, config in EMPRESAS.items():
        if dominio in [d.lower() for d in config["dominios"]]:
            return empresa_id
    return None

def resolver_empresa_por_alias(texto: str) -> str | None:
    """Busca si el texto (ej. el asunto de un mail) contiene el alias de alguna empresa conocida."""
    texto_norm = _normalizar(texto)
    for empresa_id, config in EMPRESAS.items():
        for alias in config.get("alias", []):
            if _normalizar(alias) in texto_norm:
                return empresa_id
    return None

def buscar_empleado_por_cuil(empresa_id: str, cuil: str) -> dict | None:
    """Busca un empleado por CUIL exacto (sin guiones) dentro de una empresa."""
    cuil = (cuil or "").replace("-", "").strip()
    empresa = EMPRESAS.get(empresa_id, {})
    return empresa.get("empleados", {}).get(cuil)

def buscar_empleado_por_nombre(empresa_id: str, nombre: str) -> dict | None:
    """Busca un empleado por coincidencia de nombre (normalizado, tolera variaciones)."""
    nombre_norm = _normalizar(nombre)
    empresa = EMPRESAS.get(empresa_id, {})
    for cuil, datos in empresa.get("empleados", {}).items():
        nombre_canonico_norm = _normalizar(datos["nombre_canonico"])
        # Coincide si todas las palabras del nombre canonico (partidas por espacio)
        # aparecen en el nombre buscado, o viceversa - tolera "Sarich" solo,
        # "Agustin Sarich", "Sarich, Agustin", etc.
        palabras_canonico = set(nombre_canonico_norm.split())
        palabras_busqueda = set(nombre_norm.replace(",", " ").split())
        if palabras_canonico & palabras_busqueda:  # al menos una palabra en comun
            # Ademas exigir que el apellido (asumimos ultima palabra del nombre canonico) matchee
            apellido = nombre_canonico_norm.split()[-1]
            if apellido in nombre_norm:
                return {**datos, "cuil": cuil}
    return None

def resolver_empresa(dominio: str | None = None, texto_asunto: str | None = None) -> str | None:
    """Intenta resolver la empresa primero por dominio del remitente, y si falla, por alias en el asunto."""
    if dominio:
        empresa_id = resolver_empresa_por_dominio(dominio)
        if empresa_id:
            return empresa_id
    if texto_asunto:
        empresa_id = resolver_empresa_por_alias(texto_asunto)
        if empresa_id:
            return empresa_id
    return None
