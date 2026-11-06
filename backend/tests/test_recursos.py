"""Resumo, prioridade, auditoria, filtros, login com perfis e migração do banco."""
import io
import json
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text

from app.config import settings
from app.db import SessionLocal
from app.llm.base import RespostaResumo
from app.llm.openai_compat import ClienteOpenAICompat, dividir_em_partes
from app.models import Documento, Lote, Pagina, Usuario
from app.pipeline import resumir as mod_resumir
from app.pipeline.segmentar import PaginaInfo, segmentar
from app.security import hash_senha


def _docs(c, lote):
    return c.get(f"/lotes/{lote['id']}/documentos").json()


# ------------------------------------------------------------------ resumo e prioridade
def test_documentos_tem_resumo_simples_e_prioridade(processado):
    c, lote = processado
    docs = {d["tipo"]: d for d in _docs(c, lote)}
    for d in docs.values():
        assert d["resumo_origem"] == "simples"          # sem modelo configurado
        assert d["resumo"].startswith(d["tipo_nome"])
        assert d["prioridade"] in ("alta", "media", "baixa") and d["prioridade_motivo"]
    assert docs["CONTRATO"]["prioridade"] == "alta"
    assert docs["COMPROVANTE_RESIDENCIA"]["prioridade"] == "baixa"
    assert "R$" in docs["COMPROVANTE_RESIDENCIA"]["resumo"] or docs["COMPROVANTE_RESIDENCIA"]["campos"]["datas"]
    assert "987.654.321-00" not in json.dumps(docs)    # resumo e campos nunca trazem CPF


def test_motivo_preenchido_quando_abaixo_do_limiar():
    docs = segmentar([PaginaInfo(0, "CONTRATO", 0.5, sinais={"titulo_topo": "CONTRATO"})])
    assert docs[0].revisao and any("abaixo do limiar" in m for m in docs[0].motivos)


def test_prioridade_combina_tipo_lote_e_modelo():
    assert mod_resumir.calcular_prioridade("COMPROVANTE_RESIDENCIA", 1, None)[0] == 1
    assert mod_resumir.calcular_prioridade("COMPROVANTE_RESIDENCIA", 3, None) == (3, "prioridade do lote")
    valor, motivo = mod_resumir.calcular_prioridade("COMPROVANTE_RESIDENCIA", 1, "alta", "vence amanhã")
    assert valor == 3 and "vence amanhã" in motivo
    assert mod_resumir.calcular_prioridade("DESCONHECIDO", 1, None)[0] == 3


def test_resumo_com_modelo_documento_grande_em_partes():
    chamadas = []

    def responder(req):
        corpo = json.loads(req.read().decode())
        usuario = corpo["messages"][1]["content"]
        chamadas.append(usuario)
        if usuario.startswith("PARTE"):
            conteudo = {"resumo": f"resumo da {usuario.split(':')[0].lower()}"}
        else:
            assert "RESUMOS DAS PARTES" in usuario
            conteudo = {"resumo": "Contrato de serviços entre duas empresas.",
                        "campos": {"partes": "ACME e Beta", "valor": "R$ 1.000,00", "foro": None},
                        "prioridade": "Média", "motivo_prioridade": "sem prazo próximo"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(conteudo)}}]})

    cli = ClienteOpenAICompat("http://falso/v1", "modelo-x", "k", multimodal=False, timeout=5, chars_por_parte=120)
    cli.http = httpx.Client(transport=httpx.MockTransport(responder))
    texto = "\n".join(f"Cláusula {i}: a CONTRATADA [CPF] presta serviços mensais." for i in range(12))
    r = cli.resumir("Contrato", ["partes", "objeto", "valor", "vigencia", "foro"], texto)

    assert r.partes == len(dividir_em_partes(texto, 120)) > 1
    assert sum(1 for ch in chamadas if ch.startswith("PARTE")) >= r.partes   # cada parte foi resumida
    assert r.resumo.startswith("Contrato de serviços")
    assert r.campos == {"partes": "ACME e Beta", "objeto": None, "valor": "R$ 1.000,00", "vigencia": None, "foro": None}
    assert r.prioridade == "media"


