/*!
 * Gemaque Advogados — roteiro do atendimento virtual
 * ---------------------------------------------------------------------------
 * Este arquivo contém APENAS as perguntas. Para mudar o roteiro, edite aqui:
 * não é preciso mexer na lógica do atendente (js/atendente.js).
 *
 * Cada etapa tem:
 *   id       identificador curto, usado no resumo enviado ao WhatsApp
 *   rotulo   como o item aparece no resumo (ex.: "Situação")
 *   pergunta o texto exibido
 *   opcoes   lista de respostas; { v: valor, t: texto }
 *            t com 'urgente: true' encerra a triagem e encaminha na hora
 *   tipo     'texto' para resposta livre (com 'dica' como placeholder)
 * ---------------------------------------------------------------------------
 */
window.ATENDENTE_FLUXOS = {

  criminal: {
    rotulo: 'Direito Criminal',
    etapas: [
      {
        id: 'situacao', rotulo: 'Situação',
        pergunta: 'Qual é a situação hoje?',
        opcoes: [
          { v: 'Prisão em flagrante / pessoa detida agora', urgente: true,
            aviso: 'Prisão em flagrante tem prazo: a audiência de custódia ocorre em até 24 horas. Vou te encaminhar agora mesmo ao canal direto do escritório.' },
          { v: 'Audiência marcada para os próximos dias', urgente: true,
            aviso: 'Audiência próxima exige preparação imediata. Vou te encaminhar direto ao escritório.' },
          { v: 'Responde a processo criminal em andamento' },
          { v: 'Foi intimado ou indiciado em inquérito' },
          { v: 'Execução penal (progressão, benefícios, livramento)' },
          { v: 'Quer recorrer de uma decisão ou sentença' },
          { v: 'Ainda não sei classificar' }
        ]
      },
      {
        id: 'fase', rotulo: 'Fase',
        pergunta: 'Em que fase o caso está?',
        opcoes: [
          { v: 'Inquérito policial' },
          { v: 'Processo em primeira instância' },
          { v: 'Recurso em segunda instância (TJ/TRF)' },
          { v: 'Tribunais superiores (STJ/STF)' },
          { v: 'Não sei informar' }
        ]
      },
      {
        id: 'advogado', rotulo: 'Advogado constituído',
        pergunta: 'Já existe advogado constituído no processo?',
        opcoes: [
          { v: 'Não, ainda não' },
          { v: 'Sim, e busco segunda opinião' },
          { v: 'Sim, mas quero trocar' },
          { v: 'É defensoria pública' }
        ]
      },
      {
        id: 'local', rotulo: 'Onde tramita', tipo: 'texto',
        pergunta: 'Em qual cidade e Estado o caso tramita?',
        dica: 'Ex.: Santarém/PA'
      }
    ]
  },

  ambiental: {
    rotulo: 'Direito Ambiental',
    etapas: [
      {
        id: 'situacao', rotulo: 'Situação',
        pergunta: 'O que aconteceu?',
        opcoes: [
          { v: 'Recebi auto de infração (IBAMA, ICMBio, SEMAS ou outro órgão)' },
          { v: 'Minha área foi embargada' },
          { v: 'Fui multado e quero contestar' },
          { v: 'Preciso de licenciamento ambiental' },
          { v: 'Regularização fundiária rural (CAR, CCIR, INCRA, ITERPA)' },
          { v: 'Respondo a processo por crime ambiental' },
          { v: 'Área apontada no PRODES / alerta de desmatamento' }
        ]
      },
      {
        id: 'prazo', rotulo: 'Prazo',
        pergunta: 'Você já recebeu alguma notificação ou intimação formal?',
        opcoes: [
          { v: 'Sim, nos últimos 20 dias', urgente: true,
            aviso: 'Defesa administrativa costuma ter prazo curto contado da notificação. Vou te encaminhar direto ao escritório para não perder o prazo.' },
          { v: 'Sim, há mais de 20 dias' },
          { v: 'Ainda não recebi nada por escrito' },
          { v: 'Não sei dizer' }
        ]
      },
      {
        id: 'imovel', rotulo: 'Tipo de área',
        pergunta: 'A área envolvida é:',
        opcoes: [
          { v: 'Rural — propriedade ou posse' },
          { v: 'Rural — assentamento ou área pública' },
          { v: 'Urbana' },
          { v: 'Empresa / atividade licenciada' },
          { v: 'Não se aplica' }
        ]
      },
      {
        id: 'local', rotulo: 'Município/UF', tipo: 'texto',
        pergunta: 'Em qual município e Estado fica a área?',
        dica: 'Ex.: Belterra/PA'
      }
    ]
  },

  eleitoral: {
    rotulo: 'Direito Eleitoral',
    etapas: [
      {
        id: 'quem', rotulo: 'Quem procura',
        pergunta: 'Você procura o escritório como:',
        opcoes: [
          { v: 'Candidato(a)' },
          { v: 'Partido, federação ou coligação' },
          { v: 'Responsável pela prestação de contas da campanha' },
          { v: 'Eleitor(a) ou terceiro interessado' },
          { v: 'Detentor de mandato' }
        ]
      },
      {
        id: 'questao', rotulo: 'Questão',
        pergunta: 'Qual é a questão?',
        opcoes: [
          { v: 'Propaganda irregular (minha ou de adversário)' },
          { v: 'Direito de resposta' },
          { v: 'Representação, AIJE ou AIME' },
          { v: 'Prestação de contas eleitorais' },
          { v: 'Registro ou impugnação de candidatura' },
          { v: 'Inelegibilidade / Ficha Limpa' },
          { v: 'Recurso no TRE ou no TSE' }
        ]
      },
      {
        id: 'prazo', rotulo: 'Prazo',
        pergunta: 'Há prazo em curso? No Direito Eleitoral os prazos são muito curtos.',
        opcoes: [
          { v: 'Sim, vence nos próximos dias', urgente: true,
            aviso: 'Prazo eleitoral em curso não espera. Vou te encaminhar agora ao canal direto do escritório.' },
          { v: 'Sim, mas ainda há algum tempo' },
          { v: 'Não há prazo, é consulta preventiva' },
          { v: 'Não sei' }
        ]
      },
      {
        id: 'local', rotulo: 'Município/UF', tipo: 'texto',
        pergunta: 'Qual o município e Estado da disputa?',
        dica: 'Ex.: Santarém/PA'
      }
    ]
  },

  imoveis: {
    rotulo: 'Regularização de Imóveis',
    etapas: [
      {
        id: 'origem', rotulo: 'Origem do imóvel',
        pergunta: 'Como o imóvel veio para você?',
        opcoes: [
          { v: 'Comprei, mas só tenho contrato ou recibo' },
          { v: 'Recebi de herança' },
          { v: 'Ocupo ou possuo há anos, sem documento de compra' },
          { v: 'Tenho escritura, mas falta registro ou atualização' },
          { v: 'Imóvel rural a regularizar' }
        ]
      },
      {
        id: 'tempo', rotulo: 'Tempo de posse',
        pergunta: 'Há quanto tempo você ou sua família está na posse?',
        opcoes: [
          { v: 'Menos de 5 anos' },
          { v: 'Entre 5 e 10 anos' },
          { v: 'Mais de 10 anos' },
          { v: 'Não sei precisar' }
        ]
      },
      {
        id: 'matricula', rotulo: 'Matrícula',
        pergunta: 'O imóvel tem matrícula no cartório de registro?',
        opcoes: [
          { v: 'Sim, atualizada' },
          { v: 'Sim, mas desatualizada' },
          { v: 'Não tem matrícula' },
          { v: 'Não sei' }
        ]
      },
      {
        id: 'objetivo', rotulo: 'Objetivo',
        pergunta: 'O que você precisa fazer com o imóvel?',
        opcoes: [
          { v: 'Vender' },
          { v: 'Financiar ou dar em garantia' },
          { v: 'Concluir inventário / partilha' },
          { v: 'Apenas regularizar e ter segurança' }
        ]
      },
      {
        id: 'local', rotulo: 'Município/UF', tipo: 'texto',
        pergunta: 'Onde fica o imóvel?',
        dica: 'Ex.: Santarém/PA'
      }
    ]
  },

  digital: {
    rotulo: 'Atendimento online (Escritório Digital)',
    etapas: [
      {
        id: 'assunto', rotulo: 'Assunto',
        pergunta: 'Sobre qual área é o seu caso?',
        opcoes: [
          { v: 'Criminal' },
          { v: 'Ambiental' },
          { v: 'Eleitoral' },
          { v: 'Imóveis / regularização' },
          { v: 'Outra área' }
        ]
      },
      {
        id: 'local', rotulo: 'Onde você está', tipo: 'texto',
        pergunta: 'De qual cidade e Estado você fala?',
        dica: 'Ex.: Itaituba/PA'
      },
      {
        id: 'resumo', rotulo: 'Resumo', tipo: 'texto',
        pergunta: 'Resuma em poucas linhas o que você precisa.',
        dica: 'Evite dados sigilosos neste primeiro contato.'
      }
    ]
  },

  outro: {
    rotulo: 'Outro assunto',
    etapas: [
      {
        id: 'local', rotulo: 'Cidade/UF', tipo: 'texto',
        pergunta: 'De qual cidade e Estado você fala?',
        dica: 'Ex.: Santarém/PA'
      },
      {
        id: 'resumo', rotulo: 'Resumo', tipo: 'texto',
        pergunta: 'Conte brevemente o que você precisa.',
        dica: 'Evite dados sigilosos neste primeiro contato.'
      }
    ]
  }
};

/* Ordem e rótulos do menu inicial. */
window.ATENDENTE_MENU = [
  { chave: 'criminal',  texto: 'Direito Criminal' },
  { chave: 'ambiental', texto: 'Direito Ambiental' },
  { chave: 'eleitoral', texto: 'Direito Eleitoral' },
  { chave: 'imoveis',   texto: 'Regularização de imóveis' },
  { chave: 'digital',   texto: 'Atendimento online, de outra cidade' },
  { chave: 'outro',     texto: 'Outro assunto' }
];
