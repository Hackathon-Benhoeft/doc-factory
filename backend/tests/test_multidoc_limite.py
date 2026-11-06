"""Imagem acima do limite de megapixels não pode ser decodificada pelo multidocumento (protege a memória da API)."""
import io

from PIL import Image

from app.config import settings
from app.pipeline import multidoc


def test_imagem_acima_do_limite_nao_e_decodificada(monkeypatch):
    monkeypatch.setattr(settings, "MAX_MEGAPIXELS_PAGINA", 1.0)          # limite de 1 MP
    decodificadas = []

    def espiao(*a, **k):                      # normalizar_arquivo engole exceções: por isso registra e não levanta
        decodificadas.append(1)
        raise RuntimeError("não deveria decodificar")

    monkeypatch.setattr(multidoc, "_png_de_pil", espiao)
    buf = io.BytesIO()
    Image.new("L", (1600, 1200), 255).save(buf, "PNG")                   # 1,9 MP: pequena em bytes, grande em pixels
    assert multidoc.normalizar_arquivo(buf.getvalue(), "grande.png") is None
    assert decodificadas == [], "decodificou (alocou na memória) uma imagem acima do limite"
