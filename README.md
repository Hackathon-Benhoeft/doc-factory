# Document Factory
### *OCR + Inteligência Artificial para Gestão Inteligente de Documentos*

> **Proposta de Valor:** Transformar grandes volumes de documentos em informações organizadas, compreensíveis e priorizadas.

---

## 🎯 O Problema vs. A Solução

| Desafios do Mercado | Nossa Solução |
|---|---|
| **Excesso de documentos físicos e digitais** sem padronização | **Ingestão multiformato** (PDF, imagens e documentos digitalizados) |
| **Leitura manual lenta**, custosa e sujeita a falhas | **OCR inteligente + IA contextual** para leitura e extração em escala |
| **Informação difícil de encontrar** em arquivos densos | **PDFs pesquisáveis**, indexação full-text e resumos automáticos |
| **Falta de priorização e triagem** de casos urgentes | **Classificação automática por tipo** e segmentação inteligente de lotes |

---

## 🏆 Vantagens Competitivas & Diferenciais

- 📑 **Leitura de Documentos Difíceis:** Tratamento de imagens e pipeline otimizado para digitalizações de baixa qualidade ou documentos ruidosos.
- 🧠 **Interpretação Contextual via LLM:** Muito além de um simples OCR; compreende o significado, valida coerência e identifica o tipo documental com precisão.
- 🤝 **Classificação Híbrida + Revisão Humana (HITL):** Automação em alta escala com salvaguarda operacional: documentos com menor confiança são encaminhados a uma fila intuitiva de validação humana.
- 🔒 **Privacidade & LGPD Nativa:** Detecção e tarjamento irreversível de dados sensíveis (CPF, CNPJ, RG, contatos) tanto no texto quanto visualmente no PDF.

---

## 👥 Público & Casos de Uso

- **Órgãos Públicos:** Digitalização e tramitação rápida de processos e arquivos históricos.
- **Escritórios Jurídicos & Compliance:** Análise, indexação e busca em lotes contratuais e peças processuais.
- **Hospitais & Clínicas:** Gestão e proteção de prontuários médicos e laudos.
- **Empresas & Setores Administrativos:** Triagem de notas fiscais, cadastros e documentação de RH.

---

## 📊 Métricas de Impacto

- **Taxa de Automação:** Percentual de documentos classificados e processados sem necessidade de intervenção humana.
- **Tempo Economizado:** Redução drástica das horas gastas em triagem manual e digitação de dados.
- **Precisão da Leitura:** Alto índice de assertividade no OCR e na extração semântica.
- **Volume Processado:** Capacidade elástica de digerir milhares de páginas por lote com workers distribuídos.

---

## 🛠️ Stack Tecnológica

- **Backend:** Python 3.11+ / FastAPI
- **Processamento & OCR:** PyMuPDF (fitz) / Tesseract OCR (`por`)
- **Persistência & Storage:** PostgreSQL 16 (ou SQLite) / MinIO / S3
- **Modelos de IA:** Conector agnóstico para qualquer API compatível com OpenAI (Gemini, OpenAI, Ollama, DeepSeek)

---

## ⚡ Como Rodar

### 1. Via Docker Compose (Stack Completa)

```bash
# Execute na raiz do repositório
docker compose up --build --scale worker=3
```
- **Frontend:** `http://localhost:5173`
- **API & Swagger:** `http://localhost:8000/docs`
- O login fica ativo no Docker Compose. Crie uma conta em `http://localhost:5173/cadastro`; novas contas recebem o perfil **revisor**. Ao iniciar, contas existentes com perfil analista também são promovidas para revisor; administradores mantêm o perfil.
- Defina `JWT_SEGREDO` no `backend/.env` para manter tokens válidos após reinicializações. Para criar um administrador inicial, defina `ADMIN_SENHA` antes de iniciar pela primeira vez.

### 2. Localmente (Desenvolvimento Rápido)

```bash
cd backend

# Instalar dependências e preparar variáveis
pip install -r requirements.txt
cp .env.example .env

# Iniciar API com worker inline
uvicorn app.main:app --reload
```

### 3. Teste Rápido com Lote Simulado

```bash
python backend/scripts/gerar_lote_teste.py lote_teste.pdf
curl -F arquivo=@lote_teste.pdf http://localhost:8000/lotes
```

---

## 📁 Estrutura do Repositório

```text
├── backend/
│   ├── app/
│   │   ├── api/          # Endpoints (lotes, documentos, fila de revisão, busca)
│   │   ├── pipeline/     # Pipeline: rasterização, OCR, anonimização, classificação, segmentação
│   │   ├── llm/          # Provedores de IA / LLM plugáveis
│   │   └── worker.py     # Worker assíncrono por página com retomada após falhas
│   ├── docker-compose.yml
│   └── requirements.txt
├── diagramas/            # Diagramas de estados e modelo relacional
├── arquitetura.html      # Apresentação visual e interativa da arquitetura
└── README.md
```

## Recursos de destaque (F0–F9)

| Recurso | Como demonstrar |
|---|---|
| F0 Uso de IA visível | `GET /lotes/{id}` → `ia`; Painel → cartão "Uso de IA"; documento → `decidido_por` |
| F1 Fraude "atenção" vai para a revisão | reenviar o mesmo lote com outro hash → documentos na fila com "atenção de fraude" |
| F2 Pré-revisão | tela Fila de revisão → "Sugestão da IA" (sem IA, "por regras") |
| F3 Exigências por função | Trabalhadores → eletricista exige NR-10/NR-35; `PUT /trabalhadores/{id}/funcao` |
| F4 Regras em português | tela Regras → "mantenha o contrato inteiro junto" |
| F5 % de acerto | `python scripts/avaliar_acerto.py lote_terceiros.pdf --sem-llm` (também roda no CI) |
| F6 Alertas de vencimento | tela Alertas (modo simulado); para enviar de verdade: `ALERTAS_MODO=real` + `EVOLUTION_*`/`SMTP_*` no `.env` |
| F7 Portal do fornecedor | tela Fornecedores → gerar link → `/portal/<token>` |
| F8 Várias folhas numa imagem | enviar `docs/exemplos/duas_folhas.png` → lote de 2 páginas |
| F9 Front com dados reais | Painel, Relatórios, Fila, Trabalhadores, Vencimentos, Automação, Alertas, Regras, Fornecedores |

As configurações novas estão em `backend/.env.example`. O roteiro está em `docs/ROTEIRO_DEMO.md`, e as premissas e limitações em `docs/PREMISSAS_LIMITACOES.md`.
