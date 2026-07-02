# docx/build_handbook.py
# 文件说明：植被指数智能分析平台源代码与实现主手册生成器。
# 主要职责：从当前仓库提取源码清单、FastAPI 路由和指数注册表，生成可重复构建的中文 DOCX。
# 对外入口：main。
# 依赖边界：只读取项目文件并写入 docx/，不修改业务代码、数据库或外部服务。

from __future__ import annotations

import ast
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docx" / "植被指数智能分析平台源代码与实现主手册.docx"
BACKEND = ROOT / "backend"

sys.path.insert(0, str(BACKEND))
from app.core.indices import INDEX_REGISTRY  # noqa: E402

BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "17212B"
MUTED = "5F6B76"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"
PALE_GREEN = "EAF4E3"
PALE_GOLD = "FFF4D6"
WHITE = "FFFFFF"
RED = "9B1C1C"
TOTAL_WIDTH_DXA = 9360


def set_run_font(
    run: Any,
    *,
    name: str = "Microsoft YaHei",
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    """统一设置中西文字体，避免 LibreOffice 或 Word 出现中文字体回退不一致。"""
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Calibri")
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Calibri")
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_repeat_table_header(row: Any) -> None:
    """把表头行标记为跨页重复。"""
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_cell_shading(cell: Any, fill: str) -> None:
    """设置表格单元格底色。"""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(
    cell: Any,
    *,
    top: tuple[str, str] | None = None,
    bottom: tuple[str, str] | None = None,
    left: tuple[str, str] | None = None,
    right: tuple[str, str] | None = None,
) -> None:
    """按 Word OOXML 设置单元格边框；None 表示移除该方向边框。"""
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge_name, spec in {
        "top": top,
        "bottom": bottom,
        "left": left,
        "right": right,
        "insideH": None,
        "insideV": None,
    }.items():
        edge = borders.find(qn(f"w:{edge_name}"))
        if edge is None:
            edge = OxmlElement(f"w:{edge_name}")
            borders.append(edge)
        if spec is None:
            edge.set(qn("w:val"), "nil")
            edge.set(qn("w:sz"), "0")
            edge.set(qn("w:color"), "auto")
        else:
            size, color = spec
            edge.set(qn("w:val"), "single")
            edge.set(qn("w:sz"), size)
            edge.set(qn("w:color"), color)


def apply_three_line_table(table: Any, header_fill: str = "FFFFFF") -> None:
    """应用中文论文常用三线表：顶线、表头分隔线、底线，无竖线。"""
    if not table.rows:
        return
    last_index = len(table.rows) - 1
    for row_index, row in enumerate(table.rows):
        for cell in row.cells:
            top = ("12", "000000") if row_index == 0 else None
            bottom = ("8", "000000") if row_index in {0, last_index} else None
            set_cell_border(cell, top=top, bottom=bottom, left=None, right=None)
            if row_index == 0:
                set_cell_shading(cell, header_fill)


def set_cell_margins(cell: Any, top: int = 80, bottom: int = 80, start: int = 120, end: int = 120) -> None:
    """显式设置单元格内边距，避免文字贴边。"""
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for tag, value in (("top", top), ("bottom", bottom), ("start", start), ("end", end)):
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table: Any, widths: list[int], indent: int = 120) -> None:
    """让 tblW、tblGrid 和 tcW 使用一致的 DXA 宽度。"""
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent))
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    apply_three_line_table(table)


def configure_styles(doc: Document) -> None:
    """应用 compact_reference_guide 预设的明确样式参数。"""
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    heading_tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 14, 7),
        "Heading 3": (12, DARK_BLUE, 10, 5),
    }
    for name, (size, color, before, after) in heading_tokens.items():
        style = doc.styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for name in ("List Bullet", "List Number"):
        style = doc.styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(11)
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.188)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25

    code = doc.styles.add_style("Code Block", 1)
    code.font.name = "Consolas"
    code._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    code.font.size = Pt(8.5)
    code.font.color.rgb = RGBColor.from_string("243447")
    code.paragraph_format.left_indent = Inches(0.16)
    code.paragraph_format.right_indent = Inches(0.08)
    code.paragraph_format.space_before = Pt(4)
    code.paragraph_format.space_after = Pt(8)
    code.paragraph_format.line_spacing = 1.05


def configure_header_footer(section: Any) -> None:
    """设置安静的运行页眉与页码。"""
    header = section.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0]
    for child in list(p._p):
        p._p.remove(child)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run("植被指数智能分析平台 | 源代码与实现主手册")
    set_run_font(run, size=8.5, color=MUTED)

    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    for child in list(p._p):
        p._p.remove(child)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    prefix = p.add_run("第 ")
    set_run_font(prefix, size=8.5, color=MUTED)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    p._p.append(field)
    suffix = p.add_run(" 页")
    set_run_font(suffix, size=8.5, color=MUTED)


def add_title(doc: Document, text: str, subtitle: str | None = None) -> None:
    """创建 editorial_cover 风格封面。"""
    for _ in range(5):
        doc.add_paragraph()
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = kicker.add_run("程序设计实习 · 汇报与代码答辩")
    set_run_font(run, size=11, color=BLUE, bold=True)
    kicker.paragraph_format.space_after = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)
    run = p.add_run(text)
    set_run_font(run, size=28, color=DARK_BLUE, bold=True)

    if subtitle:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(34)
        run = p.add_run(subtitle)
        set_run_font(run, size=14, color=MUTED)

    for label, value in (
        ("项目", "植被指数提取算法封装与 Web 服务实现"),
        ("技术栈", "FastAPI + Rasterio + NumPy/Joblib/PyTorch + Vue 3 + pygeoapi"),
        ("生成日期", date.today().isoformat()),
        ("代码基线", "当前工作区实现，35 个内置植被指数"),
    ):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        r1 = p.add_run(f"{label}：")
        set_run_font(r1, size=10.5, color=MUTED, bold=True)
        r2 = p.add_run(value)
        set_run_font(r2, size=10.5, color=INK)

    doc.add_paragraph()
    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.space_before = Pt(18)
    run = note.add_run("用途：源码导读、接口演示、架构说明、分块计算讲解与答辩备忘")
    set_run_font(run, size=10, color=BLUE, italic=True)
    doc.add_page_break()


def add_heading(doc: Document, text: str, level: int = 1) -> Any:
    """添加正式标题。"""
    return doc.add_heading(text, level=level)


def add_para(
    doc: Document,
    text: str,
    *,
    bold_prefix: str | None = None,
    color: str | None = None,
    keep: bool = False,
) -> Any:
    """添加正文段落，可选加粗前缀。"""
    p = doc.add_paragraph()
    p.paragraph_format.keep_together = keep
    if bold_prefix and text.startswith(bold_prefix):
        first = p.add_run(bold_prefix)
        set_run_font(first, bold=True, color=color or INK)
        rest = p.add_run(text[len(bold_prefix) :])
        set_run_font(rest, color=color or INK)
    else:
        run = p.add_run(text)
        set_run_font(run, color=color or INK)
    return p


