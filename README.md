# FinAI-BR

MVP de um agente diário para acompanhar PETR4, BBAS3, VALE3, ITUB4 e CSMG3.
Ele coleta preços e notícias, usa dois nós de análise em LangGraph, persiste o
resultado em PostgreSQL e pode enviar um resumo por e-mail.

## Configuração

```powershell
Copy-Item .env.example .env
```

Preencha `GROQ_API_KEY`. O provedor padrão é Groq; para OpenAI, defina
`LLM_PROVIDER=openai` e `OPENAI_API_KEY`. As duas APIs usam a mesma interface
e retornam JSON validado antes da persistência.

As cotações usam `yfinance` e alternam automaticamente para a Brapi quando o
Yahoo Finance estiver indisponível ou limitar requisições. `BRAPI_TOKEN` é
opcional e pode ser preenchido no `.env` para aumentar os limites da Brapi.

O modelo Groq padrão é `openai/gpt-oss-20b`. Se a API retornar `404`, confira
se o modelo está disponível na sua conta; se retornar `401` ou `403`, gere uma
nova `GROQ_API_KEY` no console da Groq.

## Execução

```powershell
docker compose up --build
# execução manual do ciclo de coleta e análise
docker compose run --rm finai python -m main run
# envio manual do relatório mais recente
docker compose run --rm finai python -m main send-report
# iniciar scheduler e também executar um ciclo imediatamente (sem esperar 18:00)
docker compose run --rm finai python -m main scheduler --run-now
```

O agendador executa coleta/análise às 18:00 BRT, de segunda a sexta, e envia o
relatório mais recente às 08:00 BRT. Feriados da B3 ainda não são considerados.

Para desenvolvimento local, instale as dependências e o projeto em modo
editável, exporte as variáveis do `.env` e execute os comandos normalmente:

```powershell
pip install -r requirements.txt
pip install -e . --no-deps
python -m main run
pytest -q
```

## CI/CD

Pull requests para `main` executam compilação, testes com cobertura e build da
imagem Docker. Depois do merge em `main`, a imagem é publicada no GitHub
Container Registry com uma tag imutável baseada no SHA do commit.

O deploy de produção usa o workflow `Deploy production` e uma VM GCP com Docker
Compose. O workflow executa o Terraform, gera uma chave SSH temporária para a
execução, aguarda o bootstrap da VM e atualiza a imagem. O arquivo `.env` de
produção permanece na VM; segredos não são copiados do repositório.

Configure no Environment `production` do GitHub:

- `GCP_PROJECT_ID`: projeto GCP onde a VM será provisionada.
- `GCP_SA_KEY`: credencial JSON de uma service account com permissões para
	Terraform e o bucket de state.
- `TF_STATE_BUCKET`: bucket GCS previamente criado para o state Terraform.
- `SSH_ALLOWED_CIDRS`: lista Terraform de CIDRs autorizados ao SSH, por
	exemplo `["203.0.113.10/32"]`; nunca use `0.0.0.0/0`.
- `GHCR_DEPLOY_USERNAME`: usuário com permissão de leitura no GHCR.
- `GHCR_DEPLOY_TOKEN`: token do GHCR com permissão `read:packages`.
- `PROD_ENV_FILE`: conteúdo completo do `.env` de produção como secret
	multiline.

O workflow grava `PROD_ENV_FILE` em `/opt/finai/.env` com permissão `600` antes
de iniciar os containers. Não versione esse arquivo.

O deploy usa a imagem `sha-<commit>`. Para rollback, altere manualmente
`FINAI_IMAGE` no arquivo `.image.env` da VPS para uma tag SHA anterior e rode:

```bash
docker compose --env-file .image.env -f docker-compose.prod.yml pull
docker compose --env-file .image.env -f docker-compose.prod.yml up -d
```
