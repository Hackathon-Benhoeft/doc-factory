# API do Document Factory — guia para o front

**Base:** `http://localhost:8000` (sem `/api`). Swagger interativo: `http://localhost:8000/docs`.
No front: `frontend/src/services/api.js` → `baseURL: 'http://localhost:8000'`.

CORS já libera `http://localhost:5173` (Vite) e `http://localhost:4200`. Para outra porta, ajuste
`CORS_ORIGINS` no `.env` do backend.

## Convenções

- **Datas:** ISO (`2026-11-05`, `2026-11-05T21:40:07`). Formate no front.
- **Prioridade:** `"alta" | "media" | "baixa"` (sem acento). Rótulo: `alta → Alta`, `media → Média`, `baixa → Baixa`.
- **Listas paginadas:** `{ total, pagina, por_pagina, paginas, itens: [...] }` (página começa em 1).
- **Erros:** sempre `{ "erro": { "codigo": 404, "mensagem": "Documento não encontrado", "detalhe": null } }`.
  Mostre `erro.mensagem` para o usuário. Em 422, `erro.detalhe` é a lista `[{campo, mensagem}]`.
- **Login** (só se `AUTH_ATIVO=true` no backend): `POST /auth/login` (form `username`, `password`) →
  `{access_token, perfil}`; envie `Authorization: Bearer <token>`. Com login desligado, nada é exigido.

## Cadastro e autenticação

- `POST /auth/registrar` recebe `{login, nome, senha}`, cria uma conta de perfil `revisor` e devolve `{access_token, perfil}`.
- Ao iniciar, contas existentes com perfil `analista` são promovidas para `revisor`; contas `admin` permanecem administradoras. Ao criar usuários via `POST /usuarios`, uma solicitação de perfil `analista` também resulta em `revisor`.
- `POST /auth/login` recebe formulário `username` e `password`; envie o token retornado no cabeçalho `Authorization` das rotas protegidas.
- O Docker Compose ativa `AUTH_ATIVO`. No desenvolvimento local, habilite essa opção para proteger as rotas do backend.
- Com `AUTH_ATIVO=true`, as rotas protegidas usam JWT; a chave compartilhada `API_KEY` é usada apenas no modo sem autenticação por usuário.

## Documento (formato usado em todas as telas)

```json
{
  "id": "3913a49ebc534dfba859ee635837a47a",
  "codigo": "DOC-2026-3913A4",
  "titulo": "ATESTADO DE SAÚDE OCUPACIONAL - ASO",
  "tipo": "ASO", "tipo_nome": "Atestado de Saúde Ocupacional (ASO)",
  "setor": "Segurança do Trabalho",
  "prioridade": "alta", "prioridade_motivo": "documento vencido há 31 dia(s)",
  "status_revisao": "auto_aprovado | pendente | revisado",
  "confianca": 0.95, "motivos": [],
  "validade": {
    "data": "2026-10-05", "inicio": "2025-10-05",
    "status": "vigente | vencendo | vencido | indeterminado | sem_validade",
    "dias_restantes": -31,
    "origem": "texto | modelo | regra",
    "evidencia": "Data do exame: 05/10/2025  →  regra: validade de 12 meses"
  },
  "resumo": "…", "resumo_origem": "modelo | simples", "campos": {"resultado": "APTO", "…": "…"},
  "lote_id": "…", "ordem": 0, "pagina_inicio": 0, "pagina_fim": 0, "n_paginas": 1,
  "criado_em": "2026-11-05T22:10:00"
}
```

Texto do prazo na tabela ("Vence em 2 dias", "No prazo"…), a partir de `validade`:
`vencido` → "Vencido há N dias" · `vencendo` → "Vence em N dias" (0 = "Vence hoje") · `vigente` → "No prazo" ·
`indeterminado` → "Validade não identificada" · `sem_validade` → "—".

## Tela "Visão geral" → `GET /painel` (uma chamada)

| Componente | Campo da resposta |
|---|---|
| StatCard "Documentos ativos" | `cartoes.documentos_ativos.valor` · subtexto `este_mes` |
| StatCard "Vencem esta semana" | `cartoes.vencem_semana.valor` · `vencem_hoje` · `vencidos` |
| StatCard "Aguardando revisão" | `cartoes.aguardando_revisao.valor` · `alta_prioridade` |
| StatCard "Analisados com sucesso" | `cartoes.analisados_sem_revisao.percentual` (%) |
| ChartSection (7 dias) | `volume_7_dias.dias[] = {data, rotulo ("Seg"… "Hoje"), total}` · `variacao_semana_anterior` (% ou null) |
| AttentionSection | `atencao[] = {tipo, gravidade (alta/media/ok), total, titulo, subtitulo, acao, rota}` |
| RecentDocuments | `recentes[]` (documentos; use `titulo`, `tipo_nome`, `setor`, `prioridade`, `criado_em`) |
| SectorDistribution | `por_setor[] = {setor, total, percentual}` (largura da barra = `percentual`) |
| Sidebar (badge da fila) | `fila_revisao` |