def test_resumo_modelo_falha_cai_para_simples(monkeypatch):
    class ModeloQueFalha:
        def resumir(self, *a):
            return None

    monkeypatch.setattr(mod_resumir, "obter_llm", lambda: ModeloQueFalha())
    lote = Lote(id="x", nome="x", arquivo_key="k", hash_sha256="h", mime="m", tamanho_bytes=1, prioridade=2)
    doc = Documento(lote_id="x", ordem=0, tipo="NOTA_FISCAL", pagina_inicio=0, pagina_fim=0, confianca=0.9,
                    status_revisao="auto_aprovado", texto="DANFE\nValor total R$ 250,00 em 10/03/2026")
    mod_resumir.resumir_documento(lote, doc)
    assert doc.resumo_origem == "simples" and "R$ 250,00" in doc.resumo and "10/03/2026" in doc.resumo


def test_resumo_com_modelo_preenche_documento(monkeypatch):
    class ModeloOk:
        def resumir(self, tipo_nome, campos, texto):
            assert "[CPF]" in texto and "123.456" not in texto     # só texto anonimizado chega ao modelo
            return RespostaResumo(resumo="Nota de R$ 250,00.", campos={"valor_total": "R$ 250,00"},
                                  prioridade="alta", motivo_prioridade="valor divergente")

    monkeypatch.setattr(mod_resumir, "obter_llm", lambda: ModeloOk())
    lote = Lote(id="x", nome="x", arquivo_key="k", hash_sha256="h", mime="m", tamanho_bytes=1, prioridade=2)
    doc = Documento(lote_id="x", ordem=0, tipo="NOTA_FISCAL", pagina_inicio=0, pagina_fim=0, confianca=0.9,
                    status_revisao="auto_aprovado", texto="DANFE destinatário [CPF]")
    mod_resumir.resumir_documento(lote, doc)
    assert doc.resumo_origem == "modelo" and doc.prioridade == 3 and "valor divergente" in doc.prioridade_motivo


# ------------------------------------------------------------------ fila, filtros e auditoria
def _lote_falso(db, prioridade=2, paginas=0) -> Lote:
    lote = Lote(nome="falso", arquivo_key="nao/existe.pdf", hash_sha256=uuid.uuid4().hex, mime="application/pdf",
                tamanho_bytes=1, total_paginas=paginas, status="concluido", prioridade=prioridade)
    db.add(lote)
    db.flush()
    return lote


def test_fila_ordena_por_prioridade_e_confianca(processado):
    c, _ = processado
    with SessionLocal() as db:
        lote = _lote_falso(db)
        for ordem, (prio, conf) in enumerate([(1, 0.10), (3, 0.70), (3, 0.40), (2, 0.20)]):
            db.add(Documento(lote_id=lote.id, ordem=ordem, tipo="CONTRATO", pagina_inicio=ordem, pagina_fim=ordem,
                             confianca=conf, status_revisao="pendente", prioridade=prio))
        db.commit()
        lote_id = lote.id
    fila = c.get("/revisao/fila", params={"lote_id": lote_id}).json()
    assert [(d["prioridade"], d["confianca"]) for d in fila] == [("alta", 0.4), ("alta", 0.7), ("media", 0.2), ("baixa", 0.1)]


def test_alterar_prioridade_gera_auditoria(processado):
    c, lote = processado
    doc = _docs(c, lote)[0]
    r = c.post(f"/documentos/{doc['id']}/revisao", json={"acao": "alterar_prioridade", "prioridade": "baixa",
                                                        "usuario": "ana"})
    assert r.status_code == 200 and r.json()[0]["prioridade"] == "baixa"
    trilha = c.get(f"/documentos/{doc['id']}/revisoes").json()
    ultimo = trilha[-1]
    assert ultimo["acao"] == "alterar_prioridade" and ultimo["usuario"] == "ana"
    assert ultimo["depois"]["prioridade"] == "baixa"
    r = c.post(f"/documentos/{doc['id']}/revisao", json={"acao": "alterar_prioridade"})
    assert r.status_code == 422


def test_listar_documentos_com_filtros(processado):
    c, lote = processado
    contratos = c.get("/documentos", params={"tipo": "CONTRATO", "lote_id": lote["id"]}).json()
    assert contratos["total"] == 2 and all(d["tipo"] == "CONTRATO" for d in contratos["itens"])
    baixas = c.get("/documentos", params={"prioridade": "baixa", "lote_id": lote["id"]}).json()["itens"]
    assert all(d["prioridade"] == "baixa" for d in baixas)


