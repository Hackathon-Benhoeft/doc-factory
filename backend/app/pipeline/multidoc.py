"""Vários documentos numa mesma imagem (F8): RG + comprovante fotografados lado a lado, duas folhas num scan.

Por que no upload e não no pipeline: detectamos as folhas por CONTORNOS (bordas da folha contra o fundo),
recortamos cada uma e reescrevemos o arquivo como um PDF em que cada recorte é uma página. Daí em diante o
pipeline é o de sempre. Se nada for detectado — ou se qualquer coisa der errado — devolvemos None e o arquivo
segue EXATAMENTE como veio. Regras conservadoras de propósito: folha única grande (≥ 85% da página), regiões
demais ou sem conteúdo → não divide. PDF com texto nativo nunca é mexido. Não usamos "espaço em branco"
(partiria documentos legítimos com lacunas) nem IA para decidir cortes físicos.
"""
import io
import logging
import os
from dataclasses import dataclass

from app.config import settings

log = logging.getLogger(__name__)

EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
FRACAO_FOLHA_UNICA = 0.85
LADO_MIN_FRACAO = 0.15
ASPECTO_MAX = 4.0
CONTEUDO_DESVIO_MIN = 12.0
CONTIDO_MIN = 0.8
LADO_DETECCAO = 1170          # ~A4 a 100 dpi: detecção rápida em imagem de qualquer tamanho
A4_LARGURA_PT = 595.0


@dataclass
class Recorte:
    caixa: tuple[int, int, int, int]   # x0,y0,x1,y1 na imagem de detecção
    png: bytes                          # recorte na resolução final (já endireitado se rotacionado)


def _ordenar_pontos(pts):
    import numpy as np
    pts = np.asarray(pts, dtype="float32")
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype="float32")  # tl tr br bl


def detectar_regioes(img_bgr) -> list[dict]:
    """Regiões de folha na escala da detecção: [{"caixa": (x0,y0,x1,y1), "pontos": 4 cantos}] — [] = não dividir."""
    import cv2
    import numpy as np

    altura, largura = img_bgr.shape[:2]
    area_pag, lado_pag = float(altura * largura), float(min(altura, largura))
    cinza = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    bordas = cv2.Canny(cv2.GaussianBlur(cinza, (5, 5), 0), 50, 150)
    bordas = cv2.dilate(bordas, np.ones((5, 5), np.uint8), iterations=2)
    contornos, _ = cv2.findContours(bordas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regioes = []
    for c in contornos:
        (cx, cy), (w, h), ang = cv2.minAreaRect(c)
        if w * h < area_pag * settings.MULTIDOC_AREA_MIN_PCT / 100:
            continue
        if min(w, h) < LADO_MIN_FRACAO * lado_pag or max(w, h) / max(min(w, h), 1) > ASPECTO_MAX:
            continue
        pontos = cv2.boxPoints(((cx, cy), (w, h), ang))
        x0, y0 = np.clip(pontos.min(axis=0), 0, None).astype(int)
        x1, y1 = pontos.max(axis=0).astype(int)
        x1, y1 = min(int(x1), largura), min(int(y1), altura)
        regioes.append({"caixa": (int(x0), int(y0), x1, y1), "pontos": pontos, "area": w * h})

    # região contida noutra (ex.: o quadro interno de um RG): fica a maior
    regioes.sort(key=lambda r: -r["area"])
    unicas: list[dict] = []
    for r in regioes:
        if not any(_contido(r["caixa"], u["caixa"]) > CONTIDO_MIN for u in unicas):
            unicas.append(r)

    if any(r["area"] >= FRACAO_FOLHA_UNICA * area_pag for r in unicas):
        return []                                     # é um documento só
    unicas = [r for r in unicas if _tem_conteudo(cinza, r["caixa"])]
    if len(unicas) < 2 or len(unicas) > settings.MULTIDOC_MAX_RECORTES:
        return []
    return _ordem_de_leitura(unicas)


def detectar_recortes(img_bgr) -> list[tuple[int, int, int, int]]:
    """Caixas das folhas na escala da detecção (função pura). [] = não dividir."""
    return [r["caixa"] for r in detectar_regioes(img_bgr)]


def _contido(a, b) -> float:
    """Fração da área de `a` que está dentro de `b`."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return ix * iy / area_a


def _tem_conteudo(cinza, caixa) -> bool:
    x0, y0, x1, y1 = caixa
    trecho = cinza[y0:y1, x0:x1]
    return trecho.size > 0 and float(trecho.std()) > CONTEUDO_DESVIO_MIN


def _ordem_de_leitura(regioes: list[dict]) -> list[dict]:
    """De cima para baixo; regiões na mesma "linha" (sobreposição vertical > 50%) da esquerda para a direita."""
    regioes = sorted(regioes, key=lambda r: r["caixa"][1])
    linhas: list[list[dict]] = []
    for r in regioes:
        y0, y1 = r["caixa"][1], r["caixa"][3]
        if linhas:
            ref = linhas[-1][0]["caixa"]
            sobre = max(0, min(y1, ref[3]) - max(y0, ref[1]))
            if sobre > 0.5 * min(y1 - y0, ref[3] - ref[1]):
                linhas[-1].append(r)
                continue
        linhas.append([r])
    return [r for linha in linhas for r in sorted(linha, key=lambda r: r["caixa"][0])]


def recortar(png_original: bytes, regioes, escala: float) -> list[Recorte]:
    """Recorta cada região na resolução final. Folha inclinada (> 2°) é endireitada por perspectiva."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(png_original, np.uint8), cv2.IMREAD_COLOR)
    alt, larg = img.shape[:2]
    saida = []
    for r in regioes:
        caixa = r["caixa"] if isinstance(r, dict) else r
        pontos = r.get("pontos") if isinstance(r, dict) else None
        recorte = None
        if pontos is not None:
            tl, tr, br, bl = _ordenar_pontos(np.asarray(pontos) * escala)
            angulo = abs(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))
            if 2 < angulo < 45:
                w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
                h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
                m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype="float32"),
                                                np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32"))
                recorte = cv2.warpPerspective(img, m, (w, h), borderValue=(255, 255, 255))
        if recorte is None:
            x0, y0, x1, y1 = (int(v * escala) for v in caixa)
            mx, my = int(0.01 * larg), int(0.01 * alt)
            recorte = img[max(0, y0 - my):min(alt, y1 + my), max(0, x0 - mx):min(larg, x1 + mx)]
        ok, buf = cv2.imencode(".png", recorte)
        if ok:
            saida.append(Recorte(caixa=tuple(caixa), png=buf.tobytes()))
    return saida


