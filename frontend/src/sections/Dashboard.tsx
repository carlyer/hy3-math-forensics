import { useState } from 'react';
import { OVERALL, LEVEL_SINGLE, LEVEL_MULTI, ERROR_DIST } from '../data/report';

function Bar({ pct, color, track = '#1a2540' }: { pct: number; color: string; track?: string }) {
  return (
    <div className="h-[6px] rounded-full flex-1" style={{ background: track }}>
      <div className="h-full rounded-full bar-anim" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 6px ${color}66` }} />
    </div>
  );
}

function Metric({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="panel p-4 relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-[2px]" style={{ background: `linear-gradient(90deg, ${color}, transparent)` }} />
      <div className="label-caps">{label}</div>
      <div className="font-disp text-[30px] font-bold mt-1" style={{ color }}>{value}</div>
      <div className="text-[11.5px] text-[#9aa7bd] mt-0.5">{sub}</div>
    </div>
  );
}

export default function Dashboard() {
  const [judgeMode, setJudgeMode] = useState<'single' | 'multi'>('single');
  const rows = judgeMode === 'single' ? LEVEL_SINGLE : LEVEL_MULTI;
  const totalErr = ERROR_DIST.filter(e => e.type !== '无错误').reduce((s, e) => s + e.count, 0);

  return (
    <div className="space-y-4">
      {/* 顶部指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Metric label="答案准确率" value={`${OVERALL.single.answerAcc}%`} sub={`158 题合并题集 · ${OVERALL.autoCheckable} 题可自动判分`} color="#22d3ee" />
        <Metric label="过程正确率" value={`${OVERALL.single.processAcc}%`} sub={`三 judge 复核：${OVERALL.multi.processAcc}%`} color="#34d399" />
        <Metric label="严格过程正确率" value={`${OVERALL.single.strictAcc}%`} sub="答案且过程均正确" color="#e879f9" />
        <Metric label="CBU 检出率" value={`${OVERALL.single.cbu}%`} sub="答案正确但过程不成立" color="#fbbf24" />
        <Metric label="定位准确率" value={`${OVERALL.validation.locAcc}%`} sub={`注入验证集 ${OVERALL.validation.locN} 条错误样本`} color="#22d3ee" />
        <Metric label="误报率" value={`${OVERALL.validation.falsePos}%`} sub={`注入验证集 ${OVERALL.validation.fpN} 条正确样本`} color="#34d399" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-3">
        {/* 难度分层 */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="label-caps">Difficulty Breakdown · 难度分层</div>
            <div className="flex gap-1 font-mono-x text-[10px]">
              {(['single', 'multi'] as const).map(m => (
                <button key={m} onClick={() => setJudgeMode(m)}
                  className={`px-2.5 py-1 rounded border transition-all ${judgeMode === m ? 'border-[#22d3ee] text-[#22d3ee] bg-[#22d3ee12]' : 'border-[#1a2540] text-[#5b6b84] hover:text-[#9aa7bd]'}`}>
                  {m === 'single' ? '单 JUDGE (GPT-5.6-terra)' : '三 JUDGE 投票'}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-4">
            {rows.map(r => (
              <div key={r.level} className="fade-up">
                <div className="flex items-baseline gap-2 mb-1.5">
                  <span className="font-mono-x text-[12px] font-bold text-[#e8edf6]">{r.level}</span>
                  <span className="text-[11px] text-[#5b6b84]">{r.label} · {r.total} 题</span>
                </div>
                {[
                  { label: '答案准确率', v: r.answerAcc, c: '#22d3ee' },
                  { label: '过程正确率', v: r.processAcc, c: '#34d399' },
                  { label: '严格正确率', v: r.strictAcc, c: '#e879f9' },
                  { label: 'CBU 率', v: r.cbu, c: '#fbbf24' },
                ].map(row => (
                  <div key={row.label} className="flex items-center gap-2.5 mb-1">
                    <span className="w-[72px] text-[10.5px] text-[#5b6b84] text-right font-mono-x">{row.label}</span>
                    <Bar pct={row.v} color={row.c} />
                    <span className="w-[52px] font-mono-x text-[11px]" style={{ color: row.c }}>{row.v.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="mt-4 p-3 rounded-md bg-[#111a2b] border-l-[3px] border-[#fbbf24] text-[12.5px] text-[#9aa7bd] leading-relaxed">
            <span className="text-[#fbbf24] font-semibold">临界点发现：</span>
            L1/L2 答案准确率均保持在 90% 以上；关键断崖出现在 L2→L3（答案 94.3% → 61.7%，过程 94.3% → 61.7%）；
            L4 严格过程正确率仅约 21.7%，研究级题目基本无法同时给出正确答案与严谨推导。
          </div>
        </div>

        {/* 错误类型分布 */}
        <div className="panel p-5">
          <div className="label-caps mb-4">Error Taxonomy · 错误类型分布</div>
          <div className="space-y-3">
            {ERROR_DIST.map(e => {
              const isOk = e.type === '无错误';
              const pct = Math.round(e.count / 158 * 100);
              return (
                <div key={e.type}>
                  <div className="flex justify-between items-baseline mb-1">
                    <span className={`text-[12.5px] ${isOk ? 'text-[#34d399]' : 'text-[#e8edf6]'}`}>{e.type}</span>
                    <span className="font-mono-x text-[11px] text-[#5b6b84]">{e.count} 条 · {pct}%</span>
                  </div>
                  <Bar pct={pct * 2} color={isOk ? '#34d399' : '#f87171'} />
                  {e.note && <div className="text-[10.5px] text-[#5b6b84] mt-0.5">{e.note}</div>}
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-3 border-t border-[#1a2540] font-mono-x text-[10.5px] text-[#5b6b84] leading-relaxed">
            共 {totalErr} 条过程错误
            {(() => {
              const skip = ERROR_DIST.find(e => e.type === '跳步推导');
              return skip ? ` · 跳步推导 ${skip.count} 条（${Math.round(skip.count / totalErr * 100)}%）` : '';
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}
