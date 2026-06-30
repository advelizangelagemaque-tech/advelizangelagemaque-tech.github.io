"""Testes do notificador Telegram (sem rede)."""

from sniper.notify import Notifier


def test_desligado_sem_credenciais():
    n = Notifier("", "")
    assert n.enabled is False
    # send é no-op e não deve levantar exceção nem acessar a rede
    n.send("oi")


def test_habilitado_com_credenciais(monkeypatch):
    chamadas = {}

    def fake_urlopen(url, data=None, timeout=None):
        chamadas["url"] = url
        chamadas["data"] = data

        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"ok"
        return _Resp()

    monkeypatch.setattr("sniper.notify.urllib.request.urlopen", fake_urlopen)
    n = Notifier("TOKEN", "123")
    assert n.enabled is True
    n.send("ola")
    assert "botTOKEN/sendMessage" in chamadas["url"]
    assert b"ola" in chamadas["data"]


def test_falha_de_rede_nao_propaga(monkeypatch):
    def boom(*a, **k):
        raise OSError("rede caiu")

    monkeypatch.setattr("sniper.notify.urllib.request.urlopen", boom)
    n = Notifier("TOKEN", "123")
    n.send("ola")  # não deve levantar
