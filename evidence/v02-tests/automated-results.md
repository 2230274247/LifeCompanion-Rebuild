# V0.2 自动化测试结果摘录

仅摘录结果，原始运行日志位于忽略目录 infra/runtime；重复复验不重复计数。

## pytest-v02.txt

```text
16 passed, 1 warning in 4.21s
```

## gateway-tests-v02.txt

```text
1..1
# tests 1
# pass 1
# fail 0
# duration_ms 612.4956
```

## jest-v02.txt

```text
PASS src/hooks/Messages/__tests__/useMessageScrolling.spec.tsx (153.298 s, 681 MB heap size)
PASS src/routes/__tests__/ChatRoute.spec.tsx (714 MB heap size)
PASS src/components/Life/__tests__/Memories.spec.tsx (769 MB heap size)
PASS src/components/Chat/Input/__tests__/submit.spec.ts (774 MB heap size)
PASS src/hooks/Input/useComposerBindings.spec.tsx (6.41 s, 847 MB heap size)
Test Suites: 5 passed, 5 total
Tests:       36 passed, 36 total
Snapshots:   0 total
Time:        174.973 s
Ran all test suites matching src/components/Life/__tests__/Memories.spec.tsx|src/routes/__tests__/ChatRoute.spec.tsx|src/components/Chat/Input/__tests__/submit.spec.ts|src/hooks/Input/useComposerBindings.spec.tsx|src/hooks/Messages/__tests__/useMessageScrolling.spec.tsx.
```

## jest-ime-v02.txt

```text
PASS src/utils/shortcuts.spec.ts (77 MB heap size)
Test Suites: 1 passed, 1 total
Tests:       54 passed, 54 total
Snapshots:   0 total
Time:        12.51 s
Ran all test suites matching src/utils/shortcuts.spec.ts.
```

## jest-life-final-v02.txt

```text
PASS src/components/Life/__tests__/Memories.spec.tsx (13.181 s, 204 MB heap size)
Test Suites: 1 passed, 1 total
Tests:       4 passed, 4 total
Snapshots:   0 total
Time:        18.57 s
Ran all test suites matching src/components/Life/__tests__/Memories.spec.tsx.
```

## jest-sidebar-final-v02.txt

```text
PASS src/components/UnifiedSidebar/__tests__/ExpandedPanel.spec.tsx (24.364 s, 311 MB heap size)
PASS src/components/UnifiedSidebar/mobile/__tests__/Header.spec.tsx (358 MB heap size)
PASS src/hooks/Nav/__tests__/useSidebarToggle.spec.tsx (421 MB heap size)
Test Suites: 3 passed, 3 total
Tests:       25 passed, 25 total
Snapshots:   0 total
Time:        37.653 s
Ran all test suites within paths "src/components/UnifiedSidebar/mobile/__tests__/Header.spec.tsx", "src/components/UnifiedSidebar/__tests__/ExpandedPanel.spec.tsx", "src/hooks/Nav/__tests__/useSidebarToggle.spec.tsx".
```
