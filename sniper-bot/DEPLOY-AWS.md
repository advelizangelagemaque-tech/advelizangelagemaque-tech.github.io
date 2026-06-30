# ☁️ Deploy na AWS (EC2) — rodar o sniper 24h

Guia para hospedar o bot numa instância EC2 que fica **ligada o tempo todo**,
snipando sozinha. Faça depois de já ter validado em paper-trading.

> 💡 **Dica de região:** os servidores da Binance ficam em **Tóquio**. Para o
> modo live (velocidade importa no sniping), crie a instância na região
> **ap-northeast-1 (Tokyo)**. Para paper-trading, qualquer região serve.

---

## 1. Criar a instância EC2

No console da AWS → **EC2** → **Launch instance**:

| Campo | Valor sugerido |
|---|---|
| **Name** | `sniper-bot` |
| **AMI** | Amazon Linux 2023 (ou Ubuntu 22.04) |
| **Tipo** | `t3.micro` (free tier) — `t4g.small` se quiser folga |
| **Key pair** | crie/baixe um `.pem` para acessar via SSH |
| **Security group** | só **SSH (porta 22)** de entrada; saída liberada |

> O bot **não precisa de portas de entrada** além do SSH — ele só faz conexões
> de saída para a Binance. Quanto menos exposto, melhor.

---

## 2. Conectar via SSH

No seu computador (amanhã):

```bash
chmod 400 sua-chave.pem
ssh -i sua-chave.pem ec2-user@SEU_IP_PUBLICO        # Ubuntu: ubuntu@SEU_IP
```

---

## 3. Trazer o código para a instância

**Opção A — repositório privado (recomendado):** depois de mover o projeto
para um repo privado seu (veja `GUIA.md`, passo 8):

```bash
git clone https://github.com/SEU_USUARIO/sniper-bot.git
cd sniper-bot
```

**Opção B — copiar do seu PC** com `scp`:

```bash
scp -i sua-chave.pem -r sniper-bot ec2-user@SEU_IP:~/
```

> Nunca deixe o `.env` com chaves entrar no Git. Ele é criado direto na instância.

---

## 4. Instalar tudo (script automático)

```bash
cd ~/sniper-bot
bash deploy/setup-aws.sh
```

Ele instala Python/git, cria o `venv`, instala dependências, **roda os testes**
e cria o `.env`. Depois:

```bash
nano .env            # cole as chaves; deixe USE_TESTNET=true
chmod 600 .env       # só você lê o arquivo de chaves
```

---

## 5. Rodar 24/7 com systemd

Assim o bot sobe sozinho no boot e **reinicia se cair**:

```bash
# ajuste o User/caminhos no arquivo se seu usuário não for ec2-user
sudo cp deploy/sniper.service /etc/systemd/system/sniper.service
sudo systemctl daemon-reload
sudo systemctl enable sniper       # liga no boot
sudo systemctl start sniper        # inicia agora
```

Acompanhar:

```bash
systemctl status sniper            # está rodando?
journalctl -u sniper -f            # logs ao vivo (Ctrl+C para sair)
```

Parar / reiniciar:

```bash
sudo systemctl stop sniper
sudo systemctl restart sniper
```

> O serviço já vem configurado para **paper-trading** (`--paper --mode ws`).
> Para live, edite o `ExecStart` em `/etc/systemd/system/sniper.service`,
> remova o `--paper`, coloque `USE_TESTNET=false` no `.env`, e
> `sudo systemctl daemon-reload && sudo systemctl restart sniper`.

---

## 6. Ver o desempenho

```bash
cd ~/sniper-bot
./venv/bin/python -m sniper.summary       # resumo do trades.csv
```

Quer trazer o `trades.csv` pra analisarmos juntas? Baixe pro seu PC:

```bash
scp -i sua-chave.pem ec2-user@SEU_IP:~/sniper-bot/trades.csv .
```

---

## ✅ Checklist de segurança na AWS

- [ ] Security group **sem** portas de entrada além do SSH
- [ ] `.env` com `chmod 600` e **nunca** no Git
- [ ] API key da Binance **sem permissão de saque**
- [ ] API key **restrita ao IP** da instância (IP elástico ajuda a fixar)
- [ ] Começar em **testnet** (`USE_TESTNET=true`)
- [ ] Repositório **privado** antes do live
- [ ] (Opcional) **billing alarm** na AWS pra não tomar susto na fatura
