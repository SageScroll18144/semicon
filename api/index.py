from flask import Flask, render_template, request, redirect, url_for, flash
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = 'recnplay2026-chave-secreta-upgrade'

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'webp'}

CAMPOS_OBRIGATORIOS_BASE = [
    'tipoProponente', 'nomeInstituicao', 'cidadeProponente',
    'nomeRepresentante', 'telefoneRepresentante', 'emailRepresentante',
    'tituloAtividade', 'formatoAtividade', 'tempoDuracao',
    'descricaoAtividade', 'eixo', 'publicoAlvo', 'restricaoEtaria'
]


def extensao_permitida(nome_arquivo):
    return '.' in nome_arquivo and \
           nome_arquivo.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS


def validar_email(email):
    padrao = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(padrao, email) is not None


def validar_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    soma = 0
    for i in range(9):
        soma += int(cpf[i]) * (10 - i)
    resto = 11 - (soma % 11)
    if resto in (10, 11):
        resto = 0
    if resto != int(cpf[9]):
        return False
    soma = 0
    for i in range(10):
        soma += int(cpf[i]) * (11 - i)
    resto = 11 - (soma % 11)
    if resto in (10, 11):
        resto = 0
    if resto != int(cpf[10]):
        return False
    return True


def validar_cnpj(cnpj):
    cnpj = re.sub(r'\D', '', cnpj)
    if len(cnpj) != 14:
        return False
    if cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = 0
    for i in range(12):
        soma += int(cnpj[i]) * pesos1[i]
    resto = 11 - (soma % 11)
    if resto in (10, 11):
        resto = 0
    if resto != int(cnpj[12]):
        return False
    soma = 0
    for i in range(13):
        soma += int(cnpj[i]) * pesos2[i]
    resto = 11 - (soma % 11)
    if resto in (10, 11):
        resto = 0
    if resto != int(cnpj[13]):
        return False
    return True