def add_bullets(doc: Document, items: Iterable[str]) -> None:
    """使用 Word 原生项目符号添加列表。"""
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item)
        set_run_font(run)


def add_steps(doc: Document, items: Iterable[str]) -> None:
    """使用 Word 原生编号添加步骤。"""
    for item in items:
        p = doc.add_paragraph(style="List Number")
        run = p.add_run(item)
        set_run_font(run)


def add_callout(doc: Document, label: str, text: str, fill: str = PALE_GOLD) -> None:
    """添加单栏重点提示。"""
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [TOTAL_WIDTH_DXA])
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    r1 = p.add_run(f"{label}：")
    set_run_font(r1, bold=True, color=DARK_BLUE)
    r2 = p.add_run(text)
    set_run_font(r2)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code(doc: Document, text: str) -> None:
    """添加带浅灰底的代码/目录块。"""
    p = doc.add_paragraph(style="Code Block")
    p.paragraph_format.keep_together = False
    p_pr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F5F7F9")
    p_pr.append(shd)
    run = p.add_run(text.rstrip())
    set_run_font(run, name="Consolas", size=8.5, color="243447")


def add_table(
    doc: Document,
    headers: list[str],
    rows: Iterable[Iterable[Any]],
    widths: list[int],
    *,
    font_size: float = 8.5,
    header_fill: str = LIGHT_BLUE,
) -> Any:
    """添加固定几何、重复表头和显式字号的表格。"""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    header = table.rows[0]
    set_repeat_table_header(header)
    for cell, text in zip(header.cells, headers):
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(str(text))
        set_run_font(run, size=font_size, color=DARK_BLUE, bold=True)

    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        if row_index % 2:
            for cell in cells:
                set_cell_shading(cell, "FAFBFC")
        for cell, value in zip(cells, values):
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run("" if value is None else str(value))
            set_run_font(run, size=font_size)
    set_table_geometry(table, widths)
    apply_three_line_table(table, header_fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_wide_section(doc: Document) -> Any:
    """创建用于源码、接口和指数大表的横向节。"""
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    section.header_distance = Inches(0.3)
    section.footer_distance = Inches(0.3)
    configure_header_footer(section)
    return section


def add_portrait_section(doc: Document) -> Any:
    """从横向附表恢复标准纵向正文。"""
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    configure_header_footer(section)
    return section


def extract_file_summary(path: Path) -> str:
    """从统一文件头中提取中文职责。"""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "二进制或非 UTF-8 文件"
    match = re.search(r"文件说明：([^。\n]+)", text[:1200])
    if match:
        return match.group(1).strip()
    suffix = path.suffix.lower()
    return {
        ".yml": "部署或服务配置",
        ".yaml": "部署或服务配置",
        ".json": "项目配置或类型配置",
        ".vue": "Vue 单文件组件",
        ".ts": "TypeScript 源文件",
        ".py": "Python 源文件",
        ".css": "样式文件",
    }.get(suffix, "项目文件")


def source_inventory() -> list[tuple[str, str, int, str]]:
    """生成全部自有源代码与关键部署文件清单。"""
    patterns = (
        "backend/app/**/*.py",
        "backend/tests/*.py",
        "backend/scripts/*.py",
        "frontend/src/**/*.ts",
        "frontend/src/**/*.vue",
        "frontend/src/**/*.css",
    )
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(ROOT.glob(pattern))
    for rel in (
        "backend/pyproject.toml",
        "frontend/package.json",
        "frontend/vite.config.js",
        "compose.yml",
        "infra/pygeoapi/config.yml",
        "infra/traefik/traefik.yml",
    ):
        path = ROOT / rel
        if path.exists():
            paths.add(path)

    rows = []
    for path in sorted(paths):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("backend/app/core") or rel.startswith("backend/app/engines"):
            layer = "算法/引擎层"
        elif rel.startswith("backend/app/api"):
            layer = "接口层"
        elif rel.startswith("backend/app/services"):
            layer = "后端服务层"
        elif rel.startswith("backend/tests"):
            layer = "测试层"
        elif rel.startswith("backend"):
            layer = "后端入口/配置"
        elif rel.startswith("frontend/src/components"):
            layer = "前端组件层"
        elif rel.startswith("frontend/src"):
            layer = "前端状态/类型层"
        elif rel.startswith("infra") or rel == "compose.yml":
            layer = "部署层"
        else:
            layer = "项目配置"
        try:
            lines = len(path.read_text(encoding="utf-8").splitlines())
        except UnicodeDecodeError:
            lines = 0
        rows.append((layer, rel, lines, extract_file_summary(path)))
    return rows


def route_inventory() -> list[tuple[str, str, str, str]]:
    """从 FastAPI 装饰器提取方法、路径和处理函数。"""
    path = ROOT / "backend/app/api/routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} or not decorator.args:
                continue
            first = decorator.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            summary = ast.get_docstring(node) or "接口处理器"
            rows.append((method, first.value, node.name, summary))
    return rows


def index_inventory() -> list[tuple[str, str, str, str, str]]:
    """读取当前运行期注册表中的内置指数元数据。"""
    rows = []
    for item in INDEX_REGISTRY.values():
        rows.append(
            (
                item.id.upper(),
                item.name,
                item.formula,
                ", ".join(item.required_bands),
                ", ".join(item.categories) or "通用",
            )
        )
    return rows


def add_contents(doc: Document) -> None:
    """添加静态章节导航，避免依赖 Word 未更新的 TOC 域。"""
    add_heading(doc, "阅读导航", 1)
    add_callout(
        doc,
        "建议汇报顺序",
        "先讲第 2、4、8、9、10、12 章，再演示第 7 章接口，最后用第 18 章答辩问答收尾。",
        PALE_GREEN,
    )
    chapters = [
        "1. 文档定位与汇报速览",
        "2. 项目目标、需求与已实现范围",
        "3. 总体架构与端到端数据流",
        "4. 文件目录设计与模块划分",
        "5. 全部源代码清单",
        "6. 后端核心对象与依赖方向",
        "7. 接口设计概要与接口文档查看方法",
        "8. pygeoapi / OGC API - Processes 实现",
        "9. 植被指数注册表设计",
        "10. 多计算引擎设计",
        "11. 自动引擎选择",
        "12. Rasterio 分块计算完整设计",
        "13. 资产、瓦片、统计和溯源产物",
        "14. 异步任务、Celery、Redis 与取消",
        "15. 智能分析 Agent 的实现与安全边界",
        "16. Vue 前端各层实现",
        "17. 部署、配置、测试与常见问题",
        "18. 汇报演示脚本与高频答辩问答",
        "附录 A. FastAPI 全接口表",
        "附录 B. 35 个植被指数表",
    ]
    add_bullets(doc, chapters)


def build_manual(doc: Document) -> None:
    """写入主手册正文。"""
    add_heading(doc, "1. 文档定位与汇报速览", 1)
    add_para(
        doc,
        "本手册不是需求规划书，而是对当前仓库真实代码的系统说明。它回答五个核心问题："
        "代码放在哪里、模块为什么这样划分、请求如何进入计算、35 个指数如何共享同一套公式、"
        "大影像为什么不会一次性撑爆内存。"
    )
    add_callout(
        doc,
        "30 秒总述",
        "平台以统一指数注册表为算法事实源，FastAPI/pygeoapi 把算法暴露为 OGC 风格服务，"
        "RasterPipeline 负责窗口化 I/O，NumPy/Joblib/PyTorch 负责数组计算，Celery 负责异步调度，"
        "Vue 3 工作台完成上传、波段映射、任务、地图、统计和 Agent 交互。",
        PALE_GREEN,
    )
    add_heading(doc, "1.1 汇报时必须主动说明的边界", 2)
    add_bullets(
        doc,
        [
            "当前代码内置 35 个指数：30 个任务书核心指数，加 5 个旧服务兼容指数。",
            "公式只定义一次，三种引擎共享 expression；不存在三份公式复制。",
            "分块计算按窗口读写，内存占用主要与块大小、波段数和指数数相关，而不是与整幅影像面积线性绑定。",
            "本地开发可使用线程池/eager；容器部署使用 Celery + Redis、MinIO、Nacos 和 Traefik。",
            "Agent 默认先生成计划，确认接口之后才真正提交计算。",
            "GPU、Docker、Nacos、MinIO 的真实运行效果取决于汇报机器环境；代码支持不等于当前机器已完成全部外部基础设施验证。",
        ],
    )

    add_heading(doc, "2. 项目目标、需求与已实现范围", 1)
    add_para(
        doc,
        "任务书要求从算法层、服务层、调用层和部署层完成植被指数服务化。当前实现把这些要求拆成可测试的"
        "独立层，并通过 `/api/system/taskbook-coverage` 暴露覆盖清单。"
    )
    add_table(
        doc,
        ["任务书要求", "当前实现", "关键代码", "说明"],
        [
            ("至少 30 种指数", "35 个内置指数", "backend/app/core/indices.py", "统一注册、统一元数据"),
            ("Rasterio 分块", "按 blockSize 生成 Window", "services/raster_pipeline.py", "共享波段读取"),
            ("同步/异步调用", "Prefer: respond-async", "api/routes.py + services/jobs.py", "同一任务模型"),
            ("Celery + Redis", "五级优先队列", "celery_app.py + worker_tasks.py", "部署模式启用"),
            ("MinIO", "输入/结果对象上传", "services/assets.py", "本地不可用时保留本地路径"),
            ("pygeoapi", "动态 Processor", "pygeoapi_processor.py", "单类处理全部指数"),
            ("Nacos + Traefik", "注册、心跳和配置桥", "services/nacos.py + nacos_bridge.py", "服务发现与网关解耦"),
            ("Vue 3 前端", "地图、上传、任务、Agent、统计", "frontend/src/", "Pinia 管理单一状态"),
        ],
        [1600, 2000, 2700, 3060],
    )

    add_heading(doc, "3. 总体架构与端到端数据流", 1)
    add_code(
        doc,
        """用户 / Vue 3 工作台
        │ 上传 GeoTIFF、选择指数、编辑波段、确认 Agent 方案
        ▼
Traefik / FastAPI / pygeoapi
        │ Schema 校验、协议转换、同步或异步分流
        ▼
JobManager / Celery + Redis
        │ 创建 RasterTask，维护状态、进度、取消和结果
        ▼
RasterPipeline
        │ 元数据校验 → 窗口生成 → 共享波段读取 → 引擎计算 → 顺序写出
        ├──────── NumPy
        ├──────── Joblib
        └──────── PyTorch CUDA（失败回退）
        ▼
GeoTIFF + overview + PNG + JSON statistics + manifest
        │
        ├──────── 本地 data 目录
        └──────── MinIO 对象存储
        ▼
Vue 地图瓦片 / ECharts / Agent 结果解释"""
    )
    add_heading(doc, "3.1 一次同步请求的完整调用链", 2)
    add_steps(
        doc,
        [
            "前端 `usePlatformApi.executeProcess` 向 `/processes/{id}/execution` 发送 JSON。",
            "Pydantic `ExecutionRequest` 校验 source、indices、bands、engine、blockSize 和 priority。",
            "路由把请求转换成 `RasterTask`，并解析 MinIO objectKey 或本地路径。",
            "`JobManager.execute_sync` 直接调用 `RasterPipeline.run`。",
            "流水线读取影像元数据，计算必需逻辑波段并集，选择实际引擎。",
            "每个窗口只读取一次必需波段，三种引擎只接触 NumPy 数组/张量。",
            "每个指数写入独立 GeoTIFF，随后构建 overview、统计、预览与 manifest。",
            "响应返回产品路径、对象键、范围、CRS、统计、实际引擎和回退原因。",
        ],
    )
    add_heading(doc, "3.2 一次异步请求的区别", 2)
    add_para(
        doc,
        "唯一关键区别是请求头包含 `Prefer: respond-async`。路由不直接运行流水线，而是调用"
        "`JobManager.submit`。本地模式进入线程池，部署模式进入 Celery 队列。前端轮询 `/jobs/{id}`，"
        "成功后读取 `/jobs/{id}/results`。核心计算代码仍然只有一份。"
    )

    add_heading(doc, "4. 文件目录设计与模块划分", 1)
    add_code(
        doc,
        """backend/app/
├── api/                HTTP Schema 与路由编排
├── core/               纯算法注册表
├── engines/            数组计算后端
├── services/           栅格、任务、资产、Agent、存储、Nacos
├── main.py             FastAPI 装配
├── worker_tasks.py     Celery 入口
└── pygeoapi_processor.py

frontend/src/
├── components/         地图、Agent、资产、任务、统计与应用框架
├── composables/        HTTP/SSE 与主题
├── stores/             Pinia 单一工作台状态
├── types/              前后端契约类型
├── App.vue             根编排
└── main.ts             启动入口

infra/
├── pygeoapi/config.yml
└── traefik/traefik.yml"""
    )
    add_heading(doc, "4.1 划分原则", 2)
    add_bullets(
        doc,
        [
            "依赖方向自外向内：路由可以依赖服务，服务可以依赖核心；核心公式不反向依赖框架。",
            "同一事实只保留一个来源：公式在注册表、前端状态在 Pinia、任务状态在 JobManager。",
            "协议和执行分离：FastAPI 与 pygeoapi 只是两种入口，最终都进入 RasterPipeline。",
            "计算和 I/O 分离：引擎只接收数组，Rasterio 只存在于流水线与分析服务。",
            "部署和业务分离：Nacos、Traefik、Celery、MinIO 通过适配层接入，不污染公式。",
        ],
    )

    add_source_appendix(doc)

    add_heading(doc, "6. 后端核心对象与依赖方向", 1)
    add_table(
        doc,
        ["对象", "职责", "输入", "输出/状态", "不得承担"],
        [
            ("IndexDefinition", "指数契约", "xp、bands、parameters", "数组与公开元数据", "Rasterio/HTTP"),
            ("ExecutionRequest", "HTTP 契约校验", "JSON", "强类型请求", "文件计算"),
            ("RasterTask", "执行参数载体", "解析后的路径与选项", "可序列化任务", "业务状态"),
            ("ExecutionPlanner", "引擎决策", "尺寸、波段、指数、请求", "selected/reason/memory", "真实计算"),
            ("ComputeEngine", "窗口数组计算", "定义列表、波段数组", "EngineResult", "文件 I/O"),
            ("RasterPipeline", "完整栅格执行", "RasterTask", "产品与 manifest", "HTTP 状态码"),
            ("JobManager", "任务生命周期", "RasterTask", "JobRecord", "公式实现"),
            ("VegetationAgent", "方案规划与解释", "自然语言、波段、知识", "待确认计划", "未确认执行"),
        ],
        [1350, 1900, 1850, 2100, 2160],
    )

    add_heading(doc, "7. 接口设计概要与接口文档查看方法", 1)
    add_heading(doc, "7.1 启动 FastAPI", 2)
    add_code(
        doc,
        r"""cd backend
D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload"""
    )
    add_heading(doc, "7.2 浏览器入口", 2)
    add_table(
        doc,
        ["入口", "地址", "用途"],
        [
            ("Swagger UI", "http://127.0.0.1:8011/docs", "交互式查看 Schema 并直接 Try it out"),
            ("ReDoc", "http://127.0.0.1:8011/redoc", "按模型和标签阅读接口说明"),
            ("OpenAPI JSON", "http://127.0.0.1:8011/openapi.json", "供前端生成、测试或导入 Postman"),
            ("健康检查", "http://127.0.0.1:8011/health", "确认 FastAPI 进程已启动"),
            ("指数目录", "http://127.0.0.1:8011/api/indices", "检查 35 个指数元数据"),
            ("Process 目录", "http://127.0.0.1:8011/processes", "查看 OGC 风格处理能力"),
        ],
        [1700, 3100, 4560],
    )
    add_heading(doc, "7.3 Swagger 演示建议", 2)
    add_steps(
        doc,
        [
            "先调用 `GET /health`，确认服务在线。",
            "调用 `GET /api/system/capabilities`，展示引擎、CUDA、指数数和存储模式。",
            "调用 `GET /api/indices/ndvi`，解释注册表元数据如何直接成为接口输出。",
            "调用 `POST /api/assets/inspect` 或上传接口，展示影像尺寸、CRS、波段和范围。",
            "调用 `POST /processes/ndvi/execution`，提交 source、bands、engine 和 blockSize。",
            "再用 `Prefer: respond-async` 演示返回 jobID，并查询 jobs/results。",
        ],
    )
    add_heading(doc, "7.4 典型执行请求", 2)
    add_code(
        doc,
        """{
  "source": {"localPath": "data/uploads/example.tif"},
  "indices": ["ndvi"],
  "bands": {"red": 3, "nir": 4},
  "engine": "auto",
  "blockSize": 1024,
  "priority": 3,
  "preview": true,
  "statistics": true
}"""
    )
    add_callout(
        doc,
        "接口设计重点",
        "`bands` 使用逻辑波段名映射物理波段号，使公式不关心 Sentinel、Landsat 或无人机的实际波段顺序。",
        PALE_GREEN,
    )

    add_heading(doc, "8. pygeoapi / OGC API - Processes 实现", 1)
    add_para(
        doc,
        "项目同时保留 FastAPI 的 OGC 风格路由和独立 pygeoapi Processor。前者方便与现有平台、Agent、"
        "上传和任务中心统一；后者展示标准框架插件能力。两者最终复用相同的注册表和 RasterPipeline。"
    )
    add_heading(doc, "8.1 配置如何找到处理器", 2)
    add_code(
        doc,
        """resources:
  spectral-index:
    type: process
    processor:
      name: app.pygeoapi_processor.SpectralIndexProcessor"""
    )
    add_para(
        doc,
        "`name` 是 Python 可导入路径。pygeoapi 实例化 `SpectralIndexProcessor`，构造函数把"
        "`PROCESS_METADATA` 交给 `BaseProcessor`；`execute(data)` 再解析 index/source/bands，"
        "构造 `RasterTask` 并返回 `(application/json, result)`。"
    )
    add_heading(doc, "8.2 为什么一个类能处理 35 个指数", 2)
    add_para(
        doc,
        "Process 输入包含 `index` 字段。处理器通过 `get_index(index_id)` 从统一注册表获取定义，"
        "因此新增指数只需要扩展注册表，不需要新增 Processor 类、重复 YAML 或复制 I/O 逻辑。"
    )
    add_heading(doc, "8.3 如何查看 pygeoapi", 2)
    add_steps(
        doc,
        [
            "确保当前工作目录能导入 `backend/app`，并让 pygeoapi 使用 `infra/pygeoapi/config.yml`。",
            "开发模式可使用 `pygeoapi serve --config infra/pygeoapi/config.yml`，配置监听端口为 5000。",
            "访问 `http://localhost:5000/` 查看 Landing Page。",
            "访问 `http://localhost:5000/openapi.json` 获取 OpenAPI 文档；Landing Page 通常提供 Swagger UI/ReDoc 链接。",
            "访问 `http://localhost:5000/processes` 查看 Process 列表。",
            "访问 `/processes/spectral-index` 查看描述，POST `/processes/spectral-index/execution` 执行。",
            "异步任务按 OGC API - Processes 使用 `/jobs`、`/jobs/{jobId}` 和结果链接查看。",
        ],
    )
    add_callout(
        doc,
        "当前实现差异",
        "独立 pygeoapi Processor 目前直接调用 RasterPipeline；平台级 FastAPI 路由拥有更完整的上传、Agent、"
        "任务轮询、瓦片和扩展分析能力。答辩时应把它们表述为“标准框架入口”和“综合平台入口”。",
    )

    add_heading(doc, "9. 植被指数注册表设计", 1)
    add_heading(doc, "9.1 IndexDefinition 字段", 2)
    add_table(
        doc,
        ["字段", "含义", "为什么需要"],
        [
            ("id/name", "机器编号与中文名", "接口、文件名和 UI 统一定位"),
            ("formula", "人类可读公式", "Swagger、前端公式卡和答辩说明"),
            ("required_bands", "逻辑波段集合", "执行前验证与共享读取并集"),
            ("expression", "后端无关计算函数", "同一公式运行在 NumPy 或 Torch"),
            ("parameters", "默认参数", "SAVI/EVI 等参数化指数"),
            ("expected_range", "建议范围", "UI 展示、异常识别和解释"),
            ("categories/tags", "分类与推荐标签", "目录筛选和 Agent RAG"),
            ("limitations", "限制条件", "避免把单一指数解释为确定诊断"),
            ("amp_safe", "混合精度安全标记", "未来控制 GPU 半精度"),
        ],
        [1650, 3000, 4710],
    )
    add_heading(doc, "9.2 公式零框架依赖", 2)
    add_code(
        doc,
        """IndexDefinition(
    id="ndvi",
    required_bands=("nir", "red"),
    expression=lambda xp, b, p:
        safe_divide(xp, b["nir"] - b["red"], b["nir"] + b["red"]),
)"""
    )
    add_para(
        doc,
        "`xp` 是数组 API：NumPy 引擎传 `numpy`，Torch 引擎传 `TorchArrayAPI`。公式不导入 Rasterio、"
        "FastAPI、Celery 或 MinIO，因此可以独立单元测试，也能新增 CuPy 等后端。"
    )
    add_heading(doc, "9.3 safe_divide 的意义", 2)
    add_para(
        doc,
        "遥感指数分母可能接近 0。直接相除会产生无穷值并污染统计。`safe_divide` 使用 `xp.where` 把绝对值"
        "小于 epsilon 的分母替换为 epsilon，使 NumPy 与 PyTorch 保持一致。随后 `sanitize_result` 再把"
        "残余 NaN/Inf 转为统一 nodata。"
    )
    add_heading(doc, "9.4 新增指数的标准步骤", 2)
    add_steps(
        doc,
        [
            "在 `INDEX_DEFINITIONS` 增加一个 `IndexDefinition`。",
            "使用逻辑波段名，不写物理波段号。",
            "所有除法使用 `safe_divide`，平方根使用 `maximum(..., 0)` 防止负数。",
            "补齐 formula、description、range、categories、tags 和 limitations。",
            "在固定数组测试中验证数值有限，并验证 NumPy/Joblib/Torch 一致性。",
            "前端无需新增公式代码，重新加载 `/api/indices` 即可展示。",
        ],
    )

    add_heading(doc, "10. 多计算引擎设计", 1)
    add_table(
        doc,
        ["引擎", "实现", "适用场景", "并行/设备", "失败策略"],
        [
            ("NumPy", "NumpyEngine", "小影像、同步、正确性基线", "CPU 顺序", "直接抛出输入错误"),
            ("Joblib", "JoblibEngine", "多指数、中大型 CPU", "线程并行指数", "缺少 joblib 时回退 NumPy"),
            ("PyTorch", "TorchEngine", "大影像、多指数、CUDA", "GPU inference_mode", "导入/CUDA/运行失败回退 Joblib"),
        ],
        [1200, 1700, 2300, 1900, 2260],
    )
    add_heading(doc, "10.1 为什么 Joblib 并行指数而不是并行写文件", 2)
    add_para(
        doc,
        "同一窗口已在主线程读入内存。Joblib 并行执行多个指数公式，能够复用波段数组；计算完成后由"
        "RasterPipeline 顺序写入不同输出文件。这样避免多个线程同时操作 Rasterio writer 的线程安全风险。"
    )
    add_heading(doc, "10.2 TorchArrayAPI 的作用", 2)
    add_para(
        doc,
        "注册表表达式需要 `abs/sqrt/sign/where/maximum` 等统一接口。PyTorch 对标量和张量的处理与 NumPy"
        "略有差异，因此 `TorchArrayAPI` 做轻量适配，让公式本身无需出现 `torch.*` 分支。"
    )
    add_heading(doc, "10.3 为什么 GPU 不一定更快", 2)
    add_para(
        doc,
        "小窗口的主机到显存拷贝、张量构造和结果回传可能比公式计算更耗时。因此自动规划器只在像元规模大、"
        "指数数量多且 CUDA 可用时选择 Torch。实际阈值应由 `backend/scripts/benchmark.py` 在目标机器校准。"
    )

    add_heading(doc, "11. 自动引擎选择", 1)
    add_para(
        doc,
        "`ExecutionPlanner.choose` 接收宽、高、波段数、指数数、请求引擎和是否同步，输出请求引擎、实际选择、"
        "原因和估算内存。显式指定 numpy/joblib/torch 时尊重用户选择；auto 才使用阈值。"
    )
    add_bullets(
        doc,
        [
            "同步或小于约 200 万像元：优先 NumPy，启动成本最低。",
            "大于约 2000 万像元、至少 4 个指数且 CUDA 可用：选择 Torch。",
            "其他中大型任务：选择 Joblib。",
            "请求 Torch 但 CUDA 不可用：执行阶段由 TorchEngine 记录原因并回退。",
            "响应和 manifest 同时记录 selectedEngine 与 actualEngine，避免把“计划使用”误当“实际使用”。",
        ],
    )

    add_heading(doc, "12. Rasterio 分块计算完整设计", 1)
    add_callout(
        doc,
        "一句话解释",
        "把整幅影像切成许多小 Window；每次只读取当前窗口所需波段，计算全部指数后立即写回对应位置，"
        "因此峰值内存由块大小决定，而不是由整幅影像决定。",
        PALE_GREEN,
    )
    add_heading(doc, "12.1 为什么需要分块", 2)
    add_para(
        doc,
        "假设一幅 20000×20000、7 波段、float32 影像，整幅读入约需 10.4 GiB，另加多个指数输出和中间数组"
        "很容易超过内存。若块大小为 1024×1024，一个波段约 4 MiB，7 波段约 28 MiB；即使同时保留多个"
        "结果，内存仍处于可控范围。"
    )
    add_heading(doc, "12.2 窗口生成", 2)
    add_code(
        doc,
        """for row in range(0, source.height, block_size):
    for column in range(0, source.width, block_size):
        Window(
            column,
            row,
            min(block_size, source.width - column),
            min(block_size, source.height - row),
        )"""
    )
    add_para(
        doc,
        "右边和下边最后一个窗口通常不足完整块，`min` 保证窗口不会越界。窗口的 row/column offset 保证"
        "写出时回到与源影像完全相同的像元位置。"
    )
    add_heading(doc, "12.3 必需波段并集与共享读取", 2)
    add_para(
        doc,
        "先对所有指数的 `required_bands` 求并集。例如 NDVI、EVI、GNDVI 同时执行时，只需读取 blue、green、"
        "red、nir 四个逻辑波段；不是每个指数分别读取。共享读取是多指数批处理最重要的 I/O 优化。"
    )
    add_heading(doc, "12.4 nodata 与 mask 处理", 2)
    add_steps(
        doc,
        [
            "使用 `source.read_masks` 获取 Rasterio 有效性掩膜。",
            "若源影像声明 nodata，再用 `np.isclose` 合并显式 nodata。",
            "计算前把无效像元改为 NaN，让三种引擎遵循同一语义。",
            "全部必需波段掩膜做逻辑或：任一必需波段无效，该像元所有相关指数无效。",
            "写出前把无效像元设为固定 -9999，统计时排除该值。",
        ],
    )
    add_heading(doc, "12.5 计算块与 GeoTIFF 写块", 2)
    add_para(
        doc,
        "请求 blockSize 被限制在 128~2048。计算窗口可以使用任意该范围整数；但 tiled GeoTIFF 的 blockxsize/"
        "blockysize 要满足 16 的倍数，因此不满足时写块回退 1024。计算块和存储块是两个概念：前者控制"
        "运行内存和进度，后者影响文件内部组织和读取性能。"
    )
    add_heading(doc, "12.6 顺序写出与空间信息保持", 2)
    add_para(
        doc,
        "输出 profile 从源 profile 复制，只修改 driver、count、dtype、nodata、压缩和分块参数，因此 CRS、"
        "transform、width、height 保持不变。每个指数拥有独立 writer，当前窗口计算后写入相同 Window。"
    )
    add_heading(doc, "12.7 进度、取消和资源清理", 2)
    add_para(
        doc,
        "窗口总数在执行前已知，进度为 `current/len(windows)`。每个窗口前检查 `is_cancelled`；无论成功、"
        "失败还是取消，`finally` 都关闭所有 writer，防止文件句柄泄漏和损坏。"
    )
    add_heading(doc, "12.8 overview、统计、预览与 manifest", 2)
    add_table(
        doc,
        ["产物", "生成方式", "用途"],
        [
            ("GeoTIFF", "逐窗口写入 float32，DEFLATE + predictor", "精确结果与下载"),
            ("内部 overview", "2/4/8/16 average", "地图缩放快速读取"),
            ("PNG 预览", "百分位拉伸与色带", "列表和无瓦片时占位"),
            ("statistics", "有效像元 min/max/mean/std/histogram", "图表和 Agent 解释"),
            ("manifest.json", "输入哈希、参数、引擎、回退、环境、产品", "复现和审计"),
            ("MinIO 对象", "可用时上传输出和预览", "跨服务访问"),
        ],
        [1700, 3400, 4260],
    )
    add_heading(doc, "12.9 当前实现与进一步优化", 2)
    add_bullets(
        doc,
        [
            "当前实现先构造全部 Window 列表，超大影像可进一步改为生成器以降低列表开销。",
            "当前统计阶段会读取整个单波段结果；超大结果可改为在线累计统计与分块直方图。",
            "当前 Joblib 并行的是窗口内多个指数；未来可建立读取-计算-写入有界流水队列。",
            "Torch 当前按窗口迁移 GPU；未来可把连续窗口组成 batch，并按显存动态缩放 batch size。",
            "结果可进一步转换为严格 COG，并接入 TiTiler/STAC。",
        ],
    )

    add_heading(doc, "13. 资产、瓦片、统计和溯源产物", 1)
    add_heading(doc, "13.1 影像检查与传感器补全", 2)
    add_para(
        doc,
        "`inspect_raster` 返回尺寸、CRS、bounds、nodata、波段描述、波长和 overview。GeoTIFF 自带描述和"
        "波长优先；GF01、LAD08/LAD09、SHB02 文件名前缀配置只在元数据缺失且波段数匹配时补全。"
    )
    add_heading(doc, "13.2 动态瓦片", 2)
    add_para(
        doc,
        "`/api/tiles/{z}/{x}/{y}.png` 把 Web Mercator 瓦片范围转换到影像 CRS，只读取当前瓦片覆盖区域；"
        "单波段结果使用拉伸色带，多波段源影像选择显示波段生成 RGB。缓存键包含文件修改时间，文件更新后自动失效。"
    )
    add_heading(doc, "13.3 路径安全", 2)
    add_para(
        doc,
        "对象键和本地路径最终必须解析到受允许的数据目录。接口不直接信任用户输入的任意文件系统路径。"
        "这是防止目录穿越和读取服务器敏感文件的基础边界。"
    )

    add_heading(doc, "14. 异步任务、Celery、Redis 与取消", 1)
    add_heading(doc, "14.1 JobRecord 状态模型", 2)
    add_bullets(
        doc,
        [
            "accepted：已接收、尚未开始。",
            "running：正在处理，包含 current/total/message。",
            "successful：结果可从 record.result 或 results 接口读取。",
            "failed：保存错误文本和结束时间。",
            "dismissed：任务被取消或撤销。",
        ],
    )
    add_heading(doc, "14.2 本地与部署模式统一", 2)
    add_para(
        doc,
        "开发模式使用 ThreadPoolExecutor，便于不启动 Redis/Celery 也能演示异步接口；部署模式调用"
        "`celery_app.send_task`。两者共享 `RasterTask`、`JobRecord` 和 `RasterPipeline`，减少环境差异。"
    )
    add_heading(doc, "14.3 优先级", 2)
    add_para(
        doc,
        "请求 priority 为 1~5。Celery 配置五级队列并启用优先级参数；本地线程池不具备严格队列优先级语义，"
        "因此答辩时应说明“接口与部署队列支持优先级，本地轻量模式主要用于开发”。"
    )

    add_heading(doc, "15. 智能分析 Agent 的实现与安全边界", 1)
    add_heading(doc, "15.1 Agent 不是直接执行器", 2)
    add_code(
        doc,
        """用户问题
→ 创建/恢复会话
→ 注册表与外部知识 RAG
→ 可选网络检索
→ 可选 LLM 意图分类
→ 确定性规则选择候选指数
→ 检查当前波段是否可执行
→ 生成执行单（awaiting_confirmation）
→ 用户编辑并确认
→ 后端二次校验
→ 提交 JobManager"""
    )
    add_heading(doc, "15.2 推荐依据", 2)
    add_bullets(
        doc,
        [
            "IntentRule：长势、稀疏植被、叶绿素、胁迫、变化等稳定任务模板。",
            "INDEX_REGISTRY：公式、波段、标签、限制，是推荐事实源。",
            "Knowledge Store：内存/PostgreSQL 外部知识，按词项评分召回。",
            "Web Search：可选增强，失败时降级本地知识。",
            "LLM：可选意图分类，不直接生成可执行 Python 或存储路径。",
        ],
    )
    add_heading(doc, "15.3 三道执行安全门", 2)
    add_steps(
        doc,
        [
            "计划阶段：缺少波段的指数标记 executable=false，不进入 selectedIndices。",
            "确认阶段：用户提交的 indices 必须是允许集合子集，否则 422。",
            "任务阶段：再次打开源影像，检查波段号在 1~source.count 范围内。",
        ],
    )
    add_heading(doc, "15.4 自定义指数安全", 2)
    add_para(
        doc,
        "表达式先由 `SafeExpressionValidator` 检查 AST，只允许算术、白名单函数和已声明波段；禁止属性访问、"
        "下标逃逸、导入和任意函数调用。随后用小型探针数组试算，确认输出形状、范围和有限性，才加入注册表。"
    )

    add_heading(doc, "16. Vue 前端各层实现", 1)
    add_table(
        doc,
        ["文件/组件", "主要职责", "关键状态/交互"],
        [
            ("App.vue", "根编排与轮询", "系统刷新、任务刷新、面板切换"),
            ("workspace.ts", "单一状态源", "asset、bands、indices、jobs、result、panel"),
            ("usePlatformApi.ts", "REST/SSE 客户端", "JSON、XHR 上传进度、SSE 帧解析"),
            ("AssetToolbar.vue", "上传和波段映射", "拖拽、overview、逻辑波段、批量提交"),
            ("IndexCatalog.vue", "指数目录", "分类、搜索、公式 token 与分式排版"),
            ("MapWorkspace.vue", "地图图层", "天地图、源 TIF、结果瓦片、定位、对比"),
            ("JobProgressPanel.vue", "任务中心", "状态、ETA、吞吐、产品和取消"),
            ("StatisticsDashboard.vue", "统计图表", "ECharts 生命周期和产品切换"),
            ("AgentDrawer.vue", "Agent 交互", "会话、SSE 思考、执行单、确认和解释"),
        ],
        [2100, 3100, 4160],
    )
    add_heading(doc, "16.1 为什么 Pinia 是单一状态源", 2)
    add_para(
        doc,
        "上传组件、地图、任务面板、统计和 Agent 都需要共享当前资产、波段映射和活动结果。若各组件分别保存，"
        "很容易出现地图展示 A 结果、统计却读取 B 结果。`workspace.ts` 集中维护并用 computed 派生活动产品。"
    )
    add_heading(doc, "16.2 SSE 解析", 2)
    add_para(
        doc,
        "`requestStream` 从 ReadableStream 累积文本，按空行拆分 SSE frame，`parseSseFrame` 读取 event/data。"
        "AgentDrawer 根据 thought/status/plan/job/result/error/done 更新不同 UI 状态，并用队列控制思考动画节奏。"
    )
    add_heading(doc, "16.3 地图稳定性设计", 2)
    add_bullets(
        doc,
        [
            "`mapWhenStyleReady` 防止 style 尚未加载时调用 addLayer。",
            "源影像使用 preview、范围和动态瓦片多级兜底，避免上传后出现空白。",
            "图层顺序固定为范围、源影像、结果，避免分析层被底图覆盖。",
            "自动定位只对新资产触发，用户手动浏览后不反复抢夺视角。",
            "瓦片 URL 使用 objectKey，避免浏览器直接访问服务器本地路径。",
        ],
    )

    add_heading(doc, "17. 部署、配置、测试与常见问题", 1)
    add_heading(doc, "17.1 Docker Compose 组件", 2)
    add_bullets(
        doc,
        [
            "API/OGC 服务实例：承载 HTTP 和 Process 能力。",
            "Celery Worker：执行长时间栅格任务。",
            "Redis：broker 与结果后端。",
            "MinIO：影像和结果工件。",
            "Nacos：服务注册与发现。",
            "Nacos Bridge：把健康实例转换成 Traefik 动态配置。",
            "Traefik：统一网关和负载均衡。",
            "Vue/Nginx：前端静态资源和反向代理。",
        ],
    )
    add_heading(doc, "17.2 质量检查命令", 2)
    add_code(
        doc,
        r"""cd backend
D:\miniconda\envs\giskeshe\python.exe -m ruff check .
D:\miniconda\envs\giskeshe\python.exe -m pytest -q

cd ..\frontend
npm run build"""
    )
    add_heading(doc, "17.3 测试覆盖地图", 2)
    add_table(
        doc,
        ["测试文件", "覆盖重点"],
        [
            ("test_indices.py", "注册表数量、NDVI 手算、有限值、Joblib/Torch 一致性"),
            ("test_raster_pipeline.py", "分块输出尺寸、CRS、transform 和产品结构"),
            ("test_assets.py", "overview 构建复用、传感器配置、元数据保护"),
            ("test_api.py", "健康、Process、上传、瓦片、异步、Agent 和能力接口"),
            ("test_agent.py", "推荐、缺波段阻断、确认、RAG、自定义指数"),
            ("test_advanced_analysis.py", "AST 白名单、变化检测、GeoJSON 统计"),
        ],
        [2700, 6660],
    )
    add_heading(doc, "17.4 常见问题", 2)
    add_table(
        doc,
        ["现象", "优先检查", "原因/处理"],
        [
            ("后端启动失败", "是否使用 giskeshe Python", "Rasterio/GDAL/Pydantic 版本必须来自固定环境"),
            ("地图无底图", "VITE_TIANDITU_TOKEN", "无令牌时使用兜底底图或检查网络"),
            ("指数不可执行", "requiredBands 与 bands", "逻辑波段缺失或物理波段号越界"),
            ("Torch 实际变 Joblib", "fallbackReasons", "CUDA 不可用、导入失败或运行失败"),
            ("任务一直 accepted", "Redis/Worker/eager", "部署队列未启动或本地模式配置不一致"),
            ("结果瓦片空白", "objectKey、bounds、CRS、overview", "路径、投影或数据范围问题"),
            ("Swagger 上传报 422", "文件类型和 multipart", "只接受可保存并由 Rasterio 打开的影像"),
        ],
        [2100, 2400, 4860],
    )

    add_heading(doc, "18. 汇报演示脚本与高频答辩问答", 1)
    add_heading(doc, "18.1 8 分钟演示顺序", 2)
    add_steps(
        doc,
        [
            "用 30 秒说明统一注册表、分块流水线、三引擎、OGC 服务和 Vue 工作台。",
            "打开 `/docs`，展示 `/api/indices/ndvi` 与 `/api/system/capabilities`。",
            "上传或选择 GeoTIFF，解释逻辑波段映射。",
            "选择 NDVI/EVI/GNDVI，提交异步任务，展示 jobID 和窗口进度。",
            "切换地图结果和统计图，指出实际引擎、统计和 manifest。",
            "在 Agent 输入“找长势不好的区域”，展示推荐、缺波段阻断和确认按钮。",
            "打开 `indices.py`、`raster_pipeline.py` 和 `routes.py`，对应讲公式、分块和接口。",
            "最后说明 CUDA/容器等环境边界与后续优化。",
        ],
    )
    add_heading(doc, "18.2 高频问题与回答", 2)
    questions = [
        ("为什么不用一个函数写完？", "公式、I/O、协议、任务和 UI 的变化原因不同。分层后每层可独立测试，新增接口或引擎不需要复制公式。"),
        ("35 个指数为什么只维护一份？", "IndexDefinition 把公式表达式参数化为 xp；NumPy 和 Torch 只替换数组 API。"),
        ("波段映射为什么用 red/nir 而不是 3/4？", "物理波段号随传感器变化，逻辑波段让公式保持传感器无关。"),
        ("分块后结果会不会有拼接缝？", "指数是逐像元运算，不依赖邻域；Window 写回原位置，不会产生边界缝。"),
        ("块越小越好吗？", "不是。太小会增加 Rasterio 调用、调度和写入次数；太大增加内存和 GPU 显存。"),
        ("为什么默认 1024？", "它在 I/O 次数和内存之间较均衡，并满足 GeoTIFF 分块的 16 倍数要求。"),
        ("为什么掩膜做逻辑或？", "任一必需波段无效，该像元的公式输入就不完整，结果应统一为 nodata。"),
        ("如何保证三引擎一致？", "同一 expression、统一 safe_divide/sanitize_result，并用固定数组比较。"),
        ("Torch 失败怎么办？", "TorchEngine 捕获导入、CUDA 和运行异常，回退 Joblib，并记录 fallbackReason。"),
        ("为什么 Joblib 用线程？", "NumPy 核心运算通常释放 GIL，线程可共享窗口数组，避免进程复制大数组。"),
        ("同步和异步是否两套算法？", "不是。区别只在调用 JobManager 的 execute_sync 或 submit，最终都进入 RasterPipeline。"),
        ("如何取消任务？", "JobManager 设置取消状态/撤销 Celery；流水线每个窗口前检查取消回调并在 finally 关闭 writer。"),
        ("pygeoapi 和 FastAPI 有什么区别？", "pygeoapi 是标准 OGC 框架入口；FastAPI 是综合平台入口，包含上传、Agent、瓦片等扩展。"),
        ("为什么只写一个 Processor？", "请求 index 动态查注册表，避免 35 个类和 YAML 重复。"),
        ("接口文档在哪里？", "FastAPI 为 /docs、/redoc、/openapi.json；pygeoapi 为 Landing Page 和 /openapi.json。"),
        ("如何防止自定义公式执行恶意代码？", "使用 AST 白名单，只允许指定名称、算术节点和函数，再用探针数组试算。"),
        ("Agent 会不会自己执行？", "不会。计划状态为 awaiting_confirmation，确认接口还会二次验证可执行指数和波段。"),
        ("RAG 的知识从哪里来？", "内置注册表、用户导入知识、PostgreSQL 持久知识和可选网络检索。"),
        ("为什么需要 manifest？", "记录输入哈希、参数、引擎、回退、环境和输出，使结果可复现、可审计。"),
        ("overview 会改变计算精度吗？", "不会。overview 只是主波段的低分辨率浏览层，计算和下载仍用全分辨率数据。"),
        ("统计为什么排除 -9999？", "它是统一输出 nodata，不代表真实指数值；纳入会严重扭曲均值和直方图。"),
        ("MinIO 不可用怎么办？", "核心结果先写本地；上传适配返回空对象键，接口仍保留本地路径供开发。"),
        ("Nacos 为什么还需要 Bridge？", "Traefik 没有直接使用本项目 Nacos 信息的原生链路，Bridge 把实例转换成 File Provider 配置。"),
        ("当前最大性能瓶颈？", "通常是磁盘读取、结果写出和全量统计，不一定是公式本身。"),
        ("下一步最值得优化什么？", "流式窗口生成、在线统计、GPU batch、严格 COG/TiTiler、基准反馈自动规划器。"),
        ("如何证明没有整幅读入？", "核心计算只在窗口循环中调用 source.read(window=window)；整幅读取只在可选统计阶段读取单个结果波段。"),
        ("统计阶段仍可能占内存吗？", "是。当前 `dataset.read(1)` 会读单个结果全幅；这是已明确的后续在线统计优化点。"),
        ("为什么前端不计算 NDVI？", "浏览器不适合处理大 GeoTIFF；后端统一保证投影、nodata、分块和可复现性。"),
        ("为什么用 Pinia？", "地图、任务、Agent 和统计共享状态，单一 store 防止多个组件状态不一致。"),
        ("如何处理传感器差异？", "优先读取影像元数据；必要时按文件名前缀和波段数补全，再由用户确认逻辑映射。"),
    ]
    for question, answer in questions:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(5)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        q = p.add_run(f"问：{question}")
        set_run_font(q, bold=True, color=DARK_BLUE)
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.22)
        a = p.add_run(f"答：{answer}")
        set_run_font(a)

    add_heading(doc, "18.3 最后一分钟总结模板", 2)
    add_callout(
        doc,
        "可直接口述",
        "这个项目的核心不是单独写出 NDVI，而是把 35 个指数抽象成统一注册表，再通过分块流水线、"
        "多引擎、标准接口和可视化工作台形成完整系统。公式层与框架解耦，FastAPI、Celery 和 pygeoapi"
        "最终复用同一套 RasterPipeline；Agent 只负责规划并受确认机制约束。当前实现已具备完整演示链路，"
        "后续重点是目标硬件基准、在线统计和更标准的 COG 服务。",
        PALE_GREEN,
    )


