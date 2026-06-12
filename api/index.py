from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import re
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
from urllib.parse import urlparse
import unicodedata
import copy
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from cryptography.fernet import Fernet
from typing import Dict, List, Set

# ──────────────────────────────────────────────
# INÍCIO: Configurações Anti-Spam / Segurança
# ──────────────────────────────────────────────
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
ALLOWED_DOMAINS = [d.strip() for d in os.environ.get('ALLOWED_DOMAINS', '').split(',') if d.strip()]
DOCUMENT_FERNET_KEY = os.environ.get('DOCUMENT_FERNET_KEY', '')
document_cipher = Fernet(DOCUMENT_FERNET_KEY.encode()) if DOCUMENT_FERNET_KEY else None
HONEYPOT_FIELD_NAME = 'website_url'
# ──────────────────────────────────────────────
# FIM: Configurações Anti-Spam / Segurança
# ──────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'chave-padrao-apenas-para-dev-local')

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Aumentado para suportar PDF + Imagens

EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'webp'}
KB = 1024
MB = 1024 * 1024
LOGO_MIN_BYTES = 100 * KB
PHOTO_MIN_BYTES = 500 * KB
IMAGE_MAX_BYTES = 5 * MB

CAMPOS_OBRIGATORIOS_BASE = [
    'tipoProponente', 
    'nomeRepresentante', 'telefoneRepresentante', 'emailRepresentante',
    'tituloAtividade', 'formatoAtividade', 'tempoDuracao',
    'objetivoAtividade', 'justificativaTematica', 'metodologiaAplicada',
    'descricaoAtividade', 'eixo', 'publicoAlvo',
    'acessoAtividade'
]


# ──────────────────────────────────────────────
# INÍCIO: Matcher de Pareceristas
# ──────────────────────────────────────────────
GRUPOS_TAGS = {
    "Categoria 1 — IA e Tecnologias Emergentes": [
        "Inteligência Artificial", "IA Generativa", "LLMs",
        "Engenharia de Prompt", "Automação", "IA aplicada a negócios",
        "IA aplicada à educação", "IA aplicada à produtividade",
        "Agentes de IA", "Transformação Digital", "XR",
        "Realidade Virtual", "Realidade Aumentada", "Blockchain",
        "Computação Quântica", "Robótica", "Visão Computacional",
        "Processamento de Linguagem Natural", "Digital Twins",
        "Edge Computing", "Wearables", "Assistentes Virtuais",
        "Tecnologia Assistiva", "Biotecnologia", "Deep Tech",
        "Futurismo", "Tecnologias Disruptivas"
    ],
    "Categoria 2 — Desenvolvimento, Dados e Segurança": [
        "Programação", "Cloud", "Arquitetura de Sistemas",
        "Desenvolvimento de Software", "Low Code", "No Code",
        "DevOps", "Integração de Sistemas", "Análise de Dados",
        "Governança de Dados", "Cibersegurança", "Conectividade",
        "Privacidade", "Internet das Coisas", "Dados", "API",
        "Open Source", "Banco de Dados", "Engenharia de Dados",
        "Data Science", "Big Data", "Business Intelligence", "LGPD",
        "Segurança Digital", "Ethical Hacking", "Infraestrutura",
        "Redes", "Computação em Nuvem", "QA e Testes", "Observabilidade"
    ],
    "Categoria 3 — Empreendedorismo e Inovação": [
        "Startups", "Ecossistemas de Inovação", "Inovação Aberta",
        "Modelagem de Negócios", "Transformação Digital",
        "Internacionalização", "Venture Capital",
        "Investimento em Inovação", "Comunidades",
        "Negócios Emergentes", "Empreendedorismo",
        "Intraempreendedorismo", "Captação de Recursos", "Pitch",
        "Escalabilidade", "Aceleração", "Incubação", "Impacto Social",
        "Economia Digital", "Novos Negócios", "Product Market Fit",
        "Validação de Mercado", "Growth", "Corporate Venture"
    ],
    "Categoria 4 — Gestão, Mercado e Trabalho": [
        "Marketing", "Branding", "Vendas", "Experiência do Cliente",
        "Liderança", "RH", "Cultura Organizacional", "Soft Skills",
        "Empregabilidade", "Carreira", "Futuro do Trabalho", "Gestão",
        "Gestão de Projetos", "Gestão Ágil", "Produtividade",
        "Estratégia", "Negociação", "Customer Success",
        "Trabalho Remoto", "Diversidade nas Organizações",
        "Educação Corporativa", "Economia do Trabalho",
        "Saúde Mental no Trabalho", "Liderança Feminina"
    ],
    "Categoria 5 — Comunicação e Mídias Digitais": [
        "Comunicação Digital", "Produção de Conteúdo", "Creator Economy",
        "Redes Sociais", "Influência Digital", "Podcast",
        "Plataformas Digitais", "Mídia Digital", "Narrativas Digitais",
        "Jornalismo", "Comunicação Institucional",
        "Marketing de Conteúdo", "SEO", "Community Building",
        "Streaming", "Audiovisual Digital", "Storytelling",
        "Desinformação", "Fact Checking", "Cultura da Internet",
        "Comunicação Pública"
    ],
    "Categoria 6 — Design, Games e Experiências Criativas": [
        "UX", "UI", "Design de Produto", "Design Digital", "Games",
        "Game Design", "Gamificação", "Interatividade",
        "Experiências Imersivas", "Design", "Service Design",
        "Design Thinking", "Design Estratégico", "Design de Experiência",
        "Motion Design", "Animação", "Criatividade", "Prototipagem",
        "Economia dos Games", "eSports", "Metaverso"
    ],
    "Categoria 7 — Arte, Cultura e Linguagens": [
        "Audiovisual", "Música", "Artes Visuais", "Literatura", "Moda",
        "Dança", "Teatro", "Fotografia", "Gastronomia",
        "Patrimônio Cultural", "Cultura Popular", "Produção Cultural",
        "Cultura Digital", "Museus", "Memória", "Curadoria",
        "Festivais", "Quadrinhos", "Arte Urbana", "Economia Criativa",
        "Expressões Artísticas", "Cultura Pernambucana",
        "Cultura Brasileira"
    ],
    "Categoria 8 — Cidade, Sustentabilidade e Território": [
        "Urbanismo", "Mobilidade", "Arquitetura", "Cidades Inteligentes",
        "Território", "Ocupação Urbana", "Infraestrutura",
        "Acessibilidade", "Políticas Urbanas", "Sustentabilidade",
        "Meio Ambiente", "Mudanças Climáticas", "Energia",
        "Economia Circular", "Resíduos Sólidos", "Habitação",
        "Patrimônio Urbano", "Desenvolvimento Territorial",
        "Resiliência Urbana", "Soluções Baseadas na Natureza",
        "Justiça Climática"
    ],
    "Categoria 9 — Sociedade, Inclusão e Impacto": [
        "Diversidade", "Inclusão", "Acessibilidade", "Educação",
        "Cidadania", "Saúde", "Comportamento", "Comunidades",
        "Impacto Social", "Equidade", "Participação Social",
        "Direitos Humanos", "Juventude", "Envelhecimento", "Gênero",
        "Raça", "Povos Tradicionais", "Saúde Digital", "Bem-estar",
        "Alfabetização Digital", "Participação Cívica",
        "Inovação Social", "Terceiro Setor"
    ]
}


PARECERISTAS = [
    {
        "id": 1,
        "nome": "Parecerista Sustentabilidade",
        "tags": ["Economia Circular", "Meio Ambiente", "Sustentabilidade", "Mudanças Climáticas"],
        "limite_atividades": 10,
        "atividades_atribuidas": 0
    },
    {
        "id": 2,
        "nome": "Parecerista Negócios",
        "tags": ["Empreendedorismo", "Startups", "Transformação Digital", "Modelagem de Negócios"],
        "limite_atividades": 10,
        "atividades_atribuidas": 0
    },
    {
        "id": 3,
        "nome": "Parecerista Impacto",
        "tags": ["Impacto Social", "Educação", "Diversidade", "Inclusão"],
        "limite_atividades": 10,
        "atividades_atribuidas": 0
    }
]


def normalizar(texto: str) -> str:
    return texto.strip().lower()


def normalizar_tags(tags: List[str]) -> Set[str]:
    return {normalizar(tag) for tag in tags}


def criar_mapa_tag_para_grupos(grupos_tags: Dict[str, List[str]]) -> Dict[str, Set[str]]:
    mapa = {}

    for grupo, tags in grupos_tags.items():
        for tag in tags:
            tag_normalizada = normalizar(tag)

            if tag_normalizada not in mapa:
                mapa[tag_normalizada] = set()

            mapa[tag_normalizada].add(grupo)

    return mapa


TAG_PARA_GRUPOS = criar_mapa_tag_para_grupos(GRUPOS_TAGS)


def obter_grupos_das_tags(tags: List[str]) -> Set[str]:
    grupos = set()

    for tag in tags:
        tag_normalizada = normalizar(tag)
        grupos.update(TAG_PARA_GRUPOS.get(tag_normalizada, set()))

    return grupos


