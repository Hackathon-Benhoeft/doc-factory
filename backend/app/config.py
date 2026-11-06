"""Configuração central — tudo vem de variáveis de ambiente / arquivo .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Infra ---------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./data/docfactory.db"   # prod: postgresql+psycopg://...
    STORAGE_BACKEND: str = "local"                    # local | s3 (MinIO/S3/GCS-interop)
    DATA_DIR: str = "./data"                          # raiz do storage local + cache
    S3_ENDPOINT: str | None = None                    # ex.: http://minio:9000
    S3_BUCKET: str = "docfactory"
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None

    # --- Ambiente -----------------------------------------------------------
    # producao = a API se recusa a subir sem login, sem segredos ou com CORS aberto
    AMBIENTE: str = "desenvolvimento"   # desenvolvimento | producao

    # --- Segurança -------------------------------------------------------
    CADASTRO_ABERTO: bool = True        # /auth/registrar: qualquer pessoa cria conta de revisor (desligue em produção)
    LOGIN_MAX_TENTATIVAS: int = 5       # erros seguidos de senha antes de bloquear o login
    LOGIN_BLOQUEIO_MIN: int = 5         # minutos de bloqueio
    MAX_MEGAPIXELS_PAGINA: float = 60.0 # página maior que isso é renderizada com DPI menor (protege a memória)
    API_KEY: str | None = None          # se definido, exige header X-API-Key
    CORS_ORIGINS: str = "*"             # separar por vírgula
    # login com perfis (analista < revisor < admin). Desligado = API aberta (demo).
    AUTH_ATIVO: bool = False
    JWT_SEGREDO: str | None = None      # sem valor: gera um aleatório a cada start (tokens caem no restart)
    JWT_EXPIRA_MIN: int = 480
    ADMIN_USUARIO: str = "admin"        # criado no primeiro start se não houver usuários
    ADMIN_SENHA: str | None = None      # sem valor: nenhum admin é criado automaticamente
    MAX_UPLOAD_MB: int = 2048
    EXTENSOES_PERMITIDAS: str = ".pdf,.tif,.tiff,.png,.jpg,.jpeg"

    # --- Pipeline: rasterização + OCR -----------------------------------
    DPI_OCR: int = 300                  # 300 dpi = sweet spot do Tesseract
    DPI_THUMB: int = 40
    OCR_LANG: str = "por"
    OCR_PSM: int = 3                    # 3 = segmentação automática de página
    OCR_TIMEOUT_S: int = 90             # página que trava o Tesseract vira 'erro' e é retentada
    TEXTO_NATIVO_MIN_CHARS: int = 50    # PDF digital com texto → pula OCR

    # --- Anonimização ------------------------------------------------------
    ANONIMIZAR_NOMES: bool = True       # nomes de pessoas → [NOME] (rótulos do documento + reconhecedor spaCy)
    ANONIMIZAR_ENDERECOS: bool = True   # logradouro + número → [ENDERECO], CEP → [CEP] (cidades ficam)
    NER_MODELO: str = "pt_core_news_md" # modelo spaCy em português; ausente = só as regras por rótulo
    CPF_SEGREDO: str | None = None      # segredo da impressão digital do CPF (dossiê); defina em produção

    # --- Classificação / revisão ----------------------------------------
    LIMIAR_REVISAO: float = 0.70       # abaixo disso → fila de revisão humana
    LIMIAR_LLM: float = 0.75            # regra abaixo disso → consulta o modelo
    LLM_SEMPRE: bool = False            # True = modelo em toda página (2ª opinião)
    BRANCO_COMO_SEPARADOR: bool = True  # página em branco fecha o documento atual

    # --- Modelo (qualquer API compatível com OpenAI) -----------------------
    LLM_PROVIDER: str = "nenhum"        # nenhum | openai | gemini | deepseek | ollama | custom
    LLM_MODEL: str = ""
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None     # sobrescreve a URL padrão do provedor
    LLM_MULTIMODAL: bool = True         # envia a imagem (mascarada) junto do texto
    LLM_TIMEOUT: int = 60
    LLM_CUSTO_POR_CHAMADA_BRL: float = 0.0  # custo médio por chamada de IA, só para estimativa na tela (0 = não mostrar R$)
    FRAUDE_ATENCAO_REVISAO: bool = True
    FUNCAO_EXIGENCIAS_ATIVO: bool = True
    PRE_REVISAO_ATIVA: bool = True          # documento pendente ganha explicação + sugestão antes do revisor abrir
    PRE_REVISAO_MAX_POR_LOTE: int = 50      # teto de chamadas de IA de pré-revisão por lote (o resto: por regras)

    # --- Vários documentos numa imagem (F8): detecção por contornos, no upload -------------
    MULTIDOC_ATIVO: bool = True
    MULTIDOC_PDF: bool = True               # também em páginas-imagem de PDF escaneado (nunca em PDF com texto)
    MULTIDOC_AREA_MIN_PCT: float = 8.0      # cada folha precisa ter pelo menos 8% da área da página
    MULTIDOC_MAX_RECORTES: int = 6          # mais regiões que isso = suspeito, não divide
    MULTIDOC_DPI_DETECCAO: int = 100
    MULTIDOC_DPI_RECORTE: int = 300
    MULTIDOC_MAX_MB: int = 100              # arquivo maior que isso não passa pela detecção (memória)

    # --- Portal do fornecedor (F7): link privado, sem login --------------------------------
    PORTAL_ATIVO: bool = True
    PORTAL_URL_BASE: str = "http://localhost:5173"   # o link enviado ao fornecedor é {base}/portal/{token}
    PORTAL_MAX_UPLOAD_MB: int = 20
    PORTAL_MAX_PAGINAS: int = 30
    PORTAL_MAX_ENVIOS_POR_HORA: int = 30   # por link e IP
    PORTAL_VALIDADE_DIAS: int = 14         # expiração padrão do convite
    PORTAL_PRIORIDADE: int = 3             # lote do portal passa na frente no worker (veredito rápido)

    # --- Alertas de vencimento (F6): o agendador é o laço do worker --------------------------
    ALERTAS_ATIVO: bool = False             # liga o envio automático (1x por dia) dentro do worker
    ALERTAS_MODO: str = "simulado"          # simulado (só registra e loga) | real (envia de verdade)
    ALERTAS_FAIXAS_DIAS: str = "30,15,7,1"  # avisa ao entrar em cada faixa de dias antes do vencimento
    ALERTAS_HORA_EXECUCAO: int = 8          # hora local (FUSO_HORAS) a partir da qual roda no dia
    ALERTAS_URL_PUBLICA: str = "http://localhost:5173"   # base dos links nas mensagens
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USUARIO: str = ""
    SMTP_SENHA: str = ""                    # nunca aparece em log nem em resposta da API
    SMTP_REMETENTE: str = ""
    SMTP_TLS: bool = True
    EVOLUTION_URL: str = ""                 # WhatsApp via Evolution API, ex.: http://localhost:8080
    EVOLUTION_INSTANCIA: str = ""           # instância já conectada ao WhatsApp
    EVOLUTION_APIKEY: str = ""              # nunca aparece em log nem em resposta da API    # a função lida no ASO/CTPS acrescenta as NRs exigidas ao checklist     # documento com risco "atencao" também vai para a fila de revisão

    # --- Validade -----------------------------------------------------------
    VALIDADE_ALERTA_DIAS: int = 30      # vence em até N dias → status "vencendo" (e prioridade alta)
    FUSO_HORAS: int = -3                # fuso para "hoje" / "esta semana" nos painéis (Brasília = -3)

    # --- Resumo -------------------------------------------------------------
    RESUMO_ATIVO: bool = True           # gera resumo de cada documento (modelo, ou simples sem modelo)
    RESUMO_CHARS_POR_PARTE: int = 6000  # documento maior que isso é resumido em partes e depois consolidado

    # --- Worker -----------------------------------------------------------
    MAX_TENTATIVAS: int = 3
    WORKER_POLL_S: float = 1.0
    WORKER_STALE_MIN: int = 2           # página "processando" há mais que isso = worker morreu
    WORKER_INLINE: bool = False         # True = roda o worker numa thread dentro da API (dev/demo)

    @property
    def alertas_faixas(self) -> list[int]:
        """"30,15,7,1" → [1, 7, 15, 30] (ordenada, sem repetição, ignora o que não for número positivo)."""
        faixas = set()
        for x in self.ALERTAS_FAIXAS_DIAS.split(","):
            try:
                n = int(x.strip())
            except ValueError:
                continue
            if n > 0:
                faixas.add(n)
        return sorted(faixas)

    @property
    def extensoes(self) -> set[str]:
        return {e.strip().lower() for e in self.EXTENSOES_PERMITIDAS.split(",")}


settings = Settings()
