# zread 生成失败诊断（2026-06-24）

当前仓库 `D:\Users\24658\Desktop\软件工程\实习` 使用 zread 生成 wiki 时失败。根因不是仓库代码，而是 LLM provider 返回大量 `429 Too Many Requests`。

关键证据：
- 原始配置阶段：`workers=15 maxRetries=0`，47 个页面任务批量触发 429 并永久失败。
- 临时降并发验证阶段：曾将 `max_concurrent` 降为 2、`max_retries` 升为 2，仍触发 429，catalog/page 均有失败。
- 诊断期间发现 2 个残留 `zread.exe` 后台进程，已停止。
- `.zread/wiki/current` 指向 `versions/2026-06-24-162110`，`wiki.json` 有 47 个目录条目，但版本目录下 Markdown 页面数为 0，缺失 47 页，因此不是完整生成成功。
- 已恢复 zread 全局配置到原始值：`max_concurrent: 15`、`max_retries: 0`。
- 证据日志：`.evidence/active/20260624-1635-zread生成失败诊断.md`。

后续建议：等待限流窗口恢复；重新生成前避免残留 zread 进程；临时使用更保守配置如 `max_concurrent: 1`、`max_retries: 3`；若仍 429，需更换额度/限速更稳定的 LLM provider。