def calcular_score(
    atividade_tags: List[str],
    parecerista_tags: List[str],
    peso_tag_direta: float = 0.8,
    peso_macrogrupo: float = 0.2
) -> Dict:
    tags_atividade = normalizar_tags(atividade_tags)
    tags_parecerista = normalizar_tags(parecerista_tags)

    tags_em_comum = tags_atividade.intersection(tags_parecerista)

    score_direto = (
        len(tags_em_comum) / len(tags_atividade)
        if tags_atividade
        else 0
    )

    grupos_atividade = obter_grupos_das_tags(atividade_tags)
    grupos_parecerista = obter_grupos_das_tags(parecerista_tags)

    grupos_em_comum = grupos_atividade.intersection(grupos_parecerista)

    score_macrogrupo = (
        len(grupos_em_comum) / len(grupos_atividade)
        if grupos_atividade
        else 0
    )

    score_final = (
        score_direto * peso_tag_direta
        + score_macrogrupo * peso_macrogrupo
    )

    return {
        "score_final": round(score_final, 4),
        "score_direto": round(score_direto, 4),
        "score_macrogrupo": round(score_macrogrupo, 4),
        "tags_em_comum": sorted(tags_em_comum),
        "grupos_atividade": sorted(grupos_atividade),
        "grupos_parecerista": sorted(grupos_parecerista),
        "grupos_em_comum": sorted(grupos_em_comum)
    }


def ranquear_pareceristas(
    atividade: Dict,
    pareceristas: List[Dict],
    score_minimo: float = 0.0
) -> List[Dict]:
    ranking = []

    for parecerista in pareceristas:
        if parecerista["atividades_atribuidas"] >= parecerista["limite_atividades"]:
            continue

        resultado = calcular_score(
            atividade["tags"],
            parecerista["tags"]
        )

        if resultado["score_final"] >= score_minimo:
            ranking.append({
                "atividade_id": atividade.get("id"),
                "atividade_titulo": atividade.get("titulo"),
                "parecerista_id": parecerista["id"],
                "parecerista_nome": parecerista["nome"],
                **resultado,
                "atividades_atribuidas": parecerista["atividades_atribuidas"]
            })

    ranking.sort(
        key=lambda item: (
            item["score_final"],
            item["score_direto"],
            -item["atividades_atribuidas"]
        ),
        reverse=True
    )

    return ranking
# ──────────────────────────────────────────────
# FIM: Matcher de Pareceristas
# ──────────────────────────────────────────────

try:
    from upstash_redis import Redis
except ImportError:
    Redis = None
    print("AVISO: Biblioteca upstash-redis não foi encontrada!")

redis_url = os.environ.get("UPSTASH_REDIS_REST_URL")
redis_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

redis_client = None
if Redis and redis_url and redis_token:
    try:
        redis_client = Redis(url=redis_url, token=redis_token)
        print("✅ Upstash conectado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao conectar ao Upstash: {e}")
else:
    print("⚠️ Upstash não configurado ou biblioteca não instalada.")

# ──────────────────────────────────────────────
# INÍCIO: Configuração Supabase
# ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")


def normalizar_tags_atividade(tags_texto, sugestao_texto):
    tags = [tag.strip() for tag in (tags_texto or '').split(',') if tag.strip()]
    sugestao = (sugestao_texto or '').strip()
    if sugestao:
        tags.append(sugestao)
    return tags


