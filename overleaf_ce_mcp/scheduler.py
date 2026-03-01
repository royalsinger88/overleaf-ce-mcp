"""自动调度模板生成（cron / systemd timer）。"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict


def _safe_time(raw: str) -> str:
    text = str(raw or "23:10").strip()
    if ":" not in text:
        raise ValueError("daily_time 格式错误，应为 HH:MM")
    hh, mm = text.split(":", 1)
    h = int(hh)
    m = int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("daily_time 超出范围，应为 HH:MM（24 小时制）")
    return f"{h:02d}:{m:02d}"


def generate_scheduler_templates(
    project_dir: str,
    repo_dir: str,
    python_bin: str = "/usr/bin/python3",
    daily_time: str = "23:10",
) -> Dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    repo = Path(repo_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_dir 不是有效目录: %s" % str(root))
    if not repo.exists() or not repo.is_dir():
        raise ValueError("repo_dir 不是有效目录: %s" % str(repo))

    hhmm = _safe_time(daily_time)
    hour, minute = hhmm.split(":")
    auto_dir = root / "paper_state" / "automation"
    auto_dir.mkdir(parents=True, exist_ok=True)

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    cron_daily = auto_dir / "paper_cycle_daily.cron.example"
    cron_weekly = auto_dir / "paper_cycle_weekly.cron.example"
    svc_daily = auto_dir / "paper-cycle-daily.service"
    timer_daily = auto_dir / "paper-cycle-daily.timer"
    svc_weekly = auto_dir / "paper-cycle-weekly.service"
    timer_weekly = auto_dir / "paper-cycle-weekly.timer"

    cron_daily.write_text(
        (
            f"# 生成时间（UTC）：{created_at}\n"
            "# 每日执行：优化循环 + 日报 +（auto 模式按周五触发周报）\n"
            f"{minute} {hour} * * * cd {repo} && "
            f"{python_bin} -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
            f"run_paper_cycle(project_dir='{root}', weekly_mode='auto')\"\n"
        ),
        encoding="utf-8",
    )
    cron_weekly.write_text(
        (
            f"# 生成时间（UTC）：{created_at}\n"
            "# 每周五执行：强制生成周报\n"
            f"{minute} {hour} * * 5 cd {repo} && "
            f"{python_bin} -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
            f"run_paper_cycle(project_dir='{root}', weekly_mode='always')\"\n"
        ),
        encoding="utf-8",
    )

    svc_daily.write_text(
        (
            "[Unit]\n"
            "Description=Paper Cycle Daily\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            f"WorkingDirectory={repo}\n"
            f"ExecStart={python_bin} -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
            f"run_paper_cycle(project_dir='{root}', weekly_mode='auto')\"\n"
        ),
        encoding="utf-8",
    )
    timer_daily.write_text(
        (
            "[Unit]\n"
            "Description=Run Paper Cycle Daily\n\n"
            "[Timer]\n"
            f"OnCalendar=*-*-* {hour}:{minute}:00\n"
            "Persistent=true\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        ),
        encoding="utf-8",
    )

    svc_weekly.write_text(
        (
            "[Unit]\n"
            "Description=Paper Cycle Weekly\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            f"WorkingDirectory={repo}\n"
            f"ExecStart={python_bin} -c \"from overleaf_ce_mcp.workflow import run_paper_cycle; "
            f"run_paper_cycle(project_dir='{root}', weekly_mode='always')\"\n"
        ),
        encoding="utf-8",
    )
    timer_weekly.write_text(
        (
            "[Unit]\n"
            "Description=Run Paper Cycle Weekly (Friday)\n\n"
            "[Timer]\n"
            f"OnCalendar=Fri *-*-* {hour}:{minute}:00\n"
            "Persistent=true\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        ),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "project_dir": str(root),
        "repo_dir": str(repo),
        "daily_time": hhmm,
        "paths": {
            "cron_daily": str(cron_daily),
            "cron_weekly": str(cron_weekly),
            "systemd_daily_service": str(svc_daily),
            "systemd_daily_timer": str(timer_daily),
            "systemd_weekly_service": str(svc_weekly),
            "systemd_weekly_timer": str(timer_weekly),
        },
    }

