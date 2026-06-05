from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import re
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
from urllib.parse import urlparse
import copy
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# ──────────────────────────────────────────────
# INÍCIO: Configurações Anti-Spam / Segurança
# ──────────────────────────────────────────────
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
ALLOWED_DOMAINS = [d.strip() for d in os.environ.get('ALLOWED_DOMAINS', '').split(',') if d.strip()]

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

CAMPOS_OBRIGATORIOS_BASE = [
    'tipoProponente', 
    'nomeRepresentante', 'telefoneRepresentante', 'emailRepresentante',
    'tituloAtividade', 'formatoAtividade', 'tempoDuracao',
    'objetivoAtividade', 'justificativaTematica', 'metodologiaAplicada',
    'descricaoAtividade', 'eixo', 'publicoAlvo',
    'acessoAtividade'
]

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
            "payload": clean_payload
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


def validar_email(email):
    padrao = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(padrao, email) is not None


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


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'GET':
        return render_template('index.html', dados={}, guest_data_json='{}', turnstile_site_key=TURNSTILE_SITE_KEY)

    dados = request.form
    arquivo_foto = request.files.get('fotoProponente')
    pdf_file = request.files.get('pdf_comprovante')

    salvar_uploads_temporarios(request.files)
    erros = []

    def render_with_data(code=400):
        form_dict = dict(dados)
        guest_data = {}
        for key in dados:
            if key.startswith('convidado'):
                guest_data[key] = dados[key]
        return render_template('index.html', dados=form_dict, guest_data_json=json.dumps(guest_data, ensure_ascii=False),
                               turnstile_site_key=TURNSTILE_SITE_KEY), code

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

    if erros:
        for erro in erros:
            flash(erro, 'error')
        return render_with_data(400)
    # FIM: Verificações de Segurança

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

    if dados.get('acessoAtividade') == 'inscricao':
        if dados.get('inscricaoResponsabilidade') != 'sim':
            erros.append('É necessário aceitar a responsabilidade sobre o processo de inscrição e a segurança dos dados conforme a LGPD.')

    tags_val = dados.get('tags', '').strip()
    suggestion = dados.get('tagSuggestion', '').strip()
    tag_count = 0
    if tags_val:
        tags_list = [t.strip() for t in tags_val.split(',') if t.strip()]
        tag_count = len(tags_list)
    if suggestion: tag_count += 1
    if tag_count < 3: erros.append('Selecione pelo menos 3 tags.')
    if tag_count > 5: erros.append('O limite máximo de tags é 5.')

    # Limites de caracteres (Removido 'objetivoAtividade')
    for campo, limite in [('objetivoAtividade', 500), ('justificativaTematica', 700),
                        ('metodologiaAplicada', 500), ('descricaoAtividade', 700),
                        ('infoExtras', 700)]:
        if len(dados.get(campo, '')) > limite:
            erros.append(f'O campo "{campo}" excedeu o limite de {limite} caracteres.')

    if dados.get('restricaoEtaria') == 'sim':
        idade_min = dados.get('idadeMinima', '').strip()
        idade_max = dados.get('idadeMaxima', '').strip()
        if not idade_min or not idade_max:
            erros.append('Preencha a idade mínima e máxima.')
        elif int(idade_min) > int(idade_max):
            erros.append('A idade mínima não pode ser maior que a máxima.')

    formato = dados.get('formatoAtividade')
    mostrar_ajuda_custo = (tipo_prop == 'pf') or (tipo_prop == 'pj' and categoria_prop in ['ong', 'coletivo'])

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
            if not dados.get('oficina_material_ajuda'): erros.append('Informe sobre ajuda de custo com material.')
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
        campos_exp_espaco = {
            'exp_espaco_ambiente': 'Ambiente (Experiência)',
            'exp_espaco_condicao': 'Condição do ambiente (Experiência)'
        }
        for campo, nome_amigavel in campos_exp_espaco.items():
            if not dados.get(campo): erros.append(f'O campo "{nome_amigavel}" é obrigatório.')

        # 4. Acessibilidade e Restrição
        if not dados.get('exp_acess_recursos', '').strip(): erros.append('O campo "Ações de acessibilidade" é obrigatório.')

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

        # 9. Infra - Equipamentos solicitados
        if not dados.get('exp_infra_equip_solicitados', '').strip(): erros.append('Informe os Equipamentos solicitados ao festival.')

        # 10. Infra - Materiais de Apoio
        if not dados.get('exp_material_ajuda'): erros.append('Informe sobre recurso financeiro para material de apoio.')
        if dados.get('exp_material_ajuda') in ('sim', 'indispensavel'):
            has_exp_mat = any(key.startswith('exp_mat_item_') and dados[key].strip() for key in dados)
            if not has_exp_mat: erros.append('Liste pelo menos um material de apoio na tabela.')
            if not dados.get('exp_justificativa_materiais', '').strip(): erros.append('A justificativa dos materiais de apoio é obrigatória.')

        # 11. Montagem e Equipe
        if not dados.get('exp_montagem_desmontagem_desc', '').strip(): erros.append('O campo "Montagem e desmontagem" é obrigatório.')
        if not dados.get('exp_infra_qtd_equipe', '').strip(): erros.append('O campo "Quantidade da equipe operacional do proponente" é obrigatório.')

        # 12. Anexos
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
            nacionalidade = dados.get(f'{prefixo}nacionalidade', '').strip()
            if not nacionalidade: erros.append(f'Nacionalidade do integrante {i} é obrigatória.')
            telefone = dados.get(f'{prefixo}telefone', '').strip()
            if not telefone: erros.append(f'Telefone do integrante {i} é obrigatório.')
            idade = dados.get(f'{prefixo}idade', '').strip()
            estado = dados.get(f'{prefixo}estado', '').strip()
            cidade_c = dados.get(f'{prefixo}cidade', '').strip()
            bairro_c = dados.get(f'{prefixo}bairro', '').strip()
            if nacionalidade == 'brasileiro' and (not estado or not cidade_c):
                erros.append(f'Estado e cidade do integrante {i} são obrigatórios.')
            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip(): erros.append(f'Passaporte do integrante estrangeiro {i} é obrigatório.')
                if not dados.get(f'{prefixo}pais_origem', '').strip(): erros.append(f'País de origem do integrante {i} é obrigatório.')
            cpf_conv = dados.get(f'{prefixo}cpf', '').strip()
            if nacionalidade == 'brasileiro':
                if not cpf_conv:
                    erros.append(f'O CPF do integrante {i} ({nome}) é obrigatório.')
                elif not validar_cpf(cpf_conv):
                    erros.append(f'O CPF do integrante {i} ({nome}) não é válido.')
            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip():
                    erros.append(f'O Passaporte/Documento do integrante estrangeiro {i} ({nome}) é obrigatório.')
            inst = dados.get(f'{prefixo}instituicao', '').strip()
            tipo_inst = dados.get(f'{prefixo}tipo_instituicao', '').strip()
            if not inst: erros.append(f'Instituição do integrante {i} é obrigatória.')
            if not tipo_inst: erros.append(f'Tipo de instituição do integrante {i} é obrigatório.')
            minibio = dados.get(f'{prefixo}minibio', '').strip()
            if not minibio: erros.append(f'Minibio del integrante {i} é obrigatória.')
            raca = dados.get(f'{prefixo}raca', '').strip()
            genero = dados.get(f'{prefixo}genero', '').strip()
            if dados.get(f'{prefixo}acessibilidade') == 'sim':
                if not dados.get(f'{prefixo}acessibilidade_desc', '').strip(): erros.append(f'Descreva os recursos de acessibilidade do integrante {i}.')
            convidados.append({
                'nome': nome, 'email': email, 'nacionalidade': nacionalidade,
                'cpf': cpf_conv, 'passaporte': dados.get(f'{prefixo}passaporte'),
                'telefone': telefone, 'instituicao': inst, 'tipo_instituicao': tipo_inst,
                'minibio': minibio, 'papel': papel, 'raca': raca, 'genero': genero,
                'idade': idade,
                'acessibilidade': dados.get(f'{prefixo}acessibilidade') == 'sim',
                'acessibilidade_desc': dados.get(f'{prefixo}acessibilidade_desc'),
                'social_linkedin': dados.get(f'{prefixo}social_linkedin'),
                'social_instagram': dados.get(f'{prefixo}social_instagram'),
                'cidade': cidade_c, 'estado': estado, 'bairro': bairro_c,
                'pais_origem': dados.get(f'{prefixo}pais_origem'),
                'foto_base64': foto_conv_base64
            })

    # Validação de Convidados (Atualizado: Roda de conversa exige 3, Debate exige 2)
    min_convidados = 2 if formato == 'debate' else 3 if formato == 'roda_de_conversa' else 1
    if not tem_convidado:
        if min_convidados > 1:
            nome_formato = 'Debate' if formato == 'debate' else 'Roda de conversa'
            erros.append(f'Para {nome_formato}, é necessário no mínimo {min_convidados} integrantes.')
        else:
            erros.append('Adicione pelo menos 1 integrante.')
    elif len(convidados) < min_convidados:
        nome_formato = 'Debate' if formato == 'debate' else 'Roda de conversa'
        erros.append(f'Para {nome_formato}, é necessário no mínimo {min_convidados} integrantes. Você adicionou apenas {len(convidados)}.')

    if erros:
        for erro in erros:
            flash(erro, 'error')
        return render_with_data(400)

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
        if dados.get('exp_material_ajuda') in ('sim', 'indispensavel'):
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

    inscricao = {
        'proponente': {
            'tipo': tipo_prop,
            'nome_instituicao': nome_proponente_val,
            'categoria': categoria_prop if tipo_prop == 'pj' else None,
            'nacionalidade': nat_prop_val,
            'cpf': dados.get('cpfProponente') if tipo_prop == 'pf' else None,
            'passaporte': dados.get('passaporteProponente') if tipo_prop == 'pf' else None,
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
            'acesso': dados.get('acessoAtividade'),
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
                'material_ajuda': dados.get('oficina_material_ajuda'),
                'materiais': materiais,
                'justificativa_materiais': dados.get('oficina_justificativa_materiais'),
                'mobiliario': dados.get('oficina_mobiliario'),
            } if formato == 'oficina' else None,
            # ──────────────────────────────────────────────────────────
            # PAYLOAD DE EXPERIÊNCIA NO DICIONÁRIO FINAL (ATUALIZADO)
            # ──────────────────────────────────────────────────────────
            'experiencia': {
                'tipologias': tipologias_selecionadas_exp,
                'dias': dados.get('exp_dias'),
                'espaco_ambiente': dados.get('exp_espaco_ambiente'),
                'espaco_condicao': dados.get('exp_espaco_condicao'),
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
                'infra_equip_solicitados': dados.get('exp_infra_equip_solicitados'),
                'material_ajuda': dados.get('exp_material_ajuda'),
                'materiais': exp_materiais,
                'justificativa_materiais': dados.get('exp_justificativa_materiais'),
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
