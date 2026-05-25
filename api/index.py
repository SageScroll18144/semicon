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
    'objetivoAtividade', 'justificativaTematica', 'metodologiaAplicada',
    'descricaoAtividade', 'eixo', 'publicoAlvo', 'restricaoEtaria',
    'acessoAtividade'
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

    # Campos obrigatórios base
    for campo in CAMPOS_OBRIGATORIOS_BASE:
        valor = dados.get(campo, '').strip()
        if not valor:
            nome_amigavel = campo.replace('_', ' ').title()
            erros.append(f'O campo "{nome_amigavel}" é obrigatório.')

    # Validações por tipo de proponente
    if tipo_prop == 'pj':
        cat = dados.get('categoria', '').strip()
        if not cat:
            erros.append('O campo "Categoria" é obrigatório.')
        cnpj = dados.get('cnpjProponente', '').strip()
        if not cnpj:
            erros.append('O CNPJ é obrigatório.')
        elif not validar_cnpj(cnpj):
            erros.append('O CNPJ informado não é válido.')

        # Logo Marca OBRIGATÓRIA para PJ
        if not arquivo_foto or arquivo_foto.filename.strip() == '':
            erros.append('A Logo Marca é obrigatória para Pessoa Jurídica.')
        elif not extensao_permitida(arquivo_foto.filename):
            erros.append('Formato de Logo Marca não permitido. Use: png, jpg, jpeg, webp')
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

    # E-mail representante
    if dados.get('emailRepresentante') and not validar_email(dados.get('emailRepresentante')):
        erros.append('O e-mail do representante não é válido.')

    # Tags: mínimo 3, máximo 5
    tags_val = dados.get('tags', '').strip()
    suggestion = dados.get('tagSuggestion', '').strip()
    tag_count = 0
    if tags_val:
        tags_list = [t.strip() for t in tags_val.split(',') if t.strip()]
        tag_count = len(tags_list)
    if suggestion:
        tag_count += 1
    if tag_count < 3:
        erros.append('Selecione pelo menos 3 tags.')
    if tag_count > 5:
        erros.append('O limite máximo de tags é 5.')

    # Texto limites
    for campo, limite in [('objetivoAtividade', 500), ('justificativaTematica', 500),
                          ('metodologiaAplicada', 500), ('descricaoAtividade', 500),
                          ('infoExtras', 500)]:
        if len(dados.get(campo, '')) > limite:
            erros.append(f'O campo "{campo}" excedeu o limite de {limite} caracteres.')

    # Faixa etária
    if dados.get('restricaoEtaria') == 'sim':
        idade_min = dados.get('idadeMinima', '').strip()
        idade_max = dados.get('idadeMaxima', '').strip()
        if not idade_min or not idade_max:
            erros.append('Preencha a idade mínima e máxima.')
        elif int(idade_min) > int(idade_max):
            erros.append('A idade mínima não pode ser maior que a máxima.')
    elif not dados.get('restricaoEtaria'):
        erros.append('Selecione se há restrição de faixa etária.')

    # Oficina
    formato = dados.get('formatoAtividade')
    if formato == 'oficina':
        if not dados.get('oficina_qtd_publico'):
            erros.append('Selecione a quantidade máxima de público.')
        if not dados.get('oficina_internet'):
            erros.append('Informe sobre internet.')
        if not dados.get('oficina_lab'):
            erros.append('Informe sobre laboratório.')
        if dados.get('oficina_lab') == 'sim':
            if not dados.get('oficina_pc_specs'):
                erros.append('Descreva as configurações mínimas dos PCs.')
            if len(dados.get('oficina_pc_specs', '')) > 200:
                erros.append('Configurações dos PCs: máximo 200 caracteres.')
            if not dados.get('oficina_soft_req'):
                erros.append('Informe sobre software.')
            elif dados.get('oficina_soft_req') == 'sim' and not dados.get('oficina_soft_desc'):
                erros.append('Descreva o software.')
            if len(dados.get('oficina_soft_desc', '')) > 200:
                erros.append('Descrição do software: máximo 200 caracteres.')
        if not dados.get('oficina_material_ajuda'):
            erros.append('Informe sobre ajuda de custo com material.')
        if not dados.get('oficina_mobiliario'):
            erros.append('Selecione o mobiliário necessário.')

        # Material table validation
        if dados.get('oficina_material_ajuda') in ('sim', 'indispensavel'):
            has_items = False
            for key in dados:
                if key.startswith('mat_item_') and dados[key].strip():
                    has_items = True
                    break
            if not has_items:
                erros.append('Liste pelo menos um material com previsão de custo.')

    # Acessibilidade 200 chars
    if len(dados.get('recursosAcessibilidade', '')) > 200:
        erros.append('Recursos de acessibilidade: máximo 200 caracteres.')

    # Convidados - mínimo 1
    convidados = []
    tem_convidado = False
    for i in range(1, 6):
        prefixo = f'convidado{i}_'
        nome = dados.get(f'{prefixo}nome', '').strip()
        if nome:
            tem_convidado = True

            # Foto OBRIGATÓRIA do convidado
            foto_conv = request.files.get(f'{prefixo}foto')
            foto_conv_nome = None
            if not foto_conv or foto_conv.filename.strip() == '':
                erros.append(f'A foto do convidado {i} ({nome}) é obrigatória.')
            elif not extensao_permitida(foto_conv.filename):
                erros.append(f'Formato de foto do convidado {i} não permitido.')
            else:
                foto_conv_nome = salvar_foto(foto_conv, f'convidado{i}_{nome}')

            email = dados.get(f'{prefixo}email', '').strip()
            if not email:
                erros.append(f'E-mail do convidado {i} é obrigatório.')
            elif not validar_email(email):
                erros.append(f'O e-mail do convidado {i} ({nome}) é inválido.')

            papel = dados.get(f'{prefixo}papel', '').strip()
            if not papel:
                erros.append(f'Selecione o papel do convidado {i}.')

            nacionalidade = dados.get(f'{prefixo}nacionalidade', '').strip()
            if not nacionalidade:
                erros.append(f'Nacionalidade do convidado {i} é obrigatória.')

            telefone = dados.get(f'{prefixo}telefone', '').strip()
            if not telefone:
                erros.append(f'Telefone do convidado {i} é obrigatório.')

            estado = dados.get(f'{prefixo}estado', '').strip()
            cidade_c = dados.get(f'{prefixo}cidade', '').strip()
            bairro_c = dados.get(f'{prefixo}bairro', '').strip()

            if nacionalidade == 'brasileiro' and (not estado or not cidade_c):
                erros.append(f'Estado e cidade do convidado {i} são obrigatórios.')

            # Bairro obrigatório se cidade for Recife
            if cidade_c and 'recife' in cidade_c.lower():
                if not bairro_c:
                    erros.append(f'O bairro do convidado {i} é obrigatório quando a cidade é Recife.')

            elif nacionalidade == 'estrangeiro':
                if not dados.get(f'{prefixo}passaporte', '').strip():
                    erros.append(f'Passaporte do convidado estrangeiro {i} é obrigatório.')
                if not dados.get(f'{prefixo}pais_origem', '').strip():
                    erros.append(f'País de origem do convidado {i} é obrigatório.')

            # CPF opcional, mas se preenchido deve ser válido
            cpf_conv = dados.get(f'{prefixo}cpf', '').strip()
            if cpf_conv and not validar_cpf(cpf_conv):
                erros.append(f'O CPF do convidado {i} ({nome}) não é válido.')

            inst = dados.get(f'{prefixo}instituicao', '').strip()
            tipo_inst = dados.get(f'{prefixo}tipo_instituicao', '').strip()
            if not inst:
                erros.append(f'Instituição do convidado {i} é obrigatória.')
            if not tipo_inst:
                erros.append(f'Tipo de instituição do convidado {i} é obrigatório.')

            minibio = dados.get(f'{prefixo}minibio', '').strip()
            if not minibio:
                erros.append(f'Minibio do convidado {i} é obrigatória.')

            raca = dados.get(f'{prefixo}raca', '').strip()
            genero = dados.get(f'{prefixo}genero', '').strip()
            if not raca:
                erros.append(f'Raça/Cor do convidado {i} é obrigatória.')
            if not genero:
                erros.append(f'Gênero do convidado {i} é obrigatório.')

            # Acessibilidade condicional
            if dados.get(f'{prefixo}acessibilidade') == 'sim':
                if not dados.get(f'{prefixo}acessibilidade_desc', '').strip():
                    erros.append(f'Descreva os recursos de acessibilidade do convidado {i}.')

            convidados.append({
                'nome': nome, 'email': email,
                'nacionalidade': nacionalidade,
                'cpf': cpf_conv,
                'passaporte': dados.get(f'{prefixo}passaporte'),
                'telefone': telefone,
                'instituicao': inst,
                'tipo_instituicao': tipo_inst,
                'minibio': minibio,
                'papel': papel,
                'raca': raca, 'genero': genero,
                'acessibilidade': dados.get(f'{prefixo}acessibilidade') == 'sim',
                'acessibilidade_desc': dados.get(f'{prefixo}acessibilidade_desc'),
                'social_linkedin': dados.get(f'{prefixo}social_linkedin'),
                'social_instagram': dados.get(f'{prefixo}social_instagram'),
                'cidade': cidade_c,
                'estado': estado,
                'bairro': bairro_c,
                'pais_origem': dados.get(f'{prefixo}pais_origem'),
                'foto': foto_conv_nome
            })

    if not tem_convidado:
        erros.append('Adicione pelo menos 1 convidado obrigatório.')

    if erros:
        for erro in erros:
            flash(erro, 'error')
        return render_template('index.html', dados=dados), 400

    # Salvamento
    foto_nome = None
    if tipo_prop == 'pj':
        foto_nome = salvar_foto(arquivo_foto, dados.get('nomeInstituicao', 'proponente'))

    nat_prop_val = dados.get('nacionalidadeProponente', '') if tipo_prop == 'pf' else ''

    # Material table
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
            'logo_marca': foto_nome
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
            'observacoes': dados.get('infoExtras'),
            'oficina': {
                'qtd_publico': dados.get('oficina_qtd_publico'),
                'internet': dados.get('oficina_internet'),
                'lab': dados.get('oficina_lab'),
                'pc_specs': dados.get('oficina_pc_specs'),
                'software_req': dados.get('oficina_soft_req'),
                'software_desc': dados.get('oficina_soft_desc'),
                'material_ajuda': dados.get('oficina_material_ajuda'),
                'materiais': materiais,
                'mobiliario': dados.get('oficina_mobiliario'),
            } if formato == 'oficina' else None
        },
        'convidados': convidados
    }

    print(f"✅ Inscrição Recebida: {inscricao['proponente']['nome_instituicao']}")
    flash('Proposta enviada com sucesso! Obrigado.', 'success')
    return redirect(url_for('home'))


app = app