## Tela "Documentos" → `GET /documentos`

Parâmetros (todos opcionais): `setor`, `prioridade`, `tipo`, `prazo`, `q` (busca), `status_revisao`, `lote_id`,
`ordenar` (`recentes` | `prazo` | `prioridade` | `confianca`), `pagina`, `por_pagina` (máx. 200).

`prazo`: `vencido` · `vencendo` (até 30 dias) · `esta_semana` (até 7 dias) · `vigente` · `indeterminado` · `sem_validade`.

| Componente | Origem |
|---|---|
| DocumentsFilter "Setores" | `GET /setores` → `[{setor, tipos}]` |
| DocumentsFilter "Tipos" | `GET /tipos` → `[{codigo, nome, descricao, prioridade, campos, validade}]` |
| DocumentsFilter "Prioridades" / "Prazos" | valores fixos acima |
| DocumentsTable | `itens[]`: `codigo`, `titulo`, `tipo_nome`, `setor`, `validade.data` + texto do prazo, `prioridade` |
| DocumentsMetrics | de `/painel`: `cartoes.vencem_semana`, `cartoes.aguardando_revisao`, `processados_hoje` |
| Abrir PDF | `GET /documentos/{id}/pdf` (anonimizado) · `?anonimizado=false` (original, perfil revisor) |
| Detalhe | `GET /documentos/{id}` · auditoria: `GET /documentos/{id}/revisoes` |

## Tela "Fila de revisão"

- Lista: `GET /revisao/fila` (prioridade alta primeiro, depois menor confiança). Mostre `motivos`.
- Miniaturas das páginas: `GET /lotes/{lote_id}/paginas/{n}/imagem` (de `pagina_inicio` a `pagina_fim`).
- Ações: `POST /documentos/{id}/revisao` com
  `{"acao": "aprovar"}` · `{"acao": "alterar_tipo", "tipo": "ASO"}` · `{"acao": "alterar_prioridade", "prioridade": "alta"}` ·
  `{"acao": "dividir", "pagina_corte": 6}` · `{"acao": "juntar_proximo"}`. Devolve os documentos afetados.

## Tela "Relatórios" → `GET /relatorios?dias=30`

| Componente | Campo |
|---|---|
| ReportsMetrics | `metricas.documentos_processados {valor, variacao}` · `metricas.tempo_medio_analise_segundos` · `metricas.concluidos_sem_revisao {percentual, variacao_pontos}` · `metricas.enviados_para_revisao.valor` |
| PriorityDonutChart | `por_prioridade[] = {prioridade, total, percentual}` |
| SectorVolume | `por_setor[]` |
| StatusPrazos | `status_prazos[] = {status, rotulo ("No prazo", "Vencem em breve", "Vencidos"), total, percentual}` |
| VolumeChart | `volume_diario[] = {data, total}` |

## Envio de lote (upload)

```js
const form = new FormData();
form.append('arquivo', file);              // PDF, TIFF, PNG ou JPG (até 2 GB)
form.append('prioridade', 'alta');         // opcional: alta | media | baixa
const { data: lote } = await api.post('/lotes', form, {
  headers: { 'Content-Type': 'multipart/form-data' },
  onUploadProgress: e => setProgresso(e.loaded / e.total),
});
// acompanhe: GET /lotes/{lote.id} a cada 2 s até status === 'concluido' (campo progresso: 0 a 1)
// 409 = arquivo já enviado (erro.detalhe.lote_id traz o lote existente)
```

Outros: `GET /lotes` (lista) · `GET /lotes/{id}/documentos` · `GET /lotes/{id}/zip` (todos os PDFs + manifesto) ·
`GET /vencimentos?ate_dias=30` · `GET /busca?q=` · `GET /health`.

## Relatório de risco de privacidade (para o encarregado de dados — DPO)

`GET /lotes/{id}/privacidade?limite=100` (perfil analista; só lote `concluido`, senão 409). Responde "este lote tem
340 CPFs (212 pessoas distintas) e 12 documentos com dados de saúde" **antes de compartilhar**. Devolve só números
e evidências; nenhum dado pessoal (nem impressão de CPF) sai por aqui.

