import { CBU_CASES, PIPELINE_LAYERS, ERROR_TAXONOMY } from '../data/report';

const COLOR_MAP: Record<string, string> = { cyan: '#22d3ee', mint: '#34d399', amber: '#fbbf24', red: '#f87171' };

export default function Cases() {
  return (
    <div className="space-y-4">
      {/* CBU 案例 */}
      <div className="panel p-5">
        <div className="label-caps mb-1">Case Library · 典型 CBU 案例</div>
        <div className="text-[12px] text-[#5b6b84] mb-4">答案正确但过程不成立（Correct-But-Unjustified）——传统只判答案的 benchmark 会把这些记为"正确"</div>
        <div className="space-y-2.5">
          {CBU_CASES.map(c => (
            <div key={c.id} className="p-3.5 rounded-md bg-[#111a2b] border-l-[3px] border-[#fbbf24] fade-up">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono-x text-[12px] font-bold text-[#e8edf6]">{c.id}</span>
                <span className="font-mono-x text-[10px] px-2 py-0.5 rounded bg-[#f8717118] text-[#f87171]">首个错误步 Step {c.errStep}</span>
                <span className="font-mono-x text-[10px] px-2 py-0.5 rounded bg-[#fbbf2418] text-[#fbbf24]">{c.errType}</span>
                <span className="font-mono-x text-[10px] px-2 py-0.5 rounded bg-[#34d39918] text-[#34d399]">答案 {c.answer} = 标准答案 ✓</span>
              </div>
              <div className="text-[12.5px] text-[#9aa7bd] mt-1.5 leading-relaxed">{c.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 五层评估管线 */}
      <div className="panel p-5">
        <div className="label-caps mb-4">Pipeline · 五层混合评估架构</div>
        <div className="space-y-2">
          {PIPELINE_LAYERS.map((l, i) => (
            <div key={l.id} className="flex items-stretch gap-3 fade-up" style={{ animationDelay: `${i * 70}ms` }}>
              <div className="w-[52px] flex-none rounded-md flex items-center justify-center font-mono-x text-[13px] font-bold"
                style={{ background: COLOR_MAP[l.color] + '15', color: COLOR_MAP[l.color], border: `1px solid ${COLOR_MAP[l.color]}44` }}>
                {l.id}
              </div>
              <div className="flex-1 p-3 rounded-md bg-[#111a2b] border border-[#1a2540]">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="text-[13.5px] font-semibold text-[#e8edf6]">{l.name}</span>
                  <span className="font-mono-x text-[10.5px] text-[#5b6b84]">{l.method}</span>
                </div>
                <div className="text-[11.5px] mt-0.5" style={{ color: COLOR_MAP[l.color] }}>检测：{l.detects}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 错误分类体系 */}
      <div className="panel p-5">
        <div className="label-caps mb-3">Taxonomy · 十类错误分类体系</div>
        <div className="flex flex-wrap gap-2">
          {ERROR_TAXONOMY.map(t => (
            <span key={t} className="px-3 py-1.5 rounded-md border border-[#1a2540] bg-[#0c1220] text-[12px] text-[#9aa7bd] hover:border-[#f87171] hover:text-[#f87171] transition-all cursor-default">
              {t}
            </span>
          ))}
        </div>
        <div className="mt-3 text-[11.5px] text-[#5b6b84]">在 ProcessBench 四分法（计算/逻辑/概念/完整性）基础上扩充，覆盖任务书点名的跳步、循环论证、误用定理、条件遗漏、幻觉五类问题</div>
      </div>
    </div>
  );
}
