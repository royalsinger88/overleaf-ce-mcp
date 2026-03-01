"""模型结构图工作流：真值拓扑 + Nano Banana Pro 提示词包。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional


def _to_list(value: Optional[List[str]]) -> List[str]:
    if not value:
        return []
    out: List[str] = []
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _write_text(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return "skipped"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "written"


def _copy_file(src: Path, dst: Path, force: bool) -> str:
    if dst.exists() and not force:
        return "skipped"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "written"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _default_modules() -> List[str]:
    return [
        "Input",
        "Feature Extractor",
        "Physics Constraint Module",
        "Feature Fusion",
        "Prediction Head",
    ]


def _build_mermaid_truth(model_name: str, modules: List[str]) -> str:
    safe_modules = modules if len(modules) >= 2 else _default_modules()
    lines = ['flowchart LR', f'  T["{model_name}"]:::title']
    node_ids: List[str] = []
    for i, m in enumerate(safe_modules):
        nid = f"N{i+1}"
        node_ids.append(nid)
        lines.append(f'  {nid}["{m}"]:::block')
    for i in range(len(node_ids) - 1):
        a = node_ids[i]
        b = node_ids[i + 1]
        lines.append(f"  {a} --> {b}")
    lines.append(f'  T -. "overall pipeline" .- {node_ids[0]}')
    lines.append("  classDef title fill:#f2f7ff,stroke:#2c4a8a,stroke-width:1.8px,color:#0f1f3a;")
    lines.append("  classDef block fill:#ffffff,stroke:#1f2d3d,stroke-width:1.4px,color:#111827;")
    return "\n".join(lines) + "\n"


def _build_main_prompt(model_name: str, truth_hint: str) -> str:
    return f"""你是学术插图设计助手。请基于我提供的参考拓扑图，生成用于 SCI 论文的模型结构图。

参考真值来源：
{truth_hint}

硬性约束（必须遵守）：
1) 不允许修改节点数量、节点名称、连线关系、箭头方向。
2) 不允许新增或删除任意模块。
3) 保持拓扑完全一致，只允许做视觉层面的提升。

目标：
- 图名：{model_name}
- 风格：论文投稿风格（干净、克制、专业）
- 画布：白底，16:9，4K
- 可读性：字体统一、字号层次清晰、线宽一致、模块间距均衡
- 配色：色盲友好，不使用高饱和荧光色
- 输出：一张主结构图（用于论文总览）

请先输出“你理解到的拓扑摘要（节点与边列表）”，再输出最终图像。"""


def _build_refine_prompt() -> str:
    return """请在不改变拓扑的前提下，仅做样式微调：
1) 统一字体与字号（标题 > 模块名 > 注释）
2) 统一线宽与圆角
3) 强化对齐与留白
4) 优化颜色对比度（保证灰度打印可辨识）
5) 让导出的 PNG/SVG 在 1 列与 2 列版式都清晰

再次强调：禁止改动任何节点和连线关系。"""


def _build_zoom_prompt(modules: List[str]) -> str:
    lines = [
        "# 局部模块放大图提示词模板",
        "",
        "请基于主结构图生成局部放大子图，要求：",
        "1. 仅放大选定模块内部结构。",
        "2. 与主图使用同一视觉体系（配色、字体、线型、注释风格）。",
        "3. 明确输入/输出张量或特征流向。",
        "4. 不改变模块真实计算顺序。",
        "",
    ]
    for m in modules:
        lines.append(f"## {m}")
        lines.append(
            f"为模块 `{m}` 生成局部结构图。保持与主图一致的视觉风格，并标注关键算子、维度变化与残差/跳连关系。"
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_readme(model_name: str, modules: List[str], truth_mode: str) -> str:
    module_text = "\n".join([f"- {m}" for m in modules])
    truth_files = (
        "- `01-topology-truth.drawio`：draw.io 真值拓扑（唯一真值源）\n"
        "- `01-topology-lock.json`：真值拓扑锁（hash 校验）\n"
        "- `01-topology-truth.mmd`：文本备查拓扑（非真值）"
        if truth_mode == "drawio"
        else "- `01-topology-truth.mmd`：真值拓扑（先确认正确性）"
    )
    step1 = (
        "1. 先确认 `01-topology-truth.drawio` 拓扑无误，并记录 `01-topology-lock.json`。"
        if truth_mode == "drawio"
        else "1. 先确认 `01-topology-truth.mmd` 拓扑无误。"
    )
    return f"""# 模型结构图生产包

模型名：`{model_name}`

## 目录说明

{truth_files}
- `02-nanobanana-main-prompt.txt`：主结构图生成提示词
- `03-nanobanana-style-refine-prompt.txt`：多轮样式微调提示词
- `04-nanobanana-zoom-prompts.md`：局部模块放大图提示词
- `05-integrity-checklist.md`：结构一致性核对清单
- `latex-figure-snippet.tex`：论文插图 LaTeX 片段

## 推荐流程（最稳）