def carregar_pareceristas():
    """Carrega avaliadores do Supabase; se indisponível, usa o fallback local."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return PARECERISTAS

    try:
        query = urllib.parse.urlencode({
            "select": "ID_avaliador,nome,email,tags_responsavel,limite_atividades,atividades_atribuidas",
            "order": "ID_avaliador.asc"
        })
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/avaliadores?{query}",
            method='GET',
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json"
            }
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode('utf-8'))

        pareceristas = []
        for row in rows:
            tags = row.get("tags_responsavel") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(',') if tag.strip()]

            pareceristas.append({
                "id": row.get("ID_avaliador"),
                "nome": row.get("nome") or f"Avaliador {row.get('ID_avaliador')}",
                "email": row.get("email"),
                "tags": tags,
                "limite_atividades": row.get("limite_atividades") or 10,
                "atividades_atribuidas": row.get("atividades_atribuidas") or 0
            })

        return pareceristas or PARECERISTAS
    except Exception as e:
        print(f"⚠️ Não foi possível carregar avaliadores do Supabase. Usando fallback local. Erro: {e}")
        return PARECERISTAS


def selecionar_avaliadores(dados, quantidade=3):
    atividade = {
        "id": None,
        "titulo": dados.get('tituloAtividade'),
        "tags": normalizar_tags_atividade(dados.get('tags'), dados.get('tagSuggestion'))
    }
    ranking = ranquear_pareceristas(atividade, carregar_pareceristas())
    ids = [item["parecerista_id"] for item in ranking[:quantidade]]

    while len(ids) < quantidade:
        ids.append(None)

    return ids, ranking[:quantidade]


def strip_base64_for_supabase(data):
    """Remove strings base64 para não estourar o limite de payload do Supabase."""
    clean = copy.deepcopy(data)
    if 'proponente' in clean and 'logo_marca_base64' in clean['proponente']:
        clean['proponente']['logo_marca_base64'] = '[ENVIADO VIA WORKER]'
    if 'convidados' in clean:
        for conv in clean['convidados']:
            if 'foto_base64' in conv:
                conv['foto_base64'] = '[ENVIADO VIA WORKER]'
    if 'atividade' in clean and clean['atividade'].get('experiencia') and 'anexos_base64' in clean['atividade']['experiencia']:
        clean['atividade']['experiencia']['anexos_base64'] = '[ENVIADOS VIA WORKER]'
    return clean


def save_to_supabase(inscricao):
    """Salva o payload no Supabase como fonte da verdade (usando urllib nativo)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("⚠️ Supabase não configurado. Pulando salvamento.")
        return None

    try:
        clean_payload = strip_base64_for_supabase(inscricao)

        body = json.dumps({
            "status": "pending",
            "payload": clean_payload,
            "ID_avaliador_1": inscricao.get("ID_avaliador_1"),
            "ID_avaliador_2": inscricao.get("ID_avaliador_2"),
            "ID_avaliador_3": inscricao.get("ID_avaliador_3")
        }, ensure_ascii=False, default=str)

        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/inscricoes",
            data=body.encode('utf-8'),
            method='POST',
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result and len(result) > 0 and 'id' in result[0]:
                supabase_id = result[0]['id']
                print(f"✅ Salvo no Supabase! ID: {supabase_id}")
                return supabase_id
            else:
                print(f"❌ Supabase retornou resposta inesperada: {result}")
                return None

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        print(f"❌ Erro Supabase HTTP {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"❌ Exceção ao salvar no Supabase: {type(e).__name__}: {e}")
        return None

# ──────────────────────────────────────────────
# FIM: Configuração Supabase
# ──────────────────────────────────────────────


def extensao_permitida(nome_arquivo):
    return '.' in nome_arquivo and \
           nome_arquivo.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS


def formatar_tamanho_upload(tamanho_bytes):
    if tamanho_bytes >= MB:
        valor = tamanho_bytes / MB
        return f'{valor:g}MB'
    return f'{round(tamanho_bytes / KB)}KB'


def tamanho_arquivo_upload(arquivo):
    if not arquivo or not arquivo.filename:
        return None
    try:
        posicao_atual = arquivo.tell()
        arquivo.seek(0, os.SEEK_END)
        tamanho = arquivo.tell()
        arquivo.seek(posicao_atual)
        return tamanho
    except Exception:
        try:
            arquivo.seek(0)
        except Exception:
            pass
        return None


def tamanho_original_upload(dados, campo_tamanho, arquivo):
    valor = dados.get(campo_tamanho, '').strip()
    if valor:
        try:
            tamanho = int(valor)
            if tamanho >= 0:
                return tamanho
        except (TypeError, ValueError):
            pass
    return tamanho_arquivo_upload(arquivo)


def validar_tamanho_upload_imagem(dados, campo_tamanho, arquivo, minimo, maximo, rotulo):
    tamanho = tamanho_original_upload(dados, campo_tamanho, arquivo)
    if tamanho is None:
        return None
    if tamanho < minimo or tamanho > maximo:
        return (
            f'{rotulo} deve ter entre {formatar_tamanho_upload(minimo)} '
            f'e {formatar_tamanho_upload(maximo)}. '
            f'Arquivo atual: {formatar_tamanho_upload(tamanho)}.'
        )
    return None


def validar_email(email):
    padrao = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(padrao, email) is not None


def validar_telefone(telefone):
    digitos = re.sub(r'\D', '', telefone or '')
    if len(digitos) not in (10, 11):
        return False
    if digitos == digitos[0] * len(digitos):
        return False
    if digitos[2:] == digitos[2] * len(digitos[2:]):
        return False
    return digitos[0] != '0' and digitos[1] != '0'


def validar_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11: return False
    if cpf == cpf[0] * 11: return False
    soma = 0
    for i in range(9): soma += int(cpf[i]) * (10 - i)
    resto = 11 - (soma % 11)
    if resto in (10, 11): resto = 0
    if resto != int(cpf[9]): return False
    soma = 0
    for i in range(10): soma += int(cpf[i]) * (11 - i)
    resto = 11 - (soma % 11)
    if resto in (10, 11): resto = 0
    return resto == int(cpf[10])


def validar_cnpj(cnpj):
    cnpj = re.sub(r'\D', '', cnpj)
    if len(cnpj) != 14: return False
    if cnpj == cnpj[0] * 14: return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = 0
    for i in range(12): soma += int(cnpj[i]) * pesos1[i]
    resto = 11 - (soma % 11)
    if resto in (10, 11): resto = 0
    if resto != int(cnpj[12]): return False
    soma = 0
    for i in range(13): soma += int(cnpj[i]) * pesos2[i]
    resto = 11 - (soma % 11)
    if resto in (10, 11): resto = 0
    return resto == int(cnpj[13])

def criptografar_documento(valor, somente_digitos=False):
    if not valor:
        return None
    if not document_cipher:
        raise RuntimeError("DOCUMENT_FERNET_KEY nao configurada")

    texto = re.sub(r"\D", "", valor) if somente_digitos else valor.strip()
    return document_cipher.encrypt(texto.encode("utf-8")).decode("utf-8")

def converter_foto_base64(arquivo_foto):
    if not arquivo_foto or arquivo_foto.filename == '':
        return None
    if not extensao_permitida(arquivo_foto.filename):
        return None
    try:
        arquivo_foto.seek(0)
        dados_bytes = arquivo_foto.read()
        encoded_string = base64.b64encode(dados_bytes).decode('utf-8')
        ext = arquivo_foto.filename.rsplit('.', 1)[1].lower()
        mime_type = 'image/jpeg' if ext in ['jpg', 'jpeg'] else f'image/{ext}'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Erro ao converter imagem: {e}")
        return None

def converter_arquivo_base64(arquivo, permitido_ext=None):
    """Converte qualquer arquivo (incluindo PDF) para base64."""
    if not arquivo or arquivo.filename == '':
        return None
    ext = arquivo.filename.rsplit('.', 1)[1].lower() if '.' in arquivo.filename else ''
    if permitido_ext and ext not in permitido_ext:
        return None
    try:
        arquivo.seek(0)
        dados_bytes = arquivo.read()
        encoded_string = base64.b64encode(dados_bytes).decode('utf-8')
        if ext == 'pdf':
            mime_type = 'application/pdf'
        elif ext in ['jpg', 'jpeg']:
            mime_type = 'image/jpeg'
        else:
            mime_type = f'image/{ext}'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Erro ao converter arquivo: {e}")
        return None


def salvar_uploads_temporarios(request_files):
    uploads = session.get('temp_uploads', {})
    foto_prop = request_files.get('fotoProponente')
    if foto_prop and foto_prop.filename:
        foto_base64 = converter_foto_base64(foto_prop)
        if foto_base64:
            uploads['fotoProponente'] = foto_base64
    for i in range(1, 6):
        foto_conv = request_files.get(f'convidado{i}_foto')
        if foto_conv and foto_conv.filename:
            foto_base64 = converter_foto_base64(foto_conv)
            if foto_base64:
                uploads[f'convidado{i}_foto'] = foto_base64
    session['temp_uploads'] = uploads


def obter_upload_temporario(chave):
    uploads = session.get('temp_uploads', {})
    return uploads.get(chave)


def limpar_uploads_temporarios():
    session.pop('temp_uploads', None)


# ──────────────────────────────────────────────
# FUNÇÃO DE ENVIO DE EMAIL
# ──────────────────────────────────────────────
def enviar_email_com_anexo(destinatario, nome_atividade, nome_proponente, pdf_file):
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASS = os.environ.get("SMTP_PASS")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "naoresponda@recnplay.com.br")

    if not SMTP_USER or not SMTP_PASS:
        print("=" * 60)
        print("⚠️  CREDENCIAIS SMTP NÃO CONFIGURADAS!")
        print("⚠️  Email NÃO será enviado. Configure as variáveis:")
        print("    SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM")
        print(f"📧 [SIMULAÇÃO] Para: {destinatario}")
        print(f"📧 [SIMULAÇÃO] Assunto: Confirmação - {nome_atividade}")
        try:
            pdf_file.seek(0)
            pdf_size = len(pdf_file.read())
            print(f"📧 [SIMULAÇÃO] Anexo PDF: {pdf_size} bytes")
            pdf_file.seek(0)
        except Exception:
            pass
        print("=" * 60)
        return False

    try:
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()

        if len(pdf_bytes) == 0:
            print("❌ PDF vazio! O arquivo não contém dados. Email não enviado.")
            return False

        print(f"📧 Preparando email para {destinatario} (PDF: {len(pdf_bytes)} bytes)...")

        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = destinatario
        msg['Subject'] = f"Confirmação de Inscrição — REC'n'Play 2026: {nome_atividade}"

        text_body = f"""Olá, {nome_proponente},

Recebemos sua proposta para a atividade "{nome_atividade}" no REC'n'Play 2026 com sucesso!

Em anexo, segue o comprovante em PDF com todos os dados enviados.

Atenciosamente,
Equipe REC'n'Play 2026
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; font-family:Arial,Helvetica,sans-serif; color:#333; background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4; padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.1);">
    <tr>
        <td style="background:linear-gradient(135deg,#FF3399,#990099); padding:35px 40px; text-align:center;">
            <h1 style="color:#fff; margin:0; font-size:28px; font-weight:700;">REC'n'Play 2026</h1>
        </td>
    </tr>
    <tr>
        <td style="padding:35px 40px;">
            <h2 style="color:#990099; margin:0 0 20px; font-size:22px;">✅ Proposta Registrada com Sucesso!</h2>
            <p style="font-size:15px; line-height:1.7; margin:0 0 15px;">
                Olá, <strong style="color:#FF3399;">{nome_proponente}</strong>!
            </p>
            <p style="font-size:15px; line-height:1.7; margin:0 0 15px;">
                Recebemos sua proposta para a atividade <strong>"{nome_atividade}"</strong>.
            </p>
            <p style="font-size:15px; line-height:1.7; margin:0 0 25px;">
                Em anexo, segue o comprovante em PDF com todos os dados enviados na inscrição.
            </p>
            <p style="font-size:15px; line-height:1.7; margin:0;">
                Atenciosamente,<br>
                <strong style="color:#990099;">Equipe REC'n'Play 2026</strong>
            </p>
        </td>
    </tr>
</table>
</td></tr>
</table>
</body>
</html>"""

        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        pdf_part = MIMEApplication(pdf_bytes, Name="proposta_recnplay_2026.pdf")
        pdf_part['Content-Disposition'] = 'attachment; filename="proposta_recnplay_2026.pdf"'
        msg.attach(pdf_part)

        print(f"📧 Conectando ao SMTP {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, destinatario, msg.as_string())
        server.quit()

        print(f"✅ Email enviado com sucesso para {destinatario}")
        return True

    except Exception as e:
        print(f"❌ Erro inesperado ao enviar email: {type(e).__name__}: {e}")
        return False


# ──────────────────────────────────────────────
# INÍCIO: Funções de Segurança
# ──────────────────────────────────────────────

def verify_turnstile(token, remote_ip=None):
    if not TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    try:
        payload = urllib.parse.urlencode({
            'secret': TURNSTILE_SECRET_KEY,
            'response': token,
        })
        if remote_ip:
            payload += f'&remoteip={urllib.parse.quote(remote_ip)}'
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=payload.encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('success', False)
    except Exception as e:
        print(f"❌ Erro na verificação Turnstile: {e}")
        return False


def validate_origin():
    if not ALLOWED_DOMAINS:
        return True
    origin = request.headers.get('Origin', '').strip()
    referer = request.headers.get('Referer', '').strip()
    if not origin and not referer:
        return False

    def _check_domain(header_value):
        if not header_value:
            return True
        try:
            parsed = urlparse(header_value)
            hostname = (parsed.hostname or '').lower()
            if not hostname:
                return False
            for allowed in ALLOWED_DOMAINS:
                allowed_lower = allowed.lower()
                if hostname == allowed_lower or hostname.endswith('.' + allowed_lower):
                    return True
            return False
        except Exception:
            return False

    if origin and not _check_domain(origin):
        return False
    if referer and not _check_domain(referer):
        return False
    return True

# ──────────────────────────────────────────────
# FIM: Funções de Segurança
# ──────────────────────────────────────────────


LOCATION_COUNTRIES_CACHE = None
LOCATION_BR_CITIES_CACHE = {}
LOCATION_FOREIGN_CITIES_CACHE = {}
LOCATION_FOREIGN_STATES_CACHE = {}


def _normalize_location_text(value):
    text = unicodedata.normalize('NFD', value or '')
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    return text.strip().casefold()


def _fetch_json(url, payload=None, timeout=10):
    data = None
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'forms-recnplay/1.0',
    }
    method = 'GET'
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        method = 'POST'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _load_countriesnow_names_by_code():
    data = _fetch_json('https://countriesnow.space/api/v0.1/countries/iso')
    names = {}
    for item in data.get('data', []):
        code = (item.get('Iso2') or item.get('iso2') or '').strip().lower()
        name = (item.get('name') or '').strip()
        if code and name:
            names[code] = name
    return names