def add_source_appendix(doc: Document) -> None:
    """写入横向源码清单。"""
    add_wide_section(doc)
    add_heading(doc, "5. 全部源代码清单", 1)
    add_para(
        doc,
        "下表由生成脚本扫描当前仓库得到，包含全部自有 Python、Vue、TypeScript、CSS 源文件和关键部署配置。"
        "行数用于汇报定位，不是质量指标。"
    )
    rows = source_inventory()
    add_table(
        doc,
        ["层", "相对路径", "行数", "职责"],
        rows,
        [1450, 4300, 700, 7950],
        font_size=7.3,
    )
    add_portrait_section(doc)


def add_api_appendix(doc: Document) -> None:
    """写入 FastAPI 全路由表。"""
    add_wide_section(doc)
    add_heading(doc, "附录 A. FastAPI 全接口表", 1)
    rows = route_inventory()
    add_para(doc, f"当前从 `backend/app/api/routes.py` 自动提取 {len(rows)} 个接口。")
    add_table(
        doc,
        ["方法", "路径", "处理函数", "职责"],
        rows,
        [900, 3900, 2500, 7100],
        font_size=7.5,
    )


def add_index_appendix(doc: Document) -> None:
    """写入 35 个指数表。"""
    doc.add_page_break()
    add_heading(doc, "附录 B. 35 个植被指数注册表", 1)
    rows = index_inventory()
    add_para(doc, f"当前统一注册表共 {len(rows)} 个内置指数。公式文本用于展示，实际计算使用 expression。")
    add_table(
        doc,
        ["ID", "中文名", "公式", "所需逻辑波段", "分类"],
        rows,
        [900, 2600, 5300, 2800, 2800],
        font_size=7.2,
    )
    add_portrait_section(doc)


