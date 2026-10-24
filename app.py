"""PhishSim tracking server.

Serves the educational landing page and records a click event when an
employee follows the simulated-phishing link. It intentionally does NOTHING
else: no credential form, no payload, no code executed on the employee side.
The link simply reveals that this was a training exercise.
"""
import sqlite3
import datetime
from pathlib import Path

import yaml
from flask import Flask, render_template, request, abort, g

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "phishsim.db"

app = Flask(__name__)


def load_config():
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db():
    if "db" not in g:
        DB_PATH.parent.mkdir(exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS targets (
            token      TEXT PRIMARY KEY,
            campaign   TEXT NOT NULL,
            email      TEXT NOT NULL,
            name       TEXT,
            sent_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS clicks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token      TEXT NOT NULL,
            clicked_at TEXT NOT NULL,
            user_agent TEXT
        );
        """
    )
    con.commit()
    con.close()


@app.route("/t/<token>")
def tracked_link(token):
    """The 'phishing' link. Logs the click, then shows the teaching page."""
    db = get_db()
    target = db.execute(
        "SELECT * FROM targets WHERE token = ?", (token,)
    ).fetchone()
    if target is None:
        abort(404)

    # Record the click. We store only what is needed to measure the exercise:
    # which token clicked and when. No passwords, no IP geolocation, no payload.
    db.execute(
        "INSERT INTO clicks (token, clicked_at, user_agent) VALUES (?, ?, ?)",
        (
            token,
            datetime.datetime.now().isoformat(timespec="seconds"),
            request.headers.get("User-Agent", "")[:300],
        ),
    )
    db.commit()

    return render_template("landing.html", name=target["name"] or "")


@app.route("/admin")
def admin():
    cfg = load_config()
    if request.args.get("key") != cfg.get("admin_key"):
        abort(403)

    db = get_db()
    rows = db.execute(
        """
        SELECT t.campaign,
               COUNT(DISTINCT t.token)                                   AS sent,
               COUNT(DISTINCT c.token)                                   AS clicked
        FROM targets t
        LEFT JOIN clicks c ON c.token = t.token
        WHERE t.sent_at IS NOT NULL
        GROUP BY t.campaign
        ORDER BY t.campaign
        """
    ).fetchall()

    campaigns = []
    for r in rows:
        sent = r["sent"] or 0
        clicked = r["clicked"] or 0
        pct = round(100 * clicked / sent) if sent else 0
        campaigns.append(
            {"name": r["campaign"], "sent": sent, "clicked": clicked, "pct": pct}
        )
    return render_template("admin.html", campaigns=campaigns)


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
