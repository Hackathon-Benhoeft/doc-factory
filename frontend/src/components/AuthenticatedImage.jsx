import { useEffect, useState } from 'react';
import api from '../services/api';

export default function AuthenticatedImage({ src, alt, className = '' }) {
  const [imagem, setImagem] = useState(null);
  const atual = imagem?.src === src ? imagem : null;

  useEffect(() => {
    let ativo = true;
    let url;
    api.get(src, { responseType: 'blob' })
      .then(({ data }) => {
        if (!ativo) return;
        url = URL.createObjectURL(data);
        setImagem({ src, url, erro: false });
      })
      .catch(() => {
        if (ativo) setImagem({ src, url: '', erro: true });
      });

    return () => {
      ativo = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [src]);

  if (atual?.url) {
    return <img className={className} src={atual.url} alt={alt} />;
  }
  if (atual?.erro) {
    return <div className={`${className} flex items-center justify-center bg-slate-100 p-2 text-center text-[10px] text-slate-500`}>Imagem indisponível</div>;
  }
  return <div className={`${className} animate-pulse bg-slate-100`} role="status" aria-label="Carregando imagem" />;
}
