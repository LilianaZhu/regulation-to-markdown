from __future__ import annotations

import re
from pathlib import Path

from .audit import AuditError, audit_completion, load_audit_manifest
from .findings import load_findings
from .merge import MergeError, covered_pages, page_segments
from .models import (
    FindingSeverity,
    FindingStatus,
    ValidationCheck,
    ValidationResult,
    VisualClassification,
    VisualDisposition,
)
from .pdf import inspect_pdf, sha256_file


def _image_targets(markdown: str) -> list[str]:
    return [
        match.group(2).strip()
        for match in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown)
    ]


def _table_shapes(markdown: str) -> list[list[int]]:
    shapes: list[list[int]] = []
    for table in re.findall(r"<table>.*?</table>", markdown, flags=re.DOTALL):
        rows = re.findall(r"<tr>.*?</tr>", table, flags=re.DOTALL)
        shapes.append([len(re.findall(r"<t[dh]>", row)) for row in rows])
    return shapes


def validate_document(
    markdown_path: str | Path,
    source_pdf_path: str | Path,
    findings_path: str | Path | None = None,
    audit_manifest_path: str | Path | None = None,
) -> ValidationResult:
    markdown_file = Path(markdown_path).resolve()
    source_pdf = Path(source_pdf_path).resolve()
    markdown = markdown_file.read_text(encoding="utf-8")
    pdf_info = inspect_pdf(source_pdf)
    checks: list[ValidationCheck] = []

    try:
        segments = page_segments(markdown)
        covered = covered_pages(markdown)
        duplicate_error = None
    except MergeError as exc:
        segments = {}
        covered = covered_pages(markdown)
        duplicate_error = str(exc)

    expected = set(range(1, pdf_info.page_count + 1))
    missing = sorted(expected - covered)
    extra = sorted(covered - expected)
    checks.append(
        ValidationCheck(
            check_id="page-coverage",
            title="PDF 页面覆盖",
            status="pass" if covered == expected else "fail",
            detail=(
                f"已覆盖全部 {pdf_info.page_count} 页"
                if covered == expected
                else f"缺失页={missing}；多余页={extra}"
            ),
            blocking=True,
        )
    )
    checks.append(
        ValidationCheck(
            check_id="duplicate-pages",
            title="页码标记唯一性",
            status="pass" if duplicate_error is None else "fail",
            detail=duplicate_error or f"{len(segments)} 个页码标记均唯一",
            blocking=True,
        )
    )

    broken_images: list[str] = []
    for target in _image_targets(markdown):
        if re.match(r"^(?:https?|data):", target, flags=re.IGNORECASE):
            continue
        if not (markdown_file.parent / target).is_file():
            broken_images.append(target)
    checks.append(
        ValidationCheck(
            check_id="image-assets",
            title="图片引用完整性",
            status="pass" if not broken_images else "fail",
            detail=(
                "没有损坏的本地图片引用"
                if not broken_images
                else f"缺失图片文件：{broken_images}"
            ),
            blocking=True,
        )
    )

    shapes = _table_shapes(markdown)
    malformed_tables = [
        index + 1
        for index, row_sizes in enumerate(shapes)
        if row_sizes and len(set(row_sizes)) > 1
    ]
    checks.append(
        ValidationCheck(
            check_id="table-shapes",
            title="HTML 表格结构",
            status="pass" if not malformed_tables else "warning",
            detail=(
                f"已检查 {len(shapes)} 个 HTML 表格"
                if not malformed_tables
                else f"以下 HTML 表格行宽不一致：{malformed_tables}"
            ),
            blocking=False,
        )
    )

    code_fences = len(re.findall(r"(?m)^```", markdown))
    checks.append(
        ValidationCheck(
            check_id="code-fences",
            title="代码围栏完整性",
            status="pass" if code_fences % 2 == 0 else "fail",
            detail=f"共发现 {code_fences} 行代码围栏标记，数量为偶数"
            if code_fences % 2 == 0
            else f"共发现 {code_fences} 行代码围栏标记，数量为奇数",
            blocking=True,
        )
    )

    audit_detail = "未提供审计清单"
    audit_passed = False
    if audit_manifest_path:
        try:
            audit_manifest = load_audit_manifest(audit_manifest_path)
            completion = audit_completion(audit_manifest)
            source_matches = audit_manifest.source_sha256 == pdf_info.sha256
            final_matches = audit_manifest.final_markdown_sha256 == sha256_file(
                markdown_file
            )
            audit_passed = bool(
                completion["complete"] and source_matches and final_matches
            )
            audit_detail = (
                "全部 AI 审校窗口和独立复核窗口均已完成"
                if audit_passed
                else "审校未完成或文件哈希不一致："
                f"{completion}; source_matches={source_matches}; "
                f"final_matches={final_matches}"
            )
        except AuditError as exc:
            audit_detail = str(exc)
    checks.append(
        ValidationCheck(
            check_id="ai-audit-completion",
            title="AI 审校与独立复核",
            status="pass" if audit_passed else "fail",
            detail=audit_detail,
            blocking=True,
        )
    )

    findings = load_findings(findings_path) if findings_path else []
    visual_categories = {
        "broken_image",
        "meaningful_visual",
        "non_substantive_visual",
    }
    visual_findings = [
        finding
        for finding in findings
        if finding.visual_classification is not None
        or finding.category in visual_categories
    ]
    invalid_visuals = []
    meaningful_pending_review = []
    omitted_non_substantive = []
    for finding in visual_findings:
        if finding.visual_classification is None:
            invalid_visuals.append(finding)
            continue
        if finding.visual_classification == VisualClassification.MEANINGFUL:
            if (
                finding.visual_disposition != VisualDisposition.DESCRIBED
                or not finding.visual_description
                or not finding.human_review_required
            ):
                invalid_visuals.append(finding)
            elif not finding.human_reviewed:
                meaningful_pending_review.append(finding)
        elif finding.visual_classification == VisualClassification.NON_SUBSTANTIVE:
            if (
                finding.visual_disposition
                not in {VisualDisposition.OMITTED, VisualDisposition.PRESERVED}
                or not finding.visual_description
            ):
                invalid_visuals.append(finding)
            elif finding.visual_disposition == VisualDisposition.OMITTED:
                omitted_non_substantive.append(finding)

    if invalid_visuals:
        visual_status = "fail"
        visual_detail = "图片分类或处理记录不完整：" + ", ".join(
            f"{item.finding_id}（PDF 第 {item.pdf_page} 页）"
            for item in invalid_visuals
        )
    elif meaningful_pending_review:
        visual_status = "warning"
        visual_detail = "以下条文相关图片已转成文字描述，仍需人工复核：" + ", ".join(
            f"{item.finding_id}（PDF 第 {item.pdf_page} 页）"
            for item in meaningful_pending_review
        )
    else:
        visual_status = "pass"
        visual_detail = (
            f"图片处理记录完整；已省略 {len(omitted_non_substantive)} 项"
            "与条文无直接关系的低信息图片"
        )
    checks.append(
        ValidationCheck(
            check_id="visual-content",
            title="图片语义分类与处理",
            status=visual_status,
            detail=visual_detail,
            blocking=True,
        )
    )

    unresolved = [
        finding
        for finding in findings
        if finding.severity in {FindingSeverity.HIGH, FindingSeverity.CRITICAL}
        and finding.status not in {FindingStatus.VERIFIED, FindingStatus.REJECTED}
    ]
    unverified_applied = [
        finding
        for finding in findings
        if finding.status in {FindingStatus.APPLIED, FindingStatus.VERIFIED}
        and not finding.source_verified
    ]
    checks.append(
        ValidationCheck(
            check_id="high-findings",
            title="高风险问题清零",
            status="pass" if not unresolved else "fail",
            detail=(
                "没有未解决的高风险或严重问题"
                if not unresolved
                else "未解决问题：" + ", ".join(item.finding_id for item in unresolved)
            ),
            blocking=True,
        )
    )
    checks.append(
        ValidationCheck(
            check_id="repair-evidence",
            title="修复原文证据",
            status="pass" if not unverified_applied else "fail",
            detail=(
                "所有已应用修复均有官方原文证据"
                if not unverified_applied
                else "缺少原文证据："
                + ", ".join(item.finding_id for item in unverified_applied)
            ),
            blocking=True,
        )
    )

    failed = any(check.status == "fail" and check.blocking for check in checks)
    warnings = any(check.status == "warning" for check in checks)
    status = "failed" if failed else "needs_review" if warnings else "passed"
    return ValidationResult(
        document_path=str(markdown_file),
        source_pdf_path=str(source_pdf),
        source_sha256=pdf_info.sha256,
        status=status,
        page_count=pdf_info.page_count,
        covered_pages=len(covered & expected),
        table_count=len(shapes),
        findings_total=len(findings),
        unresolved_high_findings=len(unresolved),
        checks=checks,
        notes=[
            "结构校验不能替代 AI 对官方 PDF 的逐页视觉复核。",
            "官方原文本身的异常应保持原样并单独记录。",
        ],
    )
