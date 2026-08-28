import { useState } from 'react';
import { DEMO_PROBLEMS } from '../data/problems';
import { loadConfig, saveConfig, solve, judge, checkTruncation, testConnection, type SolveResult, type JudgeResult } from '../lib/hy3';

type Phase = 'idle' | 'solving' | 'solved' | 'judging' | 'done' | 'error';

const LEVEL_COLOR: Record<string, string> = { L1: '#34d399', L2: '#22d3ee', L3: '#fbbf24', L4: '#f87171' };

export default function Workbench() {
  const [cfg, setCfg] = useState(loadConfig());
  const [showCfg, setShowCfg] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [custom, setCustom] = useState('');
  const [gold, setGold] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<SolveResult | null>(null);
  const [verdict, setVerdict] = useState<JudgeResult | null>(null);
  const [err, setErr] = useState('');
  const [testMsg, setTestMsg] = useState('');

  const active = DEMO_PROBLEMS.find(p => p.id === selected);
  const problemText = active ? active.problem : custom;
  const goldAnswer = active ? active.answer : gold;

  const run = async () => {
    if (!cfg.baseUrl || !cfg.apiKey) { setShowCfg(true); return; }
    if (!problemText.trim()) return;
    setPhase('solving'); setErr(''); setResult(null); setVerdict(null);
    try {
      const r = await solve(cfg, problemText);
      setResult(r); setPhase('judging');
      const v = await judge(cfg, problemText, goldAnswer, r.content);
      setVerdict(v); setPhase('done');
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setPhase('error');
    }
  };

  const trunc = result ? checkTruncation(result.finishReason, result.content) : null;
  const answerMatch = result?.finalAnswer && goldAnswer
    ? result.finalAnswer.replace(/\s/g, '').includes(goldAnswer.replace(/\s/g, '').slice(0, 8)) : null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr_340px] gap-3 items-start">
      {/* 左栏：题库 + 输入 */}
      <div className="panel p-4">
        <div className="label-caps mb-3">Problem Library · 演示题库</div>
        <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1">
          {DEMO_PROBLEMS.map(p => (
            <button key={p.id}
              onClick={() => { setSelected(p.id); setCustom(''); }}
              className={`w-full text-left px-3 py-2 rounded-md border transition-all text-[13px] ${
                selected === p.id ? 'border-[#22d3ee] bg-[#22d3ee10]' : 'border-[#1a2540] hover:border-[#22d3ee55] bg-[#0c1220]'}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono-x text-[10px] px-1.5 py-0.5 rounded" style={{ color: LEVEL_COLOR[p.level], background: LEVEL_COLOR[p.level] + '18' }}>{p.level}</span>
                <span className="font-mono-x text-[10px] text-[#5b6b84]">{p.id} · {p.domain}</span>
              </div>
              <div className="text-[#e8edf6]">{p.title}</div>
            </button>
          ))}
        </div>
        <div className="label-caps mt-4 mb-2">或自定义题目</div>
        <textarea value={custom} onChange={e => { setCustom(e.target.value); setSelected(null); }}
          placeholder="输入任意数学题，支持 LaTeX…" rows={4}
          className="w-full bg-[#050810] border border-[#1a2540] rounded-md p-2.5 text-[13px] text-[#e8edf6] focus:border-[#22d3ee] outline-none resize-y" />
        {!active && (
          <input value={gold} onChange={e => setGold(e.target.value)} placeholder="标准答案（可选，用于比对）"
            className="w-full mt-2 bg-[#050810] border border-[#1a2540] rounded-md px-2.5 py-2 text-[13px] text-[#e8edf6] focus:border-[#22d3ee] outline-none" />
        )}
        <button onClick={run} disabled={phase === 'solving' || phase === 'judging' || !problemText.trim()}
          className="w-full mt-3 py-2.5 rounded-md font-semibold text-[14px] transition-all disabled:opacity-40 bg-[#22d3ee] text-[#050810] hover:bg-[#34d399]">
          {phase === 'solving' ? 'Hy3 解题中…' : phase === 'judging' ? '过程评估中…' : '运行 解题 → 评估'}
        </button>
        <button onClick={() => setShowCfg(!showCfg)} className="w-full mt-2 py-1.5 text-[12px] text-[#5b6b84] hover:text-[#22d3ee] font-mono-x">
          {showCfg ? '▲ 收起接口配置' : '⚙ 配置 Hy3 接口（Key 仅存本地）'}
        </button>
        {showCfg && (
          <div className="mt-2 space-y-2 fade-up">
            <input value={cfg.baseUrl} onChange={e => setCfg({ ...cfg, baseUrl: e.target.value })}
              placeholder="Base URL，如 https://…/v1" className="w-full bg-[#050810] border border-[#1a2540] rounded px-2.5 py-2 text-[12px] text-[#e8edf6] focus:border-[#22d3ee] outline-none font-mono-x" />
            <input value={cfg.apiKey} onChange={e => setCfg({ ...cfg, apiKey: e.target.value })} type="password"
              placeholder="API Key（localStorage 本地保存）" className="w-full bg-[#050810] border border-[#1a2540] rounded px-2.5 py-2 text-[12px] text-[#e8edf6] focus:border-[#22d3ee] outline-none font-mono-x" />
            <input value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })}
              placeholder="模型名" className="w-full bg-[#050810] border border-[#1a2540] rounded px-2.5 py-2 text-[12px] text-[#e8edf6] focus:border-[#22d3ee] outline-none font-mono-x" />
            <div className="flex gap-2">
              <button onClick={() => { saveConfig(cfg); setShowCfg(false); }}
                className="flex-1 py-1.5 rounded border border-[#22d3ee] text-[#22d3ee] text-[12px] hover:bg-[#22d3ee15]">保存配置</button>
              <button onClick={async () => {
                  saveConfig(cfg); setTestMsg('测试中…');
                  const r = await testConnection(cfg);
                  setTestMsg((r.ok ? '✓ ' : '✗ ') + r.detail);
                }}
                className="flex-1 py-1.5 rounded border border-[#34d399] text-[#34d399] text-[12px] hover:bg-[#34d39915]">测试连接</button>
            </div>
            {testMsg && (
              <div className={`text-[11px] font-mono-x leading-relaxed p-2 rounded ${testMsg.startsWith('✓') ? 'text-[#34d399] bg-[#34d39910]' : 'text-[#f87171] bg-[#f8717110]'}`}>
                {testMsg}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 中栏：题目 + 分步解答 */}
      <div className="panel p-5 min-h-[500px]">
        <div className="label-caps mb-3">Solution · 分步解答</div>
        {problemText ? (
          <div className="mb-4 p-3 rounded-md bg-[#111a2b] border-l-[3px] border-[#22d3ee]">
            <div className="label-caps mb-1.5">题目 {active ? `· ${active.id}` : ''}</div>
            <pre className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#e8edf6] font-sans">{problemText}</pre>
            {goldAnswer && <div className="mt-2 font-mono-x text-[11px] text-[#34d399]">标准答案：{goldAnswer}</div>}
          </div>
        ) : (
          <div className="border border-dashed border-[#1a2540] rounded-md p-10 text-center text-[#5b6b84] text-[13px]">
            从左侧选择题库中的演示题（2026 高考数学新课标卷 · 低污染题源），或输入自定义题目
          </div>
        )}
        {phase === 'error' && (
          <div className="p-3 rounded-md bg-[#f8717112] border-l-[3px] border-[#f87171] text-[13px] text-[#f87171] fade-up">
            调用失败：{err}（请检查接口配置、网络与 CORS 策略）
          </div>
        )}
        {(phase === 'solving' || phase === 'judging') && (
          <div className="space-y-2 mt-2">
            {[1, 2, 3].map(i => <div key={i} className="h-12 rounded-md bg-[#111a2b] animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />)}
          </div>
        )}
        {result && (
          <div className="space-y-2 mt-1">
            {result.steps.map((s, i) => {
              const stepNo = i + 1;
              const bad = verdict?.first_error_step === stepNo;
              const after = verdict?.first_error_step != null && stepNo > verdict.first_error_step;
              return (
                <div key={i} className={`p-3 rounded-md border-l-[3px] fade-up text-[13.5px] leading-relaxed ${
                  bad ? 'border-[#f87171] bg-[#f8717110]' : after ? 'border-[#5b6b84] bg-[#111a2b66] opacity-60' : 'border-[#34d39966] bg-[#111a2b]'}`}
                  style={{ animationDelay: `${i * 60}ms` }}>
                  <div className="flex items-center gap-2">
                    <span className="font-mono-x text-[10px] text-[#5b6b84]">STEP {stepNo}</span>
                    {bad && <span className="font-mono-x text-[10px] text-[#f87171]">◉ 首个错误步</span>}
                    {after && <span className="font-mono-x text-[10px] text-[#5b6b84]">基于错误前提，不再评价</span>}
                  </div>
                  <div className="mt-1 text-[#dfe7f3]">{s}</div>
                </div>
              );
            })}
            {result.finalAnswer && (
              <div className={`p-3 rounded-md border font-mono-x text-[13px] ${
                answerMatch ? 'border-[#34d399] bg-[#34d39912] text-[#34d399]' : 'border-[#fbbf24] bg-[#fbbf2412] text-[#fbbf24]'}`}>
                Final Answer: {result.finalAnswer} {answerMatch === true ? '✓ 与标准答案一致' : answerMatch === false ? '（与标准答案不一致或无法自动比对）' : ''}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 右栏：评估结论 */}
      <div className="panel p-4 min-h-[500px]">
        <div className="label-caps mb-3">Verdict · 过程评估</div>
        {!result && <div className="border border-dashed border-[#1a2540] rounded-md p-8 text-center text-[#5b6b84] text-[12.5px]">运行后此处输出五层评估结论</div>}
        {result && (
          <div className="space-y-3 fade-up">
            <EvalRow name="L0 答案层" color="#22d3ee"
              ok={answerMatch !== false}
              text={result.finalAnswer ? `提取答案：${result.finalAnswer}` : '未提取到最终答案'} />
            <EvalRow name="L1 结构层" color="#22d3ee" ok={result.steps.length > 0}
              text={`解析出 ${result.steps.length} 个步骤`} />
            <EvalRow name="L4 截断检测" color="#f87171" ok={!trunc?.truncated}
              text={trunc?.truncated ? `疑似截断：${trunc.signals.join('；')}` : `finish_reason=${result.finishReason}，输出完整`} />
            {phase === 'judging' && <div className="h-16 rounded-md bg-[#111a2b] animate-pulse" />}
            {verdict && (
              <>
                <EvalRow name="L3 语义审查" color="#fbbf24" ok={verdict.overall_valid}
                  text={verdict.overall_valid ? '推理链条成立' : `首个错误步：Step ${verdict.first_error_step}`} />
                {verdict.error_type && (
                  <div className="p-3 rounded-md bg-[#f8717110] border border-[#f8717144]">
                    <div className="label-caps mb-1">错误类型</div>
                    <div className="text-[#f87171] font-semibold text-[15px]">{verdict.error_type}</div>
                    <div className="text-[12.5px] text-[#9aa7bd] mt-1 leading-relaxed">{verdict.error_detail}</div>
                  </div>
                )}
                <div className={`p-3 rounded-md border text-[13px] font-semibold ${
                  verdict.overall_valid && answerMatch ? 'border-[#34d399] bg-[#34d39912] text-[#34d399]'
                  : !verdict.overall_valid && answerMatch ? 'border-[#fbbf24] bg-[#fbbf2412] text-[#fbbf24]'
                  : 'border-[#f87171] bg-[#f8717112] text-[#f87171]'}`}>
                  {verdict.overall_valid && answerMatch ? '✓ 答案与过程均成立'
                    : !verdict.overall_valid && answerMatch ? '⚠ 答案正确但过程不成立（CBU）'
                    : verdict.overall_valid ? '过程成立，答案待核对' : '✗ 过程存在错误'}
                </div>
              </>
            )}
            {result.usage && (
              <div className="font-mono-x text-[10px] text-[#5b6b84] pt-1">tokens: {result.usage.total_tokens ?? '—'}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EvalRow({ name, color, ok, text }: { name: string; color: string; ok: boolean; text: string }) {
  return (
    <div className="flex items-start gap-2.5 p-2.5 rounded-md bg-[#111a2b]">
      <span className={`mt-1 w-2 h-2 rounded-full flex-none ${ok ? '' : 'pulse-dot'}`}
        style={{ background: ok ? '#34d399' : '#f87171', boxShadow: `0 0 8px ${ok ? '#34d399' : '#f87171'}` }} />
      <div>
        <div className="font-mono-x text-[10px] tracking-widest" style={{ color }}>{name}</div>
        <div className="text-[12.5px] text-[#dfe7f3] mt-0.5">{text}</div>
      </div>
    </div>
  );
}