def salvar_foto(arquivo_foto, nome_base):
    from werkzeug.utils import secure_filename
    if not arquivo_foto or arquivo_foto.filename == '':
        return None
    ext = arquivo_foto.filename.rsplit('.', 1)[1].lower()
    nome_seguro = secure_filename(nome_base.replace(' ', '_'))
    nome_arquivo = f"{nome_seguro}_foto.{ext}"
    caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
    contador = 1
    while os.path.exists(caminho):
        nome_arquivo = f"{nome_seguro}_foto_{contador}.{ext}"
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
        contador += 1
    arquivo_foto.save(caminho)
    return nome_arquivo


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'GET':
        return render_template('index.html', dados={})

    dados = request.form
    arquivo_foto = request.files.get('fotoProponente')
    erros = []

    tipo_prop = dados.get('tipoProponente', '')

    for campo in CAMPOS_OBRIGATORIOS_BASE:
        valor = dados.get(campo, '').strip()
        if not valor:
            nome_amigavel = campo.replace('_', ' ').title()
            erros.append(f'O campo "{nome_amigavel}" é obrigatório.')

    # Validações por tipo
    if tipo_prop == 'pj':
        cat = dados.get('categoria', '').strip()
        if not cat:
            erros.append('O campo "Categoria" é obrigatório para Pessoa Jurídica.')
        cnpj = dados.get('cnpjProponente', '').strip()
        if not cnpj:
            erros.append('O CNPJ é obrigatório para Pessoa Jurídica.')
        elif not validar_cnpj(cnpj):
            erros.append('O CNPJ informado não é válido.')
    else:
        nat_prop = dados.get('nacionalidadeProponente', '').strip()
        if not nat_prop:
            erros.append('A Nacionalidade é obrigatória para Pessoa Física.')
        elif nat_prop == 'brasileiro':
            cpf_val = dados.get('cpfProponente', '').strip()
            if not cpf_val:
                erros.append('O CPF é obrigatório para proponentes brasileiros.')
            elif not validar_cpf(cpf_val):
                erros.append('O CPF informado não é válido.')
        elif nat_prop == 'estrangeiro':
            pass_val = dados.get('passaporteProponente', '').strip()
            if not pass_val:
                erros.append('O Passaporte é obrigatório para proponentes estrangeiros.')

    # E-mail representante
    if dados.get('emailRepresentante') and not validar_email(dados.get('emailRepresentante')):
        erros.append('O e-mail do representante não é válido.')

    # Tags limite
    tags_val = dados.get('tags', '').strip()
    if tags_val:
        tags_list = [t.strip() for t in tags_val.split(',') if t.strip()]
        if len(tags_list) > 5:
            erros.append('O limite máximo de tags é 5.')

    # Faixa etária
    if dados.get('restricaoEtaria') == 'sim':
        idade_min = dados.get('idadeMinima', '').strip()
        idade_max = dados.get('idadeMaxima', '').strip()
        if not idade_min or not idade_max:
            erros.append('Preencha a idade mínima e máxima para a restrição etária.')
        elif int(idade_min) > int(idade_max):
            erros.append('A idade mínima não pode ser maior que a idade máxima.')

    # Oficina
    formato = dados.get('formatoAtividade')
    if formato == 'oficina':
        if not dados.get('oficina_qtd_publico'):
            erros.append('Selecione a quantidade máxima de público para a oficina.')
        if not dados.get('oficina_internet'):
            erros.append('Informe se é necessária internet para a oficina.')
        if not dados.get('oficina_lab'):
            erros.append('Informe se a oficina precisa de laboratório.')
        if dados.get('oficina_lab') == 'sim':
            if not dados.get('oficina_pc_specs'):
                erros.append('Descreva as configurações mínimas dos PCs.')
            if not dados.get('oficina_soft_req'):
                erros.append('Informe se é necessário instalar software.')
            elif dados.get('oficina_soft_req') == 'sim' and not dados.get('oficina_soft_desc'):
                erros.append('Descreva o software necessário.')
        if not dados.get('oficina_material_ajuda'):
            erros.append('Informe sobre a necessidade de ajuda de custo com material.')
        if not dados.get('oficina_mobiliario'):
            erros.append('Selecione o formato de mobiliário necessário.')

    if len(dados.get('descricaoAtividade', '')) > 700:
        erros.append('A descrição excedeu o limite de 700 caracteres.')
    if len(dados.get('infoExtras', '')) > 500:
        erros.append('As observações extras excederam o limite de 500 caracteres.')

    if arquivo_foto and arquivo_foto.filename.strip() != '':
        if not extensao_permitida(arquivo_foto.filename):
            erros.append('Formato de foto não permitido. Use: png, jpg, jpeg, webp')

    # Convidados
    convidados = []
    for i in range(1, 6):
        prefixo = f'convidado{i}_'
        nome = dados.get(f'{prefixo}nome', '').strip()
        if nome:
            email = dados.get(f'{prefixo}email', '').strip()
            nacionalidade = dados.get(f'{prefixo}nacionalidade', '').strip()
            papel = dados.get(f'{prefixo}papel', '').strip()
            if not papel:
                erros.append(f'Selecione o papel do convidado {i} ({nome}).')
            if email and not validar_email(email):
                erros.append(f'O e-mail do convidado {i} ({nome}) é inválido.')
            if nacionalidade == 'brasileiro':
                cpf_conv = dados.get(f'{prefixo}cpf', '').strip()
                if cpf_conv and not validar_cpf(cpf_conv):
                    erros.append(f'O CPF do convidado {i} ({nome}) não é válido.')
            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip():
                    erros.append(f'Passaporte obrigatório para o convidado estrangeiro {i}.')

            foto_conv = request.files.get(f'{prefixo}foto')
            foto_conv_nome = None
            if foto_conv and foto_conv.filename.strip() != '':
                if not extensao_permitida(foto_conv.filename):
                    erros.append(f'Formato de foto do convidado {i} não permitido.')
                else:
                    foto_conv_nome = salvar_foto(foto_conv, f'convidado{i}_{nome}')

            convidados.append({
                'nome': nome, 'email': email,
                'nacionalidade': nacionalidade,
                'cpf': dados.get(f'{prefixo}cpf'),
                'passaporte': dados.get(f'{prefixo}passaporte'),
                'telefone': dados.get(f'{prefixo}telefone'),
                'instituicao': dados.get(f'{prefixo}instituicao'),
                'tipo_instituicao': dados.get(f'{prefixo}tipo_instituicao'),
                'minibio': dados.get(f'{prefixo}minibio'),
                'papel': papel,
                'raca': dados.get(f'{prefixo}raca'),
                'genero': dados.get(f'{prefixo}genero'),
                'acessibilidade': dados.get(f'{prefixo}acessibilidade') == 'sim',
                'acessibilidade_desc': dados.get(f'{prefixo}acessibilidade_desc'),
                'social_linkedin': dados.get(f'{prefixo}social_linkedin'),
                'social_instagram': dados.get(f'{prefixo}social_instagram'),
                'cidade': dados.get(f'{prefixo}cidade'),
                'estado': dados.get(f'{prefixo}estado'),
                'pais_origem': dados.get(f'{prefixo}pais_origem'),
                'foto': foto_conv_nome
            })

    if erros:
        for erro in erros:
            flash(erro, 'error')
        return render_template('index.html', dados=dados), 400

    foto_nome = salvar_foto(arquivo_foto, dados.get('nomeInstituicao', 'proponente'))
    nat_prop_val = dados.get('nacionalidadeProponente', '') if tipo_prop == 'pf' else ''

    inscricao = {
        'proponente': {
            'tipo': tipo_prop,
            'nome_instituicao': dados.get('nomeInstituicao'),
            'categoria': dados.get('categoria') if tipo_prop == 'pj' else None,
            'cidade': dados.get('cidadeProponente'),
            'nacionalidade': nat_prop_val,
            'cpf': dados.get('cpfProponente') if tipo_prop == 'pf' else None,
            'passaporte': dados.get('passaporteProponente') if tipo_prop == 'pf' else None,
            'cnpj': dados.get('cnpjProponente') if tipo_prop == 'pj' else None,
            'foto': foto_nome
        },
        'representante': {
            'nome': dados.get('nomeRepresentante'),
            'telefone': dados.get('telefoneRepresentante'),
            'email': dados.get('emailRepresentante'),
        },
        'atividade': {
            'titulo': dados.get('tituloAtividade'),
            'formato': dados.get('formatoAtividade'),
            'tempo_duracao': dados.get('tempoDuracao'),
            'descricao': dados.get('descricaoAtividade'),
            'eixo': dados.get('eixo'),
            'publico_alvo': dados.get('publicoAlvo'),
            'tags': dados.get('tags'),
            'restricao_etaria': dados.get('restricaoEtaria'),
            'idade_minima': dados.get('idadeMinima'),
            'idade_maxima': dados.get('idadeMaxima'),
            'recursos_acessibilidade': dados.get('recursosAcessibilidade'),
            'observacoes': dados.get('infoExtras'),
            'oficina': {
                'qtd_publico': dados.get('oficina_qtd_publico'),
                'internet': dados.get('oficina_internet'),
                'lab': dados.get('oficina_lab'),
                'pc_specs': dados.get('oficina_pc_specs'),
                'software_req': dados.get('oficina_soft_req'),
                'software_desc': dados.get('oficina_soft_desc'),
                'material_ajuda': dados.get('oficina_material_ajuda'),
                'mobiliario': dados.get('oficina_mobiliario'),
            } if formato == 'oficina' else None
        },
        'convidados': convidados
    }

    print(f"✅ Inscrição Recebida: {inscricao['proponente']['nome_instituicao']}")

    flash('Proposta enviada com sucesso! Obrigado.', 'success')
    return redirect(url_for('home'))


app = app