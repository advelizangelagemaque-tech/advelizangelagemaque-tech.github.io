/*!
 * Gemaque Advogados — medição de campanhas (GA4 + Google Ads)
 * ---------------------------------------------------------------------------
 * COMO CONFIGURAR (3 campos, uma única vez):
 *
 *   1. adsId        → ID de conversão do Google Ads, no formato 'AW-123456789'.
 *                     Google Ads > Ferramentas > Conversões > Tag do Google.
 *   2. conversoes.whatsapp  → rótulo da conversão "Clique no WhatsApp".
 *   3. conversoes.formulario→ rótulo da conversão "Envio de formulário".
 *                     O rótulo aparece como 'AW-123456789/AbC-D_efGh12345';
 *                     use apenas a parte depois da barra.
 *
 * Enquanto adsId estiver vazio, o site continua medindo tudo no GA4 e NÃO
 * envia conversão ao Google Ads (evita disparo com ID errado).
 * ---------------------------------------------------------------------------
 */
(function () {
  'use strict';

  var CFG = {
    ga4Id: 'G-1CYK4E7279',
    adsId: '',
    conversoes: { whatsapp: '', formulario: '' },
    cookieDias: 90
  };

  var COOKIE = 'gmq_ref';
  var CLICK_IDS = ['gclid', 'gbraid', 'wbraid', 'msclkid', 'fbclid'];
  var UTMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'];

  /* ---------- utilidades ---------- */

  function lerCookie(nome) {
    var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + nome + '=([^;]*)'));
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(m[1])); } catch (e) { return null; }
  }

  function gravarCookie(nome, valor) {
    try {
      var seguro = location.protocol === 'https:' ? ';secure' : '';
      document.cookie = nome + '=' + encodeURIComponent(JSON.stringify(valor)) +
        ';path=/;max-age=' + (CFG.cookieDias * 86400) + ';samesite=lax' + seguro;
    } catch (e) { /* cookies bloqueados */ }
  }

  function enviar(evento, dados) {
    try { if (typeof window.gtag === 'function') window.gtag('event', evento, dados || {}); }
    catch (e) { /* medição nunca pode quebrar a página */ }
  }

  /* ---------- 1. captura da origem do visitante ---------- */

  function capturarOrigem() {
    var p = new URLSearchParams(location.search);
    var novo = {}, temClique = false;

    CLICK_IDS.forEach(function (k) {
      var v = p.get(k);
      if (v) { novo[k] = v; temClique = true; }
    });
    UTMS.forEach(function (k) {
      var v = p.get(k);
      if (v) { novo[k] = v; temClique = true; }
    });

    if (temClique) {
      novo.ts = new Date().toISOString().slice(0, 10);
      if (!novo.utm_source && novo.gclid) { novo.utm_source = 'google'; novo.utm_medium = 'cpc'; }
      gravarCookie(COOKIE, novo);
      return novo;
    }
    return lerCookie(COOKIE) || {};
  }

  var ORIGEM = capturarOrigem();

  /* Etiqueta curta anexada à mensagem do WhatsApp, para o escritório saber de
     qual campanha veio o contato mesmo antes de olhar o relatório. */
  function etiqueta() {
    var id = ORIGEM.gclid || ORIGEM.gbraid || ORIGEM.wbraid || ORIGEM.msclkid || ORIGEM.fbclid;
    if (!id && !ORIGEM.utm_campaign) return '';
    var partes = [];
    if (ORIGEM.utm_source) partes.push(ORIGEM.utm_source);
    if (ORIGEM.utm_campaign) partes.push(ORIGEM.utm_campaign);
    if (id) partes.push(String(id).slice(0, 10));
    return ' [ref: ' + partes.join('/') + ']';
  }

  function comEtiqueta(url) {
    try {
      var tag = etiqueta();
      if (!tag || typeof url !== 'string' || url.indexOf('wa.me') < 0) return url;
      var u = new URL(url, location.href);
      var texto = u.searchParams.get('text') || '';
      /* compara o texto já decodificado: no link a etiqueta aparece como
         %5Bref%3A..., e conferir a string crua deixaria duplicar a cada clique */
      if (texto.indexOf('[ref:') > -1) return url;
      u.searchParams.set('text', texto + tag);
      return u.toString();
    } catch (e) { return url; }
  }

  /* ---------- 2. conversões ---------- */

  var adsAtivo = /^AW-\d+$/.test(CFG.adsId);

  if (adsAtivo) {
    try {
      if (typeof window.gtag === 'function') {
        window.gtag('config', CFG.adsId, { allow_enhanced_conversions: true });
        window.gtag('set', 'url_passthrough', true);
      }
    } catch (e) { /* ignora */ }
  }

  function conversaoAds(rotulo, dados) {
    if (!adsAtivo || !rotulo) return;
    enviar('conversion', {
      send_to: CFG.adsId + '/' + rotulo,
      campanha: ORIGEM.utm_campaign || '',
      origem: (dados && dados.origem) || ''
    });
  }

  function contexto(extra) {
    var d = {
      pagina: document.title,
      utm_source: ORIGEM.utm_source || '(direto)',
      utm_medium: ORIGEM.utm_medium || '(nenhum)',
      utm_campaign: ORIGEM.utm_campaign || '(nenhuma)',
      tem_gclid: ORIGEM.gclid ? 'sim' : 'nao'
    };
    for (var k in extra) { if (Object.prototype.hasOwnProperty.call(extra, k)) d[k] = extra[k]; }
    return d;
  }

  /* Clique em qualquer canal de WhatsApp (botão do topo, flutuante, links). */
  window.gaWA = function (origem) {
    enviar('clique_whatsapp', contexto({ origem: origem || 'nao_informada' }));
    conversaoAds(CFG.conversoes.whatsapp, { origem: origem });
  };

  /* Envio dos formulários e dos quizzes de diagnóstico. */
  window.trkFormulario = function (area) {
    enviar('submit_formulario_contato', contexto({ area: area || 'nao_informada' }));
    conversaoAds(CFG.conversoes.formulario, { origem: 'formulario' });
  };

  /* Clique para ligar / e-mail — úteis como conversões secundárias. */
  window.gaTelefone = function () { enviar('clique_telefone', contexto({})); };
  window.gaEmail = function () { enviar('clique_email', contexto({})); };

  /* ---------- 3. etiqueta de origem nos links de WhatsApp ---------- */

  /* No clique (e não só no carregamento): os links gerados depois, como o do
     resultado do quiz, também recebem a etiqueta de campanha. */
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href*="wa.me"]') : null;
    if (a) { a.href = comEtiqueta(a.href); }
  }, true);

  var abrirOriginal = window.open;
  window.open = function (url) {
    try { arguments[0] = comEtiqueta(url); } catch (e) { /* ignora */ }
    return abrirOriginal.apply(window, arguments);
  };

  /* ---------- 4. diagnóstico ---------- */
  /* Abra o site com ?trkdebug=1 para conferir no console o que está medido. */
  if (new URLSearchParams(location.search).get('trkdebug') === '1') {
    /* eslint-disable no-console */
    console.log('[Gemaque] origem:', ORIGEM);
    console.log('[Gemaque] GA4:', CFG.ga4Id, '| Google Ads:', adsAtivo ? CFG.adsId : 'NÃO CONFIGURADO');
    console.log('[Gemaque] conversões Ads:', CFG.conversoes);
  }
})();
