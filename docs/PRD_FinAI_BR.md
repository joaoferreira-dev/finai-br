# Product Requirement Document (PRD)

## 1. Visão Geral do Projeto
* **Nome do Projeto:** Agente de IA para o Mercado Financeiro Brasileiro (FinAI-BR)
* **Status:** Planejamento
* **Autor:** Engenheiro de Software Solo
* **Objetivo:** Desenvolver um sistema autônomo baseado em agentes de Inteligência Artificial que monitora, coleta e analisa dados numéricos (preços) e textuais (notícias) do mercado financeiro brasileiro (B3), gerando relatórios diários de sentimento de mercado altamente estruturados para apoiar a tomada de decisão.

## 2. Objetivos de Engenharia e Aprendizado
* **Prática de Engenharia de Software:** Aplicar conceitos de arquitetura limpa, isolamento de escopo, persistência de dados estruturados e automação de rotinas (cronjobs/agendadores).
* **Prática de IA:** Dominar a orquestração de múltiplos agentes com papéis definidos utilizando o LangGraph, engenharia de prompts avançada para análise técnica/fundamentalista e estruturação de respostas via JSON (Structured Outputs).

## 3. Escopo do MVP (Produto Mínimo Viável)
O sistema operará de forma totalmente automatizada uma vez por dia, focando em um conjunto inicial de **5 ações de alta liquidez na B3**:
* PETR4 (Petrobras)
* BBAS3 (Banco do Brasil)
* VALE3 (Vale)
* ITUB4 (Itaú Unibanco)
* CSMG3 (Copasa)

### 3.1. Funcionalidades Principais (In-Scope)
* **Coleta Automática de Dados:** Captura diária do preço de fechamento, variação percentual e volume das ações selecionadas.
* **Agregação de Notícias:** Varredura diária de portais de notícias (via RSS/Google News) buscando menções específicas aos tickers rastreados.
* **Análise por Agentes de IA:** 
    * *Agente Pesquisador:* Filtra e resume notícias macroeconômicas e corporativas relevantes.
    * *Agente Analista Financeiro:* Cruza os dados numéricos de mercado com os resumos de notícias para definir o "Sentimento do Mercado" (Otimista, Neutro, Pessimista).
* **Persistência de Histórico:** Armazenamento estruturado de todas as coletas e análises em banco de dados relacional.
* **Disparos de Alertas:** Envio do relatório consolidado formatado diretamente para o usuário via email.

### 3.2. Fora de Escopo (Out-of-Scope)
* Execução de ordens de compra/venda automáticas (Trading Bot).
* Interface gráfica web ou mobile (Dashboard) nesta primeira fase.
* Análise de derivatívos (Opções/Futuros) ou fundos imobiliários (FIIs).

## 4. Requisitos Funcionais (RF)
* **RF-001:** O sistema deve extrair dados de cotação da B3 diariamente após o fechamento do pregão (18h00 BRT).
* **RF-002:** O sistema deve buscar as notícias publicadas nas últimas 24 horas sobre as ações cadastradas.
* **RF-003:** O agente de IA deve classificar o sentimento do mercado para cada ação em uma escala padronizada: Alta Confiança de Alta, Moderado, Neutro, Moderado de Baixa, Alta Confiança de Baixa.
* **RF-004:** O sistema deve estruturar o output da IA obrigatoriamente em formato JSON para garantir a consistência antes de salvar no banco de dados.
* **RF-005:** O sistema deve enviar uma notificação formatada por email até as 08h00 do dia útil seguinte contendo o resumo consolidado.

## 5. Requisitos Não-Funcionais (RNF)
* **RNF-001 (Linguagem):** Toda a base de código do ecossistema deve ser desenvolvida em **Python 3.11+**.
* **RNF-002 (Banco de Dados):** Deve utilizar **PostgreSQL** para persistência, garantindo integridade referencial entre as ações, preços históricos e relatórios.
* **RNF-003 (Custo de Operação):** O consumo de tokens de LLM deve priorizar modelos eficientes de baixo custo (ex: GPT-4o-mini ou Llama 3 via Groq) para viabilizar a execução solo contínua.
* **RNF-004 (Resiliência):** Falhas em APIs externas (ex: erro ao coletar notícias de uma ação específica) não devem derrubar o fluxo completo do sistema; o erro deve ser logado e o processo deve continuar para as demais ações.

## 6. Arquitetura de Dados & Integrações
* **Dados Financeiros:** Biblioteca `yfinance` ou API da `Brapi` para dados de fechamento.
* **Dados de Texto:** `feedparser` conectado ao RSS do Google News Brasil.
* **Orquestração de IA:** Framework `LangGraph` para gerenciar a passagem de contexto entre o Agente Pesquisador e o Agente Analista.

## 7. Cronograma Proposto de Implementação
* **Semana 1:** Setup do ambiente, modelagem do banco de dados PostgreSQL e criação dos scripts de ingestão (`yfinance` + RSS).
* **Semana 2:** Desenvolvimento da camada de IA, refinamento de prompts e garantia de outputs estruturados em JSON.
* **Semana 3:** Integração dos componentes, configuração do agendamento automatizado e desenvolvimento do serviço de envio de emails.
* **Semana 4:** Testes de ponta a ponta, tratamento de exceções, criação de logs e publicação do repositório no GitHub com documentação técnica completa.
