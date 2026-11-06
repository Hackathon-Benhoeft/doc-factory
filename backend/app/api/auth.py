"""Login (JWT) e gestão de usuários com perfis: analista < revisor < admin.

Com AUTH_ATIVO=false a API fica aberta (modo demo) e estas rotas continuam disponíveis
para preparar os usuários antes de ligar o login.
"""
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual, admin, exigir_api_key, usuario_atual
from app.config import settings
from app.db import get_db
from app.models import Usuario
from app.schemas import CadastroIn, EuOut, TokenOut, UsuarioIn, UsuarioOut
from app.security import criar_token, hash_senha, verificar_senha

log = logging.getLogger(__name__)
_HASH_FALSO = hash_senha("senha-que-nunca-confere")
router = APIRouter(tags=["login e usuários"])


# tentativas de login erradas por login: {login: (erros seguidos, bloqueado_até)} — em memória, por processo
_falhas: dict[str, tuple[int, float]] = {}
_falhas_lock = threading.Lock()


def _verificar_bloqueio(login: str) -> None:
    with _falhas_lock:
        erros, ate = _falhas.get(login, (0, 0.0))
    restante = int(ate - time.monotonic())
    if restante > 0:
        raise HTTPException(429, f"Muitas tentativas erradas. Tente de novo em {restante // 60 + 1} minuto(s).",
                            headers={"Retry-After": str(restante)})


def _registrar_falha(login: str) -> None:
    with _falhas_lock:
        erros, _ = _falhas.get(login, (0, 0.0))
        erros += 1
        ate = time.monotonic() + settings.LOGIN_BLOQUEIO_MIN * 60 if erros >= settings.LOGIN_MAX_TENTATIVAS else 0.0
        _falhas[login] = (0 if ate else erros, ate)
    if ate:
        log.warning("login '%s' bloqueado por %s min após %s tentativas erradas",
                    login, settings.LOGIN_BLOQUEIO_MIN, settings.LOGIN_MAX_TENTATIVAS)


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Troca login + senha por um token. No Swagger: botão Authorize.
    Depois de LOGIN_MAX_TENTATIVAS erros seguidos, o login fica bloqueado por LOGIN_BLOQUEIO_MIN minutos."""
    _verificar_bloqueio(form.username)
    u = db.scalar(select(Usuario).where(Usuario.login == form.username))
    # verifica a senha mesmo se o usuário não existir: o tempo de resposta não revela quem existe
    ok = verificar_senha(form.password, u.senha_hash if u else _HASH_FALSO)
    if not u or not u.ativo or not ok:
        _registrar_falha(form.username)
        raise HTTPException(401, "Login ou senha inválidos", headers={"WWW-Authenticate": "Bearer"})
    with _falhas_lock:
        _falhas.pop(form.username, None)
    return TokenOut(access_token=criar_token(u.login, u.perfil), perfil=u.perfil)


@router.post("/auth/registrar", response_model=TokenOut, status_code=201)
def registrar(dados: CadastroIn, db: Session = Depends(get_db)):
    """Cria uma conta de revisor e autentica o usuário (só com CADASTRO_ABERTO=true)."""
    if not settings.CADASTRO_ABERTO:
        raise HTTPException(403, "Cadastro desativado: peça a um administrador para criar sua conta")
    if db.scalar(select(Usuario).where(Usuario.login == dados.login)):
        raise HTTPException(409, "Este usuário já está cadastrado")

    usuario = Usuario(
        login=dados.login,
        nome=dados.nome,
        perfil="revisor",
        senha_hash=hash_senha(dados.senha),
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(409, "Este usuário já está cadastrado") from err
    return TokenOut(access_token=criar_token(usuario.login, usuario.perfil), perfil=usuario.perfil)


def _exigir_login_ativo() -> None:
    if not settings.AUTH_ATIVO:
        raise HTTPException(403, "Gestão de usuários só com o login ativo (AUTH_ATIVO=true). "
                                 "Com o login desligado, a API está aberta e qualquer pessoa criaria um admin.")


@router.get("/auth/eu", response_model=EuOut)
def quem_sou_eu(u: UsuarioAtual = Depends(usuario_atual)):
    return EuOut(login=u.login, perfil=u.perfil, autenticado=u.autenticado)


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _u: UsuarioAtual = Depends(admin),
    _api_key: None = Depends(exigir_api_key),
):
    return list(db.scalars(select(Usuario).order_by(Usuario.login)))


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def criar_usuario(dados: UsuarioIn, db: Session = Depends(get_db), _u: UsuarioAtual = Depends(admin)):
    _exigir_login_ativo()
    if db.scalar(select(Usuario).where(Usuario.login == dados.login)):
        raise HTTPException(409, "Login já existe")
    perfil = "revisor" if dados.perfil == "analista" else dados.perfil
    u = Usuario(login=dados.login, nome=dados.nome, perfil=perfil, senha_hash=hash_senha(dados.senha))
    db.add(u)
    db.commit()
    return u


@router.post("/usuarios/{usuario_id}/desativar", response_model=UsuarioOut)
def desativar_usuario(usuario_id: int, db: Session = Depends(get_db), atual: UsuarioAtual = Depends(admin)):
    _exigir_login_ativo()
    u = db.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    if atual.autenticado and u.login == atual.login:
        raise HTTPException(422, "Você não pode desativar a si mesmo")
    u.ativo = False
    db.commit()
    return u


def criar_admin_inicial(db: Session) -> None:
    """Primeiro start: cria o admin a partir de ADMIN_USUARIO/ADMIN_SENHA se não houver usuários."""
    if db.scalar(select(func.count()).select_from(Usuario)):
        return
    if not settings.ADMIN_SENHA:
        if settings.AUTH_ATIVO:
            log.warning("AUTH_ATIVO=true mas nenhum usuário existe e ADMIN_SENHA não foi definida — ninguém consegue logar")
        return
    db.add(Usuario(login=settings.ADMIN_USUARIO, nome="Administrador", perfil="admin",
                   senha_hash=hash_senha(settings.ADMIN_SENHA)))
    db.commit()
    log.info("usuário admin '%s' criado", settings.ADMIN_USUARIO)
