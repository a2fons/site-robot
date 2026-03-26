import os
import ssl
import socket
import time
import datetime
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────
SITE_URL       = os.environ["SITE_URL"]          # ex: https://meusite.com.br
KEYWORD        = os.environ.get("KEYWORD", "")   # palavra-chave esperada na página

GMAIL_FROM     = os.environ["GMAIL_FROM"].strip()        # ex: seuemail@gmail.com
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"].strip()    # senha de app do Gmail
EMAIL_TO       = os.environ["EMAIL_TO"].strip()          # ex: destino@gmail.com

TIMEOUT_SEC    = 10
# ──────────────────────────────────────────────────────────────────


def check_http(url):
    try:
        start = time.time()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, timeout=TIMEOUT_SEC, allow_redirects=True, headers=headers)
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
        days_left = (expire_date - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)).days
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
    # 403 = Cloudflare bloqueando bots (site está no ar)
    site_ok = status_code in (200, 403)

    issues = []
    if not site_ok:
        issues.append("site fora do ar")
    if elapsed_ms and elapsed_ms >= 3000:
        issues.append("resposta lenta (>3s)")
    if ssl_valid is not None and (not ssl_valid or ssl_days <= 7):
        issues.append(f"SSL expira em {ssl_days}d")
    if kw_found is False:
        issues.append("keyword ausente")

    overall = "🟢 Tudo funcionando normalmente." if not issues else f"⚠️ Atenção: {', '.join(issues)}"

    # ── Texto simples (fallback) ──
    plain = f"""Relatório de Site — {now}
{url}

Status HTTP : {status_code if status_code else 'Sem resposta'}
Tempo       : {f'{elapsed_ms} ms' if elapsed_ms else 'indisponível'}
SSL         : {'Válido' if ssl_valid else 'Inválido'} — expira em {ssl_expiry} ({ssl_days}d)
"""
    if kw_found is not None:
        plain += f"Keyword     : \"{KEYWORD}\" {'encontrada' if kw_found else 'NÃO encontrada'}\n"
    plain += f"\n{overall}"

    # ── HTML ──
    perf_color = "#2ecc71" if (elapsed_ms or 0) < 1000 else ("#f39c12" if (elapsed_ms or 0) < 3000 else "#e74c3c")
    ssl_color  = "#2ecc71" if (ssl_valid and ssl_days > 7) else "#e74c3c"
    http_color = "#2ecc71" if site_ok else "#e74c3c"
    summary_color = "#2ecc71" if not issues else "#e67e22"

    kw_row = ""
    if kw_found is not None:
        kw_color = "#2ecc71" if kw_found else "#e74c3c"
        kw_label = "encontrada" if kw_found else "NÃO encontrada"
        kw_row = f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">🔑 Keyword</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:{kw_color};font-weight:bold;">"{KEYWORD}" {kw_label}</td>
        </tr>"""

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;border:1px solid #ddd;border-radius:8px;overflow:hidden;">
      <div style="background:#1a1a2e;padding:20px 24px;">
        <h2 style="margin:0;color:#fff;font-size:18px;">🔍 Relatório de Site</h2>
        <p style="margin:4px 0 0;color:#aaa;font-size:13px;">{now} — <a href="{url}" style="color:#7eb8f7;">{url}</a></p>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">🌐 Status HTTP</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:{http_color};font-weight:bold;">{status_code if status_code else 'Sem resposta'}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">⚡ Tempo de resposta</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:{perf_color};font-weight:bold;">{f'{elapsed_ms} ms' if elapsed_ms else 'indisponível'}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;">🔒 SSL</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:{ssl_color};font-weight:bold;">{'Válido' if ssl_valid else 'Inválido'} — expira em {ssl_expiry} ({ssl_days}d)</td>
        </tr>
        {kw_row}
      </table>
      <div style="background:{summary_color};padding:14px 24px;">
        <p style="margin:0;color:#fff;font-weight:bold;font-size:14px;">{overall}</p>
      </div>
    </div>
    """

    return plain, html_body


def send_email(subject, plain, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_FROM
    msg["To"]      = EMAIL_TO

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_FROM, GMAIL_PASSWORD)
        server.sendmail(GMAIL_FROM, EMAIL_TO, msg.as_string())

    print(f"E-mail enviado para {EMAIL_TO}")


def main():
    print(f"[{datetime.datetime.now()}] Monitorando {SITE_URL}...")

    status_code, elapsed_ms, html = check_http(SITE_URL)
    ssl_valid, ssl_days, ssl_expiry = check_ssl(SITE_URL) if SITE_URL.startswith("https") else (None, 0, "N/A")
    kw_found = check_keyword(html, KEYWORD)

    plain, html_body = build_report(SITE_URL, status_code, elapsed_ms, html, ssl_valid, ssl_days, ssl_expiry, kw_found)

    # Assunto com indicação rápida do status
    issues_exist = any([
        status_code != 200,
        elapsed_ms and elapsed_ms >= 3000,
        ssl_valid is not None and (not ssl_valid or ssl_days <= 7),
        kw_found is False,
    ])
    subject = f"{'⚠️ Alerta' if issues_exist else '✅ OK'} — Monitor de Site {datetime.datetime.now().strftime('%d/%m/%Y')}"

    print(plain)
    send_email(subject, plain, html_body)


if __name__ == "__main__":
    main()
