import os
from dotenv import load_dotenv

load_dotenv()

def _f(name: str, default: float):
    v = os.getenv(name)
    return float(v) if v is not None else float(default)

class Config:
    TZ = os.getenv("TZ", "Asia/Seoul")

    OWM_API_KEY = os.getenv("OWM_API_KEY", "")
    HOME_LAT = _f("HOME_LAT", 0.0)
    HOME_LON = _f("HOME_LON", 0.0)