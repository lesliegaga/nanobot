# LLM Wiki功能完整修复与增强计划

## TL;DR

> **目标**: 修复LLM Wiki功能的关键缺陷，实现完整的知识库能力
> 
> **核心问题**: Entities/Concepts提取失败、Query无法归档、安全性漏洞、Lint功能不完整
> 
> **技术方案**: 
> - 使用JSON格式替代脆弱字符串解析
> - 实现完整的知识综合与归档流程
> - 添加安全验证和性能优化
> - 全面测试覆盖（单元测试+真实用例）
> 
> **交付物**: 
> - 修复后的 `nanobot/agent/tools/wiki.py`
> - 新增测试文件 `tests/test_wiki*.py`
> - 真实用例测试数据与脚本
> - 更新后的配置模式
> 
> **预计工作量**: 3-5天
> **并行执行**: YES - 4个Wave
> **关键路径**: Wave 1 → Wave 2 → Wave 3 → Wave 4 → 最终验证

---

### Wave FINAL: Review & Delivery

- [x] F1. **Plan Compliance Audit** — `oracle`

  **What to do**:
  - 读取整个计划
  - 验证每个"Must Have"是否已实现:
    - 检查代码中是否包含安全验证
    - 检查JSON解析是否已实现
    - 检查Query归档功能
    - 检查实体综合更新
    - 检查Lint完整性
  - 验证每个"Must NOT Have"是否被遵守:
    - 检查CLI接口是否保持不变
    - 检查数据结构是否兼容
  - 检查测试覆盖率
  - 检查文档完整性

  **Output**: 
  ```
  Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT
  ```

  **Evidence**: `.sisyphus/evidence/final-f1-audit.txt`

- [x] F2. **Code Quality Review** — `unspecified-high`

  **What to do**:
  - 运行 `ruff check .`
  - 运行 `mypy nanobot/agent/tools/wiki.py`
  - 检查代码中的AI slop模式:
    - 过多的注释
    - 过度抽象
    - 泛型命名 (data/result/item/temp)
  - 检查类型注解完整性
  - 检查文档字符串质量

  **Output**:
  ```
  Ruff [PASS/FAIL] | MyPy [PASS/FAIL] | AI Slop [CLEAN/N issues] | VERDICT
  ```

  **Evidence**: `.sisyphus/evidence/final-f2-quality.txt`

- [x] F3. **Real Manual QA** — `unspecified-high`

  **What to do**:
  - 从干净状态开始
  - 执行完整的端到端测试:
    1. `nanobot wiki init`
    2. `nanobot wiki ingest <84KB_script>`
    3. 验证实体/概念提取
    4. `nanobot wiki query "技术指标" --save`
    5. 验证synthesis页面创建
    6. `nanobot wiki lint`
    7. 验证所有5项lint检查
  - 捕获所有证据（截图、输出文件）
  - 验证跨任务集成

  **Output**:
  ```
  Init [PASS] | Ingest [PASS] | Query [PASS] | Lint [PASS] | VERDICT
  ```

  **Evidence**: `.sisyphus/evidence/final-f3-qa/`

- [x] F4. **Scope Fidelity Check** — `deep`

  **What to do**:
  - 对比代码评审报告中的需求清单:
    - 检查每个P0问题是否修复
    - 检查每个P1问题是否修复
    - 检查每个P2功能是否实现
  - 对比原始需求文档 `docs/llm-wiki.md`
  - 检查是否有范围蔓延
  - 检查是否有遗漏的需求

  **Output**:
  ```
  P0 Fixed [N/N] | P1 Fixed [N/N] | P2 Done [N/N] | Requirements Met [%] | VERDICT
  ```

  **Evidence**: `.sisyphus/evidence/final-f4-scope.txt`

---

## Final Verification Wave

> **4 review agents run in PARALLEL. ALL must APPROVE.**
> **Wait for user's explicit "okay" before marking complete.**

**When all F1-F4 pass**:
1. 汇总所有审查结果
2. 呈现给用户
3. 获取明确确认
4. 标记计划完成

**If any rejection**:
1. 分析失败原因
2. 创建修复任务
3. 重新运行相关验证
4. 再次呈现结果

---

## Commit Strategy

### Commit分组

**Group 1 (Wave 1)**: Tasks 1-4
- `security(wiki): add path validation and file size limits`
- `refactor(wiki): extract magic numbers to constants and add LLM timeout`
- `feat(wiki): add JSON-based LLM interface with error handling`
- `test(wiki): add test infrastructure and fixtures`

**Group 2 (Wave 2)**: Tasks 5-8
- `fix(wiki): use JSON format for entity/concept extraction`
- `feat(wiki): add query result archival to syntheses`
- `feat(wiki): implement true knowledge synthesis for entity updates`
- `feat(wiki): populate index.md with real metadata`

**Group 3 (Wave 3)**: Tasks 9-12
- `feat(wiki): complete all 5 lint checks`
- `feat(wiki): auto-maintain backlinks across pages`
- `fix(wiki): add comprehensive error handling and logging`
- `perf(wiki): add caching and batch processing`

**Group 4 (Wave 4)**: Tasks 13-17
- `feat(wiki): implement schema-driven workflow`
- `test(wiki): add comprehensive unit tests`
- `test(wiki): add real-world data test suite`
- `config(wiki): add configurable parameters to schema`
- `chore(wiki): final verification and fixes`

### Pre-commit Hooks

每个commit前运行:
```bash
pytest tests/test_wiki*.py -x  # 快速测试
ruff check nanobot/agent/tools/wiki.py  # 代码检查
```

---

## Success Criteria

### 功能验证