```json
{
  "nivel_risco": "alto",                        // alto: tem dado sensível · medio: só identificadores · baixo: nenhum
  "motivos": ["2 documento(s) com dados pessoais sensíveis (art. 5º, II da LGPD)"],
  "resumo": "Este lote (12 documento(s)) tem 11 CPF(s) (2 pessoa(s) distinta(s)), 4 nome(s) de pessoa, 2 documento(s) com dados de saúde.",
  "totais": {"paginas": 14, "documentos": 12, "documentos_com_dados_pessoais": 9,
             "documentos_com_dados_sensiveis": 2, "pessoas_distintas": 2, "documentos_em_revisao": 1},
  "identificadores": {"CPF": {"nome": "CPF", "ocorrencias": 11, "documentos": 9, "pessoas_distintas": 2},
                      "NOME": {...}, "RG": {...}, "ENDERECO": {...}, "CEP": {...}, "EMAIL": {...}, "TELEFONE": {...}, "CNPJ": {...}},
  "dados_sensiveis": {"SAUDE": {"nome": "Dados de saúde", "documentos": 2, "por_tipo": {"ASO": 2}, "termos_mais_frequentes": []},
                      "BIOMETRIA": {...}, "SINDICAL": {...}},
  "documentos_sensiveis": [{"documento_id": "...", "ordem": 3, "tipo": "ASO", "tipo_nome": "...", "titulo": "...",
                            "pagina_inicio": 5, "pagina_fim": 5, "categorias": ["SAUDE"],
                            "evidencias": {"SAUDE": ["tipo do documento: ASO"]}}],
  "documentos_sensiveis_truncado": false,       // true quando passou de `limite` (os totais continuam completos)
  "deteccao": {"nomes": true, "enderecos": true},   // se estiverem false, nomes/endereços ficam subcontados
  "recomendacoes": ["..."], "aviso": "..."
}
```

Como é calculado (tudo determinístico, sem modelo): identificadores = marcadores `[CPF]`, `[NOME]`... que a
anonimização já deixa no texto guardado (funciona em lotes antigos, sem reprocessar); pessoas distintas = impressões
de CPF **válido** já guardadas nas páginas; dados sensíveis = tipo do documento (ASO é sempre saúde) + léxico de termos
(termos genéricos exigem mais de um acerto). `ocorrencias` do CPF inclui qualquer número de 11 dígitos; `pessoas_distintas`
só conta CPF com dígito verificador correto. **Os números são o mínimo detectado** (nome/endereço que a detecção não
reconhece não entram) — triagem, não parecer jurídico.

## Meta de automação (para o pitch e para uma tela de configuração)

- `GET /automacao` → `{limiar_atual, curva: [{limiar, automaticos, para_revisao, percentual_automatico,
  acuracia_estimada (null sem amostra), amostra, atual}], acuracia_medida: {documentos_revisados, corretos, percentual}}`.
  Gráfico sugerido: eixo X = limiar, barras = `percentual_automatico`, linha = `acuracia_estimada`.
- `GET /automacao/sugerir?meta=95` → menor limiar que atinge a acurácia-meta pelas revisões já feitas.
- `PUT /automacao/limiar` (admin) `{"limiar": 0.85, "aplicar": true}` → muda na hora e reavalia a fila.

A acurácia é **medida** pelas revisões humanas (aprovado sem mudança = acerto; tipo trocado, dividido ou
juntado = erro). Sem revisões suficientes ela vem `null` — o sistema não inventa número.

## Dossiê do trabalhador e checklist (tela sugerida: "Trabalhadores")

O trabalhador é identificado pela **impressão digital do CPF** — o CPF não é guardado; para exibir use
`cpf_mascarado` (`***.982.247-**`). Cada documento traz `trabalhador: {id, rotulo, cpf_mascarado}` ou `null`
(documentos da empresa, como certidões, não têm trabalhador).

- `GET /trabalhadores?lote_id=&situacao=` → `{total, irregulares, exigidos, itens: [{id, rotulo, cpf_mascarado,
  documentos, situacao (regular | atencao | irregular), pendencias, faltando: [tipos], vencidos, vencendo}]}`
  (irregulares primeiro).
- `GET /trabalhadores/{id}/dossie` → o resumo acima + `checklist: [{tipo, tipo_nome, status (ok | faltando |
  vencido | vencendo | indeterminado), documento_id, validade, observacao}]` + `outros_alertas` (ex.: certificado
  de NR vencendo) + `duplicados` + `itens` (documentos da pessoa).
- `/painel` traz `trabalhadores_irregulares` e um item em `atencao` com `tipo: "trabalhadores_irregulares"`.

Documentos exigidos: `DOCUMENTOS_EXIGIDOS_TRABALHADOR` em `backend/app/tipos.py` (identidade, CTPS, ASO, ficha de EPI).

## Sinais de fraude (veredito com evidência)

Cada documento traz `risco: "confiavel" | "atencao" | "alto_risco"` e `alertas: [{codigo, gravidade (media/alta),
mensagem, evidencia}]`. Sugestão de selo: Confiável (verde) · Atenção (amarelo) · Alto risco (vermelho), mostrando
`mensagem` + `evidencia` ao passar o mouse. Códigos: `pdf_editado`, `pdf_modificado`, `repetido`,
`paginas_misturadas`, `data_futura`, `validade_invertida`. Alto risco já vai para a fila de revisão.

