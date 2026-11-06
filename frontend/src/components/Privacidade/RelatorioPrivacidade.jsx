import { useEffect, useState } from 'react';
import { Download, ShieldAlert, ShieldCheck } from 'lucide-react';
import {
  buscarRelatorioPrivacidade,
  categoriasSensiveis,
  linhasIdentificadores,
  mensagemDeErro,
  nivelDoRelatorio,
  nomeArquivoRelatorio,
} from '../../services/privacidade';

const botao = 'inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium hover:bg-slate-50';

function baixarJson(relatorio) {
  const blob = new Blob([JSON.stringify(relatorio, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivoRelatorio(relatorio);
  a.click();
  URL.revokeObjectURL(url);
}

function Indicador({ titulo, valor, nota }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4">
      <p className="text-xs font-medium text-slate-500">{titulo}</p>
      <p className="mt-1 text-2xl font-extrabold text-slate-900">{valor}</p>
      {nota && <p className="mt-1 text-[11px] text-slate-500">{nota}</p>}
    </div>
  );
}

/**
 * Relatório de risco de privacidade do lote ativo, para o encarregado de dados (DPO).
 * - loteId:     lote selecionado
 * - concluido:  só busca quando o lote terminou (antes disso a API responde 409)
 * - recarregar: número que o pai incrementa depois de revisar/reprocessar, para buscar de novo
 */
export default function RelatorioPrivacidade({ loteId, concluido, recarregar = 0 }) {
  // O resultado guarda a "chave" do pedido que o gerou; se ela não bate com a atual, ele é de outro lote e é ignorado.
  // Assim não há setState síncrono no efeito, e uma resposta atrasada nunca aparece no lote errado.
  const [resultado, setResultado] = useState(null);
  const chave = `${loteId}|${recarregar}`;

  useEffect(() => {
    if (!loteId || !concluido) return undefined;
    let ativo = true;
    buscarRelatorioPrivacidade(loteId)
      .then((dados) => ativo && setResultado({ chave, dados }))
      .catch((e) => {
        if (!ativo) return;
        if (e.response?.status === 409) setResultado({ chave, aguardando: true });
        else setResultado({ chave, erro: mensagemDeErro(e, 'Não foi possível gerar o relatório de privacidade.') });
      });
    return () => { ativo = false; };
  }, [loteId, concluido, chave]);

  const titulo = <h2 id="titulo-privacidade" className="font-bold">Risco de privacidade</h2>;
  const moldura = 'rounded-xl bg-white border border-slate-100 p-5 space-y-5';

  if (!concluido) {
    return (
      <section aria-labelledby="titulo-privacidade" className={moldura}>
        {titulo}
        <p className="text-sm text-slate-500">O relatório fica disponível quando o lote terminar de processar.</p>
      </section>
    );
  }

  const atual = resultado?.chave === chave ? resultado : null;
  if (!atual) {
    return (
      <section aria-labelledby="titulo-privacidade" className={moldura}>
        {titulo}
        <p role="status" className="text-sm text-slate-500">Gerando relatório...</p>
      </section>
    );
  }
  if (atual.aguardando) {
    return (
      <section aria-labelledby="titulo-privacidade" className={moldura}>
        {titulo}
        <p role="status" className="text-sm text-slate-500">O lote está sendo processado; o relatório ficará disponível ao concluir.</p>
      </section>
    );
  }
  if (atual.erro) {
    return (
      <section aria-labelledby="titulo-privacidade" className={moldura}>
        {titulo}
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{atual.erro}</p>
      </section>
    );
  }

  const rel = atual.dados;
  const nivel = nivelDoRelatorio(rel);
  const Icone = rel.nivel_risco === 'baixo' ? ShieldCheck : ShieldAlert;
  const identificadores = linhasIdentificadores(rel);
  const categorias = categoriasSensiveis(rel);
  const sensiveis = rel.documentos_sensiveis ?? [];
  const totais = rel.totais ?? {};

  return (
    <section aria-labelledby="titulo-privacidade" className={moldura}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {titulo}
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${nivel.classe}`}>
            <Icone className="h-3.5 w-3.5" aria-hidden="true" />{nivel.rotulo}
          </span>
        </div>
        <button type="button" className={botao} onClick={() => baixarJson(rel)}>
          <Download className="h-3.5 w-3.5" aria-hidden="true" />Baixar relatório (JSON)
        </button>
      </div>

      <p className="text-sm text-slate-700">{rel.resumo}</p>
      {rel.motivos?.length > 0 && <p className="text-xs text-slate-500">Por quê: {rel.motivos.join('; ')}.</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador titulo="Documentos com dados pessoais" valor={`${totais.documentos_com_dados_pessoais ?? 0} de ${totais.documentos ?? 0}`} />
        <Indicador titulo="Pessoas distintas" valor={totais.pessoas_distintas ?? 0} nota="por CPF válido" />
        <Indicador titulo="Documentos com dados sensíveis" valor={totais.documentos_com_dados_sensiveis ?? 0} nota="LGPD, art. 5º, II" />
        <Indicador
          titulo="Ainda em revisão"
          valor={totais.documentos_em_revisao ?? 0}
          nota={totais.documentos_em_revisao > 0 ? 'o relatório pode mudar' : undefined}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-bold">Identificadores encontrados</h3>
          {identificadores.length === 0 ? (
            <p className="text-sm text-slate-500">Nenhum identificador detectado.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Identificadores pessoais detectados no lote</caption>
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                    <th scope="col" className="py-1.5 pr-3 font-medium">Dado</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">Ocorrências</th>
                    <th scope="col" className="py-1.5 text-right font-medium">Documentos</th>
                  </tr>
                </thead>
                <tbody>
                  {identificadores.map((l) => (
                    <tr key={l.codigo} className="border-b border-slate-50">
                      <th scope="row" className="py-1.5 pr-3 text-left font-medium text-slate-700">
                        {l.codigo === 'CNPJ' ? 'CNPJ' : l.nome}
                        {l.pessoas !== null && <span className="ml-1 text-xs font-normal text-slate-500">({l.pessoas} pessoa{l.pessoas === 1 ? '' : 's'})</span>}
                      </th>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{l.ocorrencias}</td>
                      <td className="py-1.5 text-right tabular-nums">{l.documentos}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div>
          <h3 className="mb-2 text-sm font-bold">Dados sensíveis</h3>
          <ul className="space-y-2 text-sm">
            {categorias.map((c) => (
              <li key={c.codigo} className="rounded-lg border border-slate-100 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-slate-700">{c.nome}</span>
                  <span className={c.documentos > 0 ? 'font-bold text-rose-700' : 'text-slate-500'}>
                    {c.documentos > 0 ? `${c.documentos} documento${c.documentos === 1 ? '' : 's'}` : 'nada detectado'}
                  </span>
                </div>
                {c.documentos > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    {c.porTipo.length > 0 && <>Tipos: {c.porTipo.map(([t, n]) => `${t} (${n})`).join(', ')}. </>}
                    {c.termos.length > 0 && <>Termos: {c.termos.join(', ')}.</>}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {sensiveis.length > 0 && (
        <details className="rounded-lg border border-slate-200 p-3">
          <summary className="cursor-pointer text-sm font-medium">Documentos com dados sensíveis ({totais.documentos_com_dados_sensiveis ?? sensiveis.length})</summary>
          <ul className="mt-3 space-y-2 text-sm">
            {sensiveis.map((d) => (
              <li key={d.documento_id} className="rounded-lg bg-slate-50 p-3">
                <strong>{d.titulo || d.tipo_nome}</strong> · {d.tipo_nome} · páginas {d.pagina_inicio + 1}–{d.pagina_fim + 1}
                <span className="mt-0.5 block text-xs text-slate-500">
                  {Object.entries(d.evidencias ?? {}).map(([cat, ev]) => `${rel.dados_sensiveis?.[cat]?.nome ?? cat}: ${ev.join(', ')}`).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
          {rel.documentos_sensiveis_truncado && (
            <p className="mt-2 text-xs text-slate-500">Lista parcial: os totais acima consideram todos os documentos do lote. O JSON baixado também traz só a lista parcial.</p>
          )}
        </details>
      )}

      {rel.recomendacoes?.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-bold">Antes de compartilhar</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {rel.recomendacoes.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      )}

      {(rel.deteccao?.nomes === false || rel.deteccao?.enderecos === false) && (
        <p role="note" className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
          A detecção de {[rel.deteccao.nomes === false && 'nomes', rel.deteccao.enderecos === false && 'endereços'].filter(Boolean).join(' e ')} está
          desligada neste servidor: esses dados não entram na contagem nem são tarjados.
        </p>
      )}
      <p className="text-xs text-slate-500">{rel.aviso}</p>
    </section>
  );
}
