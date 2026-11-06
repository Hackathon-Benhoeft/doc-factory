"""API — Document Factory.

    uvicorn app.main:app --reload        → http://localhost:8000/docs (Swagger)
"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import alertas, auth, automacao, documentos, lotes, painel, portal_admin, portal_publico, regras, trabalhadores
from app.api.deps import UsuarioAtual, analista, exigir_api_key
from app.config import settings
from app.db import SessionLocal, init_db
from app.llm import erro_configuracao, obter_llm
from app.models import Documento, Lote, Pagina
from app.tipos import PRIORIDADE_NOME
from app.status import StatusRevisao

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

log = logging.getLogger("api")


def problemas_de_seguranca() -> list[str]:
    """O que impede um uso seguro em produção (vazio = ok)."""
    p = []
    if not settings.AUTH_ATIVO:
        p.append("login desligado (AUTH_ATIVO=false): a API está aberta para qualquer pessoa")
    if not settings.JWT_SEGREDO:
        p.append("JWT_SEGREDO não definido: os logins caem a cada reinício")
    if not settings.CPF_SEGREDO:
        p.append("CPF_SEGREDO não definido: o segredo da impressão do CPF fica no próprio banco")
    if settings.AUTH_ATIVO and settings.CADASTRO_ABERTO:
        p.append("CADASTRO_ABERTO=true: qualquer pessoa cria uma conta de revisor, podendo revisar documentos")
    if settings.ALERTAS_MODO == "real":
        from app.alertas import canais
        if not (canais.email_configurado() or canais.whatsapp_configurado()):
            p.append("ALERTAS_MODO=real sem canal configurado (SMTP_HOST+SMTP_REMETENTE ou EVOLUTION_URL+"
                     "EVOLUTION_INSTANCIA+EVOLUTION_APIKEY)")
    if "*" in settings.CORS_ORIGINS:
        p.append("CORS_ORIGINS=*: qualquer site pode chamar a API")
    return p


@asynccontextmanager
async def lifespan(_app: FastAPI):
    problemas = problemas_de_seguranca()
    if settings.AMBIENTE == "producao" and problemas:
        raise RuntimeError("AMBIENTE=producao, mas: " + "; ".join(problemas))
    for prob in problemas:
        log.warning("SEGURANÇA: %s", prob)
    init_db()
    with SessionLocal() as db:
        auth.criar_admin_inicial(db)
    if settings.WORKER_INLINE:
        from app import worker
        worker.iniciar_em_thread()
    yield
    if settings.WORKER_INLINE:
        from app import worker
        worker.parar()


app = FastAPI(title="Document Factory", version="0.3.0", lifespan=lifespan,
              description="Separa, classifica, resume e torna pesquisáveis lotes de documentos digitalizados.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _cabecalhos_de_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")     # navegador não "adivinha" o tipo
    resposta.headers.setdefault("X-Frame-Options", "DENY")               # não pode ser embutida em outro site
    resposta.headers.setdefault("Referrer-Policy", "no-referrer")
    return resposta

protegido = [Depends(exigir_api_key)]
app.include_router(auth.router)
app.include_router(painel.router, dependencies=protegido)
app.include_router(automacao.router, dependencies=protegido)
app.include_router(automacao.router_aprendizados, dependencies=protegido)
app.include_router(lotes.router, dependencies=protegido)
app.include_router(documentos.router, dependencies=protegido)
app.include_router(trabalhadores.router, dependencies=protegido)
app.include_router(trabalhadores.router_funcoes, dependencies=protegido)
app.include_router(regras.router, dependencies=protegido)
app.include_router(alertas.router, dependencies=protegido)
# ordem importa: /portal/convites (interno) antes de /portal/{token} (público, autenticação própria pelo token)
app.include_router(portal_admin.router, dependencies=protegido)
app.include_router(portal_publico.router)


# ------------------------------------------------------------ erros num formato único para o front
def _erro(status: int, mensagem: str, detalhe=None, headers=None) -> JSONResponse:
    """{"erro": {"codigo", "mensagem", "detalhe"}} — e "detail" mantido por compatibilidade."""
    corpo = {"erro": {"codigo": status, "mensagem": mensagem, "detalhe": detalhe},
             "detail": detalhe if detalhe is not None else mensagem}
    return JSONResponse(corpo, status_code=status, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def _erro_http(_req, exc: StarletteHTTPException):
    d = exc.detail
    if isinstance(d, dict):
        return _erro(exc.status_code, str(d.get("mensagem") or d.get("message") or "Erro"), d, exc.headers)
    return _erro(exc.status_code, str(d), None, exc.headers)


@app.exception_handler(RequestValidationError)
async def _erro_validacao(_req, exc: RequestValidationError):
    campos = [{"campo": ".".join(str(p) for p in e.get("loc", [])[1:]), "mensagem": e.get("msg")} for e in exc.errors()]
    return _erro(422, "Dados inválidos: " + "; ".join(f"{c['campo']}: {c['mensagem']}" for c in campos), campos)


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    """Qualquer erro não previsto: resposta no mesmo formato, SEM detalhes internos; o detalhe vai para o log
    com um código que o usuário pode informar ao suporte."""
    codigo = uuid.uuid4().hex[:8]
    log.exception("erro inesperado %s em %s %s", codigo, request.method, request.url.path)
    return _erro(500, f"Erro interno. Informe o código {codigo} ao suporte.", {"ocorrencia": codigo})


@app.get("/health", tags=["infra"])
def health():
    """Saúde da API e das dependências (para monitoramento)."""
    import pytesseract
    try:
        tesseract = str(pytesseract.get_tesseract_version())
        idiomas = pytesseract.get_languages(config="")
    except Exception as e:  # Tesseract ausente/mal configurado
        tesseract, idiomas = f"indisponível: {e}", []
    erro_modelo = erro_configuracao()
    modelo = f"mal configurado: {erro_modelo}" if erro_modelo else (settings.LLM_PROVIDER if obter_llm() else "desligado")
    return {"ok": True, "ambiente": settings.AMBIENTE, "tesseract": tesseract,
            "idioma_ocr_ok": settings.OCR_LANG in idiomas, "modelo": modelo,
            "login": "ativo" if settings.AUTH_ATIVO else "desligado (modo demo)",
            "worker_inline": settings.WORKER_INLINE, "avisos_seguranca": problemas_de_seguranca()}


@app.get("/metricas", tags=["infra"], dependencies=protegido)
def metricas(_u: UsuarioAtual = Depends(analista)):
    """Números para o dashboard e para o pitch."""
    with SessionLocal() as db:
        por_status = dict(db.execute(select(Documento.status_revisao, func.count()).group_by(Documento.status_revisao)).all())
        total_docs = sum(por_status.values())
        por_prioridade = {PRIORIDADE_NOME.get(p, str(p)): n for p, n in
                          db.execute(select(Documento.prioridade, func.count()).group_by(Documento.prioridade)).all()}
        return {
            "lotes": db.scalar(select(func.count()).select_from(Lote)),
            "lotes_por_status": dict(db.execute(select(Lote.status, func.count()).group_by(Lote.status)).all()),
            "paginas": db.scalar(select(func.count()).select_from(Pagina)),
            "paginas_por_status": dict(db.execute(select(Pagina.status, func.count()).group_by(Pagina.status)).all()),
            "documentos": total_docs,
            "documentos_por_tipo": dict(db.execute(select(Documento.tipo, func.count()).group_by(Documento.tipo)).all()),
            "documentos_por_revisao": por_status,
            "documentos_por_prioridade": por_prioridade,
            "resumos_por_origem": dict(db.execute(select(Documento.resumo_origem, func.count())
                                                  .group_by(Documento.resumo_origem)).all()),
            "taxa_automacao": round(por_status.get(StatusRevisao.AUTO_APROVADO, 0) / total_docs, 3) if total_docs else None,
            "confianca_media": db.scalar(select(func.avg(Documento.confianca))),
        }
