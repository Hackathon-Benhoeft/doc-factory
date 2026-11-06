"""Conexão com o banco (SQLite no dev, PostgreSQL em produção)."""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

E_SQLITE = settings.DATABASE_URL.startswith("sqlite")
E_POSTGRES = settings.DATABASE_URL.startswith("postgresql")

if E_SQLITE:
    os.makedirs(settings.DATA_DIR, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if E_SQLITE else {},
    pool_pre_ping=True,
)

if E_SQLITE:
    # WAL permite API e worker (processos diferentes) lendo/escrevendo juntos
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401  (registra as tabelas)
    Base.metadata.create_all(engine)
    migrar_colunas()
    promovidos = migrar_perfis_revisor()
    if promovidos:
        import logging
        logging.getLogger(__name__).info("Promovidos %s usuários para o perfil revisor", promovidos)
    if E_POSTGRES:
        _ativar_unaccent()


_UNACCENT = {"ok": False}


def _ativar_unaccent() -> None:
    """Busca sem acento no PostgreSQL ("certidao" acha "certidão"). Sem permissão para criar a
    extensão, a busca continua funcionando, só que diferenciando acento."""
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        _UNACCENT["ok"] = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("extensão unaccent indisponível (%s): busca vai diferenciar acento", e)


def tem_unaccent() -> bool:
    return _UNACCENT["ok"]


def migrar_colunas() -> list[str]:
    """Migração leve: adiciona as colunas novas que ainda não existem em tabelas antigas.

    create_all() cria tabelas, mas não altera as que já existem. Aqui só ADICIONAMOS colunas
    (nunca removemos nem mudamos tipo), então é seguro rodar a cada start.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    adicionadas = []
    with engine.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for col in tabela.columns:
                if col.name in existentes:
                    continue
                tipo = col.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE {tabela.name} ADD COLUMN "{col.name}" {tipo}'
                if col.server_default is not None:     # entre aspas: vale em SQLite e PostgreSQL ('2', 'confiavel', '0')
                    valor = str(col.server_default.arg).replace("'", "''")
                    ddl += f" DEFAULT '{valor}'"
                conn.execute(text(ddl))
                adicionadas.append(f"{tabela.name}.{col.name}")
    return adicionadas


def migrar_perfis_revisor() -> int:
    """Promove contas analistas para revisor, preservando contas admin."""
    from sqlalchemy import text

    with engine.begin() as conn:
        resultado = conn.execute(text("UPDATE usuarios SET perfil = 'revisor' WHERE perfil = 'analista'"))
    return max(resultado.rowcount, 0)
