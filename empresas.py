"""
Configuración de empresas cliente.
Cada empresa se identifica por el dominio de mail de sus RRHH/contacto
(el remitente ORIGINAL de las novedades, no el mail del contador que reenvía).
"""

EMPRESAS = {
    "tv_crecer": {
        "nombre": "TV CRECER S.R.L.",
        "cuit": "30709066729",
        "direccion": "ESCALADA 1200",
        "banco": "GALICIA",
        "dominios": ["tvcrecer.com.ar"],  # completar con el/los dominios reales del cliente
        "legajos": {
            "20186092555": "005001",
            "20359670452": "005011",
            "20398771940": "005013",
        },
    },
    # Se agregan nuevas empresas acá con la misma estructura
}

def resolver_empresa_por_dominio(dominio: str) -> str | None:
    """Devuelve el id de empresa (key de EMPRESAS) para un dominio dado, o None si no matchea ninguna."""
    dominio = dominio.lower().strip()
    for empresa_id, config in EMPRESAS.items():
        if dominio in [d.lower() for d in config["dominios"]]:
            return empresa_id
    return None
