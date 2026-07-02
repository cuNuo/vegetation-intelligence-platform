# 代码注释与源代码实现主手册

## 一句话结论

- 2026-07-02 已完成项目根 `AGENTS.md` 中文化、全量前后端源码中文注释增强，并生成可直接用于汇报的 Word 主手册 `docx/植被指数智能分析平台源代码与实现主手册.docx`。

## 适用场景

- 明日汇报、代码答辩、快速解释源码目录、模块划分、接口设计、pygeoapi、植被指数注册表和 Rasterio 分块计算时读取。
- 后续新增接口、指数或重要源码文件后，需要重新生成主手册时读取。

## 首选入口

- 路径：`docx/植被指数智能分析平台源代码与实现主手册.docx`
- 关键文件：`docx/build_handbook.py`、`AGENTS.md`、`backend/app/core/indices.py`、`backend/app/services/raster_pipeline.py`、`backend/app/api/routes.py`
- 推荐起点：先读 Word 手册第 1、7、8、9、12、18 章，再按问题定位到对应源码文件。

## 稳定约束 / 正确做法

- 主手册由 `docx/build_handbook.py` 生成，源码清单、FastAPI 全接口表和 35 指数表自动从当前代码提取，避免手工漂移。
- 手册表格已按三线表风格生成，导出 PDF 并渲染 31 页 PNG 检查通过。
- 后端 Python、前端 Vue/TypeScript/CSS、`infra/pygeoapi/config.yml` 已补中文文件头；核心函数和复杂逻辑已补中文 docstring/JSDoc/行内设计注释。
- `AGENTS.md` 只保留项目入口、硬约束和路由规则；完整源码讲解放在 Word 主手册，不把项目入口膨胀成实现百科。
- 重新生成主手册后必须再做 DOCX 到 PDF/PNG 的渲染检查，确认三线表、横向附录、页眉页脚和分页没有破损。

## 常见误区

- 不要手工改 Word 正文后忘记同步 `docx/build_handbook.py`；否则下次生成会覆盖手工内容。
- 不要把 FastAPI `/docs` 和 pygeoapi Landing Page 混为一个入口：FastAPI 是综合平台入口，pygeoapi 是标准 OGC 框架入口。
- 不要把主手册中的 Docker/Nacos/MinIO/GPU 支持表述为本机已完整验证；本次验证重点是注释、文档和现有单元/构建检查。
- `.env.example` 在本次任务开始前已是删除状态，本次未恢复；若要容器演示，需先处理环境变量模板。

## 关联 evidence

- `.evidence/active/20260702-1957-代码注释与汇报主手册.md`
- `.evidence/docx-render/source-handbook/contact-1.png`
- `.evidence/docx-render/source-handbook/contact-2.png`
- `.evidence/docx-render/source-handbook/contact-3.png`
- `.evidence/docx-render/source-handbook/contact-4.png`

## 相关路由 / 文档

- `docx/植被指数智能分析平台源代码与实现主手册.docx`
- `docx/build_handbook.py`
- `AGENTS.md`

## 最后验证

- 时间：2026-07-02 20:33
- 验证人 / 来源：Codex；Ruff、pytest、Vite build、YAML 解析、Word PDF 导出、pypdfium2 PNG 渲染与人工全页 contact sheet 检查。
- 结果：Ruff 通过；后端 39 passed，1 个上游弃用警告；前端构建通过，保留既有大 chunk 警告；YAML 解析通过；DOCX 结构为 317 段落、19 表格、5 节、69 标题，31 页渲染检查通过。