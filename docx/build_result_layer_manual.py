# docx/build_result_layer_manual.py
# 文件说明：生成结果图层缩放优化用户手册。
# 主要职责：把真实网页截图、操作步骤和维护说明写入 Word 文档。
# 依赖边界：只读取 output/playwright 截图，不启动前后端服务。

"""生成“结果图层缩放与浏览用户手册”DOCX。"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docx" / "结果图层缩放与浏览用户手册.docx"
SCREENSHOTS = {
    "upload": ROOT / "output" / "playwright" / "result-layer-manual-01-upload.png",
    "dialog": ROOT / "output" / "playwright" / "result-layer-manual-02-index-dialog.png",
    "result": ROOT / "output" / "playwright" / "result-layer-manual-03-result-map.png",
    "high_zoom": ROOT / "output" / "playwright" / "result-layer-manual-04-high-zoom.png",
}


def set_run_font(run, name: str = "Microsoft YaHei") -> None:
    """设置中英文渲染都稳定的字体。"""
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:ascii"), name)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), name)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def set_cell_shading(cell, fill: str) -> None:
    """给表格单元格设置背景色。"""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_text(cell, text: str, bold: bool = False) -> None:
    """写入单元格文本并统一格式。"""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run)
    run.font.size = Pt(9.5)
    run.bold = bold
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def configure_styles(doc: Document) -> None:
    """按 compact_reference_guide 预设配置页面、正文和标题样式。"""
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = doc.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for style_name, size, color in [
        ("Heading 1", 16, RGBColor(46, 116, 181)),
        ("Heading 2", 13, RGBColor(46, 116, 181)),
        ("Heading 3", 12, RGBColor(31, 77, 120)),
    ]:
        style = doc.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(10 if style_name == "Heading 3" else 14)
        style.paragraph_format.space_after = Pt(7 if style_name != "Heading 3" else 5)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run("结果图层缩放与浏览用户手册 | 2026-07-02")
    set_run_font(run)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(85, 85, 85)


def add_title(doc: Document) -> None:
    """写入封面标题和摘要。"""
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(3)
    run = title.add_run("结果图层缩放与浏览用户手册")
    set_run_font(run)
    run.font.size = Pt(26)
    run.bold = True
    run.font.color.rgb = RGBColor(11, 37, 69)

    subtitle = doc.add_paragraph()
    run = subtitle.add_run("植被指数智能分析平台 · 地图结果图层操作指南")
    set_run_font(run)
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(85, 85, 85)

    summary = doc.add_paragraph()
    summary.add_run(
        "本手册面向平台使用者，说明如何打开计算结果图层、定位结果范围、在高缩放级别浏览细节，"
        "以及如何通过图层面板判断当前是动态瓦片加载还是平滑放大浏览。"
    )
    for run in summary.runs:
        set_run_font(run)


def add_fact_table(doc: Document) -> None:
    """写入优化说明表。"""
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.autofit = False
    widths = [Inches(1.55), Inches(2.45), Inches(2.3)]
    headers = ["场景", "优化后表现", "用户判断方式"]
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.width = widths[index]
        set_cell_shading(cell, "E8EEF5")
        set_cell_text(cell, header, bold=True)
    rows = [
        ("常规缩放", "结果图层按 TIF 动态瓦片加载，保留 GeoTIFF 空间参考。", "图层面板显示“结果 TIF 瓦片”。"),
        ("16 级以上", "不再继续请求更高等级动态瓦片，直接复用 16 级瓦片平滑放大。", "图层面板显示“16级后平滑放大”。"),
        ("重复查看", "浏览器缓存瓦片响应，来回缩放和切换视角更顺滑。", "同一视角再次打开时等待明显减少。"),
    ]
    for row in rows:
        cells = table.add_row().cells
        for index, text in enumerate(row):
            cells[index].width = widths[index]
            set_cell_text(cells[index], text)


def add_screenshot(doc: Document, key: str, caption: str) -> None:
    """插入截图和图注。"""
    path = SCREENSHOTS[key]
    if not path.is_file():
        raise FileNotFoundError(path)
    doc.add_picture(str(path), width=Inches(6.25))
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(caption)
    set_run_font(run)
    run.font.size = Pt(9)
    run.italic = True
    run.font.color.rgb = RGBColor(85, 85, 85)


def add_steps(doc: Document) -> None:
    """写入操作步骤。"""
    doc.add_heading("一、打开结果图层", level=1)
    doc.add_paragraph("进入工作台后导入 GeoTIFF 影像。导入完成后，地图左侧图层面板会显示源影像状态，任务栏显示波段映射数量。")
    add_screenshot(doc, "upload", "图 1：导入影像后，地图工作区和图层面板进入可计算状态。")

    doc.add_paragraph("点击“植被指数提取”，在弹窗中选择需要计算的指数。默认会优先选择 NDVI；也可以搜索指数名称后选择当前可执行项。")
    add_screenshot(doc, "dialog", "图 2：在植被指数提取弹窗中选择 NDVI 并提交任务。")

    doc.add_heading("二、查看计算结果", level=1)
    doc.add_paragraph("任务完成后，在任务管理器点击“打开结果”。地图会切换到计算结果图层，可在左侧面板切换结果指数、显示模式和结果透明度。")
    add_screenshot(doc, "result", "图 3：结果图层叠加在遥感底图上，右下角颜色条显示当前指数取值范围。")

    doc.add_heading("三、高倍缩放浏览", level=1)
    doc.add_paragraph(
        "使用地图右侧缩放按钮或鼠标滚轮继续放大。16 级以上进入平滑放大模式：平台复用 16 级结果瓦片，"
        "避免高缩放级别反复触发后端重投影计算。此时仍可观察细节，但不会继续请求更高等级的动态 TIF 瓦片。"
    )
    add_screenshot(doc, "high_zoom", "图 4：18 级缩放时，面板显示“结果 TIF，16级后平滑放大”和“复用 16 级瓦片”。")


def add_troubleshooting(doc: Document) -> None:
    """写入常见问题。"""
    doc.add_heading("四、常见问题", level=1)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    widths = [Inches(2.05), Inches(4.25)]
    for index, header in enumerate(["现象", "处理方式"]):
        cell = table.rows[0].cells[index]
        cell.width = widths[index]
        set_cell_shading(cell, "E8EEF5")
        set_cell_text(cell, header, bold=True)
    rows = [
        ("结果图层未显示", "确认任务已经完成，并点击任务管理器中的“打开结果”；再检查图层面板里“计算结果”是否勾选。"),
        ("放大后底图提示无影像", "这是在线底图瓦片自身在该级别缺失，结果 TIF 图层仍会复用 16 级瓦片显示。"),
        ("颜色看不清", "调整“结果透明度”滑块，或切换到“计算后”模式只显示结果图层。"),
        ("定位不准确", "点击“计算结果”行右侧的“定位”，不要依赖滚轮手动寻找范围。"),
    ]
    for row in rows:
        cells = table.add_row().cells
        for index, text in enumerate(row):
            cells[index].width = widths[index]
            set_cell_text(cells[index], text)


def main() -> None:
    """构建 DOCX 文件。"""
    doc = Document()
    configure_styles(doc)
    add_title(doc)
    doc.add_heading("优化概览", level=1)
    add_fact_table(doc)
    add_steps(doc)
    add_troubleshooting(doc)
    doc.add_section(WD_SECTION.CONTINUOUS)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
