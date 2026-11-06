# Document Factory — backend

Hack Garanhuns Tech 2026 · Desafio 3. Recebe lotes digitalizados grandes (PDF/TIFF), separa cada
documento, classifica o tipo, gera PDF pesquisável e anonimizado e manda as dúvidas para revisão humana.
Feito para **gestão de documentos de terceiros**: diz até quando cada documento vale (com a prova),
monta o dossiê de cada trabalhador sem guardar o CPF e aponta o que falta, o que venceu e o que vai vencer.

**Guia para o front:** [`API.md`](API.md) — cada tela e componente → rota e campos.

## Cópia e restauração local

Pare a API e todos os workers antes de criar a cópia. O ZIP contém o banco e os
arquivos originais e pode incluir dados pessoais; ele não é criptografado.

```powershell
python scripts/backup_local.py criar --dados ./data --saida ../backup-docfactory.zip --offline-confirmado
python scripts/backup_local.py restaurar --arquivo ../backup-docfactory.zip --destino ../dados-restaurados
```

A restauração exige um diretório novo e verifica os hashes dos arquivos e a
integridade do SQLite. Teste a restauração separadamente antes de usá-la.

Ao reprocessar um lote com documentos, o sistema preserva um retrato anterior,
suas revisões e seus PDFs em `GET /lotes/{id}/versoes`. Selecione o lote na
tela de documentos para comparar. As correções anteriores não são reaplicadas
automaticamente; o resultado novo precisa de revisão.

## O que o sistema faz

| Capacidade | Como |
|---|---|
| Separar e agrupar | sinais de início/fim por página ("Página 1 de N", título no topo, CPF de outra pessoa, página em branco) |
| Classificar | 14 tipos (`tipos.py`): ASO, ficha de EPI, certificado de NR, CTPS, contracheque, guia do FGTS, CND federal, CRF do FGTS, CNDT, contrato, nota fiscal, identidade, comprovante, certidão — regras + modelo opcional com descrição de cada tipo |
| OCR pesquisável | Tesseract em português; PDF com texto invisível; busca no texto |
| Anonimizar | CPF, CNPJ, RG, e-mail, telefone, nomes, endereço e CEP — no banco, na busca, no resumo, na imagem enviada ao modelo e no PDF (tarja real) |
| Validade com prova | data escrita no texto → modelo (só se o trecho citado existir no texto) → regra do tipo (ASO 12 meses, CRF 30 dias, NR por norma). Status vigente / vencendo / vencido, com a evidência |
| Dossiê do trabalhador | CPF vira impressão digital (HMAC) antes da máscara; o CPF nunca é guardado. Checklist de exigidos: faltando, vencido, vencendo, duplicado |
| Resumo e campos-chave | modelo com o texto já anonimizado (documento grande: em partes); sem modelo, resumo simples |
| Prioridade | tipo + modelo + lote urgente + vencimento; fila de revisão por prioridade e confiança |
| Meta de automação | limiar ajustável ao vivo, curva automação × revisão, acurácia medida pelas revisões humanas |
| Revisão humana e auditoria | aprovar, trocar tipo, mudar prioridade, dividir, juntar; trilha com antes/depois |
| Aprender com correções | cada troca de tipo vira regra (título → tipo, vale sem modelo) e exemplo para o modelo; dá para desativar |
| Sinais de fraude | PDF editado/modificado, documento repetido em outro lote, páginas misturadas, datas impossíveis → confiável / atenção / alto risco, com evidência |
| Telas | `/painel`, `/documentos` (filtros e paginação), `/relatorios`, `/trabalhadores`, `/vencimentos`, `.zip` do lote |
| Login e perfis | JWT, analista < revisor < admin (desligado por padrão para a demo); bloqueio após 5 senhas erradas |
| Segurança | modo produção recusa configuração insegura; arquivo conferido pelo conteúdo; erros sem detalhe interno; cabeçalhos de segurança; documento enviado ao modelo como dado (não instrução); `DELETE /lotes/{id}` para eliminação (LGPD) |

**Stack:** FastAPI · PyMuPDF · Tesseract (`por`) · SQLAlchemy (SQLite no dev, PostgreSQL em produção) ·
storage local ou MinIO/S3 · modelo plugável (qualquer API compatível com OpenAI).

## Rodar em 1 minuto (sem Docker)

```bash
sudo apt install tesseract-ocr tesseract-ocr-por        # Windows: instalador UB-Mannheim + por.traineddata
pip install -r requirements.txt
cp .env.example .env                                    # WORKER_INLINE=true → API + worker num processo só
uvicorn app.main:app --reload                           # http://localhost:8000/docs
python scripts/gerar_lote_teste.py lote_teste.pdf       # lote falso de 11 páginas / 6 documentos
python scripts/gerar_lote_bernhoeft.py terceiros.pdf    # gestão de terceiros: 14 páginas / 12 documentos
                                                        # (datas relativas a hoje: vencidos, vencendo, vigentes)
curl -F arquivo=@lote_teste.pdf http://localhost:8000/lotes
pytest -q                                               # 80 testes, inclui ponta a ponta
```