```bash
# 1. 安全验证
pytest tests/test_wiki_security.py -v

# 2. 解析功能验证
pytest tests/test_wiki_parsing.py -v

# 3. Ingest流程验证
pytest tests/test_wiki_ingest.py -v

# 4. Query功能验证
pytest tests/test_wiki_query.py -v

# 5. 真实用例验证
pytest tests/test_wiki_real_data.py -v

# 6. 代码质量检查
ruff check nanobot/agent/tools/wiki.py
mypy nanobot/agent/tools/wiki.py

# 7. 覆盖率检查
pytest tests/test_wiki*.py --cov=nanobot.agent.tools.wiki --cov-report=term
```

### 最终验收标准

- [x] 所有P0问题修复并通过真实用例验证
- [x] 所有P1问题修复并通过安全测试
- [x] 单元测试覆盖率 ≥ 80%
- [x] 真实文档测试通过（提取率>80%）
- [x] 代码通过ruff和mypy检查
- [x] 所有TODO任务完成
- [x] F1-F4审查全部通过
- [x] 用户明确确认

### 性能指标

- [x] Ingest单个文件 < 30秒（包括LLM调用）
- [x] Query响应 < 10秒
- [x] Lint检查 < 5秒/页
- [x] 内存使用 < 500MB（处理50MB文件）

---

## Appendix: 关键代码片段参考

### JSON格式LLM Prompt

```python
SYSTEM_PROMPT_JSON = """Analyze the source document and respond ONLY with valid JSON.

Response format:
{
    "summary": "2-3 paragraph comprehensive summary",
    "claims": ["claim 1", "claim 2", ...],
    "entities": [
        {"name": "Entity Name", "description": "Brief description"}
    ],
    "concepts": [
        {"name": "Concept Name", "definition": "Brief definition"}
    ],
    "tags": ["tag1", "tag2", ...]
}

IMPORTANT: Respond ONLY with the JSON object, no other text."""
```

### 安全验证代码模板

```python
def _validate_source_path(self, source_path: str, allowed_roots: list[Path]) -> Path:
    """Validate that source path is within allowed directories."""
    source_file = Path(source_path).expanduser().resolve()
    if not any(source_file.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"Source path not in allowed directories: {source_path}")
    return source_file

def _validate_file_size(self, source_file: Path, max_size: int = 50 * 1024 * 1024) -> None:
    """Validate file size is within limit."""
    if source_file.stat().st_size > max_size:
        raise ValueError(f"Source file too large: {source_file} ({source_file.stat().st_size} bytes)")
```

### Query归档代码模板

```python
async def _save_synthesis(
    self, 
    wiki_root: Path, 
    query: str, 
    answer: str, 
    sources: list[str]
) -> Path:
    """Save query result as a synthesis page."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query_slug = self._sanitize_filename(query)[:50]  # Limit length
    
    synthesis_file = wiki_root / "pages" / "syntheses" / f"synthesis_{timestamp}_{query_slug}.md"
    
    frontmatter = {
        "title": f"Synthesis: {query[:100]}",
        "type": "synthesis",
        "query": query,
        "created": datetime.now().isoformat(),
        "sources_referenced": sources
    }
    
    content = self._write_frontmatter(frontmatter) + "\n\n" + answer
    synthesis_file.write_text(content, encoding="utf-8")
    
    return synthesis_file
```

---

**计划生成时间**: 2026-04-16  
**计划版本**: v1.0  
**执行命令**: `/start-work wiki-fix-plan`

