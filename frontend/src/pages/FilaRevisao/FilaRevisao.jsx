// Fila de revisão: pendentes com a "Sugestão da IA" (pré-revisão) e as ações do revisor.
import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import AuthenticatedImage from '../../components/AuthenticatedImage';
import Layout from '../../components/Layout';
import { Cartao, ComDados, Erro, Selo, botao, botaoPrimario, campo } from '../../components/Estados';
import useApi from '../../hooks/useApi';
import api from '../../services/api';
import { avisarFilaMudou, mensagemDeErro, pct } from '../../utils/formatar';

const ACAO_TEXTO = { aprovar: 'Aprovar como está', alterar_tipo: 'Alterar o tipo', verificar_manual: 'Verificar manualmente' };

function Miniaturas({ doc }) {
  const paginas = Array.from({ length: doc.n_paginas }, (_, i) => doc.pagina_inicio + i).slice(0, 4);
  return <div className="flex gap-2">
    {paginas.map(n => <AuthenticatedImage key={n} className="h-24 w-[68px] rounded border border-slate-200 bg-slate-50 object-cover"
                                          src={`/lotes/${doc.lote_id}/paginas/${n}/imagem?thumb=true`}
                                          alt={`Página ${n + 1}`} />)}
  </div>;
}

function Sugestao({ pre, tipos }) {
  if (!pre) return null;
  const tipoNome = tipos.find(t => t.codigo === pre.tipo_sugerido)?.nome || pre.tipo_sugerido;
  return <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 text-sm">
    <p className="mb-1 flex items-center gap-2 text-xs font-bold text-indigo-800">
      <Sparkles className="h-4 w-4" aria-hidden="true" />
      {pre.origem === 'ia' ? 'Sugestão da IA' : 'Sugestão automática por regras'}
      {pre.origem === 'ia' && pre.confianca > 0 && <span className="font-medium text-indigo-500">· confiança {pct(pre.confianca * 100)}</span>}
    </p>
    <p className="text-slate-700">{pre.explicacao}</p>
    <p className="mt-2 text-xs font-semibold text-slate-700">
      Sugestão: {ACAO_TEXTO[pre.acao_sugerida] || pre.acao_sugerida}{pre.tipo_sugerido ? ` para ${tipoNome}` : ''}
    </p>
    {pre.evidencias?.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
      {pre.evidencias.map(e => <li key={e}>“{e}”</li>)}
    </ul>}
    <p className="mt-2 text-[11px] text-slate-400">A sugestão nunca é aplicada sozinha: quem decide é você.</p>
  </div>;
}

function ItemDaFila({ doc, tipos, aoConcluir }) {
  const [tipo, setTipo] = useState(doc.tipo);
  const [corte, setCorte] = useState('');
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  const pre = doc.pre_revisao;
  const aplicavel = pre && (pre.acao_sugerida === 'aprovar' || (pre.acao_sugerida === 'alterar_tipo' && pre.tipo_sugerido));

  async function revisar(acao, extras = {}) {
    setSalvando(true); setErro('');
    try {
      await api.post(`/documentos/${doc.id}/revisao`, { acao, ...extras });
      avisarFilaMudou();
      aoConcluir();
    } catch (e) { setErro(mensagemDeErro(e, 'Não foi possível salvar a revisão.')); setSalvando(false); }
  }

  return <Cartao>
    <div className="flex flex-col gap-4 lg:flex-row">
      <Miniaturas doc={doc} />
      <div className="flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold text-slate-800">{doc.titulo || doc.tipo_nome}</h3>
          <Selo valor="pendente" />
          {doc.risco !== 'confiavel' && <Selo valor={doc.risco} />}
          <span className="text-xs text-slate-500">{doc.tipo_nome} · págs {doc.pagina_inicio + 1}–{doc.pagina_fim + 1} · confiança {pct(doc.confianca * 100)} · prioridade {doc.prioridade}</span>
        </div>
        {doc.origem_texto && <p className="text-xs text-slate-500">{doc.origem_texto}{doc.ia_justificativa ? ` — ${doc.ia_justificativa}` : ''}</p>}
        {doc.motivos?.length > 0 && <ul className="list-disc pl-5 text-xs text-amber-800">{doc.motivos.map(m => <li key={m}>{m}</li>)}</ul>}
        <Sugestao pre={pre} tipos={tipos} />
        {erro && <Erro mensagem={erro} />}
        <div className="flex flex-wrap items-center gap-2">
          {aplicavel && <button type="button" className={botaoPrimario} disabled={salvando}
                                onClick={() => pre.acao_sugerida === 'aprovar' ? revisar('aprovar') : revisar('alterar_tipo', { tipo: pre.tipo_sugerido })}>
            Aplicar sugestão
          </button>}
          <button type="button" className={botao} disabled={salvando} onClick={() => revisar('aprovar')}>Aprovar</button>
          <a className={botao} href={`${api.defaults.baseURL}/documentos/${doc.id}/pdf`} target="_blank" rel="noreferrer">Abrir PDF</a>
          <button type="button" className={botao} disabled={salvando} onClick={() => revisar('juntar_proximo')}>Juntar com o próximo</button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Novo tipo do documento" className={campo} value={tipo} onChange={e => setTipo(e.target.value)}>
            {!tipos.some(t => t.codigo === tipo) && <option value={tipo}>{tipo}</option>}
            {tipos.map(t => <option key={t.codigo} value={t.codigo}>{t.nome}</option>)}
          </select>
          <button type="button" className={botao} disabled={salvando || tipo === doc.tipo} onClick={() => revisar('alterar_tipo', { tipo })}>Alterar tipo</button>
          {doc.n_paginas > 1 && <>
            <label className="text-xs text-slate-600" htmlFor={`corte-${doc.id}`}>Dividir a partir da página</label>
            <input id={`corte-${doc.id}`} className={`${campo} w-20`} type="number" min={doc.pagina_inicio + 2} max={doc.pagina_fim + 1}
                   value={corte} onChange={e => setCorte(e.target.value)} />
            <button type="button" className={botao} disabled={salvando || !corte} onClick={() => revisar('dividir', { pagina_corte: Number(corte) - 1 })}>Dividir</button>
          </>}
        </div>
      </div>
    </div>
  </Cartao>;
}

export default function FilaRevisao() {
  const fila = useApi(() => Promise.all([api.get('/revisao/fila'), api.get('/tipos')]).then(([f, t]) => ({ docs: f.data, tipos: t.data })),
                      [], { intervalo: 20000 });
  return <Layout titulo="Fila de revisão" subtitulo="Documentos com dúvida: a pré-revisão explica o motivo e sugere o que fazer.">
    <ComDados estado={fila} vazio={d => d.docs.length === 0} textoVazio="Nenhum documento aguardando revisão. 🎉">
      {d => <div className="space-y-4">
        <p className="text-xs text-slate-500">{d.docs.length} documento(s) pendente(s), da prioridade mais alta para a mais baixa.</p>
        {d.docs.map(doc => <ItemDaFila key={doc.id} doc={doc} tipos={d.tipos} aoConcluir={fila.recarregar} />)}
      </div>}
    </ComDados>
  </Layout>;
}
