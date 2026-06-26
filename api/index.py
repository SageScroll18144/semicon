import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
MONDAY_API_URL = "https://api.monday.com/v2"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
SUPABASE_INSCRICOES_TABLE = (
    os.getenv("SUPABASE_INSCRICOES_TABLE", "").strip()
    or os.getenv("SUPABASE_TABLE", "inscricoes").strip()
)
SUPABASE_ID_COLUMN = (
    os.getenv("SUPABASE_INSCRICAO_ID_COLUMN", "").strip()
    or os.getenv("SUPABASE_ID_COLUMN", "ID").strip()
)
SUPABASE_MONDAY_ID_COLUMN = (
    os.getenv("SUPABASE_MONDAY_ID_COLUMN", "").strip()
    or os.getenv("SUPABASE_MONDAY_COLUMN", "ID_Monday").strip()
)
TEXT_LIMIT = 8000
OUT_OF_SCOPE_RECOMMENDATION = "Fora do escopo da categoria de análise"
RECOMMENDATION_WITH_REMARKS = "Recomendado com ressalvas"
MORE_INFO_RECOMMENDATION = "Preciso de mais informações"
LEGACY_RECOMMENDATIONS = {
    "Recomendado com ressalva": RECOMMENDATION_WITH_REMARKS,
}
RECOMMENDATION_OPTIONS = {
    "Recomendado",
    "Não recomendado",
    RECOMMENDATION_WITH_REMARKS,
    MORE_INFO_RECOMMENDATION,
    OUT_OF_SCOPE_RECOMMENDATION,
}
CATEGORIES_BY_EVALUATOR_ID = {
    "1": "IA e Tecnologias Emergentes",
    "2": "IA e Tecnologias Emergentes",
    "3": "Desenvolvimento, Dados e Segurança",
    "4": "Empreendedorismo e Inovação",
    "5": "Gestão, Mercado e Trabalho",
    "6": "Comunicação e Mídias Digitais",
    "7": "Design, Games e Experiências Criativas",
    "8": "Arte, Cultura e Linguagens",
    "9": "Cidade, Sustentabilidade e Território",
    "10": "Sociedade, Inclusão e Impacto",
}
CONDIZENCE_FIELDS = {
    "eixoCondizente": "Eixo",
    "formatoCondizente": "Formato",
    "palavrasChaveCondizentes": "Palavra-chave",
    "categoriaCondizente": "Categoria avaliada",
    "duracaoCondizente": "Duração",
    "publicoAlvoCondizente": "Público-alvo",
    "faixaEtariaCondizente": "Restrição de faixa etária",
    "dadosOperacionaisCondizentes": "Dados operacionais",
}
SCALE_FIELDS = {
    "relevanciaTematica": "Relevância temática",
    "clarezaProposta": "Clareza da proposta",
    "consistenciaMetodologica": "Consistência metodológica",
    "potencialInteracao": "Potencial de interação e engajamento com o público",
    "diversidadePerspectivas": "Diversidade de perspectiva, experiências e abordagens",
    "alinhamentoRecnplay": "Alinhamento com a proposta do REC'n'Play 2026",
}

MONDAY_COLUMN_IDS = {
    "avaliador": "numeric_mm4frs3s",
    "nome_especialista": "substituir",
    "id_supabase": "substituir",
    "descricao_publicacao": "long_text_mm3rbrj9",
    "objetivo": "long_text_mm3rs9zc",
    "justificativa": "long_text_mm3r2v15",
    "metodologia": "long_text_mm3r7p9h",
    "eixo": "text_mm3rgtmr",
    "formato": "text_mm3r5pbr",
    "integrante_1_foto": "file_mm3rke6w",
    "integrante_1": "text_mm3rj6am",
    "integrante_1_papel": "text_mm3rse4d",
    "integrante_1_estado": "text_mm3rapxk",
    "integrante_1_cidade": "text_mm3rt5ja",
    "integrante_1_linkedin": "text_mm3rh8qp",
    "integrante_1_instagram": "text_mm3rwrg5",
    "integrante_1_instituicao": "text_mm3rnvb5",
    "integrante_1_tipo_instituicao": "text_mm3red2k",
    "integrante_1_bio": "long_text_mm3rz262",
    "integrante_2_foto": "file_mm3rmsrm",
    "integrante_2": "text_mm3rbqb2",
    "integrante_2_papel": "text_mm3r9ch1",
    "integrante_2_estado": "text_mm3r9kef",
    "integrante_2_cidade": "text_mm3rzxtk",
    "integrante_2_linkedin": "text_mm3rb3en",
    "integrante_2_instagram": "text_mm3rh7rw",
    "integrante_2_instituicao": "text_mm3r77n3",
    "integrante_2_tipo_instituicao": "text_mm3r87rc",
    "integrante_2_bio": "long_text_mm3rscng",
    "integrante_3_foto": "file_mm3ry9rg",
    "integrante_3": "text_mm3rvbe8",
    "integrante_3_papel": "text_mm3r5gkq",
    "integrante_3_estado": "text_mm3rn85t",
    "integrante_3_cidade": "text_mm3rq0sm",
    "integrante_3_linkedin": "text_mm3rrgy2",
    "integrante_3_instagram": "text_mm3rmdgb",
    "integrante_3_instituicao": "text_mm3rw8xy",
    "integrante_3_tipo_instituicao": "text_mm3rvdyz",
    "integrante_3_bio": "long_text_mm3re34t",
    "integrante_4_foto": "file_mm3r6kz1",
    "integrante_4": "text_mm3rdax5",
    "integrante_4_papel": "text_mm3rhf9q",
    "integrante_4_estado": "text_mm3rqdfs",
    "integrante_4_cidade": "text_mm3rb2f5",
    "integrante_4_linkedin": "text_mm3rbtqr",
    "integrante_4_instagram": "text_mm3rg8xq",
    "integrante_4_instituicao": "text_mm3rcq56",
    "integrante_4_tipo_instituicao": "text_mm3r6v81",
    "integrante_4_bio": "long_text_mm3r1tzc",
    "integrante_5_foto": "file_mm3rmbn7",
    "integrante_5": "text_mm3rsfaz",
    "integrante_5_papel": "text_mm3rxvpw",
    "integrante_5_estado": "text_mm3rpb0t",
    "integrante_5_cidade": "text_mm3r4vw4",
    "integrante_5_linkedin": "text_mm3rrcwx",
    "integrante_5_instagram": "text_mm3r63f9",
    "integrante_5_instituicao": "text_mm3r7wmn",
    "integrante_5_tipo_instituicao": "text_mm3r7y3b",
    "integrante_5_bio": "long_text_mm3r6qq4",
    "palavras_chave": "text_mm3rbe10",
    "duracao": "text_mm3rfvv1",
    "publico_alvo": "text_mm3rxnnp",
    "restricao_faixa_etaria": "text_mm3rw1xq",
    "dados_operacionais_1": "long_text_mm3sh4ng",
    "dados_operacionais_2": "long_text_mm3sw2q7",
    "informacoes_extras": "long_text_mm3rgy4a",
    "recomendacao": "long_text_mm4fyr7m",
    "parecer": "long_text_mm4fdy8x",
}

