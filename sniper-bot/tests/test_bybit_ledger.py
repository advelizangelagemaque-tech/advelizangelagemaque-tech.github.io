"""Testes da contabilidade real do Delta (aportes vs valor atual = lucro real)."""

import os
import tempfile

from bybit_bot.delta import deposits_timeline, net_deposits, record_deposit


def _tmp():
    d = tempfile.mkdtemp()
    return os.path.join(d, "dep.csv")


def test_net_deposits_soma_aportes_e_retiradas():
    p = _tmp()
    record_deposit(280.83, at_start=True, path=p)   # saldo que já existia
    record_deposit(200.0, path=p)                    # aporte novo
    record_deposit(-50.0, path=p)                    # uma retirada
    assert abs(net_deposits(p) - 430.83) < 1e-6


def test_net_deposits_vazio():
    assert net_deposits(_tmp()) == 0.0               # sem arquivo -> 0


def test_at_start_fica_com_timestamp_zero():
    p = _tmp()
    record_deposit(100.0, at_start=True, path=p)
    record_deposit(30.0, path=p)
    tl = deposits_timeline(p)
    assert tl[0][0] == 0                              # baseline no início do tempo
    assert tl[1][0] > 0                               # aporte novo com hora real


def test_deposito_nao_vira_lucro_falso():
    # o cerne do bug que a usuária pegou: depositar NÃO é lucro.
    p = _tmp()
    record_deposit(280.0, at_start=True, path=p)
    record_deposit(200.0, path=p)                     # depósito de 200 hoje
    tl = deposits_timeline(p)

    def dep_asof(t):
        return sum(a for (dt, a) in tl if dt <= t)

    # saldo pulou de 295 para 495 SÓ por causa do depósito de 200:
    lucro_antes = 295.0 - dep_asof(1)                 # baseline 280
    lucro_depois = 495.0 - dep_asof(9_999_999_999)    # baseline + 200
    assert abs(lucro_antes - 15.0) < 1e-6
    assert abs(lucro_depois - 15.0) < 1e-6            # ESTÁVEL: o depósito não virou ganho
