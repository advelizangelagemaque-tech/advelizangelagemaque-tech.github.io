"""flashsim — simulador de arbitragem com flash loan (Fase 0: só observa, não opera).

Mede, com preços reais das DEXs, se uma arbitragem daria lucro DEPOIS de descontar
todas as taxas (swap de cada DEX + taxa do flash loan + gás). Não envia transações,
não move dinheiro, não tem chave privada. É um observador honesto para descobrir se
existe borda de verdade ANTES de arriscar qualquer valor.
"""