app = Flask(__name__)
app.template_folder = str(BASE_DIR / "templates")
app.static_folder = None


class ConfigError(RuntimeError):
    pass


def normalize(value):
    value = str(value or "").strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def monday_token():
    token = os.getenv("MONDAY_API_TOKEN", "").strip()
    if not token:
        raise ConfigError("Configure MONDAY_API_TOKEN nas variáveis de ambiente da Vercel.")
    return token


def monday_board_id():
    board_id = os.getenv("MONDAY_BOARD_ID", "").strip()
    if not board_id:
        raise ConfigError("Configure MONDAY_BOARD_ID nas variáveis de ambiente da Vercel.")
    return board_id


def monday_request(query, variables=None):
    headers = {
        "Authorization": monday_token(),
        "Content-Type": "application/json",
    }
    api_version = os.getenv("MONDAY_API_VERSION", "").strip()
    if api_version:
        headers["API-Version"] = api_version

    response = requests.post(
        MONDAY_API_URL,
        headers=headers,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Monday retornou uma resposta inválida: HTTP {response.status_code}") from exc

    if response.status_code >= 400:
        message = payload.get("error_message") or payload.get("message") or response.text
        raise RuntimeError(f"Monday retornou HTTP {response.status_code}: {message}")

    if payload.get("errors"):
        messages = "; ".join(error.get("message", "Erro desconhecido") for error in payload["errors"])
        raise RuntimeError(f"Erro no Monday: {messages}")

    return payload.get("data") or {}


def supabase_headers():
    if not SUPABASE_URL:
        raise ConfigError("Configure SUPABASE_URL nas variáveis de ambiente da Vercel.")
    if not SUPABASE_SERVICE_KEY:
        raise ConfigError("Configure SUPABASE_SERVICE_KEY nas variáveis de ambiente da Vercel.")
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
    }


def supabase_rest_url():
    if not SUPABASE_URL:
        raise ConfigError("Configure SUPABASE_URL nas variaveis de ambiente da Vercel.")
    if SUPABASE_URL.lower().endswith("/rest/v1"):
        return SUPABASE_URL
    return f"{SUPABASE_URL}/rest/v1"


