from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/autos.db"
    # IA del informe "Analizar rentabilidad". Las claves van SOLO en backend/.env (no se versiona).
    llm_provider: str = "auto"  # auto (Gemini si hay clave de Gemini, si no Anthropic) | gemini | anthropic
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"  # los nombres cambian: `python -m app.maintenance gemini-models` lista los de tu clave
    gemini_base_url: str = ""  # solo para pruebas con un servidor falso
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"  # modelo de Anthropic
    sync_hour: int = 5


env = Env()

# Valores por defecto de la búsqueda (editables desde la UI, persistidos en DB).
DEFAULT_SEARCH = {
    "marken": ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"],
    "modell": "",
    "ort_oder_plz": "Stuttgart",
    "umkreis_km": 100,
    "erstzulassung_ab": 2010,
    "erstzulassung_bis": 2020,
    "preis_ab": 2000,
    "preis_bis": 10000,
    "kilometer_ab": 50000,
    "kilometer_bis": 170000,
    "kraftstoffart": ["Benzin", "Diesel"],
    "getriebe": "",  # "", "Automatik", "Manuell"
}

# Sincronización (editable desde la UI).
DEFAULT_APP = {
    "daily_sync": False,  # sync programada: pensada para cuando la app esté en un servidor siempre encendido
    "sync_hour": env.sync_hour,  # hora de esa sync diaria (0-23)
    "auto_sync_on_open": True,  # al abrir la app, sincronizar si los datos están desactualizados
    "max_age_hours": 12,
}

# Rentabilidad (análisis bajo demanda). Cifras APROXIMADAS y editables en Ajustes; no son asesoramiento fiscal.
DEFAULT_RENTABILIDAD = {
    "perfil": "particular",  # particular | empresa
    "descuento_venta_pct": 6.0,  # el precio de ANUNCIO en España no es el de venta final
    "descuento_compra_pct": 0.0,  # negociación a la baja del precio pedido en Alemania
    "transporte": 800,  # Alemania -> Costa del Sol
    "gestoria_matriculacion": 450,  # gestoría, tasa DGT, ITV de importación, ficha reducida, placas
    "impuesto_matriculacion_pct": 4.75,  # sobre el precio de compra; tramos por CO2: <120 g/km 0 %, 120-159 4,75 %, 160-199 9,75 %, >=200 14,75 %
    "preparacion": 400,  # limpieza, revisión, neumáticos, pequeñas reparaciones
    "seguro_y_placas_transito": 150,
    "gastos_venta": 150,  # anuncios, portales
    "otros_costes": 0,
    "iva_es_pct": 21.0,
    "iva_de_pct": 19.0,
    "iva_reventa": "rebu",  # solo empresa: rebu (IVA sobre el margen) | general (IVA sobre el precio de venta)
    "compra_con_iva_deducible": False,  # solo empresa: comprado a un profesional alemán con IVA desglosado
    "margen_comprar_eur": 1500,  # veredicto numérico: margen neto mínimo para "Comprar"...
    "roi_comprar_pct": 15,  # ...y rentabilidad mínima sobre lo invertido
    "margen_dudoso_eur": 700,  # por debajo de esto: "Descartar"
}

# Pesos del scoring (editables desde la UI; se normalizan, no hace falta que sumen 1).
DEFAULT_WEIGHTS = {
    "kilometer": 0.25,
    "klimaanlage": 0.10,
    "tuev": 0.15,
    "cabrio_saison": 0.05,
    "precio": 0.25,
    "getriebe": 0.15,  # el automático se vende más en la Costa del Sol
    "umbral_verde": 7.5,
    "umbral_amarillo": 5.0,
}