def test_gerar_resumo_de_novo(processado):
    c, lote = processado
    doc = _docs(c, lote)[1]
    r = c.post(f"/documentos/{doc['id']}/resumo")
    assert r.status_code == 200 and r.json()["resumo"]


def test_upload_com_prioridade_invalida(processado, lote_pdf):
    c, _ = processado
    with open(lote_pdf, "rb") as f:
        r = c.post("/lotes", files={"arquivo": ("x.pdf", f, "application/pdf")}, data={"prioridade": "urgentissima"})
    assert r.status_code == 422


def test_worker_atende_lote_de_prioridade_maior_primeiro():
    from app import worker
    with SessionLocal() as db:
        baixa = _lote_falso(db, prioridade=1, paginas=1)
        alta = _lote_falso(db, prioridade=3, paginas=1)
        db.add_all([Pagina(lote_id=baixa.id, numero=0), Pagina(lote_id=alta.id, numero=0)])
        db.commit()
        ids = (baixa.id, alta.id)
        try:
            p = worker.reivindicar_pagina(db)
            assert p.lote_id == alta.id
        finally:
            db.execute(text("DELETE FROM paginas WHERE lote_id IN (:a, :b)"), {"a": ids[0], "b": ids[1]})
            db.execute(text("DELETE FROM lotes WHERE id IN (:a, :b)"), {"a": ids[0], "b": ids[1]})
            db.commit()


# ------------------------------------------------------------------ login e perfis
def test_cadastro_cria_revisor_e_autentica(monkeypatch, processado):
    c, _ = processado
    monkeypatch.setattr(settings, "API_KEY", "chave-de-integracao")
    r = c.post("/auth/registrar", json={
        "login": "  novo_analista  ",
        "nome": "  Nova Pessoa  ",
        "senha": "senha-segura-123",
        "perfil": "admin",
    })
    assert r.status_code == 201, r.text
    assert r.json()["perfil"] == "revisor"

    monkeypatch.setattr(settings, "AUTH_ATIVO", True)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/auth/eu", headers=headers).json() == {
        "login": "novo_analista",
        "perfil": "revisor",
        "autenticado": True,
    }
    assert c.post("/auth/registrar", json={
        "login": "novo_analista",
        "nome": "Outra pessoa",
        "senha": "senha-segura-123",
    }).status_code == 409
    assert c.post("/auth/registrar", json={
        "login": "curto",
        "nome": "Pessoa",
        "senha": "123",
    }).status_code == 422


