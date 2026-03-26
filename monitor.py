import os
import ssl
import socket
import time
import datetime
import requests

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────
SITE_URL         = os.environ["SITE_URL"]           # ex: https://meusite.com.br
KEYWORD          = os.environ.get("KEYWORD", "")    # palavra-chave esperada na página

EVOLUTION_URL    = os.environ["EVOLUTION_API_URL"]  # ex: https://evolution.up.railway.app
EVOLUTION_APIKEY = os.environ["EVOLUTION_API_KEY"]  # Global API Key do Evolution
EVOLUTION_INST   = os.environ["EVOLUTION_INSTANCE"] # nome da instância criada
WHATSAPP_TO      = os.environ["WHATSAPP_TO"]        # ex: 5511999999999 (sem +)

TIMEOUT_SEC      = 10
# ──────────────────────────────────────────────────────────────────


def check_http(url):
    try:
        start = time.time()
        resp = requests.get(url, timeout=TIMEOUT_SEC, allow_redirects=True)
        elapsed = round((time.time() - start) * 1000)
        return resp.status_code, elapsed, resp.text
    except Exception:
        return None, None, None


def check_ssl(url):
    try:
        hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(TIMEOUT_SEC)
            s.connect((hostname, 443))
            cert = s.getpeercert()
        expire_date = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days_left = (expire_date - datetime.datetime.utcnow()).days
        return True, days_left, expire_date.strftime("%d/%m/%Y")
    except ssl.SSLCertVerificationError:
        return False, 0, "Inválido"
    except Exception:
        return False, 0, "Erro"


def check_keyword(html, keyword):
    if not keyword:
        return None
    return keyword.lower() in (html or "").lower()


def status_icon(ok):
    return "✅" if ok else "❌"


def build_report(url, status_code, elapsed_ms, html, ssl_valid, ssl_days, ssl_expiry, kw_found):
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    site_ok = status_code == 200

    lines = [
        f"🔍 *Relatório de Site* — {now}",
        f"🌐 {url}",
        "",
        f"{status_icon(site_ok)} *Status HTTP:* {status_code if status_code else 'Sem resposta'}",
    ]

    if elapsed_ms is not None:
        perf_icon = "🟢" if elapsed_ms < 1000 else ("🟡" if elapsed_ms < 3000 else "🔴")
        lines.append(f"{perf_icon} *Tempo de resposta:* {elapsed_ms} ms")
    else:
        lines.append("❌ *Tempo de resposta:* indisponível")

    if ssl_valid is not None:
        ssl_icon = status_icon(ssl_valid and ssl_days > 7)
        lines.append(f"{ssl_icon} *SSL:* {'Válido' if ssl_valid else 'Inválido'} — expira em {ssl_expiry} ({ssl_days}d)")
    else:
        lines.append("⚪ *SSL:* não aplicável (HTTP)")

    if kw_found is not None:
        lines.append(f"{status_icon(kw_found)} *Keyword \"{KEYWORD}\":* {'encontrada' if kw_found else 'NÃO encontrada'}")

    issues = []
    if not site_ok:
        issues.append("site fora do ar")
    if elapsed_ms and elapsed_ms >= 3000:
        issues.append("resposta lenta (>3s)")
    if ssl_valid is not None and (not ssl_valid or ssl_days <= 7):
        issues.append(f"SSL expira em {ssl_days}d")
    if kw_found is False:
        issues.append("keyword ausente")

    lines.append("")
    if issues:
        lines.append(f"⚠️ *Atenção:* {', '.join(issues)}")
    else:
        lines.append("🟢 *Tudo funcionando normalmente.*")

    return "\n".join(lines)


def send_whatsapp(message):
    url = f"{EVOLUTION_URL.rstrip('/')}/message/sendText/{EVOLUTION_INST}"
    headers = {
        "apikey": EVOLUTION_APIKEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": WHATSAPP_TO,
        "text": message
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    print(f"WhatsApp enviado. ID: {data.get('key', {}).get('id', 'n/a')} | Status: {data.get('status', 'n/a')}")


def main():
    print(f"[{datetime.datetime.now()}] Monitorando {SITE_URL}...")

    status_code, elapsed_ms, html = check_http(SITE_URL)
    ssl_valid, ssl_days, ssl_expiry = check_ssl(SITE_URL) if SITE_URL.startswith("https") else (None, 0, "N/A")
    kw_found = check_keyword(html, KEYWORD)

    report = build_report(SITE_URL, status_code, elapsed_ms, html, ssl_valid, ssl_days, ssl_expiry, kw_found)

    print("\n" + report + "\n")
    send_whatsapp(report)


if __name__ == "__main__":
    main()
