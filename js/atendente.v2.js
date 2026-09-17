/*!
 * Gemaque Advogados — atendente virtual de triagem
 * ---------------------------------------------------------------------------
 * O que faz: conduz uma triagem por perguntas fechadas, monta um resumo do
 * caso e encaminha a pessoa ao WhatsApp do escritório com esse resumo pronto.
 *
 * O que NÃO faz, por decisão de projeto:
 *   - não responde dúvida jurídica nem opina sobre o caso;
 *   - não grava nada em servidor: as respostas vivem só na memória da aba e
 *     seguem apenas para o WhatsApp, por ação da própria pessoa;
 *   - não usa serviço externo: nenhuma resposta sai do navegador antes disso.
 *
 * O roteiro de perguntas fica em js/atendente-fluxos.v2.js.
 * A medição (GA4 e Google Ads) reaproveita js/tracking.v2.js.
 * ---------------------------------------------------------------------------
 */
(function () {
  'use strict';

  /* Número que RECEBE os leads da triagem — hoje o mesmo do restante do
     site. Para encaminhar os leads da triagem a outro número (por exemplo,
     direto ao celular da advogada) sem mexer no resto do site, troque só
     esta linha. */
  var WA_NUM = '5573999989925';
  var ABERTURA = 'Olá! Sou o atendimento virtual do escritório. Não sou advogada e não presto consulta jurídica — faço algumas perguntas rápidas para que a Dra. Elizângela já receba o seu caso organizado.';
  var SIGILO = 'Nada do que você responder aqui fica gravado neste site. As informações seguem apenas para o WhatsApp do escritório, protegidas pelo sigilo profissional (art. 7º, II, do Estatuto da Advocacia).';

  var FLUXOS = window.ATENDENTE_FLUXOS;
  var MENU = window.ATENDENTE_MENU;
  if (!FLUXOS || !MENU) return;

  /* ---------- estado da conversa (apenas em memória) ---------- */
  var estado = { aberto: false, area: null, etapa: 0, respostas: [], nome: '', urgente: null, apenasLocal: false, encerrado: false };

  /* ---------- medição ---------- */
  function medir(evento, dados) {
    try { if (typeof window.gtag === 'function') window.gtag('event', evento, dados || {}); }
    catch (e) { /* medição nunca pode quebrar o atendimento */ }
  }

  /* ---------- estilos ---------- */
  var CSS = [
    '.gmq-bot-abrir{position:fixed;right:20px;bottom:84px;z-index:998;display:inline-flex;align-items:center;gap:9px;',
    'background:#0e2a47;color:#f8f5ef;border:1px solid #b08a3e;padding:12px 18px 12px 15px;border-radius:40px;',
    "font-family:Georgia,'Garamond',serif;font-size:14.5px;font-weight:bold;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.26);transition:transform .2s,box-shadow .2s}",
    '.gmq-bot-abrir:hover{transform:translateY(-2px);box-shadow:0 8px 26px rgba(0,0,0,.32);color:#f8f5ef}',
    '.gmq-bot-abrir svg{width:20px;height:20px;fill:#c9a866;flex-shrink:0}',
    '.gmq-bot-abrir[hidden]{display:none}',
    '@media(max-width:600px){.gmq-bot-abrir{bottom:78px;padding:12px 15px;font-size:13.5px}}',

    '.gmq-bot{position:fixed;right:20px;bottom:20px;z-index:1000;width:374px;max-width:calc(100vw - 32px);',
    'max-height:min(78vh,620px);display:none;flex-direction:column;background:#f8f5ef;border:1px solid #d9d4c7;',
    "border-radius:10px;overflow:hidden;box-shadow:0 18px 50px rgba(8,26,46,.33);font-family:Georgia,'Garamond',serif}",
    '.gmq-bot.aberto{display:flex}',
    '@media(max-width:600px){.gmq-bot{right:8px;left:8px;bottom:8px;width:auto;max-height:86vh}}',

    '.gmq-bot-topo{background:#081a2e;color:#f8f5ef;padding:14px 16px;border-bottom:2px solid #b08a3e;display:flex;align-items:center;gap:12px;flex-shrink:0}',
    '.gmq-bot-topo h2{margin:0;font-size:15px;color:#f8f5ef;font-weight:bold;letter-spacing:.5px;line-height:1.3}',
    '.gmq-bot-topo p{margin:2px 0 0;font-size:11.5px;color:#c9a866;letter-spacing:1px;text-transform:uppercase}',
    '.gmq-bot-selo{width:38px;height:38px;border:1px solid #b08a3e;border-radius:50%;display:flex;align-items:center;',
    'justify-content:center;color:#c9a866;font-size:17px;font-weight:bold;flex-shrink:0}',
    '.gmq-bot-fechar{margin-left:auto;background:none;border:none;color:#c9a866;font-size:26px;line-height:1;cursor:pointer;padding:0 2px}',
    '.gmq-bot-fechar:hover{color:#f8f5ef}',

    '.gmq-bot-corpo{flex:1;overflow-y:auto;padding:18px 16px 8px;display:flex;flex-direction:column;gap:12px}',
    '.gmq-bot-fala{background:#fff;border:1px solid #d9d4c7;border-left:3px solid #b08a3e;border-radius:3px;',
    'padding:12px 14px;font-size:15px;color:#2c2c2c;line-height:1.6;max-width:94%}',
    '.gmq-bot-fala strong{color:#0e2a47}',
    '.gmq-bot-eu{align-self:flex-end;background:#0e2a47;color:#f8f5ef;border-radius:14px 14px 3px 14px;',
    'padding:9px 14px;font-size:14.5px;line-height:1.5;max-width:88%}',
    '.gmq-bot-aviso{background:rgba(176,62,62,.07);border:1px solid #d9b4b4;border-left:3px solid #b03e3e;border-radius:3px;',
    'padding:12px 14px;font-size:14.5px;color:#2c2c2c;line-height:1.6}',
    '.gmq-bot-aviso strong{color:#8c2f2f}',
    '.gmq-bot-resumo{background:#fff;border:1px solid #d9d4c7;border-radius:3px;padding:13px 15px;font-size:14px;line-height:1.75;color:#2c2c2c}',
    '.gmq-bot-resumo b{color:#0e2a47}',

    '.gmq-bot-pe{flex-shrink:0;padding:10px 16px 14px;border-top:1px solid #d9d4c7;background:#f8f5ef;display:flex;flex-direction:column;gap:8px}',
    '.gmq-bot-op{display:block;width:100%;text-align:left;background:#fff;border:1px solid #d9d4c7;border-radius:4px;',
    "padding:11px 14px;font-family:Georgia,'Garamond',serif;font-size:14.5px;color:#2c2c2c;cursor:pointer;line-height:1.45;transition:border-color .15s,background .15s}",
    '.gmq-bot-op:hover,.gmq-bot-op:focus{border-color:#b08a3e;background:rgba(176,138,62,.08);outline:none}',
    '.gmq-bot-campo{display:flex;gap:8px}',
    ".gmq-bot-campo input{flex:1;min-width:0;font-family:Georgia,'Garamond',serif;font-size:15px;color:#2c2c2c;background:#fff;",
    'border:1px solid #d9d4c7;border-radius:4px;padding:11px 13px}',
    '.gmq-bot-campo input:focus{outline:none;border-color:#b08a3e}',
    ".gmq-bot-env{background:#0e2a47;color:#f8f5ef;border:none;border-radius:4px;padding:0 17px;font-family:Georgia,'Garamond',serif;",
    'font-size:15px;font-weight:bold;cursor:pointer}',
    '.gmq-bot-env:hover{background:#b08a3e;color:#081a2e}',
    '.gmq-bot-wa{display:flex;align-items:center;justify-content:center;gap:9px;background:#25D366;color:#fff;border:none;border-radius:4px;',
    "padding:14px 18px;font-family:Georgia,'Garamond',serif;font-size:15.5px;font-weight:bold;cursor:pointer;text-decoration:none}",
    '.gmq-bot-wa:hover{background:#1da851;color:#fff}',
    '.gmq-bot-wa svg{width:21px;height:21px;fill:#fff;flex-shrink:0}',
    '.gmq-bot-sec{background:none;border:none;color:#6b6b6b;font-family:Georgia,serif;font-size:13px;cursor:pointer;text-decoration:underline;padding:2px}',
    '.gmq-bot-sec:hover{color:#b08a3e}',
    '.gmq-bot-nota{font-size:11.5px;color:#6b6b6b;line-height:1.5;text-align:center}',
    '.gmq-bot-passo{font-size:11.5px;color:#6b6b6b;letter-spacing:1px;text-transform:uppercase}'
  ].join('');

  var ICONE_WA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M.057 24l1.687-6.163a11.867 11.867 0 01-1.587-5.946C.16 5.335 5.495 0 12.05 0a11.82 11.82 0 018.413 3.488 11.82 11.82 0 013.48 8.414c-.003 6.557-5.338 11.892-11.893 11.892a11.9 11.9 0 01-5.688-1.448L.057 24zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884a9.86 9.86 0 001.51 5.26l-.999 3.648 3.978-1.197zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.096 3.2 5.077 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413z"/></svg>';

  /* ---------- montagem ---------- */
  var botao, painel, corpo, pe, flutuante;

  function montar() {
    var estilo = document.createElement('style');
    estilo.textContent = CSS;
    document.head.appendChild(estilo);

    flutuante = document.querySelector('.wa-float');

    /* Onde já existe o botão verde de WhatsApp, é ele quem abre a triagem —
       dois botões flutuantes empilhados só atrapalhariam no celular. */
    if (!flutuante) {
      botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'gmq-bot-abrir';
      botao.setAttribute('aria-haspopup', 'dialog');
      botao.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 2H4a2 2 0 00-2 2v18l4-4h14a2 2 0 002-2V4a2 2 0 00-2-2zM7 9h10v2H7V9zm0 4h7v2H7v-2zM7 5h10v2H7V5z"/></svg><span>Atendimento</span>';
      botao.addEventListener('click', abrir);
      document.body.appendChild(botao);
    }

    painel = document.createElement('section');
    painel.className = 'gmq-bot';
    painel.setAttribute('role', 'dialog');
    painel.setAttribute('aria-label', 'Atendimento virtual do Gemaque Advogados');
    painel.innerHTML =
      '<div class="gmq-bot-topo">' +
        '<div class="gmq-bot-selo" aria-hidden="true">G</div>' +
        '<div><h2>Atendimento Gemaque</h2><p>Triagem inicial</p></div>' +
        '<button type="button" class="gmq-bot-fechar" aria-label="Fechar atendimento">&times;</button>' +
      '</div>' +
      '<div class="gmq-bot-corpo" role="log" aria-live="polite"></div>' +
      '<div class="gmq-bot-pe"></div>';
    document.body.appendChild(painel);

    corpo = painel.querySelector('.gmq-bot-corpo');
    pe = painel.querySelector('.gmq-bot-pe');
    painel.querySelector('.gmq-bot-fechar').addEventListener('click', fechar);

    interceptarLinksWhatsApp();

    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && estado.aberto) fechar();
    });
  }

  /* Todo botão de WhatsApp da página abre a triagem, em vez de cair direto
     numa conversa crua. Assim nenhum contato chega sem área, situação e
     prazo.

     Não basta interceptar o clique: em navegador embutido, visualizador ou
     app que abre links externos por conta própria, a navegação escapa antes
     do nosso código rodar. Por isso o endereço é REMOVIDO do elemento e
     guardado em data-wa-original — sem href não há o que abrir, em ambiente
     nenhum. O clique passa a ser só nosso.

     Exceções: o encaminhamento final do próprio atendente, o resultado do
     quiz (que já é uma triagem) e qualquer elemento com data-wa-direto. */
  function ehConvertivel(a) {
    return !painel.contains(a) && a.id !== 'quizResultWa' && !a.hasAttribute('data-wa-direto');
  }

  function aoClicarBotao(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    var a = ev.currentTarget;
    medir('bot_abriu_por_link', { origem: a.className || a.id || 'botao' });
    abrir();
  }

  function converterBotoesWhatsApp() {
    var links = document.querySelectorAll('a[href*="wa.me"]');
    [].forEach.call(links, function (a) {
      if (!ehConvertivel(a)) return;
      a.setAttribute('data-wa-original', a.getAttribute('href') || '');
      a.removeAttribute('href');
      a.removeAttribute('target');
      a.removeAttribute('onclick');   /* o clique aqui ainda não é contato: não medir como tal */
      a.setAttribute('role', 'button');
      a.setAttribute('tabindex', '0');
      a.style.cursor = 'pointer';
      a.addEventListener('click', aoClicarBotao);
      a.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { aoClicarBotao(ev); }
      });
    });
  }

  function interceptarLinksWhatsApp() {
    converterBotoesWhatsApp();

    /* Segunda linha de defesa, para links criados depois do carregamento. */
    document.addEventListener('click', function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('a[href*="wa.me"]') : null;
      if (!a || !ehConvertivel(a)) return;
      ev.preventDefault();
      ev.stopPropagation();
      medir('bot_abriu_por_link', { origem: a.className || a.id || 'link' });
      abrir();
    }, true);
  }

  /* ---------- helpers de tela ---------- */
  function fala(html, classe) {
    var d = document.createElement('div');
    d.className = classe || 'gmq-bot-fala';
    d.innerHTML = html;
    corpo.appendChild(d);
    corpo.scrollTop = corpo.scrollHeight;
    return d;
  }

  function euDisse(texto) { fala(escapar(texto), 'gmq-bot-eu'); }

  function escapar(t) {
    return String(t).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function limparPe() { pe.innerHTML = ''; }

  function opcao(texto, aoClicar) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'gmq-bot-op';
    b.textContent = texto;
    b.addEventListener('click', aoClicar);
    pe.appendChild(b);
    return b;
  }

  function campoTexto(dica, aoEnviar) {
    var caixa = document.createElement('form');
    caixa.className = 'gmq-bot-campo';
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = dica || '';
    inp.setAttribute('aria-label', dica || 'Sua resposta');
    var bt = document.createElement('button');
    bt.type = 'submit';
    bt.className = 'gmq-bot-env';
    bt.textContent = 'Enviar';
    caixa.appendChild(inp);
    caixa.appendChild(bt);
    caixa.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var v = inp.value.trim();
      if (!v) { inp.focus(); return; }
      aoEnviar(v);
    });
    pe.appendChild(caixa);
    inp.focus();
  }

  function nota(texto) {
    var p = document.createElement('p');
    p.className = 'gmq-bot-nota';
    p.textContent = texto;
    pe.appendChild(p);
  }

  /* ---------- fluxo ---------- */
  function abrir() {
    estado.aberto = true;
    painel.classList.add('aberto');
    if (botao) botao.hidden = true;
    if (flutuante) flutuante.style.display = 'none';
    if (!corpo.childNodes.length) {
      medir('bot_abriu', { pagina: document.title });
      fala(escapar(ABERTURA));
      perguntarArea();
    }
    painel.querySelector('.gmq-bot-fechar').focus();
  }

  function fechar() {
    estado.aberto = false;
    painel.classList.remove('aberto');
    if (botao) { botao.hidden = false; botao.focus(); }
    if (flutuante) flutuante.style.display = '';
  }

  function perguntarArea() {
    limparPe();
    fala('<strong>Em que podemos ajudar?</strong>');
    MENU.forEach(function (item) {
      opcao(item.texto, function () {
        euDisse(item.texto);
        estado.area = item.chave;
        estado.etapa = 0;
        estado.respostas = [];
        medir('bot_area', { area: FLUXOS[item.chave].rotulo });
        proximaEtapa();
      });
    });
    nota('Atendimento automatizado de triagem — não substitui a avaliação da advogada.');
  }

  function proximaEtapa() {
    var fluxo = FLUXOS[estado.area];
    if (estado.etapa >= fluxo.etapas.length) { perguntarNome(); return; }

    var etapa = fluxo.etapas[estado.etapa];
    limparPe();

    var passo = document.createElement('p');
    passo.className = 'gmq-bot-passo';
    passo.textContent = 'Pergunta ' + (estado.etapa + 1) + ' de ' + fluxo.etapas.length;
    fala(escapar(etapa.pergunta)).insertAdjacentElement('afterbegin', passo);

    if (etapa.tipo === 'texto') {
      campoTexto(etapa.dica, function (valor) {
        euDisse(valor);
        registrar(etapa, valor);
        if (estado.apenasLocal) { perguntarNome(); return; }
        estado.etapa++;
        proximaEtapa();
      });
      return;
    }

    etapa.opcoes.forEach(function (op) {
      opcao(op.v, function () {
        euDisse(op.v);
        registrar(etapa, op.v);
        if (op.urgente) {
          estado.urgente = op.aviso || 'Seu caso envolve prazo em curso. Vou te encaminhar direto ao escritório.';
          medir('bot_urgencia', { area: fluxo.rotulo, motivo: op.v });
          /* Corta as perguntas restantes, mas não abre mão de saber ONDE:
             sem município não dá para identificar órgão, comarca ou plantão. */
          var iLocal = -1;
          for (var i = estado.etapa + 1; i < fluxo.etapas.length; i++) {
            if (fluxo.etapas[i].id === 'local') { iLocal = i; break; }
          }
          if (iLocal > -1) {
            estado.etapa = iLocal;
            estado.apenasLocal = true;
            proximaEtapa();
          } else {
            perguntarNome();
          }
          return;
        }
        estado.etapa++;
        proximaEtapa();
      });
    });
  }

  function registrar(etapa, valor) {
    estado.respostas.push({ rotulo: etapa.rotulo, valor: valor });
  }

  function perguntarNome() {
    limparPe();
    if (estado.urgente) fala('<strong>Atenção ao prazo.</strong> ' + escapar(estado.urgente), 'gmq-bot-aviso');
    fala('Por último: <strong>como podemos te chamar?</strong>');
    campoTexto('Seu nome', function (valor) {
      euDisse(valor);
      estado.nome = valor;
      encerrar();
    });
    var pular = document.createElement('button');
    pular.type = 'button';
    pular.className = 'gmq-bot-sec';
    pular.textContent = 'prefiro não informar';
    pular.addEventListener('click', function () { estado.nome = ''; encerrar(); });
    pe.appendChild(pular);
  }

  function encerrar() {
    estado.encerrado = true;
    limparPe();
    var fluxo = FLUXOS[estado.area];

    var linhas = estado.respostas.map(function (r) {
      return '<b>' + escapar(r.rotulo) + ':</b> ' + escapar(r.valor);
    }).join('<br>');

    fala('Obrigada' + (estado.nome ? ', ' + escapar(estado.nome) : '') +
         '. Este é o resumo que vai para a Dra. Elizângela:');
    fala('<b>Área:</b> ' + escapar(fluxo.rotulo) + (linhas ? '<br>' + linhas : ''), 'gmq-bot-resumo');
    fala(escapar(SIGILO));

    var link = document.createElement('a');
    link.className = 'gmq-bot-wa';
    link.href = 'https://wa.me/' + WA_NUM + '?text=' + encodeURIComponent(mensagem());
    link.target = '_blank';
    link.rel = 'noopener';
    link.innerHTML = ICONE_WA + '<span>Enviar para o escritório</span>';
    link.addEventListener('click', function () {
      medir('bot_concluiu', { area: fluxo.rotulo, urgente: estado.urgente ? 'sim' : 'nao' });
      if (typeof window.trkFormulario === 'function') window.trkFormulario('Atendente - ' + fluxo.rotulo);
      if (typeof window.gaWA === 'function') window.gaWA('atendente_virtual');
    });
    pe.appendChild(link);

    var recomecar = document.createElement('button');
    recomecar.type = 'button';
    recomecar.className = 'gmq-bot-sec';
    recomecar.textContent = 'recomeçar a triagem';
    recomecar.addEventListener('click', function () {
      estado = { aberto: true, area: null, etapa: 0, respostas: [], nome: '', urgente: null, apenasLocal: false, encerrado: false };
      corpo.innerHTML = '';
      fala(escapar(ABERTURA));
      perguntarArea();
    });
    pe.appendChild(recomecar);
  }

  function mensagem() {
    var fluxo = FLUXOS[estado.area];
    var partes = ['Olá, vim pelo site Gemaque Advogados (atendimento virtual).'];
    if (estado.nome) partes.push('Nome: ' + estado.nome);
    partes.push('Área: ' + fluxo.rotulo);
    if (estado.urgente) partes.push('*Caso com prazo em curso.*');
    estado.respostas.forEach(function (r) { partes.push('• ' + r.rotulo + ': ' + r.valor); });
    return partes.join('\n');
  }

  /* ---------- início ---------- */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', montar);
  } else {
    montar();
  }
})();