## Rodar a stack completa

```bash
# da RAIZ do repositório (docker-compose.yml do projeto):
docker compose up --build --scale worker=3              # Postgres + API + 3 workers + front em :5173
```

## Estrutura

```
app/
  main.py              FastAPI, CORS, API key, /health, /metricas
  config.py            todas as configurações (env/.env)
  security.py          senhas (PBKDF2) e tokens JWT
  db.py · models.py    Lote, Pagina, Documento, Revisao, Usuario (+ índice GIN full-text pt no Postgres)
                       + migração leve: adiciona colunas novas em bancos antigos
  storage.py           LocalStorage | S3Storage (MinIO) — banco guarda só a chave
  tipos.py             ← TAXONOMIA: 14 tipos, descrições, setores, regras de validade e exigidos
  worker.py            fila por página, retomada após falha, SKIP LOCKED
  api/lotes.py         upload em streaming, progresso, páginas, miniaturas, reprocessar
  api/documentos.py    documentos, PDF, resumo, fila de revisão, dividir/juntar, auditoria, busca
  api/auth.py          login e usuários (perfis analista/revisor/admin)
  api/painel.py        telas: /painel e /relatorios
  api/trabalhadores.py dossiê do trabalhador e checklist
  api/automacao.py     meta de automação (curva, limiar ao vivo)
  llm/                 interface + cliente OpenAI-compatível (OpenAI, Gemini, DeepSeek, Ollama…)
  pipeline/
    rasterizar.py      1. PyMuPDF → PNG 300 dpi por página (ou texto nativo se o PDF for digital)
    ocr.py             2. Tesseract image_to_data → texto + caixa + confiança por palavra
    anonimizar.py         CPF/CNPJ/RG/e-mail/telefone + nomes + endereço/CEP → texto, imagem e PDF
    classificar.py     3. regras (palavras + título no topo) + modelo → tipo + confiança
    segmentar.py       4. sinais de início/fim → documentos (função pura, testável)
    montar.py          5. PyMuPDF → PDF pesquisável (texto invisível) + PDF com redaction real
    resumir.py         6. resumo (modelo, em partes se for grande; ou simples) + prioridade
    validade.py           validade com evidência: texto → modelo → regra do tipo
    identidade.py         impressão digital do CPF (HMAC) — o CPF não é guardado
    checklist.py          exigidos por trabalhador: faltando, vencido, vencendo, duplicado
    automacao.py          limiar em tempo real, curva e acurácia pelas revisões
    aprendizado.py        correções humanas → regra por título + exemplos para o modelo
    fraude.py             sinais de adulteração com veredito e evidência
    orquestrador.py       liga tudo, grava banco/storage
scripts/gerar_lote_teste.py · gerar_lote_bernhoeft.py
tests/                 80 testes (pipeline, terceiros, validade, dossiê, telas, automação, anonimização, login)
```

## Endpoints

| Método | Rota | Perfil mínimo* | Para quê |
|---|---|---|---|
| POST | `/lotes` | analista | upload (multipart `arquivo`, `prioridade` = alta/media/baixa); 409 se o mesmo arquivo (SHA-256) já foi enviado |
| GET | `/lotes`, `/lotes/{id}` | analista | lista / progresso (`paginas_processadas`, `progresso`) |
| GET | `/lotes/{id}/paginas` | analista | status, tipo, confiança e sinais de cada página |
| GET | `/lotes/{id}/paginas/{n}/imagem?thumb=true` | analista | miniatura (`thumb=false`, imagem sem tarja: revisor) |
| GET | `/lotes/{id}/documentos` | analista | documentos detectados, com resumo e prioridade |
| POST | `/lotes/{id}/reprocessar[?tudo=true]` | revisor | recoloca páginas com falha (ou todas) na fila |
| GET | `/documentos?tipo=&status_revisao=&prioridade=&lote_id=` | analista | documentos de todos os lotes, com filtros |
| GET | `/documentos/{id}/pdf[?anonimizado=false]` | analista | PDF pesquisável, anonimizado por padrão (original: revisor) |
| POST | `/documentos/{id}/resumo` | revisor | gera o resumo de novo |
| GET | `/documentos/{id}/revisoes` | analista | trilha de auditoria (quem, quando, antes e depois) |
| GET | `/revisao/fila[?lote_id=]` | analista | pendentes: prioridade mais alta primeiro, depois menor confiança |
| POST | `/documentos/{id}/revisao` | revisor | `aprovar` · `alterar_tipo` · `alterar_prioridade` · `dividir` (`pagina_corte`) · `juntar_proximo` |
| GET | `/busca?q=&tipo=` | analista | full-text em português (stemming: "contrato" acha "contratada") |
| GET | `/tipos`, `/metricas` | analista | taxonomia; automação, confiança, docs por tipo e por prioridade |
| POST | `/auth/login` · GET `/auth/eu` | — | login (JWT) · quem está logado |
| GET/POST | `/usuarios` · POST `/usuarios/{id}/desativar` | admin | gestão de usuários |
| GET | `/health` | — | API, Tesseract, idioma do OCR, modelo e login |

