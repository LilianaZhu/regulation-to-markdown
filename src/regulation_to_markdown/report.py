from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from .findings import load_findings
from .models import (
    Finding,
    FindingStatus,
    ValidationResult,
    VisualClassification,
    VisualDisposition,
)
from .pdf import sha256_file

STATUS_LABELS = {
    "passed": "可以发布",
    "needs_review": "需要人工复核",
    "failed": "不可发布",
}
CHECK_LABELS = {
    "page-coverage": "PDF 页面覆盖",
    "duplicate-pages": "页码标记唯一性",
    "image-assets": "图片引用完整性",
    "visual-content": "图片语义分类与处理",
    "table-shapes": "HTML 表格结构",
    "code-fences": "代码围栏完整性",
    "ai-audit-completion": "AI 审校与独立复核",
    "high-findings": "高风险问题清零",
    "repair-evidence": "修复原文证据",
}
CHECK_STATUS_LABELS = {
    "pass": "通过",
    "warning": "需复核",
    "fail": "失败",
}
SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
}
CATEGORY_LABELS = {
    "wrong_text": "文本错误",
    "missing_text": "文本缺失",
    "duplicated_text": "文本重复",
    "missing_structure": "结构缺失",
    "broken_image": "图片问题",
    "meaningful_visual": "条文相关图片",
    "non_substantive_visual": "低信息图片处理",
    "source_anomaly": "官方原文异常",
}


def _ordered_counts(
    counts: Counter[str],
    labels: dict[str, str],
    order: tuple[str, ...],
) -> str:
    parts = [f"{labels.get(key, key)} {counts[key]} 项" for key in order if counts[key]]
    return "、".join(parts) if parts else "无"


def _evidence_names(
    result: ValidationResult,
    findings_path: str | Path | None,
    audit_manifest_path: str | Path | None,
) -> list[str]:
    names: list[str] = []
    for path in (findings_path, audit_manifest_path):
        if path:
            names.append(Path(path).name)
    repairs = Path(result.document_path).with_suffix(
        Path(result.document_path).suffix + ".repairs.jsonl"
    )
    if repairs.is_file():
        names.append(repairs.name)
    return list(dict.fromkeys(names))