@lru_cache(maxsize=1024)
def supabase_id_for_monday_id(monday_id):
    monday_id = str(monday_id or "").strip()
    if not monday_id:
        return ""
    if not SUPABASE_INSCRICOES_TABLE:
        raise ConfigError("Configure SUPABASE_INSCRICOES_TABLE nas variáveis de ambiente da Vercel.")
    if not SUPABASE_ID_COLUMN or not SUPABASE_MONDAY_ID_COLUMN:
        raise ConfigError("Configure as colunas de ID do Supabase nas variáveis de ambiente da Vercel.")

    response = requests.get(
        f"{supabase_rest_url()}/{SUPABASE_INSCRICOES_TABLE}",
        headers=supabase_headers(),
        params={
            "select": SUPABASE_ID_COLUMN,
            SUPABASE_MONDAY_ID_COLUMN: f"eq.{monday_id}",
            "limit": "1",
        },
        timeout=15,
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Supabase retornou uma resposta inválida: HTTP {response.status_code}") from exc

    if response.status_code >= 400:
        message = payload.get("message") if isinstance(payload, dict) else response.text
        raise RuntimeError(f"Supabase retornou HTTP {response.status_code}: {message}")

    if not isinstance(payload, list) or not payload:
        return ""

    supabase_id = payload[0].get(SUPABASE_ID_COLUMN)
    return "" if supabase_id is None else str(supabase_id)


def error_response(error, status=500):
    code = 400 if isinstance(error, ConfigError) else status
    return jsonify({"error": str(error)}), code


def empty_review():
    return {
        "descricaoSugestao": "",
        "eixoSugestao": "",
        "formatoSugestao": "",
        "palavraSugerida": "",
        "condizencias": {},
        "categoriaSelecionada": "",
        "integrantes": [],
        "duracaoEsperada": "",
        "idadeMinima": "",
        "idadeMaxima": "",
        "dadosOperacionaisAdaptaveis": "",
        "dadosOperacionaisAdaptacao": "",
        "escalas": {},
        "recomendacao": "",
        "informacoesComplementares": "",
        "foraEscopo": "",
    }


def column_title_key(title):
    title = str(title or "").strip()
    title = unicodedata.normalize("NFKD", title)
    title = "".join(char for char in title if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", title).strip().lower()


def parse_json_value(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def collect_match_values(value):
    values = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"id", "name", "title", "text", "email"} and nested is not None:
                values.append(str(nested))
            values.extend(collect_match_values(nested))
    elif isinstance(value, list):
        for item in value:
            values.extend(collect_match_values(item))
    elif value is not None:
        values.append(str(value))
    return values


@lru_cache(maxsize=1)
def board_columns():
    query = """
    query BoardColumns($boardId: [ID!]!) {
      boards(ids: $boardId) {
        columns {
          id
          title
          type
        }
      }
    }
    """
    data = monday_request(query, {"boardId": [monday_board_id()]})
    boards = data.get("boards") or []
    if not boards:
        raise ConfigError("MONDAY_BOARD_ID não encontrou nenhum board no Monday.")
    return boards[0].get("columns") or []


def resolve_column(column_key, title_candidates, required=True):
    explicit_id = str(MONDAY_COLUMN_IDS.get(column_key, "") or "").strip()
    columns = board_columns()
    by_id = {column["id"]: column for column in columns}
    if explicit_id and explicit_id.lower() != "substituir":
        if explicit_id in by_id:
            return by_id[explicit_id]
        if required:
            raise ConfigError(f"MONDAY_COLUMN_IDS['{column_key}'] aponta para uma coluna que não existe no board: {explicit_id}")
        return None

    by_title = {column_title_key(column["title"]): column for column in columns}
    for title in title_candidates:
        match = by_title.get(column_title_key(title))
        if match:
            return match

    if required:
        expected = ", ".join(title_candidates)
        raise ConfigError(
            f"Não encontrei a coluna esperada ({expected}). "
            f"Ajuste MONDAY_COLUMN_IDS['{column_key}'] com o ID da coluna no Monday."
        )
    return None


@lru_cache(maxsize=1)
def app_columns():
    return {
        "avaliador": resolve_column("avaliador", ["Avaliador definitivo", "Avaliador", "Especialista"]),
        "nome_especialista": resolve_column(
            "nome_especialista",
            ["Nome do especialista", "Especialista", "Nome do avaliador"],
            required=False,
        ),
        "id_supabase": resolve_column(
            "id_supabase",
            ["ID Supabase", "ID do Supabase", "Supabase ID"],
            required=False,
        ),
        "descricao_publicacao": resolve_column(
            "descricao_publicacao",
            ["Descrição para publicação", "Descricao para publicacao", "Descrição", "Descricao"],
            required=False,
        ),
        "objetivo": resolve_column("objetivo", ["Objetivo"], required=False),
        "justificativa": resolve_column("justificativa", ["Justificativa"], required=False),
        "metodologia": resolve_column("metodologia", ["Metodologia"], required=False),
        "eixo": resolve_column("eixo", ["Eixo"], required=False),
        "formato": resolve_column("formato", ["Formato"], required=False),
        "integrante_1_foto": resolve_column("integrante_1_foto", ["C1 - Foto"], required=False),
        "integrante_1": resolve_column("integrante_1", ["C1 - Nome", "C1 - Nome Integrante", "C1 - Nome integrante"], required=False),
        "integrante_1_papel": resolve_column("integrante_1_papel", ["C1 - Papel"], required=False),
        "integrante_1_estado": resolve_column("integrante_1_estado", ["C1 - Estado"], required=False),
        "integrante_1_cidade": resolve_column("integrante_1_cidade", ["C1 - Cidade"], required=False),
        "integrante_1_linkedin": resolve_column("integrante_1_linkedin", ["C1 - LinkedIn", "C1 - Linkedin"], required=False),
        "integrante_1_instagram": resolve_column("integrante_1_instagram", ["C1 - Instagram"], required=False),
        "integrante_1_instituicao": resolve_column("integrante_1_instituicao", ["C1 - Instituicao", "C1 - Instituição"], required=False),
        "integrante_1_tipo_instituicao": resolve_column("integrante_1_tipo_instituicao", ["C1 - Tipo Instituicao", "C1 - Tipo Instituição"], required=False),
        "integrante_1_bio": resolve_column("integrante_1_bio", ["C1 - Minibio", "C1 - Bio"], required=False),
        "integrante_2_foto": resolve_column("integrante_2_foto", ["C2 - Foto"], required=False),
        "integrante_2": resolve_column("integrante_2", ["C2 - Nome", "C2 - Nome Integrante", "C2 - Nome integrante"], required=False),
        "integrante_2_papel": resolve_column("integrante_2_papel", ["C2 - Papel"], required=False),
        "integrante_2_estado": resolve_column("integrante_2_estado", ["C2 - Estado"], required=False),
        "integrante_2_cidade": resolve_column("integrante_2_cidade", ["C2 - Cidade"], required=False),
        "integrante_2_linkedin": resolve_column("integrante_2_linkedin", ["C2 - LinkedIn", "C2 - Linkedin"], required=False),
        "integrante_2_instagram": resolve_column("integrante_2_instagram", ["C2 - Instagram"], required=False),
        "integrante_2_instituicao": resolve_column("integrante_2_instituicao", ["C2 - Instituicao", "C2 - Instituição"], required=False),
        "integrante_2_tipo_instituicao": resolve_column("integrante_2_tipo_instituicao", ["C2 - Tipo Instituicao", "C2 - Tipo Instituição"], required=False),
        "integrante_2_bio": resolve_column("integrante_2_bio", ["C2 - Minibio", "C2 - Bio"], required=False),
        "integrante_3_foto": resolve_column("integrante_3_foto", ["C3 - Foto"], required=False),
        "integrante_3": resolve_column("integrante_3", ["C3 - Nome", "C3 - Nome Integrante", "C3 - Nome integrante"], required=False),
        "integrante_3_papel": resolve_column("integrante_3_papel", ["C3 - Papel"], required=False),
        "integrante_3_estado": resolve_column("integrante_3_estado", ["C3 - Estado"], required=False),
        "integrante_3_cidade": resolve_column("integrante_3_cidade", ["C3 - Cidade"], required=False),
        "integrante_3_linkedin": resolve_column("integrante_3_linkedin", ["C3 - LinkedIn", "C3 - Linkedin"], required=False),
        "integrante_3_instagram": resolve_column("integrante_3_instagram", ["C3 - Instagram"], required=False),
        "integrante_3_instituicao": resolve_column("integrante_3_instituicao", ["C3 - Instituicao", "C3 - Instituição"], required=False),
        "integrante_3_tipo_instituicao": resolve_column("integrante_3_tipo_instituicao", ["C3 - Tipo Instituicao", "C3 - Tipo Instituição"], required=False),
        "integrante_3_bio": resolve_column("integrante_3_bio", ["C3 - Minibio", "C3 - Bio"], required=False),
        "integrante_4_foto": resolve_column("integrante_4_foto", ["C4 - Foto"], required=False),
        "integrante_4": resolve_column("integrante_4", ["C4 - Nome", "C4 - Nome Integrante", "C4 - Nome integrante"], required=False),
        "integrante_4_papel": resolve_column("integrante_4_papel", ["C4 - Papel"], required=False),
        "integrante_4_estado": resolve_column("integrante_4_estado", ["C4 - Estado"], required=False),
        "integrante_4_cidade": resolve_column("integrante_4_cidade", ["C4 - Cidade"], required=False),
        "integrante_4_linkedin": resolve_column("integrante_4_linkedin", ["C4 - LinkedIn", "C4 - Linkedin"], required=False),
        "integrante_4_instagram": resolve_column("integrante_4_instagram", ["C4 - Instagram"], required=False),
        "integrante_4_instituicao": resolve_column("integrante_4_instituicao", ["C4 - Instituicao", "C4 - Instituição"], required=False),
        "integrante_4_tipo_instituicao": resolve_column("integrante_4_tipo_instituicao", ["C4 - Tipo Instituicao", "C4 - Tipo Instituição"], required=False),
        "integrante_4_bio": resolve_column("integrante_4_bio", ["C4 - Minibio", "C4 - Bio"], required=False),
        "integrante_5_foto": resolve_column("integrante_5_foto", ["C5 - Foto"], required=False),
        "integrante_5": resolve_column("integrante_5", ["C5 - Nome", "C5 - Nome Integrante", "C5 - Nome integrante"], required=False),
        "integrante_5_papel": resolve_column("integrante_5_papel", ["C5 - Papel"], required=False),
        "integrante_5_estado": resolve_column("integrante_5_estado", ["C5 - Estado"], required=False),
        "integrante_5_cidade": resolve_column("integrante_5_cidade", ["C5 - Cidade"], required=False),
        "integrante_5_linkedin": resolve_column("integrante_5_linkedin", ["C5 - LinkedIn", "C5 - Linkedin"], required=False),
        "integrante_5_instagram": resolve_column("integrante_5_instagram", ["C5 - Instagram"], required=False),
        "integrante_5_instituicao": resolve_column("integrante_5_instituicao", ["C5 - Instituicao", "C5 - Instituição"], required=False),
        "integrante_5_tipo_instituicao": resolve_column("integrante_5_tipo_instituicao", ["C5 - Tipo Instituicao", "C5 - Tipo Instituição"], required=False),
        "integrante_5_bio": resolve_column("integrante_5_bio", ["C5 - Minibio", "C5 - Bio"], required=False),
        "palavras_chave": resolve_column("palavras_chave", ["Palavra-chave", "Palavras-chave", "Tags"], required=False),
        "duracao": resolve_column("duracao", ["Duração", "Duracao"], required=False),
        "publico_alvo": resolve_column("publico_alvo", ["Público-alvo", "Publico-alvo", "Público alvo"], required=False),
        "restricao_faixa_etaria": resolve_column(
            "restricao_faixa_etaria",
            ["Restrição de faixa etária", "Restricao de faixa etaria", "Faixa etária", "Faixa etaria"],
            required=False,
        ),
        "dados_operacionais_1": resolve_column(
            "dados_operacionais_1",
            ["Dados operacionais", "Operacional", "Necessidades operacionais"],
            required=False,
        ),
        "dados_operacionais_2": resolve_column(
            "dados_operacionais_2",
            ["Dados operacionais", "Operacional", "Necessidades operacionais"],
            required=False,
        ),
        "informacoes_extras": resolve_column(
            "informacoes_extras",
            ["Informações extras", "Informacoes extras", "Observações", "Observacoes"],
            required=False,
        ),
        "recomendacao": resolve_column(
            "recomendacao",
            ["Recomendação", "Recomendacao", "Avaliação", "Avaliacao", "Resultado da avaliação"],
        ),
        "parecer": resolve_column(
            "parecer",
            ["Parecer", "Informações complementares", "Informacoes complementares", "Ressalvas"],
        ),
    }


def item_column_values(item):
    return {column_value["id"]: column_value for column_value in item.get("column_values", [])}


def column_text(item, column):
    if not column:
        return ""
    value = item_column_values(item).get(column["id"]) or {}
    return value.get("text") or ""


def read_column(item, columns, key):
    return column_text(item, columns.get(key))


def file_entries(item, column):
    if not column:
        return []
    value = item_column_values(item).get(column["id"]) or {}
    parsed = parse_json_value(value.get("value"))
    if not isinstance(parsed, dict):
        return []
    files = parsed.get("files")
    return files if isinstance(files, list) else []


def file_asset_id(file_entry):
    if not isinstance(file_entry, dict):
        return ""
    for key in ("assetId", "asset_id", "id"):
        asset_id = file_entry.get(key)
        if asset_id:
            return str(asset_id)
    return ""


def collect_integrante_asset_ids(items):
    columns = app_columns()
    asset_ids = []
    for item in items:
        for index in range(1, 6):
            column = columns.get(f"integrante_{index}_foto")
            for file_entry in file_entries(item, column):
                asset_id = file_asset_id(file_entry)
                if asset_id:
                    asset_ids.append(asset_id)
    return sorted(set(asset_ids))


def chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_asset_urls(asset_ids):
    urls = {}
    if not asset_ids:
        return urls

    for batch in chunks(asset_ids, 100):
        try:
            data = monday_request(
                """
                query Assets($assetIds: [ID!]!) {
                  assets(ids: $assetIds) {
                    id
                    public_url
                    url
                  }
                }
                """,
                {"assetIds": batch},
            )
        except Exception:
            try:
                data = monday_request(
                    """
                    query Assets($assetIds: [ID!]!) {
                      assets(ids: $assetIds) {
                        id
                        url
                      }
                    }
                    """,
                    {"assetIds": batch},
                )
            except Exception:
                data = {}
        for asset in data.get("assets") or []:
            asset_id = str(asset.get("id") or "")
            url = asset.get("public_url") or asset.get("url") or ""
            if asset_id and url:
                urls[asset_id] = url
    return urls


def attach_asset_urls(items):
    asset_urls = fetch_asset_urls(collect_integrante_asset_ids(items))
    if not asset_urls:
        return items
    for item in items:
        item["_asset_urls"] = asset_urls
    return items


def first_file_info(item, column):
    asset_urls = item.get("_asset_urls") or {}
    for file_entry in file_entries(item, column):
        if not isinstance(file_entry, dict):
            continue
        asset_id = file_asset_id(file_entry)
        url = (
            file_entry.get("public_url")
            or file_entry.get("url")
            or file_entry.get("url_thumbnail")
            or asset_urls.get(asset_id)
            or ""
        )
        name = file_entry.get("name") or file_entry.get("fileName") or ""
        if url or name:
            return {"url": str(url), "name": str(name)}
    return {"url": "", "name": ""}


def activity_integrantes(item, columns):
    integrantes = []
    for index in range(1, 6):
        nome = read_column(item, columns, f"integrante_{index}").strip()
        foto = first_file_info(item, columns.get(f"integrante_{index}_foto"))
        details = {
            "papel": read_column(item, columns, f"integrante_{index}_papel").strip(),
            "cidade": read_column(item, columns, f"integrante_{index}_cidade").strip(),
            "estado": read_column(item, columns, f"integrante_{index}_estado").strip(),
            "linkedin": read_column(item, columns, f"integrante_{index}_linkedin").strip(),
            "instagram": read_column(item, columns, f"integrante_{index}_instagram").strip(),
            "instituicao": read_column(item, columns, f"integrante_{index}_instituicao").strip(),
            "tipoInstituicao": read_column(item, columns, f"integrante_{index}_tipo_instituicao").strip(),
            "bio": read_column(item, columns, f"integrante_{index}_bio").strip(),
        }
        if nome or foto["url"] or any(details.values()):
            integrantes.append(
                {
                    "nome": nome,
                    "fotoUrl": foto["url"],
                    "fotoNome": foto["name"],
                    **details,
                }
            )
    return integrantes


def activity_dados_operacionais(item, columns):
    parts = [
        read_column(item, columns, "dados_operacionais_1").strip(),
        read_column(item, columns, "dados_operacionais_2").strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def parse_existing_review(text):
    parsed = parse_json_value(text)
    if isinstance(parsed, dict):
        review = empty_review()
        review.update(parsed)
        review["condizencias"] = parsed.get("condizencias") or {}
        review["integrantes"] = parsed.get("integrantes") or []
        review["escalas"] = parsed.get("escalas") or {}
        review["recomendacao"] = normalize_recommendation(review.get("recomendacao"))
        return review

    review = empty_review()
    if text:
        review["informacoesComplementares"] = str(text)
    return review


def normalize_recommendation(value):
    value = str(value or "").strip()
    return LEGACY_RECOMMENDATIONS.get(value, value)


def format_activity_id(monday_id, supabase_id):
    monday_id = str(monday_id or "").strip()
    supabase_id = str(supabase_id or "").strip()
    if supabase_id:
        return f"{monday_id} / {supabase_id}"
    return monday_id


def matches_avaliador(item, avaliador_id):
    route_value = str(avaliador_id or "").strip()
    if not route_value:
        return False

    column = app_columns()["avaliador"]
    value = item_column_values(item).get(column["id"]) or {}
    candidates = [value.get("text") or ""]
    candidates.extend(collect_match_values(parse_json_value(value.get("value"))))

    route_slug = normalize(route_value)
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate:
            continue
        if candidate.lower() == route_value.lower() or normalize(candidate) == route_slug:
            return True
    return False


def fetch_items():
    item_fields = """
      cursor
      items {
        id
        name
        column_values {
          id
          text
          value
          type
        }
      }
    """
    first_page_query = """
    query BoardItems($boardId: [ID!]!) {
      boards(ids: $boardId) {
        items_page(limit: 500) {
          __ITEM_FIELDS__
        }
      }
    }
    """.replace("__ITEM_FIELDS__", item_fields)
    next_page_query = """
    query NextBoardItems($cursor: String!) {
      next_items_page(limit: 500, cursor: $cursor) {
        __ITEM_FIELDS__
      }
    }
    """.replace("__ITEM_FIELDS__", item_fields)
    items = []
    data = monday_request(first_page_query, {"boardId": [monday_board_id()]})
    boards = data.get("boards") or []
    if not boards:
        return items

    page = boards[0].get("items_page") or {}

    while True:
        items.extend(page.get("items") or [])
        cursor = page.get("cursor")
        if not cursor:
            return attach_asset_urls(items)
        data = monday_request(next_page_query, {"cursor": cursor})
        page = data.get("next_items_page") or {}


def status_is_submitted(item):
    columns = app_columns()
    recommendation = read_column(item, columns, "recomendacao").strip()
    review = parse_existing_review(read_column(item, columns, "parecer"))
    return bool(recommendation or review.get("recomendacao"))


def serialize_item(item):
    columns = app_columns()
    review = parse_existing_review(read_column(item, columns, "parecer"))
    recommendation = normalize_recommendation(
        read_column(item, columns, "recomendacao").strip() or review.get("recomendacao", "")
    )
    if recommendation:
        review["recomendacao"] = recommendation

    submitted = status_is_submitted(item)
    integrantes = activity_integrantes(item, columns)
    item_id = str(item["id"])
    supabase_id = supabase_id_for_monday_id(item_id)
    supabase_id = f'2026CA{30000 + int(supabase_id)}'
    return {
        "itemId": item_id,
        "idSupabase": supabase_id,
        "idAtividade": format_activity_id(item_id, supabase_id),
        "nomeAtividade": item.get("name") or "",
        "nomeEspecialista": read_column(item, columns, "nome_especialista"),
        "objetivo": read_column(item, columns, "objetivo"),
        "justificativa": read_column(item, columns, "justificativa"),
        "metodologia": read_column(item, columns, "metodologia"),
        "descricaoPublicacao": read_column(item, columns, "descricao_publicacao"),
        "eixo": read_column(item, columns, "eixo"),
        "formato": read_column(item, columns, "formato"),
        "integrantes": integrantes,
        "integrantesTexto": "\n".join(integrante["nome"] for integrante in integrantes),
        "palavrasChave": read_column(item, columns, "palavras_chave"),
        "duracao": read_column(item, columns, "duracao"),
        "publicoAlvo": read_column(item, columns, "publico_alvo"),
        "restricaoFaixaEtaria": read_column(item, columns, "restricao_faixa_etaria"),
        "dadosOperacionais": activity_dados_operacionais(item, columns),
        "informacoesExtras": read_column(item, columns, "informacoes_extras"),
        "review": review,
        "recomendacao": recommendation,
        "enviado": submitted,
        "enviadoTexto": "Enviado" if submitted else "",
    }


def evaluations_for(avaliador_id):
    return [serialize_item(item) for item in fetch_items() if matches_avaliador(item, avaliador_id)]


def monday_value_for(column, text):
    column_type = (column or {}).get("type")
    text = str(text or "")

    if column_type == "status":
        return {"label": text}
    if column_type == "dropdown":
        return {"labels": [text]}
    if column_type == "checkbox":
        return {"checked": "true" if text else "false"}
    if column_type in {"text", "long_text"}:
        return {"text": text}
    return text


def clean_text(value):
    value = str(value or "").strip()
    if len(value) > TEXT_LIMIT:
        raise ConfigError(f"Textos devem ter no máximo {TEXT_LIMIT} caracteres.")
    return value


def clean_yes_no(value):
    value = normalize(value)
    if value in {"sim", "s", "yes", "true", "1"}:
        return "sim"
    if value in {"nao", "não", "n", "no", "false", "0"}:
        return "nao"
    return ""


def clean_scale(value):
    try:
        scale = int(value)
    except (TypeError, ValueError):
        return None
    return scale if 1 <= scale <= 4 else None


def category_for_evaluator_id(avaliador_id):
    text = str(avaliador_id or "").strip()
    direct = text.lstrip("0") or text
    numeric_match = re.search(r"\d+", text)
    numeric = numeric_match.group(0).lstrip("0") if numeric_match else ""
    return (
        CATEGORIES_BY_EVALUATOR_ID.get(text)
        or CATEGORIES_BY_EVALUATOR_ID.get(direct)
        or CATEGORIES_BY_EVALUATOR_ID.get(numeric, "")
    )


def clean_age(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.fullmatch(r"\d{1,3}", text):
        return None
    age = int(text)
    return age if 0 <= age <= 130 else None


def has_age_restriction_text(value):
    text = str(value or "").strip()
    if not text:
        return False
    normalized = normalize(text)
    if normalized in {"nao", "n", "nenhuma"}:
        return False
    no_restriction_markers = {
        "sem-restricao",
        "nao-possui",
        "nao-ha",
        "nao-tem",
        "nao-se-aplica",
        "nenhuma",
        "livre",
        "todas-as-idades",
        "todos-os-publicos",
    }
    return not any(marker in normalized for marker in no_restriction_markers)


def has_blocking_condizence_issue(review):
    condizencias = review.get("condizencias") or {}
    return any(
        key != "categoriaCondizente" and condizencias.get(key) == "nao"
        for key in CONDIZENCE_FIELDS
    )


def all_condizente(review):
    condizencias = review.get("condizencias") or {}
    if any(condizencias.get(key) != "sim" for key in CONDIZENCE_FIELDS):
        return False
    for integrante in review.get("integrantes") or []:
        if integrante.get("deAcordo") != "sim":
            return False
    return True


def validate_review(payload, source_row=None, avaliador_id=""):
    data = payload.get("review") if isinstance(payload.get("review"), dict) else payload
    data = data or {}
    source_row = source_row or {}
    errors = []

    review = empty_review()
    review["descricaoSugestao"] = clean_text(data.get("descricaoSugestao"))
    review["eixoSugestao"] = clean_text(data.get("eixoSugestao"))
    review["formatoSugestao"] = clean_text(data.get("formatoSugestao"))
    review["palavraSugerida"] = clean_text(data.get("palavraSugerida"))
    selected_category = category_for_evaluator_id(avaliador_id)
    if not selected_category:
        errors.append("Categoria não encontrada para este avaliador.")
    else:
        review["categoriaSelecionada"] = selected_category
    review["duracaoEsperada"] = clean_text(data.get("duracaoEsperada"))
    review["dadosOperacionaisAdaptaveis"] = clean_yes_no(data.get("dadosOperacionaisAdaptaveis"))
    review["dadosOperacionaisAdaptacao"] = clean_text(data.get("dadosOperacionaisAdaptacao"))
    review["informacoesComplementares"] = clean_text(data.get("informacoesComplementares"))
    review["foraEscopo"] = clean_text(data.get("foraEscopo"))

    source_condizencias = data.get("condizencias") if isinstance(data.get("condizencias"), dict) else {}
    category_value = clean_yes_no(data.get("categoriaCondizente") or source_condizencias.get("categoriaCondizente"))
    if not category_value:
        errors.append("Informe se a categoria avaliada está condizente.")
    review["condizencias"]["categoriaCondizente"] = category_value

    if category_value == "nao":
        review["recomendacao"] = OUT_OF_SCOPE_RECOMMENDATION
        if not review["foraEscopo"]:
            errors.append("Informe o motivo de fora do escopo da categoria de análise.")
        if errors:
            raise ConfigError(" ".join(errors))
        return review

    for key, label in CONDIZENCE_FIELDS.items():
        if key == "categoriaCondizente":
            continue
        value = clean_yes_no(data.get(key) or source_condizencias.get(key))
        review["condizencias"][key] = value
        if not value:
            errors.append(f"Informe se {label} está condizente.")
        if value == "nao":
            if key == "eixoCondizente" and not review["eixoSugestao"]:
                errors.append("Informe a sugestão de eixo.")
            if key == "formatoCondizente" and not review["formatoSugestao"]:
                errors.append("Informe a sugestão de formato.")
            if key == "duracaoCondizente" and not review["duracaoEsperada"]:
                errors.append("Informe o tempo esperado da atividade.")

    min_age = clean_age(data.get("idadeMinima"))
    max_age = clean_age(data.get("idadeMaxima"))
    if min_age not in {"", None}:
        review["idadeMinima"] = min_age
    if max_age not in {"", None}:
        review["idadeMaxima"] = max_age
    if has_age_restriction_text(source_row.get("restricaoFaixaEtaria")):
        if min_age in {"", None}:
            errors.append("Informe a idade mínima da restrição.")
        if max_age in {"", None}:
            errors.append("Informe a idade máxima da restrição.")
        if min_age not in {"", None} and max_age not in {"", None} and min_age > max_age:
            errors.append("A idade mínima não pode ser maior que a idade máxima.")
    else:
        if str(data.get("idadeMinima") or "").strip() and min_age is None:
            errors.append("Informe uma idade mínima válida.")
        if str(data.get("idadeMaxima") or "").strip() and max_age is None:
            errors.append("Informe uma idade máxima válida.")

    source_integrantes = data.get("integrantes") if isinstance(data.get("integrantes"), list) else []
    for index, integrante in enumerate(source_integrantes, start=1):
        if not isinstance(integrante, dict):
            continue
        item = {
            "nome": clean_text(integrante.get("nome")),
            "deAcordo": clean_yes_no(integrante.get("deAcordo")),
            "acao": normalize(integrante.get("acao")),
            "sugestao": clean_text(integrante.get("sugestao")),
        }
        if not item["deAcordo"]:
            errors.append(f"Informe se o integrante {index} está de acordo.")
        if item["deAcordo"] == "nao":
            if item["acao"] not in {"cancelar", "trocar"}:
                errors.append(f"Informe se o integrante {index} deve ser cancelado ou trocado.")
            if item["acao"] == "trocar" and not item["sugestao"]:
                errors.append(f"Informe a sugestão de troca do integrante {index}.")
        review["integrantes"].append(item)

    source_scales = data.get("escalas") if isinstance(data.get("escalas"), dict) else {}
    for key, label in SCALE_FIELDS.items():
        scale = clean_scale(data.get(key) or source_scales.get(key))
        if scale is None:
            errors.append(f"Informe a escala de {label}.")
        else:
            review["escalas"][key] = scale

    recommendation = normalize_recommendation(clean_text(data.get("recomendacao")))
    if recommendation not in RECOMMENDATION_OPTIONS:
        errors.append("Selecione uma recomendação válida.")
    elif recommendation == OUT_OF_SCOPE_RECOMMENDATION:
        errors.append("Use fora do escopo apenas quando a categoria avaliada não estiver condizente.")
    elif has_blocking_condizence_issue(review) and recommendation == "Recomendado":
        errors.append("Não é possível aprovar quando há item não condizente.")
    else:
        review["recomendacao"] = recommendation

    if errors:
        raise ConfigError(" ".join(errors))
    return review


def update_monday_item(item_id, review):
    columns = app_columns()
    column_values = {
        columns["recomendacao"]["id"]: monday_value_for(columns["recomendacao"], review["recomendacao"]),
        columns["parecer"]["id"]: monday_value_for(
            columns["parecer"],
            json.dumps(review, ensure_ascii=False, indent=2),
        ),
    }

    mutation = """
    mutation UpdateEvaluation($boardId: ID!, $itemId: ID!, $columnValues: JSON!) {
      change_multiple_column_values(
        board_id: $boardId,
        item_id: $itemId,
        column_values: $columnValues,
        create_labels_if_missing: true
      ) {
        id
      }
    }
    """
    return monday_request(
        mutation,
        {
            "boardId": monday_board_id(),
            "itemId": str(item_id),
            "columnValues": json.dumps(column_values, ensure_ascii=False),
        },
    )


@app.route("/")
@app.route("/<path:avaliador_id>")
def index(avaliador_id=""):
    if avaliador_id.startswith("api/"):
        return jsonify({"error": "Rota não encontrada."}), 404
    return render_template("index.html", avaliador_id=avaliador_id)


@app.get("/api/avaliacoes/<path:avaliador_id>")
def list_evaluations(avaliador_id):
    try:
        rows = evaluations_for(avaliador_id)
        return jsonify({"avaliadorId": avaliador_id, "rows": rows, "total": len(rows)})
    except Exception as exc:
        return error_response(exc)


@app.post("/api/avaliacoes/<path:avaliador_id>/<item_id>")
def submit_evaluation(avaliador_id, item_id):
    try:
        payload = request.get_json(silent=True) or {}
        rows = evaluations_for(avaliador_id)
        source_row = next((row for row in rows if row["itemId"] == str(item_id)), None)
        if not source_row:
            return jsonify({"error": "Item não encontrado para este avaliador."}), 404
        review = validate_review(payload, source_row, avaliador_id)

        update_monday_item(item_id, review)
        return jsonify(
            {
                "ok": True,
                "itemId": str(item_id),
                "review": review,
                "recomendacao": review["recomendacao"],
                "enviado": True,
            }
        )
    except Exception as exc:
        return error_response(exc)
