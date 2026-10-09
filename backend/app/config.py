from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/autos.db"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    sync_hour: int = 7


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
    "sync_hour": env.sync_hour,  # hora de la sync diaria (0-23)
    "auto_sync_on_open": True,  # al abrir la app, sincronizar si los datos están desactualizados
    "max_age_hours": 12,
}

# Pesos del scoring (editables desde la UI). Los pesos deterministas + LLM suman 1.0.
DEFAULT_WEIGHTS = {
    "kilometer": 0.20,
    "klimaanlage": 0.10,
    "tuev": 0.10,
    "cabrio_saison": 0.05,
    "precio": 0.20,
    "llm_rentabilidad": 0.35,
    "umbral_verde": 8.0,
    "umbral_amarillo": 5.0,
}
