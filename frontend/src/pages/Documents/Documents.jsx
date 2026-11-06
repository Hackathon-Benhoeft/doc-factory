import { useCallback, useEffect, useState } from 'react';
import Sidebar from '../../components/Sidebar';
import Header from '../../components/Header';
import AuthenticatedImage from '../../components/AuthenticatedImage';
import api from '../../services/api';
import RelatorioPrivacidade from '../../components/Privacidade/RelatorioPrivacidade';
import PainelAcerto from '../../components/Documents/PainelAcerto';
import { Selo } from '../../components/Estados';
import { avisarFilaMudou, pct } from '../../utils/formatar';

const button = 'rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium hover:bg-slate-50 disabled:opacity-50';

export default function Documents() {
  const [lotes, setLotes] = useState([]);
  const [documentos, setDocumentos] = useState([]);
  const [tipos, setTipos] = useState([]);
  const [versoes, setVersoes] = useState([]);
  const [busca, setBusca] = useState('');
  const [loteAtivo, setLoteAtivo] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [progressoEnvio, setProgressoEnvio] = useState(null);
  const [aberto, setAberto] = useState(null);
  const [corte, setCorte] = useState('');
  const [tipo, setTipo] = useState('');
  const [versaoRelatorio, setVersaoRelatorio] = useState(0);   // sobe após revisar/reprocessar: o relatório de privacidade é buscado de novo
  const [reprocessando, setReprocessando] = useState(false);
  const [regrasLote, setRegrasLote] = useState('');             // regras de separação só para o próximo envio
  const [verAcerto, setVerAcerto] = useState(false);
  const lote = lotes.find(l => l.id === loteAtivo);

  const atualizar = useCallback(async () => {
    try {
      const [l, d, t] = await Promise.all([
        api.get('/lotes'), api.get('/documentos', { params: { q: busca || undefined, lote_id: loteAtivo || undefined, por_pagina: 200 } }), api.get('/tipos'),
      ]);
      setLotes(l.data); setDocumentos(d.data.itens); setTipos(t.data);
      if (loteAtivo) {
        try { const v = await api.get(`/lotes/${loteAtivo}/versoes`); setVersoes(v.data); }
        catch { setVersoes([]); }
      } else { setVersoes([]); }
    } catch (e) { setErro(e.response?.data?.erro?.mensagem || 'Não foi possível acessar o backend.'); }
  }, [busca, loteAtivo]);

  useEffect(() => {
    const primeira = setTimeout(atualizar, 0);
    const timer = setInterval(atualizar, 4000);
    return () => { clearTimeout(primeira); clearInterval(timer); };
  }, [atualizar]);

  async function enviar(event) {
    const arquivo = event.target.files?.[0];
    event.target.value = '';
    if (!arquivo) return;
    const dados = new FormData(); dados.append('arquivo', arquivo);
    if (regrasLote.trim()) dados.append('regras', regrasLote.trim());
    setErro(''); setProgressoEnvio(null); setEnviando(true);
    try {
      const r = await api.post('/lotes', dados, {
        onUploadProgress: ({ loaded, total }) => {
          if (total > 0) setProgressoEnvio(Math.min(100, Math.floor(loaded * 100 / total)));
        },
      });
      setLoteAtivo(r.data.id); setAberto(null); await atualizar();
    } catch (e) {
      setErro(e.response?.status === 413 ? 'O arquivo ultrapassa o limite permitido para envio.' :
        e.response?.data?.erro?.mensagem || 'Não foi possível enviar o arquivo. Verifique a conexão e tente novamente.');
    } finally { setEnviando(false); setProgressoEnvio(null); }
  }

  async function revisar(acao, extras = {}) {
    try {
      await api.post(`/documentos/${aberto.id}/revisao`, { acao, usuario: 'revisor', ...extras });
      setAberto(null); setCorte(''); setVersaoRelatorio(v => v + 1); avisarFilaMudou(); await atualizar();
    } catch (e) { setErro(e.response?.data?.erro?.mensagem || 'Não foi possível salvar a revisão.'); }
  }

  async function reprocessar(tudo) {
    if (reprocessando || lote?.status === 'processando' || lote?.status === 'segmentando') return;
    setReprocessando(true);
    try {
      if (!tudo) {
        const { data: paginas } = await api.get(`/lotes/${loteAtivo}/paginas`);
        if (!paginas.some(pagina => ['erro', 'falhou'].includes(pagina.status))) {
          setErro('Não há páginas com erro para reprocessar. Para executar novamente, escolha “Reprocessar lote completo”.');
          return;
        }
      }
      await api.post(`/lotes/${loteAtivo}/reprocessar`, null, { params: { tudo } });
      setAberto(null);
      await atualizar();
      setVersaoRelatorio(v => v + 1);
    } catch (e) { setErro(e.response?.data?.erro?.mensagem || e.response?.data?.detail || 'Não foi possível reprocessar o lote.'); }
    finally { setReprocessando(false); }
  }

  const loteProcessando = lote?.status === 'processando' || lote?.status === 'segmentando';

  return <div className="min-h-screen bg-slate-50 flex font-sans antialiased">
    <Sidebar /><div className="flex-1 ml-64 flex flex-col"><Header />
      <main className="p-8 max-w-7xl w-full mx-auto space-y-6">
        <div className="flex justify-between items-center gap-4">
          <div><h1 className="text-2xl font-bold text-slate-900">Documentos</h1><p className="text-sm text-slate-500">Envie um lote e acompanhe o processamento.</p></div>
          <div className="flex flex-wrap items-center gap-2">
            <input aria-label="Regras de separação só para este lote" className="w-72 rounded-xl border border-slate-200 px-3 py-3 text-xs" placeholder="Regras só para este lote (opcional), ex.: mantenha o contrato inteiro junto" value={regrasLote} onChange={e => setRegrasLote(e.target.value)} />
            <label className="cursor-pointer rounded-xl bg-indigo-950 px-4 py-3 text-sm text-white">{enviando ? 'Enviando...' : 'Enviar documentos'}<input className="sr-only" type="file" accept=".pdf,.tif,.tiff,.png,.jpg,.jpeg" onChange={enviar} disabled={enviando} /></label>
          </div>
        </div>
        {enviando && <div className="rounded-xl bg-white border border-slate-100 p-4" role="status" aria-live="polite">
          <p className="text-sm text-slate-700">{progressoEnvio === 100 ? 'Envio concluído. Aguardando confirmação do servidor...' : progressoEnvio === null ? 'Preparando envio...' : `Enviando arquivo: ${progressoEnvio}%`}</p>
          {progressoEnvio !== null && <progress className="mt-2 w-full" max="100" value={progressoEnvio} aria-label="Progresso do envio" />}
        </div>}
        {erro && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{erro}</div>}
        <section className="rounded-xl bg-white border border-slate-100 p-5"><h2 className="font-bold mb-3">Lotes enviados</h2>
          {lotes.length === 0 ? <p className="text-sm text-slate-500">Nenhum lote enviado.</p> : <div className="space-y-2">{lotes.map(l => <button key={l.id} onClick={() => { setLoteAtivo(l.id); setAberto(null); setVerAcerto(false); }} className={`w-full text-left rounded-lg p-3 text-sm ${l.id === loteAtivo ? 'bg-indigo-50' : 'bg-slate-50'}`}><strong>{l.nome}</strong> — {l.status} · {l.paginas_processadas}/{l.total_paginas} páginas ({Math.round(l.progresso * 100)}%)
            {l.ia && <span className="ml-2 inline-block rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-semibold text-indigo-700" title={`${l.ia.chamadas_classificacao} classificação · ${l.ia.chamadas_resumo} resumo · ${l.ia.chamadas_outras} outras`}>IA em {pct(l.ia.percentual_paginas_com_ia)} das páginas · {l.ia.chamadas_total} chamada(s)</span>}
            {l.origem === 'portal' && <span className="ml-2 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">Portal{l.fornecedor ? `: ${l.fornecedor}` : ''}</span>}
            {l.multidoc && <span className="ml-2 inline-block rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-semibold text-sky-800">{l.multidoc.reduce((s, m) => s + m.recortes, 0)} folhas recortadas de {l.multidoc.length} página(s)</span>}
            {l.erro && <span className="block text-red-700">{l.erro}</span>}</button>)}</div>}
        </section>
        {loteAtivo && lotes.find(l => l.id === loteAtivo)?.alertas?.filter(a => a.codigo === 'paginas_incerto').map(a =>
          <div key={a.codigo} role="alert" className="rounded-xl bg-amber-50 p-4 text-sm text-amber-800">{a.mensagem} {a.evidencia}</div>
        )}
        {loteAtivo && <div className="flex flex-wrap gap-2"><button className={button} disabled={reprocessando || loteProcessando} onClick={() => reprocessar(false)}>{reprocessando || loteProcessando ? 'Aguardando processamento...' : 'Reprocessar páginas com erro'}</button><button className={button} disabled={reprocessando || loteProcessando} onClick={() => reprocessar(true)}>Reprocessar lote completo</button>
          {lote?.tem_gabarito && <button className={button} onClick={() => setVerAcerto(v => !v)}>{verAcerto ? 'Ocultar acerto' : 'Ver acerto'}</button>}</div>}
        {loteAtivo && verAcerto && <PainelAcerto loteId={loteAtivo} />}
        {lote?.regras_aplicadas?.length > 0 && <p className="text-xs text-slate-500">Regras de separação deste lote: {lote.regras_aplicadas.map(r => `“${r.texto}”`).join(', ')}</p>}
        {loteAtivo && <RelatorioPrivacidade loteId={loteAtivo} concluido={lotes.find(l => l.id === loteAtivo)?.status === 'concluido'} recarregar={versaoRelatorio} />}
        <section className="rounded-xl bg-white border border-slate-100 p-5 space-y-4"><div className="flex justify-between items-center gap-4"><h2 className="font-bold">Documentos {loteAtivo && 'do lote'}</h2><button className={button} onClick={() => { setLoteAtivo(''); setAberto(null); }}>Todos os lotes</button></div>
          <input className="border rounded-lg px-3 py-2 text-sm w-full" placeholder="Buscar no texto dos documentos" value={busca} onChange={e => setBusca(e.target.value)} />
          {documentos.length === 0 ? <p className="text-sm text-slate-500">Nenhum documento encontrado.</p> : <div className="space-y-2">{documentos.map(d => <button key={d.id} className="w-full text-left p-3 rounded-lg border border-slate-100 hover:bg-slate-50 text-sm" onClick={() => { setAberto(d); setTipo(d.tipo); }}><strong>{d.titulo || d.tipo_nome}</strong> · {d.tipo_nome} · páginas {d.pagina_inicio + 1}–{d.pagina_fim + 1}
            <span className="ml-2 inline-flex flex-wrap gap-1 align-middle"><Selo valor={d.status_revisao} />{d.risco !== 'confiavel' && <Selo valor={d.risco} />}{d.origem_texto && <Selo valor="nao_enviado" texto={d.origem_texto} />}</span>
            {d.ia_justificativa && <span className="block text-xs text-slate-500">IA: {d.ia_justificativa}</span>}</button>)}</div>}
          {documentos.length === 200 && <p className="text-xs text-slate-500">Exibindo até 200 documentos; refine a busca ou selecione um lote.</p>}
        </section>
        {loteAtivo && versoes.length > 0 && <section className="rounded-xl bg-white border border-slate-100 p-5 space-y-4">
          <h2 className="font-bold">Comparar com versões anteriores</h2>
          <p className="text-sm text-slate-500">As correções anteriores ficam no histórico; confira os novos resultados e revise novamente quando necessário.</p>
          {versoes.map(v => <details key={v.id} className="rounded-lg border border-slate-200 p-3">
            <summary className="cursor-pointer font-medium text-sm">Versão {v.id} · {new Date(v.criado_em).toLocaleString('pt-BR')} · {v.revisoes.length} revisões</summary>
            <div className="grid md:grid-cols-2 gap-4 mt-4 text-sm">
              <div><h3 className="font-bold mb-2">Antes do reprocessamento</h3>{v.documentos.map(d => <p key={d.id} className="mb-2">{d.tipo} · páginas {d.pagina_inicio + 1}–{d.pagina_fim + 1} · {d.status_revisao} <a className="text-indigo-700 underline" href={`${api.defaults.baseURL}/lotes/${loteAtivo}/versoes/${v.id}/documentos/${d.id}/pdf`} target="_blank" rel="noreferrer">PDF</a></p>)}</div>
              <div><h3 className="font-bold mb-2">Resultado atual</h3>{documentos.map(d => <p key={d.id} className="mb-2">{d.tipo_nome} · páginas {d.pagina_inicio + 1}–{d.pagina_fim + 1} · {d.status_revisao}</p>)}</div>
            </div>
            {v.revisoes.length > 0 && <div className="mt-3 text-xs text-slate-600"><strong>Histórico:</strong> {v.revisoes.map(r => `${r.usuario}: ${r.acao}`).join(' · ')}</div>}
          </details>)}
        </section>}
        {aberto && <section className="rounded-xl bg-white border border-slate-100 p-5 space-y-4"><div className="flex justify-between"><h2 className="font-bold">Revisar {aberto.titulo || aberto.tipo_nome}</h2><button className={button} onClick={() => setAberto(null)}>Fechar</button></div>
          <p className="text-sm text-slate-600">Páginas {aberto.pagina_inicio + 1} a {aberto.pagina_fim + 1} · Indicador de confiança: {Math.round(aberto.confianca * 100)}% · {aberto.status_revisao}</p>
          {aberto.motivos?.length > 0 && <p className="text-sm text-amber-700">{aberto.motivos.join('; ')}</p>}
          <div className="flex flex-wrap gap-2 text-xs">
            {aberto.origem_texto && <Selo valor="nao_enviado" texto={aberto.origem_texto} />}
            {aberto.resumo_origem && <Selo valor="nao_enviado" texto={aberto.resumo_origem === 'modelo' ? 'Resumo por IA' : 'Resumo simples (regras)'} />}
            {aberto.validade?.origem && <Selo valor={aberto.validade.status} texto={`Validade (${aberto.validade.origem === 'modelo' ? 'IA' : aberto.validade.origem})`} title={aberto.validade.evidencia ? `Evidência: ${aberto.validade.evidencia}` : undefined} />}
            <Selo valor={aberto.risco} />
          </div>
          {aberto.ia_justificativa && <p className="text-xs text-slate-600">Justificativa da IA: {aberto.ia_justificativa}</p>}
          {aberto.validade?.evidencia && <p className="text-xs text-slate-600">Prova da validade: “{aberto.validade.evidencia}”</p>}
          {aberto.regras_aplicadas?.length > 0 && <p className="text-xs text-indigo-700">Regra aplicada: {aberto.regras_aplicadas.join('; ')}</p>}
          {aberto.alertas?.length > 0 && <ul className="list-disc pl-5 text-xs text-rose-700">{aberto.alertas.map(a => <li key={a.codigo + a.evidencia}>{a.mensagem} — {a.evidencia}</li>)}</ul>}
          {aberto.resumo && <p className="text-sm text-slate-700">{aberto.resumo}</p>}
          <div className="flex gap-3 overflow-x-auto">{Array.from({ length: aberto.n_paginas }, (_, i) => aberto.pagina_inicio + i).map(n => <figure key={n} className="min-w-28 text-xs text-slate-500"><AuthenticatedImage className="w-28 border" src={`/lotes/${aberto.lote_id}/paginas/${n}/imagem?thumb=true`} alt={`Página ${n + 1}`} /><figcaption>Página {n + 1}</figcaption></figure>)}</div>
          <div className="flex flex-wrap gap-2 items-center"><a className={button} href={`${api.defaults.baseURL}/documentos/${aberto.id}/pdf`} target="_blank" rel="noreferrer">Abrir PDF</a><button className={button} onClick={() => revisar('aprovar')}>Aprovar</button><button className={button} onClick={() => revisar('juntar_proximo')}>Juntar ao próximo</button></div>
          <div className="flex flex-wrap gap-2"><select aria-label="Tipo do documento" className={button} value={tipo} onChange={e => setTipo(e.target.value)}>{!tipos.some(t => t.codigo === tipo) && <option value={tipo}>{tipo}</option>}{tipos.map(t => <option key={t.codigo} value={t.codigo}>{t.nome}</option>)}</select><button className={button} onClick={() => revisar('alterar_tipo', { tipo })}>Alterar tipo</button></div>
          <div className="flex flex-wrap gap-2 items-center"><label className="text-sm" htmlFor="pagina-corte">Dividir a partir da página:</label><input id="pagina-corte" className="border rounded-lg px-3 py-2 text-sm w-24" type="number" min={aberto.pagina_inicio + 2} max={aberto.pagina_fim + 1} value={corte} onChange={e => setCorte(e.target.value)} /><button className={button} disabled={!corte} onClick={() => revisar('dividir', { pagina_corte: Number(corte) - 1 })}>Dividir</button></div>
        </section>}
      </main>
    </div>
  </div>;
}
