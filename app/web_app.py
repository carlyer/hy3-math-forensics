"""Hy3 数学解题过程评估 Web 应用.

基于 FastAPI + 纯前端（Tailwind / KaTeX / Mermaid）构建，提供：
- 单题求解：输入题目后生成完整解题过程
- 过程评估：规则校验 + 可选 LLM-as-judge（单裁判 / 三裁判）
- 可视化：步骤卡片、依赖图、错误定位、CBU 提示
- 题库选择：从 dataset/problems_merged_v2.jsonl 中任选题目

启动:
    cd /path/to/workspace/hy3-math-eval
    /path/to/venv/bin/python3 -m uvicorn app.web_app:app --host 0.0.0.0 --port 7860

访问:
    http://localhost:7860
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 自动加载 .env
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.hy3_client import Hy3MathClient, load_client_from_env
from app.prompt_templates import build_messages
from app.solution_parser import parse_solution
from dataset.answer_checker import check_answer
from evaluator.llm_judge import LLMJudge
from evaluator.multi_judge import MultiLLMJudge
from evaluator.process_evaluator import ProcessEvaluator


app = FastAPI(title="Hy3 Math Process Evaluation Demo")

# 全局客户端（vLLM 本地服务或 API）
client: Hy3MathClient = load_client_from_env()

# 加载题库（用于前端下拉选择）
DATASET_PATH = Path(__file__).parent.parent / "dataset" / "problems_merged_v2.jsonl"


def _load_problems(path: Path) -> List[Dict[str, Any]]:
    problems = []
    if not path.exists():
        return problems
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


problems_db: List[Dict[str, Any]] = _load_problems(DATASET_PATH)


class SolveRequest(BaseModel):
    problem: str = Field(..., description="题目文本")
    level: str = Field("auto", description="难度层级 L1/L2/L3/L4/auto")
    max_tokens: int = Field(3072, ge=256, le=8192, description="最大生成 token 数")
    temperature: float = Field(0.6, ge=0.0, le=2.0, description="采样温度")
    gold_answer: Optional[str] = Field(None, description="标准答案（可选）")
    verification_method: str = Field("exact_match", description="答案校验方式")
    use_llm_judge: bool = Field(False, description="是否启用 GPT 单裁判")
    use_multi_judge: bool = Field(False, description="是否启用三裁判交叉复核")


class ProblemSummary(BaseModel):
    id: str
    level: str
    preview: str


def _build_llm_judge(use_llm: bool, use_multi: bool) -> Optional[Any]:
    """根据请求参数构造裁判器."""
    if use_multi:
        return MultiLLMJudge()
    if use_llm:
        return LLMJudge()
    return None


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "model": client.model_name or "unknown"}


@app.get("/api/problems", response_model=List[ProblemSummary])
def list_problems() -> List[Dict[str, str]]:
    """返回题库列表（用于前端下拉选择）."""
    return [
        {
            "id": p["id"],
            "level": p.get("level", "unknown"),
            "preview": f"[{p.get('level', '?')}] {p['problem'][:80]}...",
        }
        for p in problems_db
    ]


@app.get("/api/problem/{problem_id}")
def get_problem(problem_id: str) -> Dict[str, Any]:
    """根据 ID 返回完整题目信息."""
    for p in problems_db:
        if p.get("id") == problem_id:
            return p
    raise HTTPException(status_code=404, detail=f"未找到题目: {problem_id}")


@app.post("/api/solve")
def solve(req: SolveRequest) -> Dict[str, Any]:
    """生成解题过程并执行过程评估."""
    problem_text = req.problem.strip()
    if not problem_text:
        raise HTTPException(status_code=400, detail="题目不能为空")

    # 1. 生成解题过程
    messages = build_messages(problem_text)
    outputs = client.chat_generate(
        [messages],
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    out = outputs[0]
    raw_output = out["text"]
    reasoning_content = out.get("reasoning_content")

    parsed = parse_solution(
        problem_id="web-demo",
        raw_output=raw_output,
        reasoning_content=reasoning_content,
    )
    steps = [
        {"index": s.index, "text": s.text, "depends_on": s.depends_on}
        for s in parsed.steps
    ]
    final_answer = parsed.final_answer

    # 2. 答案校验
    gold_answer = req.gold_answer
    if gold_answer is not None and gold_answer.strip():
        verification = {"method": req.verification_method}
        answer_correct, answer_detail = check_answer(
            final_answer, gold_answer, verification
        )
    else:
        answer_correct, answer_detail = None, "未提供标准答案，跳过答案校验"

    # 3. 过程评估
    llm_judge = _build_llm_judge(req.use_llm_judge, req.use_multi_judge)
    evaluator = ProcessEvaluator(llm_judge=llm_judge)
    eval_result = evaluator.evaluate(
        problem_text=problem_text,
        steps=steps,
        answer_correct=answer_correct if answer_correct is not None else False,
        use_llm=llm_judge is not None,
        verification_method=req.verification_method,
        raw_output=raw_output,
        finish_reason=out.get("finish_reason"),
        max_tokens=req.max_tokens,
        completion_tokens=out.get("token_usage", {}).get("completion_tokens"),
        level=req.level if req.level not in ("auto", "") else None,
        final_answer=final_answer,
    )

    return {
        "problem": problem_text,
        "level": req.level,
        "final_answer": final_answer,
        "gold_answer": gold_answer,
        "answer_correct": answer_correct,
        "answer_check_detail": answer_detail,
        "steps": steps,
        "raw_output": raw_output,
        "reasoning_content": reasoning_content,
        "token_usage": out.get("token_usage"),
        "finish_reason": out.get("finish_reason"),
        "model_name": out.get("model_name"),
        "timestamp": out.get("timestamp"),
        "evaluation": eval_result,
    }


# 挂载静态文件（前端单页应用）
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
