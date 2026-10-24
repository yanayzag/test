"""Send the simulated-phishing lure email to a list of employees.

Safety by design:
  * Dry-run is the DEFAULT. Nothing is emailed unless you pass --send.
  * --send is refused unless config.yaml has `authorized: true`, confirming
    you are authorized to run this exercise against your own employees.
  * Each recipient gets a unique token so clicks can be measured; the link
    points only at your own tracking server's educational landing page.
"""
import argparse
import csv
import os
import secrets
import smtplib
import sqlite3
import sys
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml
from jinja2 import Template

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "phishsim.db"


def load_config():
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS targets (
            token    TEXT PRIMARY KEY,
            campaign TEXT NOT NULL,
            email    TEXT NOT NULL,
            name     TEXT,
            sent_at  TEXT
        );
        """
    )
    con.commit()
    return con


def read_recipients():
    path = BASE_DIR / "recipients.csv"
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_message(cfg, name, link):
    tmpl = Template(
        (BASE_DIR / "templates" / "email_dog_policy.html").read_text(encoding="utf-8")
    )
    html = tmpl.render(name=name, link=link)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🐕 מדיניות חדשה: הבאת כלבים למשרד — אישור נדרש עד יום חמישי"
    msg["From"] = f"{cfg['smtp']['from_name']} <{cfg['smtp']['from_email']}>"
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def main():
    ap = argparse.ArgumentParser(description="Send a PhishSim awareness campaign.")
    ap.add_argument("--campaign", required=True, help="Campaign name/label.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Print instead of sending (default).")
    group.add_argument("--send", action="store_true",
                       help="Actually send the emails (requires authorization).")
    args = ap.parse_args()

    cfg = load_config()
    recipients = read_recipients()
    con = ensure_db()

    sending = args.send
    if sending and not cfg.get("authorized"):
        sys.exit(
            "Refusing to --send: set `authorized: true` in config.yaml to confirm "
            "you are authorized to run this exercise against your own employees."
        )

    server = None
    if sending:
        s = cfg["smtp"]
        server = smtplib.SMTP(s["host"], s["port"])
        if s.get("use_tls"):
            server.starttls()
        password = os.environ.get("SMTP_PASSWORD", s.get("password", ""))
        if s.get("username"):
            server.login(s["username"], password)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    for r in recipients:
        token = secrets.token_urlsafe(16)
        link = f"{cfg['base_url'].rstrip('/')}/t/{token}"
        con.execute(
            "INSERT INTO targets (token, campaign, email, name, sent_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, args.campaign, r["email"], r.get("name", ""), now if sending else None),
        )
        con.commit()

        msg = build_message(cfg, r.get("name", ""), link)
        msg["To"] = r["email"]

        if sending:
            server.sendmail(cfg["smtp"]["from_email"], [r["email"]], msg.as_string())
            print(f"SENT   -> {r['email']}")
        else:
            print(f"DRY-RUN -> {r['email']}  link={link}")

    if server:
        server.quit()

    mode = "sent" if sending else "dry-run (nothing sent)"
    print(f"\nCampaign '{args.campaign}': {len(recipients)} recipients [{mode}].")
    if not sending:
        print("Add --send (and set authorized: true) to send for real.")


if __name__ == "__main__":
    main()
