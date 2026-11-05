# 静态检查与构建

- `typecheck-frontend-final-v02.status`: frontend_typecheck_exit=0；文件最后写入时间 2026-11-02T19:24:13.669821+08:00
- `build-frontend-final-v02.status`: frontend_build_exit=0；文件最后写入时间 2026-11-02T19:23:36.162369+08:00
- `typecheck-provider-v02.log`: 无诊断输出；文件最后写入时间 2026-11-02T18:50:35.665653+08:00
- `lint-v02.log`: 无诊断输出；文件最后写入时间 2026-11-02T18:53:09.673990+08:00
- `lint-sidebar-final-v02.log`: 无诊断输出；文件最后写入时间 2026-11-02T19:21:57.903634+08:00
- 最终构建尾部：

```text
     │ 
     │ Help: Consider using indirect eval. For more information, check the documentation: https://rolldown.rs/guide/troubleshooting#avoiding-direct-eval
─────╯

[plugin builtin:vite-reporter] 
(!) Some chunks are larger than 1500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rolldownOptions.output.codeSplitting to improve chunking: https://rolldown.rs/reference/OutputOptions.codeSplitting
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.

PWA v1.3.0
mode      generateSW
precache  54 entries (13161.90 KiB)
files generated
  dist/sw.js
  dist/workbox-1b73dcc2.js
✓ built in 24.54s

```
- Lighthouse：默认真实 3080 冲突；独立 3098 的 Windows NODE_OPTIONS 路径分割失败。

```text
[WebServer] Error: Cannot find module 'H:\AI'
Error: Process from config.webServer was not able to start. Exit code: 1
```
