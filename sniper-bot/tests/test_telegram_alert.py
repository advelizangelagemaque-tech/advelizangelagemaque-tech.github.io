"""Testes da parte pura do alerta Telegram (sem rede)."""

from bybit_bot.telegram_alert import parse_chat_id, parse_env


def test_parse_env():
    txt = "# config\nTELEGRAM_TOKEN=123:abc\n\nTELEGRAM_CHAT_ID = 999 \n"
    conf = parse_env(txt)
    assert conf["TELEGRAM_TOKEN"] == "123:abc"
    assert conf["TELEGRAM_CHAT_ID"] == "999"


def test_parse_chat_id_pega_o_mais_recente():
    payload = {"result": [
        {"message": {"chat": {"id": 111}}},
        {"message": {"chat": {"id": 222}}},
    ]}
    assert parse_chat_id(payload) == 222


def test_parse_chat_id_edited_e_vazio():
    assert parse_chat_id({"result": [{"edited_message": {"chat": {"id": 5}}}]}) == 5
    assert parse_chat_id({"result": []}) is None
    assert parse_chat_id({}) is None
