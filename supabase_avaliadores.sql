-- 1) Tabela de avaliadores/pareceristas.
create table if not exists public.avaliadores (
    "ID_avaliador" integer primary key,
    nome text not null,
    email text,
    tags_responsavel text[] not null default '{}',
    limite_atividades integer not null default 10,
    atividades_atribuidas integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 2) Carga inicial. Troque os e-mails pelos contatos reais dos avaliadores.
insert into public.avaliadores ("ID_avaliador", nome, email, tags_responsavel)
values
(
    1,
    'Avaliador Tecnologia Base',
    'avaliador.tecnologia_base@example.com',
    array['Blockchain', 'Dados', 'Cibersegurança', 'Cloud', 'Computação Quântica', 'Desenvolvimento de Software']
),
(
    2,
    'Avaliador IA e XR',
    'avaliador.ia_xr@example.com',
    array['Inteligência Artificial', 'XR / Realidade Virtual e Aumentada', 'Desenvolvimento de Software']
),
(
    3,
    'Avaliador Automação, IoT e Robótica',
    'avaliador.automacao_iot_robotica@example.com',
    array['Automação', 'Internet das Coisas', 'Robótica', 'Sistemas Embarcados', 'Cultura Maker', 'Simulação e Modelagem', 'Desenvolvimento de Software']
),
(
    4,
    'Avaliador Negócios e Inovação',
    'avaliador.negocios_inovacao@example.com',
    array['Empreendedorismo', 'Inovação', 'Startup', 'Empresa Júnior', 'Modelagem de Negócios', 'Internacionalização', 'Investimentos', 'Transformação Digital', 'Gestão de Comunidades']
),
(
    5,
    'Avaliador Marketing, Pessoas e Vendas',
    'avaliador.marketing_pessoas_vendas@example.com',
    array['Marketing', 'Branding', 'RH', 'Cultura Organizacional', 'Carreira Profissional', 'Desenvolvimento de Times', 'Comportamento do Consumidor', 'Vendas B2B e B2C', 'Agro', 'Futuro do trabalho', 'Atacado e Varejo']
),
(
    6,
    'Avaliador Comunicação e Conteúdo',
    'avaliador.comunicacao_conteudo@example.com',
    array['Comunicação', 'Criação de Conteúdo', 'Podcast', 'Audiovisual']
),
(
    7,
    'Avaliador UX e Games',
    'avaliador.ux_games@example.com',
    array['Experiência do Usuário (UX / CX)', 'Interface do Usuário (UI)', 'Gameficação', 'Desenvolvimento de Jogos', 'E-Sports', 'Desenvolvimento de Software']
),
(
    8,
    'Avaliador Artes e Cultura',
    'avaliador.artes_cultura@example.com',
    array['Artes Visuais', 'Fotografia', 'Literatura', 'Moda', 'Música', 'Dança', 'Gastronomia', 'Teatro']
),
(
    9,
    'Avaliador Cidades e Território',
    'avaliador.cidades_territorio@example.com',
    array['Urbanismo', 'Arquitetura', 'Mobilidade Urbana', 'Território', 'Cidadania Digital', 'Intervenções Urbanas', 'Cidades Inteligentes']
),
(
    10,
    'Avaliador Sustentabilidade',
    'avaliador.sustentabilidade@example.com',
    array['Meio Ambiente', 'ESG', 'Economia Circular', 'Mudanças Climáticas', 'Energia Renovável', 'Gestão de Resíduos', 'ODS']
),
(
    11,
    'Avaliador Diversidade e Impacto',
    'avaliador.diversidade_impacto@example.com',
    array['Acessibilidade', 'PcD', 'Mulheres', 'LGBTQIAPN+', 'Pessoa Idosa', 'Equidade Racial', 'Neurodivergência', 'Diversidade e Inclusão', 'Periferias', 'Desinformação', 'Cultura Popular', 'Patrimônio', 'Artes', 'Impacto Social', 'Educação e Formação', 'Infância']
)
on conflict ("ID_avaliador") do update set
    nome = excluded.nome,
    email = excluded.email,
    tags_responsavel = excluded.tags_responsavel,
    updated_at = now();

-- 3) Colunas na tabela de inscrições.
alter table public.inscricoes
    add column if not exists "ID_avaliador_1" integer;

alter table public.inscricoes
    add column if not exists "ID_avaliador_2" integer;

alter table public.inscricoes
    add column if not exists "ID_avaliador_3" integer;

-- 4) Foreign keys. Mantemos ON DELETE SET NULL para preservar inscrições caso um avaliador seja removido.
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'inscricoes_id_avaliador_1_fkey'
    ) then
        alter table public.inscricoes
            add constraint inscricoes_id_avaliador_1_fkey
            foreign key ("ID_avaliador_1")
            references public.avaliadores ("ID_avaliador")
            on update cascade
            on delete set null;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'inscricoes_id_avaliador_2_fkey'
    ) then
        alter table public.inscricoes
            add constraint inscricoes_id_avaliador_2_fkey
            foreign key ("ID_avaliador_2")
            references public.avaliadores ("ID_avaliador")
            on update cascade
            on delete set null;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'inscricoes_id_avaliador_3_fkey'
    ) then
        alter table public.inscricoes
            add constraint inscricoes_id_avaliador_3_fkey
            foreign key ("ID_avaliador_3")
            references public.avaliadores ("ID_avaliador")
            on update cascade
            on delete set null;
    end if;
end $$;

create index if not exists inscricoes_id_avaliador_1_idx
    on public.inscricoes ("ID_avaliador_1");

create index if not exists inscricoes_id_avaliador_2_idx
    on public.inscricoes ("ID_avaliador_2");

create index if not exists inscricoes_id_avaliador_3_idx
    on public.inscricoes ("ID_avaliador_3");
