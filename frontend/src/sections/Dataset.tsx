import { DATASET_COMPOSITION } from '../data/report';

const LEVEL_COLOR: Record<string, string> = { L1: '#34d399', L2: '#22d3ee', L3: '#fbbf24', L4: '#f87171' };

export default function Dataset() {
  const total = DATASET_COMPOSITION.reduce((s, d) => s + d.count, 0);
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-3 items-start">
      <div className="panel p-5">
        <div className="label-caps mb-4">Dataset · 分层题集构成（158 题）</div>
        <div className="space-y-3">
          {DATASET_COMPOSITION.map(d => (
            <div key={d.level} className="p-4 rounded-md bg-[#111a2b] border border-[#1a2540] fade-up">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono-x text-[14px] font-bold px-2 py-0.5 rounded"
                  style={{ color: LEVEL_COLOR[d.level], background: LEVEL_COLOR[d.level] + '18' }}>{d.level}</span>
                <span className="font-disp text-[20px] font-bold" style={{ color: LEVEL_COLOR[d.level] }}>{d.count}<span className="text-[12px] text-[#5b6b84] font-normal"> 题</span></span>
                <div className="flex-1 h-[6px] rounded-full bg-[#1a2540] overflow-hidden">
                  <div className="h-full rounded-full bar-anim" style={{ width: `${d.count / total * 100}%`, background: LEVEL_COLOR[d.level] }} />
                </div>
                <span className="font-mono-x text-[11px] text-[#5b6b84]">{Math.round(d.count / total * 100)}%</span>
              </div>
              <div className="text-[12.5px] text-[#9aa7bd]"><span className="text-[#5b6b84] font-mono-x text-[10px] tracking-widest">来源　</span>{d.sources}</div>
              <div className="text-[12.5px] text-[#9aa7bd] mt-0.5"><span className="text-[#5b6b84] font-mono-x text-[10px] tracking-widest">用途　</span>{d.purpose}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <div className="panel p-5">
          <div className="label-caps mb-3">Validation Set · 注入错误验证集</div>
          <div className="flex items-end gap-4">
            <div className="font-disp text-[34px] font-bold text-[#22d3ee]">28</div>
            <div className="text-[12px] text-[#9aa7bd] pb-1.5">23 条注入错误 + 5 条正确对照<br />记录注入位置与类型作 ground truth</div>
          </div>
          <div className="mt-3 space-y-1.5 font-mono-x text-[11px]">
            <div className="flex justify-between"><span className="text-[#5b6b84]">定位准确率</span><span className="text-[#34d399]">86.96% (20/23)</span></div>
            <div className="flex justify-between"><span className="text-[#5b6b84]">误报率</span><span className="text-[#34d399]">0.00% (0/5)</span></div>
            <div className="flex justify-between"><span className="text-[#5b6b84]">FrontierMath 人工抽检</span><span className="text-[#22d3ee]">12 道全数复核</span></div>
          </div>
        </div>

        <div className="panel p-5">
          <div className="label-caps mb-3">Evaluation Method · 方法论对标</div>
          <div className="space-y-2.5 text-[12.5px] text-[#9aa7bd] leading-relaxed">
            <p>评估范式对齐 <span className="text-[#e8edf6]">ProcessBench</span>：输出最早错误步索引，首错之后的步骤不再单独评价；指标同时惩罚高误报与高漏报。</p>
            <p>动机数据：答案正确的解答中，OlympiadBench 有 <span className="text-[#fbbf24] font-mono-x">32.2%</span>、Omni-MATH 有 <span className="text-[#fbbf24] font-mono-x">51.8%</span> 存在过程错误——只判答案会系统性高估模型能力。</p>
          </div>
        </div>

        <div className="panel p-5">
          <div className="label-caps mb-3">Multi-Judge · 三裁判交叉复核</div>
          <div className="text-[12.5px] text-[#9aa7bd] leading-relaxed">
            Hy3 + 两个外部模型投票：过程正确性取明确多数、错误步取中位数、错误类型取众数。三 judge 复核后过程正确率 55.1% → <span className="text-[#fbbf24] font-mono-x">51.9%</span>，CBU 率 10.7% → <span className="text-[#fbbf24] font-mono-x">14.1%</span>，说明外部裁判捕捉到了自审遗漏。
          </div>
        </div>
      </div>
    </div>
  );
}