@pytest.fixture
def login_ativo(monkeypatch, processado):
    monkeypatch.setattr(settings, "AUTH_ATIVO", True)
    c, lote = processado
    with SessionLocal() as db:
        for login, perfil in (("ana_revisora", "revisor"), ("rui_revisor", "revisor"), ("adm", "admin")):
            if not db.scalar(select(Usuario).where(Usuario.login == login)):
                db.add(Usuario(login=login, nome=login, perfil=perfil, senha_hash=hash_senha("senha-de-teste")))
        db.commit()

    def token(login):
        r = c.post("/auth/login", data={"username": login, "password": "senha-de-teste"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return c, lote, token


def test_login_e_perfis(login_ativo, monkeypatch):
    c, lote, token = login_ativo
    monkeypatch.setattr(settings, "API_KEY", "chave-de-integracao")
    assert c.get("/lotes").status_code == 401                                  # sem token
    assert c.post("/auth/login", data={"username": "adm", "password": "errada"}).status_code == 401

    ana, rui, adm = token("ana_revisora"), token("rui_revisor"), token("adm")
    assert c.get("/auth/eu", headers=ana).json() == {"login": "ana_revisora", "perfil": "revisor", "autenticado": True}
    docs = c.get(f"/lotes/{lote['id']}/documentos", headers=ana).json()
    assert docs                                                                  # revisor consulta e revisa
    alvo = docs[-1]["id"]
    assert c.post(f"/documentos/{alvo}/revisao", json={"acao": "aprovar"}, headers=ana).status_code == 200
    assert c.get(f"/documentos/{alvo}/pdf", params={"anonimizado": False}, headers=ana).status_code == 200
    assert c.get(f"/documentos/{alvo}/pdf", headers=ana).status_code == 200     # anonimizado liberado
    assert c.get(f"/lotes/{lote['id']}/paginas/0/imagem", headers=ana).status_code == 200
    assert c.get(f"/lotes/{lote['id']}/paginas/0/imagem", headers=rui).status_code == 200

    r = c.post(f"/documentos/{alvo}/revisao", json={"acao": "aprovar", "usuario": "forjado"}, headers=rui)
    assert r.status_code == 200
    assert c.get(f"/documentos/{alvo}/revisoes", headers=rui).json()[-1]["usuario"] == "rui_revisor"  # vem do token

    assert c.get("/usuarios", headers=rui).status_code == 403
    novo = {"login": "novo_user", "nome": "Novo", "senha": "outra-senha-123", "perfil": "analista"}
    criado = c.post("/usuarios", json=novo, headers=adm)
    assert criado.status_code == 201
    assert criado.json()["perfil"] == "revisor"
    assert c.post("/usuarios", json=novo, headers=adm).status_code == 409


# ------------------------------------------------------------------ migração
def test_migracao_adiciona_colunas_novas(tmp_path, monkeypatch):
    import app.db as db_mod
    antigo = create_engine(f"sqlite:///{tmp_path}/antigo.db")
    with antigo.begin() as conn:   # tabela 'lotes' como era na versão anterior (sem prioridade/enviado_por)
        conn.execute(text("CREATE TABLE lotes (id VARCHAR(32) PRIMARY KEY, nome VARCHAR(255), arquivo_key VARCHAR(512), "
                          "hash_sha256 VARCHAR(64), mime VARCHAR(100), tamanho_bytes INTEGER, total_paginas INTEGER, "
                          "status VARCHAR(20), erro TEXT, criado_em DATETIME, atualizado_em DATETIME)"))
        conn.execute(text("INSERT INTO lotes (id, nome) VALUES ('l1', 'antigo')"))
    monkeypatch.setattr(db_mod, "engine", antigo)
    adicionadas = db_mod.migrar_colunas()
    assert "lotes.prioridade" in adicionadas and "lotes.enviado_por" in adicionadas
    with antigo.connect() as conn:
        assert conn.execute(text("SELECT prioridade FROM lotes WHERE id='l1'")).scalar() == 2   # default aplicado
    assert db_mod.migrar_colunas() == []                                                      # idempotente


def test_migracao_promove_analistas_para_revisor(tmp_path, monkeypatch):
    import app.db as db_mod

    banco = create_engine(f"sqlite:///{tmp_path}/perfis.db")
    with banco.begin() as conn:
        conn.execute(text("CREATE TABLE usuarios (login VARCHAR(100), perfil VARCHAR(20))"))
        conn.execute(text("INSERT INTO usuarios (login, perfil) VALUES "
                          "('analista', 'analista'), ('revisor', 'revisor'), ('admin', 'admin')"))
    monkeypatch.setattr(db_mod, "engine", banco)

    assert db_mod.migrar_perfis_revisor() == 1
    with banco.connect() as conn:
        perfis = dict(conn.execute(text("SELECT login, perfil FROM usuarios")).all())
    assert perfis == {"analista": "revisor", "revisor": "revisor", "admin": "admin"}
    assert db_mod.migrar_perfis_revisor() == 0


def test_health(processado):
    c, _ = processado
    h = c.get("/health").json()
    assert h["ok"] and h["idioma_ocr_ok"] and h["modelo"] == "desligado"


def test_imagem_pagina_thumb(processado):
    c, lote = processado
    r = c.get(f"/lotes/{lote['id']}/paginas/0/imagem")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).width > 0


def test_modelo_tenta_de_novo_quando_limite_estoura(monkeypatch):
    import app.llm.openai_compat as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    respostas = iter([httpx.Response(429, json={}), httpx.Response(503, json={}),
                      httpx.Response(200, json={"choices": [{"message": {"content": '{"resumo": "ok"}'}}]})])
    cli = ClienteOpenAICompat("http://falso/v1", "m", "k", multimodal=False, timeout=5)
    cli.http = httpx.Client(transport=httpx.MockTransport(lambda req: next(respostas)))
    assert cli.resumir("Contrato", [], "texto do contrato").resumo == "ok"
