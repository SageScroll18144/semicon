from flask import Flask, jsonify, render_template, request
import json
import os
import urllib.parse
import urllib.request


app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
NOME_TABELA = os.environ.get("SUPABASE_TABLE", "temperaturas")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _json_error(message, status_code):
    return jsonify({"status": "erro", "mensagem": message}), status_code


def _parse_sensor_payload():
    payload = request.get_json(silent=True) or {}

    if "temperatura" not in payload:
        raise ValueError("Campo obrigatorio ausente: temperatura")

    try:
        temperatura = float(payload["temperatura"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Campo temperatura deve ser numerico") from exc

    sensor_id = str(payload.get("sensor_id") or "esp32").strip() or "esp32"
    return {"temperatura": temperatura, "sensor_id": sensor_id}


def salvar_temperatura_supabase(data):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        app.logger.warning("Supabase nao configurado. Variaveis de ambiente ausentes.")
        return False

    payload = {
        "sensor_id": data["sensor_id"],
        "temperatura": data["temperatura"],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{NOME_TABELA}"

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        app.logger.exception("Erro ao salvar no Supabase: %s", exc)
        return False


def buscar_historico_supabase(limit=50):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return []

    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{NOME_TABELA}?{query_string}"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        app.logger.exception("Erro ao buscar historico no Supabase: %s", exc)
        return []

    return [
        {
            "temperatura": item.get("temperatura"),
            "sensor_id": item.get("sensor_id"),
            "timestamp": item.get("created_at", ""),
        }
        for item in dados
    ]


def handle_temperatura_request():
    if request.method == "OPTIONS":
        return "", 204

    if request.method == "POST":
        try:
            data = _parse_sensor_payload()
        except ValueError as exc:
            return _json_error(str(exc), 400)

        if salvar_temperatura_supabase(data):
            return jsonify({"status": "sucesso", "mensagem": "Dado salvo no Supabase"})

        return _json_error("Erro ao salvar no banco de dados", 500)

    historico = buscar_historico_supabase(limit=50)
    return jsonify({"historico": historico})


def _client_wants_html():
    best_match = request.accept_mimetypes.best_match(["text/html", "application/json"])
    return best_match == "text/html"


@app.route("/api/temperatura", methods=["GET", "POST", "OPTIONS"])
@app.route("/temperatura", methods=["GET", "POST", "OPTIONS"])
def temperatura():
    return handle_temperatura_request()


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def catch_all(path):
    normalized_path = (path or "").strip("/")

    if request.method != "GET":
        return handle_temperatura_request()

    if normalized_path in {"api", "api/index"} and not _client_wants_html():
        return handle_temperatura_request()

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
