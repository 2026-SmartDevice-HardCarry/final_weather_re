from flask import Flask, render_template
from datetime import datetime
import pytz

from config import Config
from services.openweather import get_openweather

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

tz = pytz.timezone(Config.TZ)

@app.route("/")
def dashboard():
    now = datetime.now(tz)
    
    # ---- Weather ----
    weather = get_openweather(Config.OWM_API_KEY, Config.HOME_LAT, Config.HOME_LON)
    precip_prob = float(weather.get("precip_prob", 0.0)) if weather.get("ok") else 0.0

    return render_template(
        "dashboard.html",
        now=now.strftime("%Y-%m-%d %H:%M"),
        weather=weather if weather.get("ok") else {"temp": None, "feels_like": None, "precip_prob": 0.0, "weather_desc": ""},
        precip_prob=precip_prob
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)