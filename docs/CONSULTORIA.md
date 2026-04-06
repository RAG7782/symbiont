# SYMBIONT — Pacotes de Consultoria

> Servicos profissionais de implantacao e suporte

---

## Tier 1: Setup Assistido — R$ 2.000 (unico)

**Para**: Profissional individual ou escritorio pequeno que quer IA local funcionando rapido.

**Escopo (3-5 dias)**:
- Instalacao remota de Ollama + modelos (7 modelos, ~83 GB)
- Instalacao e configuracao do SYMBIONT v0.3.0
- Configuracao de 3 presets de dominio (ex: juridico, coding, geral)
- Configuracao do `sym serve` como servico persistente
- Treinamento 1:1 por videoconferencia (1 hora)
- Dataset inicial personalizado (10-20 exemplos do dominio do cliente)

**Entregaveis**:
- [x] SYMBIONT operacional com Ollama
- [x] 3 presets configurados
- [x] Dataset JSONL do dominio
- [x] Guia de uso personalizado (PDF)
- [x] 30 dias de suporte por email/Telegram

**SLA**: Resposta em ate 24h uteis.

**Requisitos do cliente**: MacBook com 16+ GB RAM ou PC com GPU.

---

## Tier 2: Pro — R$ 5.000 (unico)

**Para**: Escritorio medio ou startup que quer IA integrada ao fluxo de trabalho.

**Escopo (10-15 dias)**:
- Tudo do Tier 1 +
- Deploy de colonia remota em 1 VPS do cliente
- Configuracao de Kestra com 5+ flows personalizados
- Integracao com 1 sistema externo (email, CRM, ou Slack)
- Dashboard personalizado com metricas do cliente
- Dataset expandido (50+ exemplos)
- Fine-tune de 1 modelo no dominio do cliente (Modal GPU)
- Treinamento da equipe (ate 5 pessoas, 2 horas)

**Entregaveis**:
- [x] Tudo do Tier 1
- [x] Colonia remota operacional
- [x] 5+ Kestra flows
- [x] 1 integracao externa
- [x] Modelo fine-tuned deployado no Ollama
- [x] 60 dias de suporte por email/Telegram/call

**SLA**: Resposta em ate 12h uteis. 1 call de suporte/semana.

---

## Tier 3: Enterprise — R$ 15.000 (unico)

**Para**: Empresa ou departamento que quer IA como infraestrutura de produção.

**Escopo (30-45 dias)**:
- Tudo do Tier 2 +
- Deploy distribuido em ate 3 servidores (federation completa)
- Squads configurados por departamento/projeto
- Integracao com ate 3 sistemas (CRM, email, webhook, Slack, etc)
- Fine-tune de ate 3 modelos (dominio juridico, coding, geral)
- Pipeline CI/CD para deploy automatizado
- Dashboard enterprise com alertas Telegram
- Documentacao tecnica completa
- Treinamento da equipe (ate 15 pessoas, 4 horas)
- Sessao mensal de otimizacao (3 meses)

**Entregaveis**:
- [x] Tudo do Tier 2
- [x] Federation de 3+ organismos
- [x] Squads por departamento
- [x] 3 integracoes externas
- [x] 3 modelos fine-tuned
- [x] Pipeline CI/CD
- [x] 90 dias de suporte prioritario

**SLA**: Resposta em ate 4h uteis. Call de emergencia 24/7.

---

## Servicos Adicionais (avulsos)

| Servico | Preco | Descricao |
|---------|-------|-----------|
| Fine-tune adicional | R$ 1.500 | 1 modelo + dataset + deploy |
| Colonia adicional | R$ 800 | Deploy em 1 VPS extra |
| Integracao adicional | R$ 1.200 | Conectar a 1 sistema extra |
| Treinamento extra | R$ 500/h | Sessao individual ou equipe |
| Suporte mensal | R$ 800/mes | Suporte continuo + 1 call/semana |
| Consultoria estrategica | R$ 2.000/sessao | Arquitetura de IA para o negocio |

---

## Processo de Contratacao

1. **Diagnostico** (gratis, 30min): Entender necessidades e definir escopo
2. **Proposta**: Documento com escopo, prazo e preco
3. **Kickoff**: Pagamento de 50% + inicio do trabalho
4. **Entrega**: Implantacao + treinamento + documentacao
5. **Aceite**: Pagamento de 50% restante + inicio do suporte

---

## Contato

- Email: renatoapgomes@gmail.com
- GitHub: github.com/RAG7782/symbiont
- LinkedIn: linkedin.com/in/renatoapgomes

---

## Perguntas Frequentes

**Preciso de servidor dedicado?**
Nao para Tier 1. Roda no seu Mac/PC. Tiers 2-3 podem usar VPS (R$50-150/mes).

**Quanto custa manter o SYMBIONT rodando?**
R$0 se usar apenas modelos locais. R$5-30/mes se usar cloud (OpenRouter/Modal) para tarefas pesadas.

**Meus dados ficam seguros?**
100% local no Tier 1. Nos Tiers 2-3, dados trafegam apenas pela rede Tailscale (criptografada) entre seus servidores.

**Posso expandir depois?**
Sim. Comece com Tier 1 e adicione colonias, fine-tunes e integracoes avulsas conforme necessidade.

**Voces fazem manutencao continua?**
Sim, via servico de Suporte Mensal (R$800/mes). Inclui atualizacoes, monitoramento e 1 call semanal.