def add_sources(doc: Document) -> None:
    """添加实现依据和官方参考。"""
    add_heading(doc, "参考与事实来源", 1)
    add_bullets(
        doc,
        [
            "项目任务书：docx/植被指数提取算法封装与Web服务实现实习任务书.docx。",
            "当前源码：backend/app/、backend/tests/、frontend/src/、infra/、compose.yml。",
            "pygeoapi 官方文档：OGC API - Processes、插件开发、运行方式与 OpenAPI 页面。",
            "接口和指数附录由本生成脚本从当前源码自动提取，避免手工清单漂移。",
        ],
    )
    add_callout(
        doc,
        "时效说明",
        "本手册生成日期见封面。若后续新增接口、指数或文件，请重新运行 build_handbook.py 并重新做 DOCX 渲染检查。",
    )


def main() -> None:
    """生成完整主手册。"""
    doc = Document()
    configure_styles(doc)
    for section in doc.sections:
        configure_header_footer(section)
    add_title(doc, "植被指数智能分析平台", "源代码清单、目录设计、模块划分、接口与分层实现主手册")
    add_contents(doc)
    build_manual(doc)
    add_api_appendix(doc)
    add_index_appendix(doc)
    add_sources(doc)

    core = doc.core_properties
    core.title = "植被指数智能分析平台源代码与实现主手册"
    core.subject = "程序设计实习汇报、代码导读与答辩手册"
    core.author = "植被指数智能分析平台项目组"
    core.keywords = "植被指数, Rasterio, FastAPI, pygeoapi, Vue, 分块计算, OGC API Processes"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
