"""cexarb — medidor de arbitragem entre corretoras (CEX-CEX), Fase 0.

Lê os livros de ordem públicos de duas corretoras (ex: Bybit e Binance) e mede o
lucro REAL possível depois das taxas — sem chave, sem login, sem mover dinheiro.
Serve para testar, com dados reais, se o 'gap' que aparece na tela sobrevive aos
custos. (Isto NÃO usa flash loan: flash loan é on-chain; aqui é CEX-CEX com
capital próprio.)
"""