\* Só vale com `AUTH_ATIVO=true`. Desligado (padrão, modo demo), a API fica aberta.

## Resumo de cada documento

Depois que o documento é montado (e de novo após dividir, juntar ou trocar o tipo):

- **Com modelo configurado:** o modelo recebe **só o texto já anonimizado** e o tipo do documento, e
  devolve um resumo de 2 a 3 frases, os campos-chave do tipo (definidos em `tipos.py`, ex.: contrato →
  partes, objeto, valor, vigência, foro) e uma sugestão de prioridade com o motivo. Campo que não está
  no texto volta `null`: o modelo é instruído a não inventar.
- **Documento grande:** o texto é dividido em partes de `RESUMO_CHARS_POR_PARTE` caracteres; cada parte
  é resumida e os resumos parciais são consolidados (repete até caber numa chamada).
- **Sem modelo, ou se ele falhar:** resumo simples — tipo, nº de páginas, título, datas e valores
  encontrados no texto. O campo `resumo_origem` diz de onde veio (`modelo` ou `simples`).

## Prioridade

- **Do lote** (no upload): lotes `alta` são processados primeiro pelos workers.
- **Do documento** (fila de revisão): a maior entre a prioridade padrão do tipo (`tipos.py`), a
  sugerida pelo modelo e, se o lote foi enviado como `alta`, a do lote. Tipo desconhecido = `alta`.
  O revisor pode mudar com a ação `alterar_prioridade`; `prioridade_motivo` explica a origem.

## Login e perfis

`AUTH_ATIVO=true` liga o login com JWT. Perfis: **analista** (envia e consulta, só vê PDF anonimizado) <
**revisor** (revisa, vê o original) < **admin** (gerencia usuários). No primeiro start, se não houver
usuários, o admin é criado com `ADMIN_USUARIO`/`ADMIN_SENHA`. Nas revisões, o usuário gravado na
auditoria vem do token. Defina `JWT_SEGREDO` em produção (sem ele, os tokens caem a cada restart).

O banco é migrado automaticamente no start: colunas novas são adicionadas em tabelas antigas.

## Como a decisão é tomada

**Tipo da página.** As regras pontuam cada tipo: +1 por palavra-chave e +3 por título no topo da
página. Se a confiança fica abaixo de `LIMIAR_LLM`, o modelo é consultado recebendo o texto mascarado e a
imagem com tarja. Quando as duas concordam, a confiança sobe. Quando discordam, a confiança cai e o
documento vai para revisão.

**Corte entre documentos**, do sinal mais forte para o mais fraco:

1. "Página 2 de 3": é continuação.
2. "Página 1 de N": é início.
3. Título no topo da página.
4. O modelo diz que é início.
5. O tipo mudou.
6. Página em branco: funciona como separador.

**Confiança do documento.** É a menor entre a confiança do tipo, a de cada corte e a qualidade do OCR.
O documento vai para a fila de revisão se:

- a confiança ficar abaixo de `LIMIAR_REVISAO` (padrão: 70%);
- o tipo for desconhecido;
- regras e modelo discordarem;
- a contagem "1 de N" não bater com o número de páginas.

## Roteiro de demo (pitch)

1. Subir o lote e mostrar a barra de progresso.
2. **Matar o worker** (`kill -9`) no meio do lote, religar com `python -m app.worker --recuperar-agora`
   e mostrar que ele continua de onde parou.
3. Mostrar os documentos separados por cor e tipo, e a fila de revisão com o motivo de cada pendência.
4. Corrigir um corte com "dividir" e mostrar que o PDF é regenerado e a correção fica na trilha de auditoria.
5. Abrir o PDF anonimizado: o CPF some do texto **e** da imagem.
6. Buscar uma palavra no OCR.
7. Abrir `/metricas` e mostrar a taxa de automação.

## Limitações e próximos passos

- A taxonomia e os limiares estão calibrados num lote sintético. Recalibrem com os dados de teste
  e meçam acurácia de corte e de tipo.
- Nomes são detectados por rótulos do documento ("Nome:", "Cliente:", "filho de"...) + reconhecedor
  spaCy (`pt_core_news_md`); endereços por padrão de logradouro + número. Pode falhar com nomes fora
  de rótulos em textos muito curtos ou com OCR ruim. Próximo passo: medir com os dados reais e,
  se preciso, um modelo de entidades maior (`pt_core_news_lg`) ou o Presidio.
- Pré-processamento mínimo. Próximo passo: deskew e binarização adaptativa para scans ruins.
- Login com perfis já existe (JWT). Próximo passo: SSO/OAuth2 da organização e expiração com refresh token.
- Resumo e prioridade pelo modelo foram testados com respostas simuladas; validar com o provedor escolhido.
- Correções humanas ficam em `revisoes` e podem virar dataset para um classificador treinado
  (LayoutLMv3/Donut), reduzindo custo de modelo.
- **Licença:** o PyMuPDF é AGPL. Para uso comercial, usar a licença paga ou trocar por pypdfium2 + OCRmyPDF.