- [x] 13. 实现Schema驱动工作流

  **What to do**:
  - 修改 `_load_schema()` 方法读取 `AGENTS.md` 文件
  - 解析schema中的配置项（工作流、模板、约定）
  - 添加 `_apply_schema_workflow()` 方法:
    - 根据schema配置调整ingest流程
    - 根据schema配置调整query流程
    - 根据schema配置调整lint流程
  - 支持schema覆盖:
    - 允许用户通过修改 `AGENTS.md` 自定义wiki结构
    - 模板可配置
    - 目录结构可配置
  - 在 `init` 时创建默认schema（保持向后兼容）

  **Must NOT do**:
  - 不强制使用schema（保留默认行为）
  - 不改变现有数据结构

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: 需要设计灵活的schema解析和应用逻辑

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 5, 7, 10

  **References**:
  - `docs/llm-wiki.md` - schema设计需求
  - `AGENTS.md` - schema模板文件

  **Acceptance Criteria**:
  - [x] `_load_schema()` 读取并解析 `AGENTS.md`
  - [x] `_apply_schema_workflow()` 应用schema配置
  - [x] 用户可自定义wiki结构
  - [x] 默认行为保持不变

  **QA Scenarios**:

  ```
  Scenario: Schema加载与应用
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_schema.py::test_schema_workflow -v
    Expected Result: Schema配置被正确读取和应用
    Evidence: .sisyphus/evidence/task-13-schema.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): implement schema-driven workflow`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_schema.py`

- [x] 14. 编写单元测试 (解析、安全、核心功能)

  **What to do**:
  在已创建的测试文件中添加具体测试用例:
  
  1. **test_wiki_parsing.py**:
     - `test_json_parse_success` - JSON解析成功
     - `test_json_parse_failure` - JSON解析失败处理
     - `test_parse_failure_fallback` - 降级处理
     - `test_entity_extraction` - 实体提取
     - `test_concept_extraction` - 概念提取
  
  2. **test_wiki_security.py**:
     - `test_path_traversal_blocked` - 路径遍历防护
     - `test_large_file_rejected` - 大文件拒绝
     - `test_llm_timeout` - LLM超时
     - `test_invalid_encoding_handled` - 编码错误处理
  
  3. **test_wiki_ingest.py**:
     - `test_ingest_creates_pages` - Ingest创建页面
     - `test_ingest_updates_index` - Index更新
     - `test_ingest_entity_synthesis` - 实体综合
     - `test_entity_page_synthesis` - 页面综合
     - `test_contradiction_detection` - 矛盾检测
     - `test_index_metadata` - Index元数据
  
  4. **test_wiki_query.py**:
     - `test_query_finds_pages` - Query搜索页面
     - `test_query_save_to_wiki` - Query保存结果
     - `test_query_default_no_save` - 默认不保存

  **Must NOT do**:
  - 不添加真实LLM调用测试（用mock）
  - 不测试外部依赖

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要编写全面的测试用例

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 4 (基础设施), Task 5, 6, 7, 8 (功能实现)

  **References**:
  - 已有测试文件作为参考

  **Acceptance Criteria**:
  - [x] 所有测试文件包含具体测试用例
  - [x] 测试覆盖率 ≥ 80%
  - [x] 所有测试通过
  - [x] 使用pytest-mock进行LLM调用mock

  **QA Scenarios**:

  ```
  Scenario: 单元测试全部通过
    Tool: Bash
    Steps:
      1. cd /mnt/d/git/nanobot
      2. pytest tests/test_wiki_*.py -v --tb=short
    Expected Result: 所有测试通过
    Evidence: .sisyphus/evidence/task-14-unit-tests.txt
  
  Scenario: 测试覆盖率检查
    Tool: Bash
    Steps:
      1. pytest tests/test_wiki_*.py --cov=nanobot.agent.tools.wiki --cov-report=term-missing
    Expected Result: 覆盖率 ≥ 80%
    Evidence: .sisyphus/evidence/task-14-coverage.txt
  ```

  **Commit**: YES
  - Message: `test(wiki): add comprehensive unit tests`
  - Files: `tests/test_wiki_*.py`

- [x] 15. 创建真实用例测试套件

  **What to do**:
  - 创建 `tests/test_data/sample_technical_indicators.md` (使用84KB技术指标剧本):
    - 包含58个技术指标信号的简化版本（用于测试）
    - 约5-10KB大小
  - 创建 `tests/test_wiki_real_data.py`:
    - `test_real_document_entities` - 真实文档实体提取
    - `test_real_document_concepts` - 真实文档概念提取
    - `test_real_ingest_end_to_end` - 端到端ingest测试
    - `test_real_query_workflow` - 真实query流程
  - 创建 `tests/test_data/expected_entities.json` - 期望提取的实体列表
  - 创建 `tests/test_data/expected_concepts.json` - 期望提取的概念列表
  - 运行真实测试验证提取质量

  **Must NOT do**:
  - 不包含完整84KB文件（太大）
  - 不依赖真实LLM（使用mock或跳过）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要准备真实测试数据和期望结果

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 4, 5, 6, 7

  **References**:
  - 代码评审报告中的真实测试部分
  - 84KB技术指标剧本文件

  **Acceptance Criteria**:
  - [x] 真实测试数据文件创建
  - [x] 期望实体/概念列表定义
  - [x] 真实用例测试实现
  - [x] 文档说明如何运行真实测试

  **QA Scenarios**:

  ```
  Scenario: 真实用例测试
    Tool: Bash
    Steps:
      1. 运行测试: pytest tests/test_wiki_real_data.py -v -s
    Expected Result: 真实数据测试通过
    Evidence: .sisyphus/evidence/task-15-real-data.txt
  ```

  **Commit**: YES
  - Message: `test(wiki): add real-world data test suite`
  - Files: `tests/test_wiki_real_data.py`, `tests/test_data/*`

- [x] 16. 更新配置模式

  **What to do**:
  - 修改 `nanobot/config/schema.py`:
    - 添加 `WikiConfig` 类（如尚未存在）
    - 添加可配置字段:
      - `temperature: float = 0.3`
      - `max_tokens: int = 4096`
      - `max_content_length: int = 30000`
      - `stale_threshold_days: int = 90`
      - `max_query_pages: int = 15`
      - `llm_timeout_seconds: int = 120`
      - `max_source_size_mb: int = 50`
  - 更新 `ToolsConfig` 引用新的 `WikiConfig`
  - 确保配置可通过 `config.json` 覆盖
  - 添加配置验证

  **Must NOT do**:
  - 不改变现有配置结构
  - 不删除已有配置项

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Pydantic配置模式更新

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 2 (常量定义作为参考)

  **References**:
  - `nanobot/config/schema.py` - 配置模式定义
  - `nanobot/agent/tools/wiki.py` - 使用的常量

  **Acceptance Criteria**:
  - [x] `WikiConfig` 类添加所有配置字段
  - [x] 配置可通过 `config.json` 自定义
  - [x] 默认值与代码中的常量一致
  - [x] 配置验证正常工作

  **QA Scenarios**:

  ```
  Scenario: 配置加载
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_config.py -k wiki -v
    Expected Result: Wiki配置被正确加载和验证
    Evidence: .sisyphus/evidence/task-16-config.txt
  ```

  **Commit**: YES
  - Message: `config(wiki): add configurable parameters to schema`
  - Files: `nanobot/config/schema.py`, `tests/test_config.py`

- [x] 17. 最终验证与代码审查

  **What to do**:
  - 运行完整测试套件:
    - `pytest tests/test_wiki*.py -v`
    - 检查所有测试通过
  - 运行类型检查:
    - `mypy nanobot/agent/tools/wiki.py`
    - 修复所有类型错误
  - 运行代码格式检查:
    - `ruff check nanobot/agent/tools/wiki.py`
    - 修复所有lint错误
  - 代码审查:
    - 检查代码风格一致性
    - 检查文档字符串完整性
    - 检查错误处理完整性
  - 真实文档测试:
    - 使用84KB技术指标剧本进行完整ingest测试
    - 验证Entities/Concepts提取质量
    - 验证Query归档功能
    - 验证Lint功能

  **Must NOT do**:
  - 不添加新功能
  - 不进行重构

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 综合验证

  **Parallelization**:
  - **Can Run In Parallel**: NO (依赖所有任务)
  - **Parallel Group**: Wave 4 (Final)
  - **Blocks**: Wave FINAL
  - **Blocked By**: ALL previous tasks

  **References**:
  - 整个代码库

  **Acceptance Criteria**:
  - [x] 所有测试通过
  - [x] 类型检查通过
  - [x] 代码lint通过
  - [x] 真实文档测试通过（提取率>80%）

  **QA Scenarios**:

  ```
  Scenario: 完整测试套件
    Tool: Bash
    Steps:
      1. pytest tests/test_wiki*.py -v --tb=short
    Expected Result: 所有测试通过
    Evidence: .sisyphus/evidence/task-17-full-test.txt
  
  Scenario: 代码质量检查
    Tool: Bash
    Steps:
      1. ruff check nanobot/agent/tools/wiki.py
      2. mypy nanobot/agent/tools/wiki.py
    Expected Result: 无错误
    Evidence: .sisyphus/evidence/task-17-quality.txt
  
  Scenario: 真实文档验证
    Tool: Bash (手动)
    Steps:
      1. nanobot wiki init --path /tmp/test-wiki
      2. nanobot wiki ingest /path/to/84kb_script.md
      3. ls /tmp/test-wiki/pages/entities/ | wc -l
    Expected Result: 提取20+实体
    Evidence: .sisyphus/evidence/task-17-real-validation.txt
  ```

  **Commit**: YES (如需要修复)
  - Message: `chore(wiki): final verification and fixes`

---


- [x] 9. 完善Lint功能 (5项完整检查)

  **What to do**:
  实现代码评审中缺失的Lint检查：
  
  1. **矛盾检测** (改进):
     - 扩大分析范围（不限于10页）
     - 使用LLM分析内容实质矛盾
     - 添加 `_detect_contradictions_llm()` 方法
  
  2. **过时检测** (改进):
     - 使用LLM分析内容实质是否过时（而非仅按日期）
     - 添加 `_detect_stale_content_llm()` 方法
  
  3. **重要概念缺失页面** (新增):
     - 扫描所有页面内容中的 `[[...]]` 链接
     - 检测链接目标是否不存在
     - 生成缺失概念列表
     - 添加 `_detect_missing_concepts()` 方法
  
  4. **数据缺口** (新增):
     - 识别内容中的信息缺口
     - 建议可用的web搜索查询
     - 添加 `_detect_information_gaps()` 方法
  
  5. **缺失交叉引用** (改进):
     - 检测"应该链接但未链接"的情况
     - 基于语义相似性推荐链接
     - 添加 `_detect_missing_links()` 方法

  **Must NOT do**:
  - 不自动修复问题（只报告）
  - 不改变现有孤儿页面检测

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要多个Lint检查的实现

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 5 (实体提取修复)

  **References**:
  - `nanobot/agent/tools/wiki.py` - Lint相关方法
  - 代码评审报告 "3. Lint" 部分

  **Acceptance Criteria**:
  - [x] 5项Lint检查全部实现
  - [x] 每项检查返回清晰的报告
  - [x] lint报告保存到 `log.md`
  - [x] 性能可接受（单页<5秒）

  **QA Scenarios**:

  ```
  Scenario: 完整Lint检查
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_lint.py::test_full_lint_suite -v
    Expected Result: 5项检查全部运行并产生报告
    Evidence: .sisyphus/evidence/task-9-lint-full.txt
  
  Scenario: 缺失概念检测
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_lint.py::test_missing_concepts -v
    Expected Result: 检测到"提到却无页面"的概念
    Evidence: .sisyphus/evidence/task-9-missing-concepts.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): complete all 5 lint checks`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_lint.py`

- [x] 10. 实现backlinks自动维护

  **What to do**:
  - 创建 `_update_backlinks()` 方法:
    - 扫描所有页面的 `[[...]]` 链接
    - 构建入站链接图（哪些页面链接到当前页面）
    - 在每个页面底部添加"Backlinks" section
  - 在 `_create_entity_page()`, `_create_concept_page()` 中调用
  - 在 `_update_entity_page()` 中更新backlinks
  - backlinks格式: `## Backlinks\n\n- [[Source Page]]`

  **Must NOT do**:
  - 不扫描页面外的链接
  - 不修改页面主要内容

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要图遍历和文件更新逻辑

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 5 (实体提取), Task 7 (页面更新)

  **References**:
  - `docs/llm-wiki.md` - schema中关于backlinks的描述

  **Acceptance Criteria**:
  - [x] `_update_backlinks()` 方法实现
  - [x] 入站链接图正确构建
  - [x] 每个页面包含Backlinks section
  - [x] backlinks随页面更新自动维护

  **QA Scenarios**:

  ```
  Scenario: Backlinks自动维护
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_links.py::test_backlinks_maintenance -v
    Expected Result: 页面正确显示入站链接
    Evidence: .sisyphus/evidence/task-10-backlinks.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): auto-maintain backlinks across pages`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_links.py`

- [x] 11. 添加解析失败日志与错误处理

  **What to do**:
  - 增强错误处理:
    - 替换所有 `except Exception: pass` 为具体异常处理
    - 添加 `_handle_parsing_error()` 方法记录失败详情
    - 包含原始LLM输出前500字符
  - 添加日志记录:
    - 使用 `logging` 模块
    - 记录LLM调用参数和响应
    - 记录文件操作
    - 记录性能指标（调用耗时）
  - 在 `log.md` 中添加错误条目

  **Must NOT do**:
  - 不添加过多的日志（避免噪音）
  - 不记录敏感信息（API keys等）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要全面的错误处理审计

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 5 (解析修复)

  **References**:
  - `nanobot/agent/tools/wiki.py:745-746` - 当前静默异常

  **Acceptance Criteria**:
  - [x] 所有 `except Exception: pass` 被替换
  - [x] 解析失败记录到日志
  - [x] LLM调用记录参数和响应长度
  - [x] 性能指标（调用耗时）被记录

  **QA Scenarios**:

  ```
  Scenario: 错误日志记录
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_logging.py::test_error_logging -v
    Expected Result: 错误被正确记录，包含上下文信息
    Evidence: .sisyphus/evidence/task-11-error-logging.txt
  ```

  **Commit**: YES
  - Message: `fix(wiki): add comprehensive error handling and logging`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_logging.py`

- [x] 12. 性能优化 (缓存、并行化)

  **What to do**:
  1. **添加缓存**:
     - 使用 `functools.lru_cache` 缓存频繁访问的页面
     - 添加 `_get_cached_page()` 方法
     - 缓存frontmatter解析结果
  
  2. **批量处理优化**:
     - 添加 `_ingest_batch()` 方法支持批量ingest
     - 使用 `asyncio.gather()` 并行处理多个源文件
  
  3. **Index更新优化**:
     - 添加 `force` 参数控制是否强制更新
     - 优化大文件处理（分段读取）

  **Must NOT do**:
  - 不改变核心逻辑
  - 不引入复杂缓存系统

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 性能优化，需要理解瓶颈

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 5, 6, 7

  **References**:
  - 代码评审报告 "5. 性能考虑" 部分

  **Acceptance Criteria**:
  - [x] LRU缓存实现
  - [x] 批量ingest支持
  - [x] Index更新可选择性执行
  - [x] 性能测试显示改进（如可能）

  **QA Scenarios**:

  ```
  Scenario: 缓存功能
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_performance.py::test_page_caching -v
    Expected Result: 缓存命中减少文件读取
    Evidence: .sisyphus/evidence/task-12-caching.txt
  ```

  **Commit**: YES
  - Message: `perf(wiki): add caching and batch processing`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_performance.py`

---


- [x] 5. 修复Entities/Concepts提取 (JSON解析)

  **What to do**:
  - 修改 `_analyze_source_with_llm()` 使用新的 `_call_llm_json()` 方法
  - 更新LLM prompt要求返回JSON格式（而非字符串格式）
  - 修改 `_parse_llm_response()` 以解析JSON而非字符串匹配
  - 确保entities和concepts以列表形式返回（而非字典）
  - 添加解析失败时的降级处理（返回空列表而非抛出异常）
  - 更新 `_create_entity_page()` 和 `_create_concept_page()` 以处理新的数据结构

  **Must NOT do**:
  - 不修改页面写入逻辑（在Task 7处理）
  - 不改变索引更新逻辑（在Task 8处理）

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: 核心功能修复，需要理解现有逻辑和JSON转换

  **Parallelization**:
  - **Can Run In Parallel**: NO (依赖Task 2, 3)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7, 10
  - **Blocked By**: Task 2 (常量), Task 3 (JSON接口)

  **References**:
  - `nanobot/agent/tools/wiki.py:354-431` - 当前解析逻辑
  - `nanobot/agent/tools/wiki.py:661-662` - 实体页面更新

  **Acceptance Criteria**:
  - [x] `_analyze_source_with_llm()` 使用JSON格式
  - [x] Entities以列表形式提取（每个包含name和description）
  - [x] Concepts以列表形式提取（每个包含name和definition）
  - [x] 解析失败时返回空列表并记录日志
  - [x] 真实用例测试通过（使用84KB技术指标剧本）

  **QA Scenarios**:

  ```
  Scenario: 真实文档Entities提取
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_ingest.py::test_real_document_entities -v -s
    Expected Result: 从84KB剧本中提取20+个技术指标实体
    Evidence: .sisyphus/evidence/task-5-real-entities.txt
  
  Scenario: 真实文档Concepts提取
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_ingest.py::test_real_document_concepts -v -s
    Expected Result: 从84KB剧本中提取30+个技术分析概念
    Evidence: .sisyphus/evidence/task-5-real-concepts.txt
  
  Scenario: JSON解析失败降级
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_parsing.py::test_parse_failure_fallback -v
    Expected Result: 无效JSON返回空列表，不抛出异常
    Evidence: .sisyphus/evidence/task-5-parse-fallback.txt
  ```

  **Commit**: YES
  - Message: `fix(wiki): use JSON format for entity/concept extraction`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_parsing.py`, `tests/test_wiki_ingest.py`

- [x] 6. 实现Query归档功能

  **What to do**:
  - 修改 `_query_wiki()` 添加 `save_to_wiki` 参数（默认False）
  - 当 `save_to_wiki=True` 时，将答案保存到 `pages/syntheses/{timestamp}_{query_slug}.md`
  - 创建 `_save_synthesis()` 辅助方法:
    - 生成唯一文件名（基于时间戳和查询slug）
    - 添加合适的frontmatter（query, timestamp, sources_referenced）
    - 写入synthesis页面
  - 更新 `_log_entry()` 记录synthesis创建
  - 在CLI slash命令中添加 `--save` 或 `--synthesize` 选项

  **Must NOT do**:
  - 不改变默认行为（向后兼容）
  - 不修改query搜索逻辑

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: 需要理解现有query流程和文件写入模式

  **Parallelization**:
  - **Can Run In Parallel**: YES (与Task 5, 7)
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 2 (常量), Task 3 (JSON接口)

  **References**:
  - `nanobot/agent/tools/wiki.py:1094-1099` - 当前query返回格式
  - `nanobot/agent/tools/wiki.py:661-662` - 页面创建模式

  **Acceptance Criteria**:
  - [x] `save_to_wiki` 参数添加到 `_query_wiki()`
  - [x] `_save_synthesis()` 方法实现
  - [x] Synthesis页面包含完整frontmatter
  - [x] 文件名格式: `synthesis_YYYYMMDD_HHMMSS_{slug}.md`
  - [x] CLI slash命令支持 `--save` 选项

  **QA Scenarios**:

  ```
  Scenario: Query归档成功
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_query.py::test_query_save_to_wiki -v
    Expected Result: 答案被保存到pages/syntheses/目录
    Evidence: .sisyphus/evidence/task-6-save-synthesis.txt
  
  Scenario: 默认不保存
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_query.py::test_query_default_no_save -v
    Expected Result: 默认情况下不创建synthesis页面
    Evidence: .sisyphus/evidence/task-6-default-no-save.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): add query result archival to syntheses`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_query.py`

- [x] 7. 修复实体页面更新逻辑 (知识综合)

  **What to do**:
  - 修改 `_update_entity_page()` 实现真正的知识综合:
    - 读取现有页面内容
    - 使用LLM重新综合整页内容（而非机械追加）
    - LLM应处理矛盾、更新摘要、维护一致性
  - 创建 `_synthesize_entity_page()` 方法:
    - 输入: 现有内容 + 新信息
    - 输出: 综合后的完整页面内容
    - 使用JSON格式定义输出结构
  - 更新 `_update_concept_page()` 使用相同模式
  - 添加 "contradictions" section（如schema要求）
  - 在frontmatter中记录更新历史和source引用

  **Must NOT do**:
  - 不删除现有页面内容（保留历史）
  - 不改变页面基本结构

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: 需要复杂的LLM交互设计和知识综合逻辑

  **Parallelization**:
  - **Can Run In Parallel**: YES (与Task 5, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 10
  - **Blocked By**: Task 3 (JSON接口), Task 5 (实体提取修复)

  **References**:
  - `nanobot/agent/tools/wiki.py:661-662` - 当前机械追加逻辑
  - `docs/llm-wiki.md` - 知识综合需求描述

  **Acceptance Criteria**:
  - [x] `_synthesize_entity_page()` 方法实现
  - [x] 使用LLM重新综合页面内容
  - [x] 矛盾处理逻辑（记录到contradictions section）
  - [x] 更新历史记录在frontmatter中
  - [x] 真实测试验证综合质量

  **QA Scenarios**:

  ```
  Scenario: 实体页面综合更新
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_ingest.py::test_entity_page_synthesis -v -s
    Expected Result: 多次ingest后页面内容被正确综合
    Evidence: .sisyphus/evidence/task-7-entity-synthesis.txt
  
  Scenario: 矛盾检测与记录
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_ingest.py::test_contradiction_detection -v -s
    Expected Result: 矛盾信息被检测到并记录在contradictions section
    Evidence: .sisyphus/evidence/task-7-contradiction.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): implement true knowledge synthesis for entity updates`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_ingest.py`

- [x] 8. 修复index.md元数据填充

  **What to do**:
  - 修改 `_update_index()` 提取并填充真实元数据:
    - **Sources**: 从页面frontmatter提取summary, source count
    - **Entities**: 提取type, related sources count
    - **Concepts**: 提取definition
    - **Syntheses**: 提取query, date
  - 更新表格列格式以显示元数据
  - 添加 `_extract_page_summary()` 辅助方法（前200字符）
  - 添加 `_count_entity_sources()` 统计相关源文件数

  **Must NOT do**:
  - 不改变index.md基本结构
  - 不添加复杂计算（保持简单）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: 主要是数据提取和格式化

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `nanobot/agent/tools/wiki.py:954-976` - 当前index更新逻辑

  **Acceptance Criteria**:
  - [x] index.md中的Summary列显示真实摘要
  - [x] Entity页面显示Type和Source Count
  - [x] Concept页面显示Definition预览
  - [x] 元数据提取不超过200字符

  **QA Scenarios**:

  ```
  Scenario: Index元数据填充
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_ingest.py::test_index_metadata -v
    Expected Result: index.md包含真实元数据而非"-"
    Evidence: .sisyphus/evidence/task-8-index-metadata.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): populate index.md with real metadata`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_ingest.py`

---


### 原始需求
根据 `docs/llm-wiki.md` 设计文档，LLM Wiki应实现：
- 三层架构：Raw sources / Wiki pages / Schema
- Ingest流程：读取源文件 → 提取实体/概念 → 生成摘要页面 → 更新索引
- Query流程：搜索相关页面 → 综合答案 → 归档回wiki
- Lint功能：矛盾检测、过时检测、孤儿页面检测、缺失概念检测、数据缺口识别

### 代码评审发现的问题

**P0 - 关键功能缺陷**:
1. Entities/Concepts提取完全失败（解析逻辑脆弱）
2. Query无法归档答案（缺少syntheses页面生成）
3. 实体页面更新只是机械追加，非真正知识综合

**P1 - 安全与稳定性**:
4. 路径遍历漏洞
5. 文件大小无限制
6. LLM调用无超时
7. Lint功能不完整

**P2 - 完整需求实现**:
8. index.md元数据不足
9. Schema与工作流脱节
10. 缺少backlinks维护
11. 性能可优化

### 技术决策
- **LLM输出格式**: JSON（替代字符串匹配）
- **测试策略**: 单元测试 + 真实用例测试
- **修改范围**: 完全对齐需求（P0+P1+P2）

---

## Work Objectives

### 核心目标
实现一个健壮、安全、功能完整的LLM驱动个人知识库系统

### 具体交付物
1. **修复后的核心代码** (`nanobot/agent/tools/wiki.py`)
   - JSON格式LLM交互
   - 完整的安全验证
   - 正确的知识综合逻辑
   - Query归档功能
   - 完整的Lint检查

2. **配置文件更新** (`nanobot/config/schema.py`)
   - WikiConfig扩展字段
   - 可配置的LLM参数

3. **测试套件** (`tests/`)
   - `test_wiki_parsing.py` - 解析逻辑单元测试
   - `test_wiki_ingest.py` - Ingest流程测试
   - `test_wiki_query.py` - Query功能测试
   - `test_wiki_security.py` - 安全验证测试
   - `test_data/` - 真实用例测试数据

4. **文档更新**
   - 更新 `docs/llm-wiki.md`（如需要）

### 定义完成标准
- [x] 所有P0问题修复并通过真实用例验证
- [x] 所有P1问题修复并通过安全测试
- [x] 单元测试覆盖率 ≥ 80%
- [x] 真实文档测试通过（使用84KB技术指标剧本文件）
- [x] 代码通过类型检查和lint

### Must Have
- [x] Entities/Concepts提取正常工作（真实测试验证）
- [x] Query可以归档答案到syntheses目录
- [x] 路径遍历漏洞修复
- 文件大小限制（50MB）
- LLM调用超时（120秒）
- 完整的Lint功能（5项检查）

### Must NOT Have (Guardrails)
- 不改变现有CLI接口（保持向后兼容）
- 不破坏已有wiki数据结构
- 不引入新的外部依赖（使用标准库）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest已配置)
- **Automated tests**: YES (TDD-style)
- **Framework**: pytest-asyncio

### QA Policy
Every task includes agent-executed QA scenarios.

### 测试级别
1. **单元测试**: 解析逻辑、安全验证、工具函数
2. **集成测试**: Ingest完整流程、Query完整流程
3. **真实用例测试**: 使用84KB技术指标剧本文件验证
4. **安全测试**: 路径遍历、文件大小限制、超时控制

---

## Execution Strategy

### 并行执行Wave规划

```
Wave 1 (Foundation - 安全与基础结构):
├── Task 1: 添加安全验证机制 (路径验证、文件大小限制)
├── Task 2: 添加配置常量与超时控制
├── Task 3: 重构LLM调用接口 (JSON格式支持)
└── Task 4: 创建测试基础设施

Wave 2 (Core Features - 关键功能修复):
├── Task 5: 修复Entities/Concepts提取 (JSON解析)
├── Task 6: 实现Query归档功能
├── Task 7: 修复实体页面更新逻辑 (知识综合)
└── Task 8: 修复index.md元数据填充

Wave 3 (Lint & Polish - 功能完善):
├── Task 9: 完善Lint功能 (5项完整检查)
├── Task 10: 实现backlinks自动维护
├── Task 11: 添加解析失败日志与错误处理
└── Task 12: 性能优化 (缓存、并行化)

Wave 4 (Schema & Testing - 高级功能与测试):
├── Task 13: 实现Schema驱动工作流
├── Task 14: 编写单元测试 (解析、安全、核心功能)
├── Task 15: 创建真实用例测试套件
├── Task 16: 更新配置模式
└── Task 17: 最终验证与代码审查

Wave FINAL (Review & Delivery):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### 依赖关系

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1, 2 | - | 3, 5, 6, 7, 8 |
| 3 | 1, 2 | 5, 6, 7 |
| 4 | - | 14, 15 |
| 5 | 2, 3 | 7, 10 |
| 6 | 2, 3 | - |
| 7 | 3, 5 | 10 |
| 8 | - | - |
| 9 | 5 | - |
| 10 | 5, 7 | - |
| 11 | 5 | - |
| 12 | 5, 6, 7 | - |
| 13 | 5, 7, 10 | - |
| 14 | 4, 5 | - |
| 15 | 4, 5, 6, 7 | - |
| 16 | 2 | - |
| 17 | ALL | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: Tasks 1-4 → `quick` (1-2), `quick` (3), `quick` (4)
- **Wave 2**: Tasks 5-8 → `deep` (5, 7), `unspecified-high` (6), `quick` (8)
- **Wave 3**: Tasks 9-12 → `unspecified-high` (9, 11, 12), `unspecified-high` (10)
- **Wave 4**: Tasks 13-17 → `deep` (13), `unspecified-high` (14, 15), `quick` (16), `unspecified-high` (17)
- **Wave FINAL**: Tasks F1-F4 → `oracle`, `unspecified-high` (2), `unspecified-high` (3), `deep` (4)

---

## TODOs

### Wave 1: Foundation - 安全与基础结构

- [x] 1. 添加安全验证机制

  **What to do**:
  - 在 `WikiTool` 中添加路径验证方法 `_validate_source_path()`
  - 添加文件大小检查 `_validate_file_size()` (限制50MB)
  - 验证源路径是否在允许的目录内（workspace或显式配置的路径）
  - 更新 `ingest` 命令处理以使用新的验证方法

  **Must NOT do**:
  - 不改变现有的CLI接口
  - 不修改LLM调用逻辑（在Wave 3处理）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: 纯Python工具函数实现，无复杂逻辑

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 3, 5, 6, 7, 8
  - **Blocked By**: None

  **References**:
  - `nanobot/agent/tools/wiki.py:561-566` - 当前路径处理（缺少验证）
  - `nanobot/agent/tools/wiki.py:569-570` - 文件读取（无大小检查）
  - 代码评审报告 "4. 安全性" 部分

  **Acceptance Criteria**:
  - [x] `_validate_source_path()` 方法实现，检查路径是否在允许目录内
  - [x] `_validate_file_size()` 方法实现，限制50MB
  - [x] 所有文件操作前调用验证方法
  - [x] 验证失败时返回清晰的错误消息

  **QA Scenarios**:

  ```
  Scenario: 路径遍历攻击防护
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_security.py::test_path_traversal_blocked -v
    Expected Result: 测试通过，路径遍历被阻止
    Evidence: .sisyphus/evidence/task-1-path-traversal.txt
  
  Scenario: 超大文件被拒绝
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_security.py::test_large_file_rejected -v
    Expected Result: 测试通过，>50MB文件被拒绝
    Evidence: .sisyphus/evidence/task-1-file-size.txt
  ```

  **Commit**: YES
  - Message: `security(wiki): add path validation and file size limits`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_security.py`

- [x] 2. 添加配置常量与超时控制

  **What to do**:
  - 在 `WikiTool` 类顶部定义配置常量（替代魔法数字）:
    - `MAX_CONTENT_LENGTH = 30000`
    - `MAX_QUERY_PAGES = 15`
    - `STALE_THRESHOLD_DAYS = 90`
    - `MAX_SOURCE_SIZE = 50 * 1024 * 1024` (50MB)
    - `LLM_TIMEOUT_SECONDS = 120`
    - `MAX_ANALYSIS_TOKENS = 4096`
  - 修改 `_call_llm()` 方法添加超时控制 `asyncio.timeout()`
  - 更新所有使用魔法数字的地方引用常量

  **Must NOT do**:
  - 不修改配置模式（在Task 16处理）
  - 不改变LLM交互格式（在Wave 2处理）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: 简单的常量提取和替换

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 3, 5, 6, 7
  - **Blocked By**: None

  **References**:
  - `nanobot/agent/tools/wiki.py:298-300` - 魔法数字位置
  - `nanobot/agent/tools/wiki.py:459` - LLM调用（无超时）

  **Acceptance Criteria**:
  - [x] 所有魔法数字替换为类常量
  - [x] `_call_llm()` 添加 `asyncio.timeout(LLM_TIMEOUT_SECONDS)`
  - [x] 超时异常被正确捕获并返回友好错误消息

  **QA Scenarios**:

  ```
  Scenario: LLM调用超时处理
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_security.py::test_llm_timeout -v
    Expected Result: 测试通过，超时异常被正确处理
    Evidence: .sisyphus/evidence/task-2-timeout.txt
  
  Scenario: 常量定义检查
    Tool: Bash (grep)
    Steps:
      1. grep -n "MAX_CONTENT_LENGTH\|MAX_QUERY_PAGES\|STALE_THRESHOLD_DAYS" nanobot/agent/tools/wiki.py
    Expected Result: 显示类常量定义和使用
    Evidence: .sisyphus/evidence/task-2-constants.txt
  ```

  **Commit**: YES (与Task 1一起)
  - Message: `refactor(wiki): extract magic numbers to constants and add LLM timeout`

- [x] 3. 重构LLM调用接口 (JSON格式支持)

  **What to do**:
  - 创建新的 `_call_llm_json()` 方法，要求LLM返回JSON格式
  - 设计JSON schema用于source分析:
    ```json
    {
      "summary": "2-3 paragraph summary",
      "claims": ["claim 1", "claim 2"],
      "entities": [{"name": "...", "description": "..."}],
      "concepts": [{"name": "...", "definition": "..."}],
      "tags": ["tag1", "tag2"]
    }
    ```
  - 更新system prompt要求JSON输出
  - 添加JSON解析和错误处理（带重试机制）
  - 保留旧的 `_call_llm()` 用于非JSON调用

  **Must NOT do**:
  - 不立即替换所有调用（在Task 5进行）
  - 不改变现有的字符串解析逻辑（保留兼容性）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: 接口设计，逻辑清晰

  **Parallelization**:
  - **Can Run In Parallel**: YES (与Task 1, 2)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5, 6, 7
  - **Blocked By**: Task 2 (依赖常量定义)

  **References**:
  - `nanobot/agent/tools/wiki.py:354-431` - 当前脆弱解析逻辑
  - 代码评审报告建议的JSON格式

  **Acceptance Criteria**:
  - [x] `_call_llm_json()` 方法实现
  - [x] JSON schema定义清晰
  - [x] JSON解析带错误处理（JSONDecodeError）
  - [x] 解析失败时记录日志并尝试修复

  **QA Scenarios**:

  ```
  Scenario: JSON解析成功
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_parsing.py::test_json_parse_success -v
    Expected Result: 测试通过，有效JSON被正确解析
    Evidence: .sisyphus/evidence/task-3-json-success.txt
  
  Scenario: JSON解析失败处理
    Tool: Bash (pytest)
    Steps:
      1. 运行测试: pytest tests/test_wiki_parsing.py::test_json_parse_failure -v
    Expected Result: 测试通过，无效JSON触发错误处理
    Evidence: .sisyphus/evidence/task-3-json-failure.txt
  ```

  **Commit**: YES
  - Message: `feat(wiki): add JSON-based LLM interface with error handling`
  - Files: `nanobot/agent/tools/wiki.py`, `tests/test_wiki_parsing.py`

- [x] 4. 创建测试基础设施

  **What to do**:
  - 创建 `tests/test_wiki_parsing.py` - 解析逻辑测试
  - 创建 `tests/test_wiki_security.py` - 安全测试
  - 创建 `tests/test_wiki_ingest.py` - Ingest流程测试
  - 创建 `tests/test_wiki_query.py` - Query功能测试
  - 创建 `tests/test_data/` 目录存放测试数据
  - 添加pytest fixtures:
    - `wiki_tool` - 初始化的WikiTool实例
    - `temp_wiki_dir` - 临时wiki目录
    - `sample_source_file` - 示例源文件

  **Must NOT do**:
  - 不添加具体测试用例（在Wave 4添加）
  - 不创建真实用例数据（在Task 15创建）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: 测试基础设施搭建

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 14, 15
  - **Blocked By**: None

  **References**:
  - `tests/` 目录现有测试文件作为参考
  - pytest-asyncio文档

  **Acceptance Criteria**:
  - [x] 4个测试文件创建
  - [x] pytest fixtures定义完成
  - [x] `tests/conftest.py` 更新（如需要）
  - [x] 运行 `pytest tests/test_wiki*.py --collect-only` 成功

  **QA Scenarios**:

  ```
  Scenario: 测试收集成功
    Tool: Bash
    Steps:
      1. cd /mnt/d/git/nanobot
      2. pytest tests/test_wiki*.py --collect-only
    Expected Result: 显示测试文件和fixtures被正确收集
    Evidence: .sisyphus/evidence/task-4-test-collection.txt
  ```

  **Commit**: YES
  - Message: `test(wiki): add test infrastructure and fixtures`
  - Files: `tests/test_wiki_*.py`, `tests/conftest.py`

---