def _load_countries():
    global LOCATION_COUNTRIES_CACHE
    if LOCATION_COUNTRIES_CACHE is not None:
        return LOCATION_COUNTRIES_CACHE

    countriesnow_names = {}
    try:
        countriesnow_names = _load_countriesnow_names_by_code()
    except Exception as e:
        print(f"Erro ao consultar CountriesNow ISO: {e}")

    data = _fetch_json('https://restcountries.com/v3.1/all?fields=name,cca2,translations')
    countries = []
    for item in data:
        code = (item.get('cca2') or '').strip().lower()
        name = item.get('name') or {}
        translations = item.get('translations') or {}
        por = translations.get('por') or {}
        label = (por.get('common') or name.get('common') or '').strip()
        english_name = (name.get('common') or label).strip()
        if not code or not label:
            continue
        countries.append({
            'label': label,
            'code': code,
            'api_name': countriesnow_names.get(code, english_name),
            'search': _normalize_location_text(' '.join(filter(None, [
                label,
                english_name,
                name.get('official', ''),
                por.get('official', ''),
            ]))),
        })
    LOCATION_COUNTRIES_CACHE = sorted(countries, key=lambda item: item['label'])
    return LOCATION_COUNTRIES_CACHE


def _filter_location_labels(labels, query, limit=20):
    normalized_query = _normalize_location_text(query)
    results = []
    seen = set()
    for label in labels:
        normalized_label = _normalize_location_text(label)
        if normalized_query not in normalized_label or normalized_label in seen:
            continue
        seen.add(normalized_label)
        results.append({'label': label})
        if len(results) >= limit:
            break
    return results


def _country_suggestions(query, limit=20):
    normalized_query = _normalize_location_text(query)
    results = []
    for country in _load_countries():
        if normalized_query not in country['search']:
            continue
        results.append({'label': country['label'], 'code': country['code']})
        if len(results) >= limit:
            break
    return results


def _all_country_suggestions():
    return [{'label': country['label'], 'code': country['code']} for country in _load_countries()]


def _country_api_name(country_code):
    country_code = (country_code or '').strip().lower()
    for country in _load_countries():
        if country['code'] == country_code:
            return country['api_name']
    return ''


def _br_city_labels(estado=''):
    estado = (estado or '').strip().upper()
    cache_key = estado or 'BR'
    if cache_key in LOCATION_BR_CITIES_CACHE:
        return LOCATION_BR_CITIES_CACHE[cache_key]

    if estado and re.fullmatch(r'[A-Z]{2}', estado):
        url = f'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{estado}/municipios?orderBy=nome'
    else:
        url = 'https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome'
    data = _fetch_json(url)
    labels = [item.get('nome', '').strip() for item in data if item.get('nome')]
    LOCATION_BR_CITIES_CACHE[cache_key] = labels
    return labels


def _foreign_city_labels(country_code):
    country_code = (country_code or '').strip().lower()
    if not country_code:
        return []
    if country_code in LOCATION_FOREIGN_CITIES_CACHE:
        return LOCATION_FOREIGN_CITIES_CACHE[country_code]

    api_name = _country_api_name(country_code)
    if not api_name:
        return []
    data = _fetch_json('https://countriesnow.space/api/v0.1/countries/cities', {'country': api_name})
    labels = sorted({city.strip() for city in data.get('data', []) if city and city.strip()})
    LOCATION_FOREIGN_CITIES_CACHE[country_code] = labels
    return labels


def _foreign_state_labels(country_code):
    country_code = (country_code or '').strip().lower()
    if not country_code:
        return []
    if country_code in LOCATION_FOREIGN_STATES_CACHE:
        return LOCATION_FOREIGN_STATES_CACHE[country_code]

    api_name = _country_api_name(country_code)
    if not api_name:
        return []
    data = _fetch_json('https://countriesnow.space/api/v0.1/countries/states', {'country': api_name})
    country_data = data.get('data') if isinstance(data, dict) else {}
    raw_states = country_data.get('states', []) if isinstance(country_data, dict) else []
    labels = sorted({state.get('name', '').strip() for state in raw_states if state.get('name')})
    LOCATION_FOREIGN_STATES_CACHE[country_code] = labels
    return labels