- Filtro: `GET /documentos?risco=alto_risco`. O lote também traz `alertas` (metadados do arquivo enviado).
- `/painel`: `documentos_suspeitos` e item em `atencao` com `tipo: "fraude"`.

## Aprender com as correções

Toda vez que o revisor usa `alterar_tipo`, o sistema aprende: o título do documento vira regra (vale mesmo sem
modelo) e o trecho anonimizado vira exemplo para o modelo.

- `GET /aprendizados` → `[{id, titulo, tipo_errado, tipo_certo, usuario, usos, ativo, criado_em}]`
  (`usos` = quantas páginas já foram decididas por esse aprendizado).
- `POST /aprendizados/{id}/desativar` (admin) → desfaz uma correção feita por engano.

## Erros e segurança (o que o front deve tratar)

- **500** — erro inesperado: `erro.mensagem` traz um código de ocorrência ("Informe o código 5383630e ao suporte");
  o detalhe técnico fica só no log do servidor.
- **401** — sem login / token expirado → mandar para a tela de login.
- **403** — perfil sem permissão (ex.: revisor tentando administrar usuários).
- **409** — arquivo já enviado (`erro.detalhe.lote_id`) ou lote ainda em processamento.
- **413 / 415** — arquivo grande demais / tipo não aceito (o conteúdo é conferido, não só a extensão).
- **429** — login bloqueado por tentativas erradas; respeite o cabeçalho `Retry-After` (segundos).

## Apagar um lote (LGPD — direito de eliminação)

`DELETE /lotes/{id}` (admin) apaga o lote, as páginas, os documentos, os arquivos e as pessoas que ficarem sem
documento. Responde `{apagado, nome, paginas, documentos}` e deixa só um registro de auditoria sem dados pessoais.
Lote em processamento → 409.

## Endpoints novos (F0–F8) — resumo

- **F0:** `LoteOut.ia` traz `{chamadas_total, chamadas_classificacao, chamadas_resumo, chamadas_outras, paginas_com_ia, paginas_total, percentual_paginas_com_ia, custo_estimado_brl}` e `/painel` ganha o bloco `ia`. `DocumentoOut` traz `decidido_por` (regra, ia, combinado ou humano), `origem_texto` e `ia_justificativa`. Reprocessar zera os contadores.
- **F2:** `DocumentoOut.pre_revisao` traz `{explicacao, acao_sugerida, tipo_sugerido, confianca, evidencias, origem}`. `POST /documentos/{id}/pre-revisao` (analista) gera a sugestão de novo. `GET /automacao` ganha `pre_revisao {revisoes_com_sugestao, seguidas, percentual}`.
- **F3:** `GET /funcoes`; `PUT /trabalhadores/{id}/funcao {funcao_chave}` (revisor). Trabalhadores e dossiê ganham `funcao`, `funcao_origem` e `exigidos`, e o checklist ganha itens `CERTIFICADO_NR:NR-xx` com `motivo_exigencia`.
- **F4:**
  - `POST /regras-separacao/interpretar` (revisor; não grava; 422 traz `exemplos`).
  - `POST`/`GET /regras-separacao`.
  - `/{id}/ativar` e `/{id}/desativar` (revisor); `DELETE /{id}` (admin).
  - `POST /lotes` aceita o campo `regras`; `reprocessar` aceita `?atualizar_regras=true`.
  - `LoteOut.regras_aplicadas` e `DocumentoOut.regras_aplicadas`.
- **F5:** `PUT /lotes/{id}/gabarito` (revisor; 422 se inválido). `GET /lotes/{id}/avaliacao` (409 sem gabarito ou com o lote não concluído). `LoteOut.tem_gabarito`.
- **F6:** `/alertas/config`, `/alertas/contatos` (GET; POST e DELETE para admin), `/alertas/contatos/{id}/testar`, `/alertas/pendentes`, `POST /alertas/executar?simular=`, `/alertas/historico`.
- **F7:**
  - Interno: `POST /portal/convites` (revisor; o token aparece só nessa resposta), `GET /portal/convites`, `/{id}/revogar`, `/{id}/envios`.
  - Público: `GET /portal/{token}`, `POST /portal/{token}/enviar`, `GET /portal/{token}/envios/{envio_id}`. Token inválido sempre responde 404 `Link inválido ou expirado`. Os limites devolvem 413, 415, 422 ou 429.
  - `LoteOut` ganha `origem` e `fornecedor`.
- **F8:** `LoteOut.multidoc` traz `[{pagina_original, recortes}]` quando a imagem enviada tinha várias folhas.