def _decodificar(png: bytes):
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


def _png_de_pil(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _dividir_imagem(png: bytes) -> list[Recorte]:
    """Detecta numa cópia reduzida e recorta no original. [] = não dividir."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    alt, larg = img.shape[:2]
    if alt * larg / 1e6 > settings.MAX_MEGAPIXELS_PAGINA * 4:
        log.info("multidoc: imagem grande demais (%.0f MP); não divide", alt * larg / 1e6)
        return []
    escala = max(alt, larg) / LADO_DETECCAO
    pequena = cv2.resize(img, (max(1, int(larg / escala)), max(1, int(alt / escala))), interpolation=cv2.INTER_AREA)
    regioes = detectar_regioes(pequena)
    return recortar(png, regioes, escala) if regioes else []


def _pagina_imagem(doc, png: bytes) -> None:
    from PIL import Image
    w, h = Image.open(io.BytesIO(png)).size
    pagina = doc.new_page(width=A4_LARGURA_PT, height=A4_LARGURA_PT * h / max(w, 1))
    pagina.insert_image(pagina.rect, stream=png)


def normalizar_arquivo(conteudo: bytes, nome: str) -> tuple[bytes, list[dict]] | None:
    """Arquivo com ≥ 2 folhas numa mesma página → (PDF normalizado, [{"pagina_original", "recortes"}]).
    Nada a dividir, PDF com texto nativo, ou qualquer erro → None (o arquivo segue como veio)."""
    try:
        return _normalizar(conteudo, nome)
    except Exception:
        log.exception("multidoc: falha ao analisar %s; seguindo com o arquivo original", nome)
        return None


def _normalizar(conteudo: bytes, nome: str) -> tuple[bytes, list[dict]] | None:
    import pymupdf
    from PIL import Image, ImageOps, ImageSequence

    ext = os.path.splitext(nome or "")[1].lower()
    paginas: list[tuple[str, object]] = []          # ("png", bytes) para imagem | ("pdf", índice) para página PDF
    divisoes: dict[int, list[Recorte]] = {}
    origem_pdf = None

    if ext in EXT_IMAGEM:
        img = Image.open(io.BytesIO(conteudo))
        for i, quadro in enumerate(ImageSequence.Iterator(img)):
            # o tamanho vem do cabeçalho (sem decodificar): recusa ANTES de alocar a imagem inteira na memória
            if quadro.width * quadro.height / 1e6 > settings.MAX_MEGAPIXELS_PAGINA:
                log.info("multidoc: quadro de %.0f MP grande demais; não analisa", quadro.width * quadro.height / 1e6)
                return None
            png = _png_de_pil(ImageOps.exif_transpose(quadro.convert("RGB")))
            paginas.append(("png", png))
            rec = _dividir_imagem(png)
            if len(rec) >= 2:
                divisoes[i] = rec
    elif ext == ".pdf" and settings.MULTIDOC_PDF:
        origem_pdf = pymupdf.open(stream=conteudo, filetype="pdf")
        for i, pag in enumerate(origem_pdf):
            paginas.append(("pdf", i))
            if len(pag.get_text().strip()) >= settings.TEXTO_NATIVO_MIN_CHARS:
                continue                              # PDF digital: nunca mexe
            # detecta em baixa resolução (rápido); só renderiza em alta a página que vai ser dividida
            baixa = pag.get_pixmap(dpi=settings.MULTIDOC_DPI_DETECCAO, colorspace=pymupdf.csRGB).tobytes("png")
            regioes = detectar_regioes(_decodificar(baixa))
            if len(regioes) >= 2:
                alta = pag.get_pixmap(dpi=settings.MULTIDOC_DPI_RECORTE, colorspace=pymupdf.csRGB).tobytes("png")
                rec = recortar(alta, regioes, settings.MULTIDOC_DPI_RECORTE / settings.MULTIDOC_DPI_DETECCAO)
                if len(rec) >= 2:
                    divisoes[i] = rec
    else:
        return None

    if not divisoes:
        return None
    novo = pymupdf.open()
    for i, (tipo, valor) in enumerate(paginas):
        if i in divisoes:
            for r in divisoes[i]:
                _pagina_imagem(novo, r.png)
        elif tipo == "pdf":
            novo.insert_pdf(origem_pdf, from_page=valor, to_page=valor)
        else:
            _pagina_imagem(novo, valor)
    info = [{"pagina_original": i, "recortes": len(r)} for i, r in sorted(divisoes.items())]
    return novo.tobytes(garbage=3, deflate=True), info