def render_validation_report(
    result: ValidationResult,
    findings: list[Finding],
    *,
    evidence_files: list[str] | None = None,
) -> str:
    evidence_files = evidence_files or []
    check_counts = Counter(check.status for check in result.checks)
    finding_status_counts = Counter(finding.status.value for finding in findings)
    severity_counts = Counter(finding.severity.value for finding in findings)
    verified = [
        finding for finding in findings if finding.status == FindingStatus.VERIFIED
    ]
    unresolved = [
        finding
        for finding in findings
        if finding.status not in {FindingStatus.VERIFIED, FindingStatus.REJECTED}
    ]
    verified_severities = Counter(finding.severity.value for finding in verified)
    verified_categories = Counter(finding.category for finding in verified)
    verified_pages = sorted({finding.pdf_page for finding in verified})
    meaningful_visuals = [
        finding
        for finding in findings
        if finding.visual_classification == VisualClassification.MEANINGFUL
    ]
    omitted_visuals = [
        finding
        for finding in findings
        if finding.visual_classification == VisualClassification.NON_SUBSTANTIVE
        and finding.visual_disposition == VisualDisposition.OMITTED
    ]
    pending_visual_review = [
        finding for finding in meaningful_visuals if not finding.human_reviewed
    ]

    frontmatter = {
        "schema_version": 2,
        "report_type": "regulation-to-markdown-validation",
        "status": result.status,
        "release_allowed": result.status == "passed",
        "generated_at": result.generated_at.isoformat(),
        "files": {
            "source_pdf": Path(result.source_pdf_path).name,
            "final_markdown": Path(result.document_path).name,
        },
        "source_sha256": result.source_sha256,
        "final_sha256": sha256_file(result.document_path),
        "summary": {
            "page_count": result.page_count,
            "covered_pages": result.covered_pages,
            "table_count": result.table_count,
            "checks": {
                "passed": check_counts["pass"],
                "warnings": check_counts["warning"],
                "failed": check_counts["fail"],
            },
            "findings": {
                "total": len(findings),
                "verified": finding_status_counts[FindingStatus.VERIFIED.value],
                "rejected": finding_status_counts[FindingStatus.REJECTED.value],
                "unresolved": len(unresolved),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "medium": severity_counts["medium"],
                "low": severity_counts["low"],
            },
            "visuals": {
                "meaningful": len(meaningful_visuals),
                "omitted_non_substantive": len(omitted_visuals),
                "needs_human_review": len(pending_visual_review),
            },
        },
        "evidence_files": evidence_files,
    }
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    ).strip()

    status_label = STATUS_LABELS[result.status]
    conclusion = {
        "passed": (
            f"{result.page_count} 页官方 PDF 已全部覆盖，所有发布门禁均已通过。"
        ),
        "needs_review": "存在需要人工确认的项目，当前文件不得作为最终版本发布。",
        "failed": "存在阻断性问题，当前文件不得发布。",
    }[result.status]
    lines = [
        "---",
        yaml_text,
        "---",
        "",
        "# 法规 Markdown 核验报告",
        "",
        f"> **核验结论：{status_label}**  ",
        f"> {conclusion}",
        "",
        "## 操作者需要处理",
        "",
    ]

    actionable_checks = [check for check in result.checks if check.status != "pass"]
    if not actionable_checks and not unresolved:
        lines.extend(["- 无。报告未发现需要操作者继续处理的项目。", ""])
    for check in actionable_checks:
        lines.extend(
            [
                (
                    f"- **{CHECK_STATUS_LABELS[check.status]}｜"
                    f"{CHECK_LABELS.get(check.check_id, check.title)}**：{check.detail}"
                )
            ]
        )
    for finding in unresolved:
        lines.append(
            f"- **PDF 第 {finding.pdf_page} 页｜"
            f"{SEVERITY_LABELS.get(finding.severity.value, finding.severity.value)}风险｜"
            f"{CATEGORY_LABELS.get(finding.category, finding.category)}**"
            f"（`{finding.finding_id}`）：{finding.rationale}"
        )
    if actionable_checks or unresolved:
        lines.append("")

    lines.extend(
        [
            "## 核验摘要",
            "",
            f"- 页面覆盖：{result.covered_pages}/{result.page_count} 页",
            (
                f"- 发布门禁：{check_counts['pass']} 项通过，"
                f"{check_counts['warning']} 项需复核，"
                f"{check_counts['fail']} 项失败"
            ),
            (
                f"- 审校问题：共 {len(findings)} 项，"
                f"{finding_status_counts[FindingStatus.VERIFIED.value]} 项已验证，"
                f"{len(unresolved)} 项未解决"
            ),
            f"- HTML 表格：{result.table_count} 个",
            "",
            "## 已核验问题摘要",
            "",
        ]
    )
    if verified:
        lines.extend(
            [
                f"- 严重程度：{_ordered_counts(verified_severities, SEVERITY_LABELS, ('critical', 'high', 'medium', 'low'))}",
                f"- 问题类型：{_ordered_counts(verified_categories, CATEGORY_LABELS, tuple(verified_categories))}",
                f"- 涉及 PDF 页码：{', '.join(map(str, verified_pages))}",
                "- 每项修复均已重新对照官方 PDF，并完成独立复核。",
            ]
        )
    else:
        lines.append("- 未记录已验证的问题。")

    lines.extend(["", "## 视觉内容处理", ""])
    if not meaningful_visuals and not omitted_visuals:
        lines.append("- 未记录需要描述或明确省略的图片。")
    for finding in meaningful_visuals:
        review_state = "已人工复核" if finding.human_reviewed else "⚠️ 需要人工复核"
        lines.append(
            f"- **PDF 第 {finding.pdf_page} 页｜条文相关图片｜{review_state}**："
            f"{finding.visual_description or finding.rationale}"
        )
    for finding in omitted_visuals:
        lines.append(
            f"- **PDF 第 {finding.pdf_page} 页｜已省略低信息图片**："
            f"{finding.visual_description or finding.rationale}"
        )

    lines.extend(["", "## 发布门禁", ""])
    for check in result.checks:
        lines.append(
            f"- **{CHECK_STATUS_LABELS[check.status]}**｜"
            f"{CHECK_LABELS.get(check.check_id, check.title)}：{check.detail}"
        )

    lines.extend(
        [
            "",
            "## 文件与证据",
            "",
            f"- 官方 PDF：`{Path(result.source_pdf_path).name}`",
            f"- 最终 Markdown：`{Path(result.document_path).name}`",
        ]
    )
    if evidence_files:
        lines.append("- 审计证据：" + "、".join(f"`{name}`" for name in evidence_files))
    else:
        lines.append("- 审计证据：未向报告生成器提供证据文件路径")

    lines.extend(
        [
            "",
            "<details>",
            "<summary>技术信息</summary>",
            "",
            f"- 生成时间：`{result.generated_at.isoformat()}`",
            f"- 源 PDF SHA-256：`{result.source_sha256}`",
            "- 结构校验不能替代 AI 对官方 PDF 的逐页视觉复核。",
            "- 官方原文本身的异常应保持原样并单独记录。",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_report(
    result: ValidationResult,
    report_path: str | Path,
    findings_path: str | Path | None = None,
    audit_manifest_path: str | Path | None = None,
) -> str:
    findings = load_findings(findings_path) if findings_path else []
    destination = Path(report_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_validation_report(
            result,
            findings,
            evidence_files=_evidence_names(
                result,
                findings_path,
                audit_manifest_path,
            ),
        ),
        encoding="utf-8",
        newline="\n",
    )
    return str(destination)
