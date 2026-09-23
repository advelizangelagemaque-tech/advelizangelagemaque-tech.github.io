# Atendimento digital — Gemaque Advogados

Bot de WhatsApp próprio, com IA, sem plataforma paga no meio.

## Por que próprio

O Chatsac e o Digisac vendem **caixa de entrada compartilhada com automação
engessada** — e nenhum dos dois cumpriu a reunião marcada. O que o escritório
precisa não é caixa de entrada (são 1 a 2 pessoas atendendo): é **triagem que
entende texto livre e separa o que tem prazo correndo do que não tem**.

## Arquitetura

```
WhatsApp (+55 93 98134-3999)
        │
        ▼
Meta Cloud API  ──webhook──►  Cloudflare Worker  ──►  Claude Haiku
                                     │                (linguagem + compreensão)
                                     │
                                     ├──►  KV (memória da conversa, 24h)
                                     └──►  ficha do lead → WhatsApp da Dra.
```

Duas peças móveis. A Alinne tinha cinco (Meta + n8n + banco + planilha + painel)
e quebrava em qualquer uma delas.

## Divisão de responsabilidade

| Camada | Quem decide | O que faz |
|---|---|---|
| Linguagem | IA (Claude Haiku) | entende texto livre, responde no tom certo, não repete pergunta, sem menu |
| Conteúdo | `prompt-sistema.md` | o que pode e o que **nunca** pode afirmar |
| Fechamento | a advogada | a IA marca a conversa; contrato e honorário são sempre humanos |

A IA controla **como** se fala. Ela não controla **o que** se afirma.

## Custo real

| Item | Custo |
|---|---|
| Claude Haiku | ~R$ 0,02 por conversa completa (~20 mensagens) |
| Cloudflare Workers | grátis até 100 mil requisições/dia |
| Cloudflare KV | grátis até 100 mil leituras/dia |
| WhatsApp Cloud API | conversa iniciada pelo cliente: grátis até 01/10/2026 |

**100 conversas no mês ≈ R$ 2.** Depois de out/2026, a Meta passa a cobrar
~R$ 0,035 por mensagem de serviço dentro da janela de 24h — a 100 conversas/mês
isso fica na casa de R$ 70.

Comparação: Chatsac e Digisac cobram mensalidade fixa independente de volume.

## Limites que o bot respeita (Provimento 205/2021 da OAB + LGPD)

O bot **nunca**:

- diz se a pessoa tem razão ou qual será o resultado;
- fala em honorário, valor, faixa de preço ou forma de pagamento;
- promete resultado ou prazo de solução;
- inventa lei, artigo, processo ou decisão;
- pede CPF, RG, senha, dado bancário ou foto de documento;
- se declara humano.

O texto completo dessas regras está em [`prompt-sistema.md`](prompt-sistema.md).
**Leia e risque o que não concordar** — é esse arquivo que governa o bot, não o
código.

## O que empurra para o fechamento

Prazo legal, que no nicho do escritório é curto e verdadeiro:

- **Ambiental:** 20 dias para defesa do auto de infração do IBAMA, contados do
  recebimento.
- **Eleitoral:** direito de resposta conta em horas. 1º turno em **04/10/2026**.
- **Criminal:** audiência de custódia em 24h.
- **Imobiliário/INCRA:** *não* é urgente — e o bot está proibido de fingir que é.

O gatilho é informação verdadeira, não pressão de venda.

## Riscos honestos

| Risco | Como está contido |
|---|---|
| Alucinação (o erro que derrubou a Alinne) | o bot só pode afirmar o que está na base do `prompt-sistema.md`; tudo fora disso vira encaminhamento |
| Injeção de instrução pelo lead | regra explícita de ignorar comandos vindos da mensagem |
| Bot falando o que não devia | 100% das conversas ficam logadas para revisão na primeira semana |
| Perder o controle | botão de desligar: uma variável no Cloudflare volta tudo para atendimento manual |
| Manutenção | é nosso, então é nossa — não há suporte para acionar (o que, visto o Chatsac, não é perda) |

## Estado atual

Já pronto:

- portfólio Meta verificado — `1827370984210861`
- número **+55 93 98134-3999** CONECTADO, com Coexistence funcionando
- app Meta "Triagem Gemaque" — `2017540668972326`
- `prompt-sistema.md` escrito

Falta:

1. **Remover o acesso do Chatsac à conta do WhatsApp** — Meta → Configurações
   da empresa → Contas → Contas do WhatsApp → Gemaque Advogados → Parceiros →
   remover ChatSac. Enquanto ele estiver lá, o webhook fica apontado para o
   painel deles.
2. Criar a conta Cloudflare (grátis) e a chave da API.
3. Escrever o Worker.
4. Teste em número de teste antes de apontar o número real.

**Regra de segurança:** nenhuma chave, token ou segredo é colado no chat. Os
valores vão direto no cofre de variáveis do Cloudflare. O código lê a variável;
o valor nunca precisa ser visto.

## Condição combinada

O bot entrega lead qualificado com prazo identificado. Isso só vira contrato se
alguém falar com a pessoa. **Duas janelas fixas de 15 minutos por dia** para
trabalhar os leads — sem isso, o problema não era o Chatsac e não vai ser o bot:
13 dos 18 leads da Alinne morreram sem ninguém abrir.
