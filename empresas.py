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
        "legajos": {
            "20186092555": "005001",
            "20359670452": "005011",
            "20398771940": "005013",
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
