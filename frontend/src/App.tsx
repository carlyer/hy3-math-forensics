import { useState } from 'react';
import Workbench from './sections/Workbench';
import Dashboard from './sections/Dashboard';
import Cases from './sections/Cases';
import Dataset from './sections/Dataset';

type Tab = 'workbench' | 'dashboard' | 'cases' | 'dataset';

const TABS: { key: Tab; label: string; en: string }[] = [
  { key: 'workbench', label: '解题工作台', en: 'WORKBENCH' },
  { key: 'dashboard', label: '评测仪表盘', en: 'DASHBOARD' },
  { key: 'cases', label: '案例与方法', en: 'CASES' },
  { key: 'dataset', label: '题集与验证', en: 'DATASET' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('workbench');
  return (
    <div className="min-h-screen">
      {/* 顶栏 */}
      <header className="sticky top-0 z-40 border-b border-[#1a2540] bg-[#050810ee] backdrop-blur-md">
        <div className="max-w-[1440px] mx-auto px-4 py-3 flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <div className="relative w-8 h-8">
              <div className="absolute inset-0 rounded-full border-2 border-[#22d3ee] opacity-40 animate-ping" style={{ animationDuration: '4.2s' }} />
              <div className="absolute inset-0 rounded-full border border-[#22d3ee] flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-[#22d3ee] pulse-dot" />
              </div>
            </div>
            <div>
              <div className="font-disp font-bold text-[15px] leading-tight">Hy3 数学过程评估工作台</div>
              <div className="font-mono-x text-[9.5px] tracking-[0.22em] text-[#5b6b84]">PROCESS-LEVEL EVAL · 犀牛鸟实战任务二 · 个人/活动作品</div>
            </div>
          </div>
          <nav className="flex gap-1 ml-auto">
            {TABS.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`px-3.5 py-2 rounded-md text-[12.5px] transition-all ${
                  tab === t.key ? 'bg-[#22d3ee15] text-[#22d3ee] border border-[#22d3ee55]' : 'text-[#9aa7bd] border border-transparent hover:text-[#e8edf6]'}`}>
                <span className="font-mono-x text-[9px] tracking-widest block opacity-60">{t.en}</span>
                {t.label}
              </button>
            ))}
          </nav>
          <div className="hidden md:flex items-center gap-1.5 font-mono-x text-[10px] text-[#34d399]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#34d399] pulse-dot" />158 PROBLEMS · 5-LAYER EVALUATOR
          </div>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-4 py-4">
        {tab === 'workbench' && <Workbench />}
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'cases' && <Cases />}
        {tab === 'dataset' && <Dataset />}

        <footer className="mt-6 pt-4 border-t border-[#1a2540] flex flex-wrap gap-x-6 gap-y-1 font-mono-x text-[10px] text-[#5b6b84]">
          <span>模型能力调用通过 Hy3 API 完成 · 不训练/不微调</span>
          <span>API Key 仅存于浏览器 localStorage，不写入代码与仓库</span>
          <span>本项目为个人/活动作品，非腾讯官方发布</span>
        </footer>
      </main>
    </div>
  );
}