{step1}  
2. 把真值图作为参考图，使用 `02-*` 生成主结构图。  
3. 用 `03-*` 多轮只改样式，不改结构。  
4. 用 `04-*` 生成局部放大图。  
5. 用 `05-*` 做最终一致性核验。  

## 当前模块清单

{module_text}
"""


def _build_integrity_checklist() -> str:
    return """# 结构一致性核对清单

在提交论文图前逐项勾选：

- [ ] 节点数量与真值拓扑一致
- [ ] 节点命名与真值拓扑一致
- [ ] 连线关系与箭头方向一致
- [ ] 无新增/删除模块
- [ ] 局部放大图与主图模块含义一致
- [ ] 字体、配色、线宽在主图和子图中一致
- [ ] 图注与正文描述一致（不夸大功能）
"""


def _build_latex_snippet(model_name: str) -> str:
    return rf"""\begin{{figure*}}[t]
\centering
\includegraphics[width=\textwidth]{{figures/model-diagram/main-architecture.png}}
\caption{{Overall architecture of {model_name}.}}
\label{{fig:model-architecture}}
\end{{figure*}}

% 局部模块图（示例）
% \begin{{figure}}[t]
% \centering
% \includegraphics[width=\linewidth]{{figures/model-diagram/zoom-module.png}}
% \caption{{Zoomed-in view of a key module.}}
% \label{{fig:model-zoom}}
% \end{{figure}}
"""


def init_model_diagram_pack(
    project_dir: str,
    model_name: str,
    drawio_file_path: Optional[str] = None,
    truth_priority: str = "auto",
    mermaid_code: Optional[str] = None,
    modules: Optional[List[str]] = None,
    output_subdir: str = "figures/model-diagram",
    force: bool = False,
) -> Dict[str, object]:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"project_dir 不是有效目录: {root}")
    if not model_name or not str(model_name).strip():
        raise ValueError("model_name 不能为空")
    truth_choice = str(truth_priority or "auto").strip().lower()
    if truth_choice not in ("auto", "drawio", "mermaid"):
        raise ValueError("truth_priority 仅支持 auto/drawio/mermaid")

    module_list = _to_list(modules) or _default_modules()
    out_dir = (root / output_subdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    drawio_src: Optional[Path] = None
    if drawio_file_path:
        drawio_src = Path(drawio_file_path).expanduser().resolve()
        if not drawio_src.exists() or not drawio_src.is_file():
            raise ValueError(f"drawio_file_path 不存在: {drawio_src}")

    if truth_choice == "drawio" and drawio_src is None:
        raise ValueError("truth_priority=drawio 时必须提供 drawio_file_path")

    use_drawio = drawio_src is not None and truth_choice in ("auto", "drawio")
    truth_mode = "drawio" if use_drawio else "mermaid"

    truth_code = (mermaid_code or "").strip() or _build_mermaid_truth(model_name.strip(), module_list)

    files = {
        out_dir / "01-topology-truth.mmd": truth_code,
        out_dir / "02-nanobanana-main-prompt.txt": _build_main_prompt(
            model_name.strip(),
            truth_hint=(
                "请以 `01-topology-truth.drawio` 为唯一真值源；若与其他描述冲突，以 drawio 为准。"
                if truth_mode == "drawio"
                else "请以 `01-topology-truth.mmd` 为真值源。"
            ),
        ),
        out_dir / "03-nanobanana-style-refine-prompt.txt": _build_refine_prompt(),
        out_dir / "04-nanobanana-zoom-prompts.md": _build_zoom_prompt(module_list),
        out_dir / "05-integrity-checklist.md": _build_integrity_checklist(),
        out_dir / "README.md": _build_readme(model_name.strip(), module_list, truth_mode=truth_mode),
        out_dir / "latex-figure-snippet.tex": _build_latex_snippet(model_name.strip()),
    }

    written: List[str] = []
    skipped: List[str] = []
    for fp, content in files.items():
        status = _write_text(fp, content, force=force)
        if status == "written":
            written.append(str(fp))
        else:
            skipped.append(str(fp))

    lock_payload: Dict[str, object] = {}
    if truth_mode == "drawio" and drawio_src is not None:
        dst = out_dir / "01-topology-truth.drawio"
        status = _copy_file(drawio_src, dst, force=force)
        if status == "written":
            written.append(str(dst))
        else:
            skipped.append(str(dst))
        lock_payload = {
            "truth_mode": "drawio",
            "source_file": str(drawio_src),
            "truth_file": str(dst),
            "sha256": _sha256_file(dst),
        }
        lock_path = out_dir / "01-topology-lock.json"
        status = _write_text(lock_path, json.dumps(lock_payload, ensure_ascii=False, indent=2) + "\n", force=force)
        if status == "written":
            written.append(str(lock_path))
        else:
            skipped.append(str(lock_path))

    return {
        "ok": True,
        "project_dir": str(root),
        "output_dir": str(out_dir),
        "model_name": model_name.strip(),
        "truth_mode": truth_mode,
        "truth_lock": lock_payload if lock_payload else None,
        "modules": module_list,
        "written": written,
        "skipped": skipped,
    }