@app.route('/api/localidades', methods=['GET'])
def api_localidades():
    query = request.args.get('q', '').strip()
    tipo = request.args.get('tipo', 'cidade').strip().lower()
    country = request.args.get('country', '').strip().lower()
    estado = request.args.get('estado', '').strip().upper()
    all_requested = request.args.get('all', '').strip().lower() in {'1', 'true', 'sim'}
    if tipo not in {'cidade', 'pais', 'estado'} or (not all_requested and len(query) < 2):
        return jsonify({'suggestions': []})

    try:
        if tipo == 'pais':
            suggestions = _all_country_suggestions() if all_requested else _country_suggestions(query)
        elif tipo == 'estado':
            labels = _foreign_state_labels(country)
            suggestions = [{'label': label} for label in labels] if all_requested else _filter_location_labels(labels, query)
        elif country == 'br':
            labels = _br_city_labels(estado)
            suggestions = [{'label': label} for label in labels] if all_requested else _filter_location_labels(labels, query)
        else:
            labels = _foreign_city_labels(country)
            suggestions = [{'label': label} for label in labels] if all_requested else _filter_location_labels(labels, query)
    except Exception as e:
        print(f"Erro ao consultar API de localidades: {e}")
        return jsonify({'suggestions': []})

    return jsonify({'suggestions': suggestions})


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'GET':
        return render_template(
            'index.html',
            dados={},
            form_data_json='{}',
            guest_data_json='{}',
            exp_espaco_condicao_values=[],
            turnstile_site_key=TURNSTILE_SITE_KEY
        )

    dados = request.form
    arquivo_foto = request.files.get('fotoProponente')
    pdf_file = request.files.get('pdf_comprovante')
    pdf_validado_cliente = bool(pdf_file and pdf_file.filename and dados.get('pdf_validado_cliente') == 'sim')

    erros = []
    erros_envio = []

    def render_with_data(code=400):
        form_dict = dict(dados)
        exp_espaco_condicao_values = [valor for valor in dados.getlist('exp_espaco_condicao') if valor]
        guest_data = {}
        for key in dados:
            if key.startswith('convidado'):
                guest_data[key] = dados[key]
        return render_template(
            'index.html',
            dados=form_dict,
            form_data_json=json.dumps(form_dict, ensure_ascii=False),
            guest_data_json=json.dumps(guest_data, ensure_ascii=False),
            exp_espaco_condicao_values=exp_espaco_condicao_values,
            turnstile_site_key=TURNSTILE_SITE_KEY
        ), code

    # INÍCIO: Verificações de Segurança
    honeypot_value = dados.get(HONEYPOT_FIELD_NAME, '').strip()
    if honeypot_value:
        flash('Proposta enviada com sucesso!', 'success')
        return redirect(url_for('home'))

    if not validate_origin():
        flash('Origem da requisição não autorizada.', 'error')
        return render_with_data(403)

    turnstile_token = dados.get('cf-turnstile-response', '').strip()
    if TURNSTILE_SECRET_KEY:
        if not turnstile_token:
            erros.append('Complete a verificação de segurança (CAPTCHA).')
        elif not verify_turnstile(turnstile_token, request.remote_addr):
            erros.append('Falha na verificação de segurança. Recarregue a página e tente novamente.')

    if dados.get('tipoProponente', '') == 'pj' and arquivo_foto and arquivo_foto.filename:
        erro_tamanho = validar_tamanho_upload_imagem(
            dados,
            'fotoProponente_original_size',
            arquivo_foto,
            LOGO_MIN_BYTES,
            IMAGE_MAX_BYTES,
            'O logotipo'
        )
        if erro_tamanho:
            erros.append(erro_tamanho)

    for i in range(1, 6):
        prefixo = f'convidado{i}_'
        if not dados.get(f'{prefixo}nome', '').strip():
            continue
        foto_conv = request.files.get(f'{prefixo}foto')
        if not foto_conv or not foto_conv.filename:
            continue
        erro_tamanho = validar_tamanho_upload_imagem(
            dados,
            f'{prefixo}foto_original_size',
            foto_conv,
            PHOTO_MIN_BYTES,
            IMAGE_MAX_BYTES,
            f'A fotografia do integrante {i}'
        )
        if erro_tamanho:
            erros.append(erro_tamanho)

    if erros:
        for erro in erros:
            flash(erro, 'error')
        return render_with_data(400)
    # FIM: Verificações de Segurança

    salvar_uploads_temporarios(request.files)

    tipo_prop = dados.get('tipoProponente', '')
    categoria_prop = dados.get('categoria', '')

    # Validação base
    for campo in CAMPOS_OBRIGATORIOS_BASE:
        valor = dados.get(campo, '').strip()
        if not valor:
            nome_amigavel = campo.replace('_', ' ').title()
            erros.append(f'O campo "{nome_amigavel}" é obrigatório.')

    # Validação condicional do Nome do Proponente
    if tipo_prop == 'pj':
        if not dados.get('nomeInstituicao', '').strip():
            erros.append('O campo "Nome da instituição" é obrigatório.')
    else:
        if not dados.get('nomeInstituicaoPF', '').strip():
            erros.append('O campo "Nome do proponente" é obrigatório.')

    if tipo_prop == 'pj':
        cat = categoria_prop.strip()
        if not cat: erros.append('O campo "Categoria" é obrigatório.')
        cnpj = dados.get('cnpjProponente', '').strip()
        if not cnpj:
            erros.append('O CNPJ é obrigatório.')
        elif not validar_cnpj(cnpj):
            erros.append('O CNPJ informado não é válido.')
        logo_temporaria = obter_upload_temporario('fotoProponente')
        if ((not arquivo_foto or arquivo_foto.filename.strip() == '') and not logo_temporaria):
            erros.append('A logo da instituição é obrigatória para Pessoa Jurídica.')
        elif arquivo_foto and arquivo_foto.filename and not extensao_permitida(arquivo_foto.filename):
            erros.append('Formato de logo não permitido. Use: png, jpg, jpeg, webp')
    else:
        nat_prop = dados.get('nacionalidadeProponente', '').strip()
        if not nat_prop:
            erros.append('A Nacionalidade é obrigatória.')
        elif nat_prop == 'brasileiro':
            cpf_val = dados.get('cpfProponente', '').strip()
            if not cpf_val:
                erros.append('O CPF é obrigatório para brasileiros.')
            elif not validar_cpf(cpf_val):
                erros.append('O CPF informado não é válido.')
        elif nat_prop == 'estrangeiro':
            if not dados.get('passaporteProponente', '').strip():
                erros.append('O Passaporte é obrigatório para estrangeiros.')

    if dados.get('emailRepresentante') and not validar_email(dados.get('emailRepresentante')):
        erros.append('O e-mail do representante não é válido.')
    if dados.get('telefoneRepresentante') and not validar_telefone(dados.get('telefoneRepresentante')):
        erros.append('O telefone do representante não é válido.')

    acesso_atividade = dados.get('acessoAtividade')

    if acesso_atividade == 'inscricao':
        if dados.get('inscricaoResponsabilidade') != 'sim':
            erros.append('É necessário aceitar a responsabilidade sobre o processo de inscrição e a segurança dos dados conforme a LGPD.')

    tags_val = dados.get('tags', '').strip()
    suggestion = dados.get('tagSuggestion', '').strip()
    tag_count = 0
    tags_list = []
    if tags_val:
        tags_list = [t.strip() for t in tags_val.split(',') if t.strip()]
        tag_count = len(tags_list)
    if suggestion: tag_count += 1
    if tag_count < 3: erros.append('Selecione pelo menos 3 tags.')
    if tag_count > 5: erros.append('O limite máximo de tags é 5.')
    tags_permitidas = {tag for grupo_tags in GRUPOS_TAGS.values() for tag in grupo_tags}
    tags_invalidas = [tag for tag in tags_list if tag not in tags_permitidas]
    if tags_invalidas:
        erros.append('Remova tags inválidas: ' + ', '.join(tags_invalidas) + '.')

    # Limites de caracteres (Removido 'objetivoAtividade')
    for campo, limite in [('objetivoAtividade', 500), ('justificativaTematica', 700),
                        ('metodologiaAplicada', 500), ('descricaoAtividade', 700),
                        ('infoExtras', 700)]:
        if len(dados.get(campo, '')) > limite:
            erros.append(f'O campo "{campo}" excedeu o limite de {limite} caracteres.')

    if dados.get('restricaoEtaria') == 'sim':
        idade_min = dados.get('idadeMinima', '').strip()
        idade_max = dados.get('idadeMaxima', '').strip()
        if idade_min and not idade_min.isdigit():
            erros.append('A idade mínima deve ser um número válido.')
        if idade_max and not idade_max.isdigit():
            erros.append('A idade máxima deve ser um número válido.')
        if idade_min.isdigit() and int(idade_min) > 120:
            erros.append('A idade mínima não pode ser maior que 120.')
        if idade_max.isdigit() and int(idade_max) > 120:
            erros.append('A idade máxima não pode ser maior que 120.')
        if idade_min.isdigit() and idade_max.isdigit() and int(idade_min) > int(idade_max):
            erros.append('A idade mínima não pode ser maior que a máxima.')

    formato = dados.get('formatoAtividade')
    duracao = dados.get('tempoDuracao')
    exp_espaco_condicao_values = [valor for valor in dados.getlist('exp_espaco_condicao') if valor]
    mostrar_ajuda_custo = (tipo_prop == 'pf') or (tipo_prop == 'pj' and categoria_prop in ['ong', 'coletivo'])
    exp_acessibilidade = dados.get('exp_acessibilidade', '').strip()
    if not exp_acessibilidade and dados.get('exp_acess_recursos', '').strip():
        exp_acessibilidade = 'sim'

    duracoes_por_formato = {
        'debate': {'1h'},
        'roda_de_conversa': {'1h'},
        'oficina': {'2h', '2h30', '3h', '3h30', '4h'},
        'experiencia': {'1h', '2h', '3h', '4h', 'dia_todo'},
    }
    acessos_por_formato = {
        'debate': {'ordem_chegada'},
        'roda_de_conversa': {'ordem_chegada'},
        'oficina': {'ordem_chegada', 'inscricao'},
        'experiencia': {'ordem_chegada', 'livre', 'inscricao'},
    }

    if formato in duracoes_por_formato and duracao and duracao not in duracoes_por_formato[formato]:
        erros.append('A duração selecionada não é válida para o formato escolhido.')
    if formato in acessos_por_formato and acesso_atividade and acesso_atividade not in acessos_por_formato[formato]:
        erros.append('O acesso selecionado não é válido para o formato escolhido.')
    if dados.get('publicoAlvo') == 'outros':
        publico_alvo_outros = dados.get('publicoAlvoOutros', '').strip()
        if not publico_alvo_outros:
            erros.append('Descreva o público-alvo ao selecionar "Outros".')
        elif len(publico_alvo_outros) > 120:
            erros.append('Público-alvo (Outros): máximo 120 caracteres.')

    if formato == 'oficina':
        if not dados.get('oficina_qtd_publico'): erros.append('Selecione a quantidade máxima de público.')
        if not dados.get('oficina_lab'): erros.append('Informe sobre laboratório.')
        if dados.get('oficina_lab') == 'sim':
            if not dados.get('oficina_pc_specs'): erros.append('Descreva as configurações mínimas dos PCs.')
            if len(dados.get('oficina_pc_specs', '')) > 200: erros.append('Configurações dos PCs: máximo 200 caracteres.')
            if not dados.get('oficina_soft_req'): erros.append('Informe sobre software.')
            elif dados.get('oficina_soft_req') == 'sim' and not dados.get('oficina_soft_desc'): erros.append('Descreva o software.')
            if len(dados.get('oficina_soft_desc', '')) > 200: erros.append('Descrição do software: máximo 200 caracteres.')
        if not dados.get('oficina_mobiliario'): erros.append('Selecione o mobiliário necessário.')
        if mostrar_ajuda_custo:
            if not dados.get('oficina_material_ajuda'): erros.append('Informe sobre recurso financeiro para aquisição de materiais de apoio.')
            if dados.get('oficina_material_ajuda') in ('sim', 'indispensavel'):
                has_items = False
                for key in dados:
                    if key.startswith('mat_item_') and dados[key].strip():
                        has_items = True
                        break
                if not has_items: erros.append('Liste pelo menos um material com previsão de custo.')
                if not dados.get('oficina_justificativa_materiais', '').strip():
                    erros.append('A justificativa dos materiais é obrigatória quando há ajuda de custo.')
                elif len(dados.get('oficina_justificativa_materiais', '')) > 500:
                    erros.append('Justificativa dos materiais: máximo 500 caracteres.')

    # ──────────────────────────────────────────────────────────
    # VALIDAÇÃO EXCLUSIVA PARA FORMATO EXPERIÊNCIA (ATUALIZADO)
    # ──────────────────────────────────────────────────────────
    elif formato == 'experiencia':
        # 1. Tipologias
        tipologias_exp = ['exp_tipologia_tecnologica', 'exp_tipologia_interativa', 'exp_tipologia_imersiva', 'exp_tipologia_demonstrativa', 'exp_tipologia_hibrida']
        if not any(dados.get(t) for t in tipologias_exp):
            erros.append('Selecione pelo menos uma Tipologia da experiência.')

        # 2. Dias
        if not dados.get('exp_dias'): erros.append('Informe a quantidade de dias (Experiência).')

        # 3. Espaço
        if not dados.get('exp_espaco_ambiente'):
            erros.append('O campo "Ambiente (Experiência)" é obrigatório.')
        if not exp_espaco_condicao_values:
            erros.append('O campo "Condição do ambiente (Experiência)" é obrigatório.')
        
        # VALIDAÇÃO DO CAMPO "OUTROS" DA CONDIÇÃO DO AMBIENTE
        if 'outros' in exp_espaco_condicao_values and not dados.get('exp_espaco_condicao_outros', '').strip():
            erros.append('Descreva a condição do ambiente ao selecionar "Outros".')

        # 4. Acessibilidade e Restrição
        if exp_acessibilidade not in {'sim', 'nao'}:
            erros.append('Informe se existem ações de acessibilidade na experiência.')
        elif exp_acessibilidade == 'sim':
            if not dados.get('exp_acess_recursos', '').strip():
                erros.append('O campo "Quais ações?" é obrigatório ao selecionar acessibilidade.')
            elif len(dados.get('exp_acess_recursos', '')) > 200:
                erros.append('Ações de acessibilidade: máximo 200 caracteres.')

        # 5. Operação
        campos_exp_op = {
            'exp_oper_funcionamento': 'Funcionamento (Experiência)',
            'exp_oper_permanencia': 'Permanência média do usuário (Experiência)',
            'exp_oper_qtd_simultanea': 'Quantidade simultânea de usuários (Experiência)',
            'exp_oper_fluxo_hora': 'Fluxo de usuários estimado por hora (Experiência)',
            'exp_oper_qtd_equipe': 'Quantidade de equipe operacional (Experiência)'
        }
        for campo, nome_amigavel in campos_exp_op.items():
            if not dados.get(campo, '').strip(): erros.append(f'O campo "{nome_amigavel}" é obrigatório.')

        # 6. Infra - Ponto de Energia
        if not dados.get('exp_infra_energia'): erros.append('Informe sobre Ponto de energia.')
        if dados.get('exp_infra_energia') == 'sim':
            if not dados.get('exp_infra_pontos_energia_qtd', '').strip(): erros.append('Informe a Quantidade de Pontos de energia.')
            if not dados.get('exp_infra_energia_equip', '').strip(): erros.append('Informe os Equipamentos/finalidade dos Pontos de energia.')
            if not dados.get('exp_infra_energia_spec', '').strip(): erros.append('Informe a Especificação dos Pontos de energia.')
            if not dados.get('exp_infra_energia_carga', '').strip(): erros.append('Informe a Capacidade/Carga dos Pontos de energia.')

        # 7. Infra - Mobiliário
        if not dados.get('exp_infra_mobiliario_opcao'): erros.append('Informe sobre Mobiliário próprio.')
        if dados.get('exp_infra_mobiliario_opcao') == 'sim' and not dados.get('exp_infra_mobiliario_desc', '').strip():
            erros.append('Descreva o mobiliário próprio.')

        # 8. Infra - Equipamentos próprios
        if not dados.get('exp_infra_equip_proprios_opcao'): erros.append('Informe sobre Equipamentos próprios.')
        if dados.get('exp_infra_equip_proprios_opcao') == 'sim':
            has_exp_equip = any(key.startswith('exp_equip_item_') and dados[key].strip() for key in dados)
            if not has_exp_equip: erros.append('Liste pelo menos um equipamento próprio na tabela.')

        # 9. Infra - Materiais de Apoio
        if mostrar_ajuda_custo:
            if not dados.get('exp_material_ajuda'): erros.append('Informe sobre recurso financeiro para aquisição de materiais de apoio.')
            if dados.get('exp_material_ajuda') in ('sim', 'indispensavel'):
                has_exp_mat = any(key.startswith('exp_mat_item_') and dados[key].strip() for key in dados)
                if not has_exp_mat: erros.append('Liste pelo menos um material de apoio na tabela.')
                if not dados.get('exp_justificativa_materiais', '').strip(): erros.append('A justificativa dos materiais de apoio é obrigatória.')

        # 10. Montagem e Equipe
        if not dados.get('exp_montagem_desmontagem_desc', '').strip(): erros.append('O campo "Montagem e desmontagem" é obrigatório.')
        if not dados.get('exp_infra_qtd_equipe', '').strip(): erros.append('O campo "Quantidade da equipe operacional do proponente" é obrigatório.')

        # 11. Anexos
        croqui_file = request.files.get('exp_anexo_croqui')
        if not croqui_file or croqui_file.filename.strip() == '':
            erros.append('O anexo "Croqui esquemático" é obrigatório.')
        elif croqui_file.filename and not croqui_file.filename.lower().endswith('.pdf'):
            erros.append('O Croqui esquemático deve ser um arquivo PDF.')

        imagens_file = request.files.get('exp_anexo_imagens')
        if not imagens_file or imagens_file.filename.strip() == '':
            erros.append('O anexo "Imagens de referência" é obrigatório.')
        elif imagens_file.filename and not extensao_permitida(imagens_file.filename):
            erros.append('As Imagens de referência devem ser JPG ou PNG.')
    # ──────────────────────────────────────────────────────────
    # FIM: VALIDAÇÃO EXCLUSIVA PARA FORMATO EXPERIÊNCIA
    # ──────────────────────────────────────────────────────────

    if len(dados.get('recursosAcessibilidade', '')) > 200:
        erros.append('Recursos de acessibilidade: máximo 200 caracteres.')

    if dados.get('infra_outros') == 'sim':
        has_infra_items = False
        for key in dados:
            if key.startswith('infra_item_') and dados[key].strip():
                has_infra_items = True
                break
        if not has_infra_items:
            erros.append('Liste pelo menos um recurso de infraestrutura em "Outros".')

    if mostrar_ajuda_custo:
        if not dados.get('ajuda_custo'):
            erros.append('Informe se precisa de recurso financeiro para ajuda de custo.')
        elif dados.get('ajuda_custo') in ('sim', 'indispensavel'):
            has_ac_items = False
            for key in dados:
                if key.startswith('ac_item_') and dados[key].strip():
                    has_ac_items = True
                    break
            if not has_ac_items:
                erros.append('Liste pelo menos um item de ajuda de custo.')
            if not dados.get('justificativa_ajuda_custo', '').strip():
                erros.append('A justificativa da ajuda de custo é obrigatória.')
            elif len(dados.get('justificativa_ajuda_custo', '')) > 500:
                erros.append('Justificativa da ajuda de custo: máximo 500 caracteres.')

    convidados = []
    tem_convidado = False
    for i in range(1, 6):
        prefixo = f'convidado{i}_'
        nome = dados.get(f'{prefixo}nome', '').strip()
        if nome:
            tem_convidado = True
            foto_conv = request.files.get(f'{prefixo}foto')
            foto_conv_base64 = None
            foto_temporaria = obter_upload_temporario(f'convidado{i}_foto')
            if ((not foto_conv or foto_conv.filename.strip() == '') and not foto_temporaria):
                erros.append(f'A foto do integrante {i} ({nome}) é obrigatória.')
            elif foto_conv and foto_conv.filename and not extensao_permitida(foto_conv.filename):
                erros.append(f'Formato de foto do integrante {i} não permitido.')
            else:
                if foto_conv and foto_conv.filename:
                    foto_conv_base64 = converter_foto_base64(foto_conv)
                else:
                    foto_conv_base64 = obter_upload_temporario(f'convidado{i}_foto')
            email = dados.get(f'{prefixo}email', '').strip()
            if not email:
                erros.append(f'E-mail do integrante {i} é obrigatório.')
            elif not validar_email(email):
                erros.append(f'O e-mail do integrante {i} ({nome}) é inválido.')
            papel = dados.get(f'{prefixo}papel', '').strip()
            if not papel: erros.append(f'Selecione o papel do integrante {i}.')
            papeis_por_formato = {
                'debate': {'convidado', 'mediador'},
                'roda_de_conversa': {'ministrante', 'mediador'},
                'oficina': {'oficineiro'},
                'experiencia': {'facilitador', 'monitor'}
            }
            if papel and formato in papeis_por_formato and papel not in papeis_por_formato[formato]:
                erros.append(f'O papel selecionado para o integrante {i} não é válido para este formato de atividade.')
            nacionalidade = dados.get(f'{prefixo}nacionalidade', '').strip()
            if not nacionalidade: erros.append(f'Nacionalidade do integrante {i} é obrigatória.')
            telefone = dados.get(f'{prefixo}telefone', '').strip()
            if not telefone: erros.append(f'Telefone do integrante {i} é obrigatório.')
            elif not validar_telefone(telefone):
                erros.append(f'O telefone do integrante {i} ({nome}) não é válido.')
            idade = dados.get(f'{prefixo}idade', '').strip()
            estado = dados.get(f'{prefixo}estado', '').strip()
            cidade_c = dados.get(f'{prefixo}cidade', '').strip()
            bairro_c = dados.get(f'{prefixo}bairro', '').strip()
            pais_origem = dados.get(f'{prefixo}pais_origem', '').strip()
            estado_origem = dados.get(f'{prefixo}estado_origem', '').strip()
            cidade_origem = dados.get(f'{prefixo}cidade_origem', '').strip()
            if nacionalidade == 'brasileiro' and (not estado or not cidade_c):
                erros.append(f'Estado e cidade do integrante {i} são obrigatórios.')
            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip(): erros.append(f'Passaporte do integrante estrangeiro {i} é obrigatório.')
                if not pais_origem: erros.append(f'País de origem do integrante {i} é obrigatório.')
                if not estado_origem: erros.append(f'Estado de origem do integrante {i} é obrigatório.')
            cpf_conv = dados.get(f'{prefixo}cpf', '').strip()
            if nacionalidade == 'brasileiro':
                if not cpf_conv:
                    erros.append(f'O CPF do integrante {i} ({nome}) é obrigatório.')
                elif not validar_cpf(cpf_conv):
                    erros.append(f'O CPF do integrante {i} ({nome}) não é válido.')
            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip():
                    erros.append(f'O Passaporte/Documento do integrante estrangeiro {i} ({nome}) é obrigatório.')
            cargo_profissao = dados.get(f'{prefixo}cargo_profissao', '').strip()
            if not cargo_profissao: erros.append(f'Cargo/Profissão exercida do integrante {i} é obrigatório.')
            inst = dados.get(f'{prefixo}instituicao', '').strip()
            tipo_inst = dados.get(f'{prefixo}tipo_instituicao', '').strip()
            if not tipo_inst: erros.append(f'Tipo de instituição do integrante {i} é obrigatório.')
            minibio = dados.get(f'{prefixo}minibio', '').strip()
            if not minibio: erros.append(f'Minibio del integrante {i} é obrigatória.')
            raca = dados.get(f'{prefixo}raca', '').strip()
            genero = dados.get(f'{prefixo}genero', '').strip()
            if dados.get(f'{prefixo}acessibilidade') == 'sim':
                if not dados.get(f'{prefixo}acessibilidade_desc', '').strip(): erros.append(f'Descreva os recursos de acessibilidade do integrante {i}.')
            convidados.append({
                'nome': nome, 'email': email, 'nacionalidade': nacionalidade,
                'cpf': criptografar_documento(cpf_conv, somente_digitos=True) if cpf_conv else None,
                'passaporte': criptografar_documento(dados.get(f'{prefixo}passaporte')) if dados.get(f'{prefixo}passaporte') else None,
                'telefone': telefone, 'cargo_profissao': cargo_profissao,
                'instituicao': inst, 'tipo_instituicao': tipo_inst,
                'minibio': minibio, 'papel': papel, 'raca': raca, 'genero': genero,
                'idade': idade,
                'acessibilidade': dados.get(f'{prefixo}acessibilidade') == 'sim',
                'acessibilidade_desc': dados.get(f'{prefixo}acessibilidade_desc'),
                'social_linkedin': dados.get(f'{prefixo}social_linkedin'),
                'social_instagram': dados.get(f'{prefixo}social_instagram'),
                'cidade': cidade_c, 'estado': estado, 'bairro': bairro_c,
                'pais_origem': pais_origem,
                'estado_origem': estado_origem,
                'cidade_origem': cidade_origem,
                'foto_base64': foto_conv_base64
            })

    limites_convidados_por_formato = {
        'oficina': {'nome': 'Oficina', 'min': 1, 'max': 4},
        'roda_de_conversa': {'nome': 'Roda de conversa', 'min': 2, 'max': 3},
        'debate': {'nome': 'Debate', 'min': 2, 'max': 5},
        'experiencia': {'nome': 'Experiência', 'min': 1, 'max': 5},
    }
    limites_convidados = limites_convidados_por_formato.get(
        formato,
        {'nome': 'este formato', 'min': 1, 'max': 5}
    )
    min_convidados = limites_convidados['min']
    max_convidados = limites_convidados['max']
    nome_formato = limites_convidados['nome']
    if not tem_convidado:
        if min_convidados > 1:
            erros.append(f'Para {nome_formato}, é necessário no mínimo {min_convidados} integrantes.')
        else:
            erros.append('Adicione pelo menos 1 integrante.')
    elif len(convidados) < min_convidados:
        erros.append(f'Para {nome_formato}, é necessário no mínimo {min_convidados} integrantes. Você adicionou apenas {len(convidados)}.')
    elif len(convidados) > max_convidados:
        erros.append(f'Para {nome_formato}, é permitido no máximo {max_convidados} integrantes.')

    if dados.get('aceite_termos') != 'sim' or dados.get('direitos_autorais') != 'sim' or dados.get('consentimento_lgpd') != 'sim':
        erros_envio.append('Você deve aceitar os Termos, Direitos Autorais e LGPD para enviar.')

    if erros_envio:
        for erro in erros_envio:
            flash(erro, 'error')
        return render_with_data(400)

    if erros and not pdf_validado_cliente:
        for erro in erros:
            flash(erro, 'error')
        return render_with_data(400)
    if erros and pdf_validado_cliente:
        print('Aviso: validacoes de formulario ignoradas apos PDF validado no cliente: ' + ' | '.join(erros))

    foto_proponente_base64 = None
    if tipo_prop == 'pj':
        if arquivo_foto and arquivo_foto.filename:
            foto_proponente_base64 = converter_foto_base64(arquivo_foto)
        else:
            foto_proponente_base64 = obter_upload_temporario('fotoProponente')

    nat_prop_val = dados.get('nacionalidadeProponente', '') if tipo_prop == 'pf' else ''

    materiais = []
    for key in sorted(dados.keys()):
        if key.startswith('mat_item_'):
            idx = key.split('_')[-1]
            item = dados.get(f'mat_item_{idx}', '').strip()
            if item:
                materiais.append({
                    'item': item,
                    'quantidade': dados.get(f'mat_qtd_{idx}', '1'),
                    'valor_unitario': dados.get(f'mat_valor_{idx}', '0'),
                })

    infra_outros_items = []
    if dados.get('infra_outros') == 'sim':
        for key in sorted(dados.keys()):
            if key.startswith('infra_item_'):
                idx = key.split('_')[-1]
                item = dados.get(f'infra_item_{idx}', '').strip()
                if item:
                    infra_outros_items.append({
                        'recurso': item,
                        'quantidade': dados.get(f'infra_qtd_{idx}', '1'),
                        'observacoes': dados.get(f'infra_obs_{idx}', '').strip(),
                    })

    ajuda_custo_items = []
    if mostrar_ajuda_custo and dados.get('ajuda_custo') in ('sim', 'indispensavel'):
        for key in sorted(dados.keys()):
            if key.startswith('ac_item_'):
                idx = key.split('_')[-1]
                item = dados.get(f'ac_item_{idx}', '').strip()
                if item:
                    ajuda_custo_items.append({
                        'item': item,
                        'quantidade': dados.get(f'ac_qtd_{idx}', '1'),
                        'valor_unitario': dados.get(f'ac_valor_{idx}', '0'),
                    })

    infra_recursos = []
    if dados.get('infra_projecao') == 'sim': infra_recursos.append('Recursos básicos de projeção')
    if dados.get('infra_som') == 'sim': infra_recursos.append('Sistema básico de som')
    if dados.get('infra_microfones') == 'sim': infra_recursos.append('Microfones')
    if dados.get('infra_internet') == 'sim': infra_recursos.append('Internet')
    if dados.get('infra_outros') == 'sim':
        if infra_outros_items:
            infra_recursos.append('Outros: ' + '; '.join(i['recurso'] for i in infra_outros_items))
        else:
            infra_recursos.append('Outros')

    # ──────────────────────────────────────────────────────────
    # PROCESSAMENTO DE DADOS DE EXPERIÊNCIA (ATUALIZADO)
    # ──────────────────────────────────────────────────────────
    tipologias_selecionadas_exp = []
    exp_equip_items = []
    exp_materiais = []
    anexos_exp_base64 = {}

    if formato == 'experiencia':
        # 1. Tipologias
        map_tipologias = {
            'exp_tipologia_tecnologica': 'Tecnológica',
            'exp_tipologia_interativa': 'Interativa',
            'exp_tipologia_imersiva': 'Imersiva',
            'exp_tipologia_demonstrativa': 'Demonstrativa',
            'exp_tipologia_hibrida': 'Híbrida'
        }
        for key, label in map_tipologias.items():
            if dados.get(key) == 'sim':
                tipologias_selecionadas_exp.append(label)

        # 2. Tabela Dinâmica de Equipamentos Próprios
        if dados.get('exp_infra_equip_proprios_opcao') == 'sim':
            for key in sorted(dados.keys()):
                if key.startswith('exp_equip_item_'):
                    idx = key.split('_')[-1]
                    item = dados.get(f'exp_equip_item_{idx}', '').strip()
                    if item:
                        exp_equip_items.append({
                            'equipamento': item,
                            'quantidade': dados.get(f'exp_equip_qtd_{idx}', '1'),
                            'observacoes': dados.get(f'exp_equip_obs_{idx}', '').strip()
                        })

        # 3. Tabela Dinâmica de Materiais de Apoio
        if mostrar_ajuda_custo and dados.get('exp_material_ajuda') in ('sim', 'indispensavel'):
            for key in sorted(dados.keys()):
                if key.startswith('exp_mat_item_'):
                    idx = key.split('_')[-1]
                    item = dados.get(f'exp_mat_item_{idx}', '').strip()
                    if item:
                        exp_materiais.append({
                            'item': item,
                            'quantidade': dados.get(f'exp_mat_qtd_{idx}', '1'),
                            'valor_unitario': dados.get(f'exp_mat_valor_{idx}', '0'),
                        })

        # 4. Anexos
        croqui_file = request.files.get('exp_anexo_croqui')
        if croqui_file and croqui_file.filename:
            b64 = converter_arquivo_base64(croqui_file, permitido_ext=['pdf'])
            if b64: anexos_exp_base64['exp_anexo_croqui'] = b64

        imagens_file = request.files.get('exp_anexo_imagens')
        if imagens_file and imagens_file.filename:
            b64 = converter_arquivo_base64(imagens_file, permitido_ext=['png', 'jpg', 'jpeg'])
            if b64: anexos_exp_base64['exp_anexo_imagens'] = b64
            
    # ──────────────────────────────────────────────────────────
    # FIM: PROCESSAMENTO DE DADOS DE EXPERIÊNCIA
    # ──────────────────────────────────────────────────────────

    # Captura condicional do Nome
    nome_proponente_val = dados.get('nomeInstituicao') if tipo_prop == 'pj' else dados.get('nomeInstituicaoPF')
    ids_avaliadores, avaliadores_sugeridos = selecionar_avaliadores(dados)

    inscricao = {
        'ID_avaliador_1': ids_avaliadores[0],
        'ID_avaliador_2': ids_avaliadores[1],
        'ID_avaliador_3': ids_avaliadores[2],
        'avaliadores_sugeridos': avaliadores_sugeridos,
        'proponente': {
            'tipo': tipo_prop,
            'nome_instituicao': nome_proponente_val,
            'categoria': categoria_prop if tipo_prop == 'pj' else None,
            'nacionalidade': nat_prop_val,
            'cpf': criptografar_documento(dados.get('cpfProponente'), somente_digitos=True) if tipo_prop == 'pf' and dados.get('cpfProponente') else None,
            'passaporte': criptografar_documento(dados.get('passaporteProponente')) if tipo_prop == 'pf' and dados.get('passaporteProponente') else None,
            'cnpj': dados.get('cnpjProponente') if tipo_prop == 'pj' else None,
            'logo_marca_base64': foto_proponente_base64
        },
        'representante': {
            'nome': dados.get('nomeRepresentante'),
            'telefone': dados.get('telefoneRepresentante'),
            'email': dados.get('emailRepresentante'),
        },
        'atividade': {
            'titulo': dados.get('tituloAtividade'),
            'formato': dados.get('formatoAtividade'),
            'duracao_prevista': dados.get('tempoDuracao'),
            'acesso': acesso_atividade,
            'inscricao_responsabilidade': dados.get('inscricaoResponsabilidade') == 'sim',
            'aceite_termos': dados.get('aceite_termos') == 'sim',
            'direitos_autorais': dados.get('direitos_autorais') == 'sim',
            'consentimento_lgpd': dados.get('consentimento_lgpd') == 'sim',
            'objetivo': dados.get('objetivoAtividade'),
            'justificativa': dados.get('justificativaTematica'),
            'metodologia': dados.get('metodologiaAplicada'),
            'descricao': dados.get('descricaoAtividade'),
            'eixo': dados.get('eixo'),
            'publico_alvo': dados.get('publicoAlvo'),
            'publico_alvo_outros': dados.get('publicoAlvoOutros') if dados.get('publicoAlvo') == 'outros' else None,
            'tags': dados.get('tags'),
            'tag_suggestion': dados.get('tagSuggestion'),
            'restricao_etaria': dados.get('restricaoEtaria'),
            'idade_minima': dados.get('idadeMinima'),
            'idade_maxima': dados.get('idadeMaxima'),
            'recursos_acessibilidade': dados.get('recursosAcessibilidade'),
            'infra_recursos': infra_recursos,
            'infra_projecao': dados.get('infra_projecao') == 'sim',
            'infra_som': dados.get('infra_som') == 'sim',
            'infra_microfones': dados.get('infra_microfones') == 'sim',
            'infra_internet': dados.get('infra_internet') == 'sim',
            'infra_outros': dados.get('infra_outros') == 'sim',
            'infra_outros_items': infra_outros_items,
            'ajuda_custo': dados.get('ajuda_custo') if mostrar_ajuda_custo else None,
            'ajuda_custo_items': ajuda_custo_items,
            'justificativa_ajuda_custo': dados.get('justificativa_ajuda_custo') if mostrar_ajuda_custo else None,
            'observacoes': dados.get('infoExtras'),
            'oficina': {
                'qtd_publico': dados.get('oficina_qtd_publico'),
                'internet': dados.get('infra_internet') == 'sim',
                'lab': dados.get('oficina_lab'),
                'pc_specs': dados.get('oficina_pc_specs'),
                'software_req': dados.get('oficina_soft_req'),
                'software_desc': dados.get('oficina_soft_desc'),
                'material_ajuda': dados.get('oficina_material_ajuda') if mostrar_ajuda_custo else None,
                'materiais': materiais if mostrar_ajuda_custo else [],
                'justificativa_materiais': dados.get('oficina_justificativa_materiais') if mostrar_ajuda_custo else None,
                'mobiliario': dados.get('oficina_mobiliario'),
            } if formato == 'oficina' else None,
            # ──────────────────────────────────────────────────────────
            # PAYLOAD DE EXPERIÊNCIA NO DICIONÁRIO FINAL (ATUALIZADO)
            # ──────────────────────────────────────────────────────────
            'experiencia': {
                'tipologias': tipologias_selecionadas_exp,
                'dias': dados.get('exp_dias'),
                'espaco_ambiente': dados.get('exp_espaco_ambiente'),
                'espaco_condicao': exp_espaco_condicao_values,
                'espaco_condicao_outros': dados.get('exp_espaco_condicao_outros', '').strip() if 'outros' in exp_espaco_condicao_values else None,
                'acess_recursos': dados.get('exp_acess_recursos'),
                'acess_restricoes': dados.get('exp_acess_restricoes'),
                'oper_funcionamento': dados.get('exp_oper_funcionamento'),
                'oper_permanencia': dados.get('exp_oper_permanencia'),
                'oper_qtd_simultanea': dados.get('exp_oper_qtd_simultanea'),
                'oper_fluxo_hora': dados.get('exp_oper_fluxo_hora'),
                'oper_qtd_equipe': dados.get('exp_oper_qtd_equipe'),
                'infra_energia': dados.get('exp_infra_energia'),
                'infra_pontos_energia_qtd': dados.get('exp_infra_pontos_energia_qtd') if dados.get('exp_infra_energia') == 'sim' else None,
                'infra_energia_equip': dados.get('exp_infra_energia_equip') if dados.get('exp_infra_energia') == 'sim' else None,
                'infra_energia_spec': dados.get('exp_infra_energia_spec') if dados.get('exp_infra_energia') == 'sim' else None,
                'infra_energia_carga': dados.get('exp_infra_energia_carga') if dados.get('exp_infra_energia') == 'sim' else None,
                'infra_mobiliario_opcao': dados.get('exp_infra_mobiliario_opcao'),
                'infra_mobiliario_desc': dados.get('exp_infra_mobiliario_desc') if dados.get('exp_infra_mobiliario_opcao') == 'sim' else None,
                'infra_equip_proprios_opcao': dados.get('exp_infra_equip_proprios_opcao'),
                'infra_equip_proprios_items': exp_equip_items,
                'material_ajuda': dados.get('exp_material_ajuda') if mostrar_ajuda_custo else None,
                'materiais': exp_materiais if mostrar_ajuda_custo else [],
                'justificativa_materiais': dados.get('exp_justificativa_materiais') if mostrar_ajuda_custo else None,
                'montagem_desmontagem_desc': dados.get('exp_montagem_desmontagem_desc'),
                'infra_qtd_equipe': dados.get('exp_infra_qtd_equipe'),
                'anexo_video': dados.get('exp_anexo_video'),
                'anexos_base64': anexos_exp_base64
            } if formato == 'experiencia' else None
            # ──────────────────────────────────────────────────────────
            # FIM: PAYLOAD DE EXPERIÊNCIA
            # ──────────────────────────────────────────────────────────
        },
        'convidados': convidados
    }

    # ──────────────────────────────────────────────
    # INÍCIO: Persistência e Fila
    # ──────────────────────────────────────────────
    supabase_id = None
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        supabase_id = save_to_supabase(inscricao)
        if supabase_id:
            inscricao['supabase_id'] = supabase_id
        else:
            print("⚠️ Falha ao salvar no Supabase, mas continuando com a fila...")

    if redis_client:
        try:
            payload_json = json.dumps(inscricao, ensure_ascii=False, default=str)
            redis_client.lpush('fila_inscricoes', payload_json)
            print(f"✅ Inscrição enviada para a fila Upstash: {inscricao['proponente']['nome_instituicao']}")
            limpar_uploads_temporarios()
        except Exception as e:
            print(f"❌ Erro ao enviar para o Upstash: {e}")
            flash('Erro interno ao processar a inscrição. Tente novamente mais tarde.', 'error')
            return render_with_data(500)
    else:
        print("⚠️ Upstash não configurado. Dados não foram enfileirados.")
        if not supabase_id:
            flash('Sistema de persistência não configurado. Contate o suporte.', 'error')
            return render_with_data(500)
        flash('Proposta registrada! Processamento pendente.', 'success')

    # ──────────────────────────────────────────────
    # INÍCIO: Envio do Email com PDF
    # ──────────────────────────────────────────────
    email_representante = dados.get('emailRepresentante')
    nome_atividade = dados.get('tituloAtividade')
    # Usa o nome correto do proponente baseado no tipo
    nome_proponente = nome_proponente_val or ''

    if pdf_file and email_representante:
        try:
            email_enviado = enviar_email_com_anexo(
                destinatario=email_representante,
                nome_atividade=nome_atividade,
                nome_proponente=nome_proponente,
                pdf_file=pdf_file
            )
            if email_enviado:
                print("📧 Comprovante PDF enviado por email com sucesso.")
            else:
                print("⚠️ Email não foi enviado, mas a inscrição foi salva com sucesso.")
        except Exception as e:
            print(f"⚠️ Erro crítico ao enviar email (mas dados salvos): {e}")
    else:
        if not pdf_file:
            print("⚠️ PDF não foi recebido do frontend. Email não será enviado.")
        if not email_representante:
            print("⚠️ Email do representante não informado. Email não será enviado.")
    # ──────────────────────────────────────────────
    # FIM: Envio do Email
    # ──────────────────────────────────────────────

    flash('Proposta enviada com sucesso!', 'success')
    return redirect(url_for('home'))


app = app
