"""PhishSim tracker — minimal click counter for the awareness campaign.

Serves the educational page and counts how many people clicked the email link.
It records only a timestamp (and whether the click is from a new browser, via a
cookie) — no passwords, no names, no payload. Everything stops at the teaching
page.

Run:   STATS_KEY=your-secret python app.py
Link to put in the email:   https://<this server>/go
View results:               https://<this server>/stats?key=your-secret
"""
import os
import json
import datetime
from pathlib import Path

from flask import (Flask, request, make_response, send_from_directory,
                   render_template_string)

BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "data" / "clicks.jsonl"
STATS_KEY = os.environ.get("STATS_KEY", "change-me")
TEAM_SIZE = int(os.environ.get("TEAM_SIZE", "40"))

app = Flask(__name__)


def record_click(is_unique, user_agent):
    LOG_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "t": datetime.datetime.now().isoformat(timespec="seconds"),
        "unique": is_unique,
        "ua": (user_agent or "")[:200],
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_clicks():
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


@app.route("/go")
def go():
    """The email link lands here: count the click, then show the lesson."""
    is_unique = request.cookies.get("ps_seen") != "1"
    record_click(is_unique, request.headers.get("User-Agent"))
    resp = make_response(send_from_directory(BASE_DIR, "index.html"))
    resp.set_cookie("ps_seen", "1", max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@app.route("/")
def home():
    # Preview the page without counting (for the admin to review).
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(BASE_DIR / "assets", filename)


STATS_HTML = """
<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>סטטיסטיקות · ExperTeam</title>
<style>
 body{font-family:-apple-system,"Segoe UI",Rubik,Arial,sans-serif;direction:rtl;
   background:#f4f1f8;color:#2a2140;margin:0;padding:24px;}
 .wrap{max-width:640px;margin:0 auto;}
 img.logo{height:40px;margin-bottom:16px;}
 h1{color:#6E3FA3;font-size:22px;}
 .cards{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0;}
 .c{flex:1;min-width:150px;background:#fff;border:1px solid #e9e3f1;border-radius:14px;
   padding:18px;text-align:center;box-shadow:0 4px 14px rgba(84,44,126,.05);}
 .c b{display:block;font-size:34px;color:#6E3FA3;}
 .c.pink b{color:#D6218A;} .c.blue b{color:#0098D4;}
 .c span{color:#6b6480;font-size:14px;}
 table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;
   border:1px solid #e9e3f1;margin-top:8px;}
 th,td{padding:9px 14px;text-align:right;border-bottom:1px solid #f0ecf6;font-size:14px;}
 th{background:#6E3FA3;color:#fff;}
 .empty{color:#6b6480;}
</style></head><body><div class="wrap">
 <img class="logo" src="/assets/experteam-logo.png" alt="ExperTeam">
 <h1>תוצאות תרגיל המודעות 🎣</h1>
 <div class="cards">
   <div class="c pink"><b>{{ unique }}</b><span>לחצו על הלינק (ייחודיים)</span></div>
   <div class="c blue"><b>{{ rate }}%</b><span>מתוך {{ team }} עובדים</span></div>
   <div class="c"><b>{{ total }}</b><span>סה"כ קליקים (כולל רענונים)</span></div>
 </div>
 {% if clicks %}
 <table><tr><th>#</th><th>זמן לחיצה</th><th>ביקור חדש?</th></tr>
 {% for clk in clicks %}
   <tr><td>{{ loop.index }}</td><td>{{ clk.t }}</td><td>{{ "✅ כן" if clk.unique else "↩︎ רענון" }}</td></tr>
 {% endfor %}</table>
 {% else %}<p class="empty">עדיין אף אחד לא לחץ.</p>{% endif %}
</div></body></html>
"""


@app.route("/stats")
def stats():
    if request.args.get("key") != STATS_KEY:
        return "Forbidden — add ?key=<STATS_KEY>", 403
    clicks = read_clicks()
    unique = sum(1 for c in clicks if c.get("unique"))
    total = len(clicks)
    rate = round(100 * unique / TEAM_SIZE) if TEAM_SIZE else 0
    return render_template_string(
        STATS_HTML, clicks=clicks, unique=unique, total=total,
        rate=rate, team=TEAM_SIZE,
    )


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
