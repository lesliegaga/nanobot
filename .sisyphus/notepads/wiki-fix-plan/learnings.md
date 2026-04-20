# WikiConfig 配置模式分析报告

## 分析时间
2026-04-20

## 1. WikiConfig 现状

**重要发现：WikiConfig 类已存在！**

位置：`nanobot/config/schema.py` 第 323-327 行

```python
class WikiConfig(Base):
    """LLM Wiki knowledge base configuration."""

    path: str = ""  # Wiki root directory. If empty, defaults to {workspace}/wiki
```

WikiConfig 已经集成到 ToolsConfig 中（第 334 行）：
```python
wiki: WikiConfig = Field(default_factory=WikiConfig)
```

## 2. ToolsConfig 完整结构

```python
class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    wiki: WikiConfig = Field(default_factory=WikiConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
```

### 子配置类：
- **WebToolsConfig** (第 295-301 行): 包含 proxy 和 search (WebSearchConfig)
- **ExecToolConfig** (第 304-308 行): 包含 timeout 和 path_append
- **MCPServerConfig** (第 311-320 行): MCP 服务器配置（stdio 或 HTTP 模式）

## 3. 配置类继承和验证模式

### 基础模式
```python
class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
```

所有配置类都继承自 `Base`，这意味着：
- 配置键同时支持 camelCase 和 snake_case
- 通过 Pydantic 的 alias_generator 自动转换

### 添加新配置类的标准模式

以 WikiConfig 为示例：

```python
class WikiConfig(Base):
    """配置类文档字符串。"""
    
    # 基础字段
    enabled: bool = False  # 是否启用
    path: str = ""  # 路径配置
    
    # 嵌套配置使用 Field(default_factory=...)
    nested: OtherConfig = Field(default_factory=OtherConfig)
```

### 集成到父配置

```python
class ToolsConfig(Base):
    wiki: WikiConfig = Field(default_factory=WikiConfig)
```

### 字段类型使用规范

| 类型 | 使用场景 | 示例 |
|------|----------|------|
| `bool` | 开关配置 | `enabled: bool = False` |
| `str` | 字符串值 | `path: str = ""` |
| `int` | 数值配置 | `timeout: int = 60` |
| `list[str]` | 字符串列表 | `allow_from: list[str] = Field(default_factory=list)` |
| `dict[str, X]` | 字典配置 | `mcp_servers: dict[str, MCPServerConfig]` |
| `Literal[...]` | 枚举值 | `policy: Literal["open", "mention"]` |
| `X \| None` | 可选值 | `proxy: str \| None = None` |

## 4. 配置使用示例

JSON 配置格式（自动支持 camelCase）：

```json
{
  "tools": {
    "wiki": {
      "path": "/path/to/wiki"
    }
  }
}
```

或 snake_case：

```json
{
  "tools": {
    "wiki": {
      "path": "/path/to/wiki"
    }
  }
}
```

## 5. 最佳实践总结

1. **继承 Base 类**：确保配置键支持 camelCase/snake_case 双格式
2. **使用 Field(default_factory=...)**：避免可变默认值问题
3. **提供默认值**：所有字段应有合理的默认值
4. **添加文档字符串**：类和方法都应有清晰的文档
5. **类型注解**：使用 Python 3.11+ 类型注解（如 `str \| None`）
6. **注释说明**：复杂字段添加行内注释说明用途

## 6. 结论

**WikiConfig 已经存在且正确集成到配置系统中**，无需添加新的配置类。如果需要扩展 WikiConfig 的功能，可以直接修改现有的 WikiConfig 类，添加新的字段。
# Wiki.py 代码分析报告

生成时间: 2026-04-20
文件: nanobot/agent/tools/wiki.py
总行数: 1206

---

## 1. 代码结构概览

```
WikiTool 类结构:
├── __init__()                    # 初始化，行30-46
├── _require_llm()                # LLM检查，行48-54
├── properties: name/description/parameters  # 行56-110
├── _get_wiki_root()              # 解析wiki根目录，行112-120
├── _ensure_structure()           # 确保目录结构，行122-140
├── _read_frontmatter()           # 解析YAML frontmatter，行150-173
├── _write_frontmatter()          # 生成YAML frontmatter，行175-186
├── _sanitize_filename()          # 文件名净化，行188-193
├── _log_entry()                  # 日志记录，行195-215
├── _init_wiki()                  # 初始化wiki，行217-356
├── _call_llm()                   # LLM调用，行358-380
├── _analyze_source_with_llm()    # 分析源文件，行382-467
├── _generate_entity_page()       # 生成实体页面，行469-535
├── _generate_concept_page()      # 生成概念页面，行537-601
├── _ingest_source()              # 摄入源文件，行603-742
├── _update_index()               # 更新索引，行744-831
├── _query_wiki()                 # 查询wiki，行833-934
├── _analyze_contradictions_with_llm()  # 矛盾分析，行936-982
├── _analyze_page_quality_with_llm()    # 质量分析，行984-1022
├── _lint_wiki()                  # Lint检查，行1024-1136
├── _list_sources()               # 列出源文件，行1138-1165
└── execute()                     # 主执行入口，行1167-1206
```

---

## 2. P0 问题 (严重 - 安全/功能缺陷)

### 2.1 缺少文件大小验证 (安全漏洞)
**位置**: `_ingest_source()` 行603-742
**问题**: 在读取源文件内容时没有验证文件大小限制

```python
# 行633-636
try:
    content = source_file.read_text(encoding="utf-8")
except UnicodeDecodeError:
    content = f"[Binary file: {source_file.name}]"
```

**风险**: 大文件可能导致内存耗尽
**建议**: 添加文件大小检查，例如限制为 10MB

### 2.2 缺少路径遍历防护
**位置**: `_ingest_source()` 行612
**问题**: source_path 解析后没有验证是否在工作区内

```python
# 行612
source_file = Path(source_path).expanduser().resolve()
if not source_file.exists():
    return f"Error: Source not found: {source_path}"
```

**风险**: 可能读取系统敏感文件
**建议**: 添加路径白名单验证

### 2.3 静默异常处理
**位置**: `_ingest_source()` 行698-714, `_lint_wiki()` 行1102-1119
**问题**: 多个地方的 `except Exception: pass` 静默吞掉所有错误

```python
# 行703-704
try:
    entity_page = await self._generate_entity_page(...)
    ...
except Exception as e:
    pass  # 静默吞掉异常

# 行713-714
try:
    concept_page = await self._generate_concept_page(...)
    ...
except Exception as e:
    pass  # 静默吞掉异常
```

**风险**: 无法诊断失败原因，数据可能丢失
**建议**: 至少记录错误日志

### 2.4 实体/概念页面更新逻辑只是机械追加
**位置**: `_generate_entity_page()` 行482-497, `_generate_concept_page()` 行550-563
**问题**: 更新现有页面时只是简单追加内容，没有合并或去重

```python
# 行496-497
new_section = f"\n\n## From: {source_name}\n\n{entity_desc}\n"
updated_content = self._write_frontmatter(frontmatter) + "\n" + body + new_section
```

**风险**: 多次摄入同一源文件会导致重复内容
**建议**: 添加源文件引用去重逻辑

---

## 3. P1 问题 (重要 - 功能/性能缺陷)

### 3.1 LLM响应使用脆弱的字符串解析
**位置**: `_analyze_source_with_llm()` 行419-466
**问题**: 依赖硬编码的字符串模式解析LLM输出

```python
# 行434-448
if line.startswith("SUMMARY:"):
    current_section = "summary"
    continue
elif line.startswith("CLAIMS:"):
    current_section = "claims"
    continue
# ... 更多硬编码模式
```

**风险**: LLM输出格式稍有偏差就会解析失败
**建议**: 使用结构化输出(JSON模式)或更健壮的解析器

### 3.2 没有Query归档功能
**位置**: `_query_wiki()` 行833-934
**问题**: 查询结果没有保存，无法建立查询历史

```python
# 行922-923
# Log the query
self._log_entry(wiki_root, "query", query[:80])
```

**仅记录到log.md，没有专门的查询历史文件**
**建议**: 创建 queries/ 目录保存查询和答案

### 3.3 矛盾检测限制过多
**位置**: `_analyze_contradictions_with_llm()` 行946
**问题**: 只分析前10个页面

```python
# 行946
for title, info in list(pages.items())[:10]:  # 限制为10个页面
```

**风险**: 大wiki中可能遗漏重要矛盾
**建议**: 分批处理或按相关性排序

### 3.4 质量检查只检查5个页面
**位置**: `_lint_wiki()` 行1111
**问题**: 质量检查只随机检查前5个页面

```python
# 行1111
for title, info in list(all_pages.items())[:5]:
```

**风险**: 大量页面中问题难以发现
**建议**: 轮询检查或允许指定范围

### 3.5 链接解析正则不够健壮
**位置**: `_lint_wiki()` 行1062
**问题**: 正则只匹配简单的 [[Page Name]] 格式

```python
# 行1062
link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
```

**问题**: 不匹配带别名的链接 [[Page Name|Alias]]
**建议**: 改进正则表达式

### 3.6 Index.md 元数据填充不真实
**位置**: `_update_index()` 行744-831
**问题**: 表格中的 Summary、Type、Sources 列都填充为 "-"

```python
# 行788-789
tags = ", ".join(s["tags"]) if s["tags"] else "-"
index_lines.append(f"| [[{s['title']}]] | - | {s['created']} | {tags} |")
# 行800
index_lines.append(f"| [[{e['title']}]] | - | - | {e['updated']} |")
```

**建议**: 从页面内容中提取实际摘要和类型信息

---

## 4. P2 问题 (建议改进)

### 4.1 Frontmatter解析过于简单
**位置**: `_read_frontmatter()` 行150-173
**问题**: 使用自定义字符串分割，不支持嵌套结构

```python
# 行167-171
for line in frontmatter_text.split("\n"):
    line = line.strip()
    if ":" in line:
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
```

**建议**: 使用 PyYAML 库

### 4.2 文件名净化不够严格
**位置**: `_sanitize_filename()` 行188-193
**问题**: 只移除特定字符，可能产生保留文件名

```python
# 行191-192
safe = re.sub(r'[^\w\s-]', '', name).strip()
safe = re.sub(r'[-\s]+', '_', safe)
```

**建议**: 检查保留字和路径分隔符

### 4.3 缺少并发控制
**问题**: 多个操作同时写入同一文件可能导致竞态条件
**建议**: 添加文件锁机制

### 4.4 Lint错误链接限制为10个
**位置**: `_lint_wiki()` 行1083

```python
# 行1083
issues.append(f"**Broken links**: {', '.join(missing[:10])}")
```

**建议**: 显示总数并分页

---

## 5. 魔法数字列表

| 行号 | 值 | 用途 | 建议常量名 |
|------|-----|------|------------|
| 363 | 4096 | LLM默认max_tokens | DEFAULT_MAX_TOKENS |
| 414 | 30000 | 源文件内容截断长度 | MAX_SOURCE_CONTENT_LENGTH |
| 417 | 4096 | 分析源文件max_tokens | ANALYSIS_MAX_TOKENS |
| 684 | 50000 | 源页面原始内容显示限制 | MAX_RAW_CONTENT_DISPLAY |
| 885 | 3000 | 查询时页面内容截断 | QUERY_CONTENT_TRUNCATE |
| 895 | 2000 | 错误时索引内容显示 | INDEX_PREVIEW_LENGTH |
| 915 | 2000 | LLM查询时索引预览 | INDEX_CONTEXT_LENGTH |
| 920 | 4096 | 查询响应max_tokens | QUERY_MAX_TOKENS |
| 946 | 10 | 矛盾分析页面限制 | CONTRADICTION_ANALYSIS_LIMIT |
| 948 | 1000 | 矛盾分析摘要长度 | CONTRADICTION_SUMMARY_LENGTH |
| 970 | 2048 | 矛盾检测max_tokens | CONTRADICTION_MAX_TOKENS |
| 1009 | 5000 | 质量分析内容长度 | QUALITY_ANALYSIS_LENGTH |
| 1011 | 1024 | 质量分析max_tokens | QUALITY_MAX_TOKENS |
| 1093 | 90 | 过时页面天数阈值 | STALE_PAGE_DAYS |
| 1111 | 5 | 质量检查页面数量 | QUALITY_CHECK_SAMPLE_SIZE |
| 922 | 80 | 查询日志截断长度 | QUERY_LOG_TRUNCATE_LENGTH |

---

## 6. 需要修复的函数和方法

### 高优先级 (P0)
1. `_ingest_source()` - 添加文件大小验证和路径检查
2. `_generate_entity_page()` - 修复机械追加问题
3. `_generate_concept_page()` - 修复机械追加问题
4. 全局 - 移除或改进所有 `except: pass`

### 中优先级 (P1)
5. `_analyze_source_with_llm()` - 改用JSON结构化输出
6. `_query_wiki()` - 添加Query归档功能
7. `_update_index()` - 填充真实的元数据
8. `_lint_wiki()` - 改进链接解析正则

### 低优先级 (P2)
9. `_read_frontmatter()` - 考虑使用PyYAML
10. `_sanitize_filename()` - 加强文件名验证
11. 提取所有魔法数字为常量

---

## 7. 代码统计

- 总函数/方法数: 20
- 使用LLM的方法: 7
- 涉及文件IO的方法: 15
- 魔法数字出现: 16处
- 静默异常处理: 4处

---

*报告由代码分析工具自动生成*

## 2026-04-20 Wiki相关文档查找结果

### 找到的文档清单

#### 1. 设计文档
- **docs/llm-wiki.md** (75行) - LLM Wiki核心设计文档
  - 描述三层架构：Raw Sources -> Wiki -> Schema
  - 定义三大操作：Ingest、Query、Lint
  - 强调知识累积和交叉引用
  - 要求使用JSON格式与LLM交互

#### 2. 使用文档
- **docs/wiki-usage.md** (325行) - 使用指南
  - CLI命令参考 (init, ingest, query, lint, sources)
  - Agent工具参数说明
  - 页面格式规范 (Frontmatter, 链接格式)
  - 与Obsidian集成说明

#### 3. 项目约定
- **AGENTS.md** (94行) - 项目知识库
  - nanobot项目目录结构
  - 代码约定 (Ruff、类型注解等)
  - 反模式和独特风格说明
  - 按任务定位代码的速查表

#### 4. 修复计划
- **.sisyphus/plans/wiki-fix-plan.md** (1507行)
  - Wave 1: 安全与基础结构 (4个任务)
  - Wave 2: 关键功能修复 (4个任务)
  - Wave 3: 功能完善 (4个任务)
  - Wave 4: 高级功能与测试 (5个任务)
  - Wave FINAL: 审查与交付 (4个任务)

#### 5. 代码评审报告
- **.sisyphus/drafts/wiki-code-review.md** (1038行)
  - 真实测试发现：Entities/Concepts提取完全失败 (0%匹配率)
  - 需求满足度：约70% (12项满足/6项部分/5项缺失)
  - 安全问题：路径遍历漏洞、文件大小无限制
  - P0/P1/P2问题分类

#### 6. 实现代码
- **nanobot/agent/tools/wiki.py** (1206行)
  - WikiTool类实现
  - 脆弱解析逻辑 (字符串匹配而非JSON)
  - 缺少Query归档功能
  - 缺少完整Lint检查

### 核心Schema定义 (来自AGENTS.md模板)

```markdown
# Wiki Schema结构
- raw/ - 原始源文档（只读）
- pages/ - LLM生成的页面
  - index.md - 内容目录
  - entities/ - 实体页面
  - concepts/ - 概念页面
  - sources/ - 源文档摘要
  - syntheses/ - 综合分析页面
- log.md - 操作日志
- AGENTS.md - Schema定义
```

### 关键发现

1. **Entities/Concepts提取完全失败** - 真实测试验证，解析逻辑依赖脆弱的字符串匹配
2. **Query无法归档答案** - 缺少syntheses页面生成机制
3. **Lint功能不完整** - 5项检查中3项未实现或过于粗糙
4. **安全问题** - 路径遍历、文件大小无限制、LLM调用无超时
5. **Schema与工作流脱节** - AGENTS.md只是静态模板

### JSON格式LLM Prompt参考

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


---

# 测试基础设施分析报告

## 分析时间
2026-04-20

## 1. 测试文件组织结构

### 现有测试文件列表 (24个)
```
tests/
├── test_azure_openai_provider.py  # Azure OpenAI提供商测试
├── test_base_channel.py           # 基础频道测试
├── test_cli_input.py              # CLI输入测试
├── test_commands.py               # 命令测试
├── test_config_paths.py           # 配置路径测试
├── test_consolidate_offset.py     # 合并偏移量测试
├── test_context_prompt_cache.py   # 上下文提示缓存测试
├── test_cron_service.py           # Cron服务测试
├── test_dingtalk_channel.py       # 钉钉频道测试
├── test_email_channel.py          # 邮件频道测试
├── test_feishu_post_content.py    # 飞书帖子内容测试
├── test_feishu_table_split.py     # 飞书表格分割测试
├── test_heartbeat_service.py      # 心跳服务测试
├── test_loop_save_turn.py         # 循环保存测试
├── test_matrix_channel.py         # Matrix频道测试
├── test_mcp_tool.py               # MCP工具测试
├── test_memory_consolidation_types.py  # 内存合并类型测试
├── test_message_tool.py           # 消息工具测试
├── test_message_tool_suppress.py  # 消息工具抑制测试
├── test_qq_channel.py             # QQ频道测试
├── test_slack_channel.py          # Slack频道测试
├── test_stock_analysis_libformula.py   # 股票分析公式测试
├── test_task_cancel.py            # 任务取消测试
├── test_telegram_channel.py       # Telegram频道测试
├── test_tool_validation.py        # 工具验证测试
└── AGENTS.md                      # 测试文档
```

### 命名规范
- **测试文件命名**: `test_<模块名>.py` 或 `test_<模块>_<子功能>.py`
- **测试函数命名**: `test_<被测功能>_<场景描述>()
- **异步测试**: 使用 `@pytest.mark.asyncio` 装饰器

## 2. pytest配置 (pyproject.toml)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 关键配置说明
- **asyncio_mode = "auto"**: 自动检测异步测试，无需手动标记每个测试函数
- **testpaths**: 指定测试目录为 tests/

## 3. Fixtures 模式

### 发现总结
- **无 conftest.py**: 项目没有使用 conftest.py 文件
- **Fixtures 定义位置**: 直接在测试文件中定义（使用 @pytest.fixture 装饰器）
- ** Fixtures 使用方式**: 通过参数注入使用

### Fixture 定义示例
```python
# test_commands.py 中的 fixture
@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.load_config") as mock_lc, \
         patch("nanobot.cli.commands.get_workspace_path") as mock_ws:
        
        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()
        
        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"
        
        mock_cp.return_value = config_file
        mock_ws.return_value = workspace_dir
        mock_sc.side_effect = lambda config: config_file.write_text("{}")
        
        yield config_file, workspace_dir
        
        if base_dir.exists():
            shutil.rmtree(base_dir)
```

### 另一个 Fixture 示例 (test_mcp_tool.py)
```python
@pytest.fixture(autouse=True)
def _fake_mcp_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """自动使用的 fixture，每个测试前执行"""
    mod = ModuleType("mcp")
    mod.types = SimpleNamespace(TextContent=_FakeTextContent)
    monkeypatch.setitem(sys.modules, "mcp", mod)
```

## 4. pytest-asyncio 使用模式

### 异步测试基本模式
```python
import pytest

@pytest.mark.asyncio
async def test_async_function() -> None:
    result = await some_async_function()
    assert result == expected_value
```

### 异步测试完整示例 (test_cron_service.py)
```python
@pytest.mark.asyncio
async def test_running_service_honors_external_disable(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    called: list[str] = []

    async def on_job(job) -> None:
        called.append(job.id)

    service = CronService(store_path, on_job=on_job)
    job = service.add_job(
        name="external-disable",
        schedule=CronSchedule(kind="every", every_ms=200),
        message="hello",
    )
    await service.start()
    try:
        await asyncio.sleep(0.05)
        external = CronService(store_path)
        updated = external.enable_job(job.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False

        await asyncio.sleep(0.35)
        assert called == []
    finally:
        service.stop()
```

### 异步测试要点
1. **使用 `@pytest.mark.asyncio`**: 即使配置了 `asyncio_mode = "auto"`，也建议显式标记
2. **async/await 语法**: 测试函数定义为 `async def`
3. **清理工作**: 使用 try/finally 确保资源清理
4. **超时控制**: 对于可能超时的操作，显式控制等待时间

## 5. Mock 和 Patch 使用模式

### 导入方式
```python
from unittest.mock import AsyncMock, MagicMock, Mock, patch
```

### 1. Monkeypatch 模式 (用于替换模块属性)
```python
@pytest.mark.asyncio
async def test_start_uses_request_proxy_without_builder_proxy(monkeypatch) -> None:
    config = TelegramConfig(...)
    bus = MessageBus()
    channel = TelegramChannel(config, bus)
    app = _FakeApp(lambda: setattr(channel, "_running", False))
    builder = _FakeBuilder(app)

    monkeypatch.setattr("nanobot.channels.telegram.HTTPXRequest", _FakeHTTPXRequest)
    monkeypatch.setattr(
        "nanobot.channels.telegram.Application",
        SimpleNamespace(builder=lambda: builder),
    )

    await channel.start()
    assert len(_FakeHTTPXRequest.instances) == 1
```

### 2. Patch 上下文管理器模式
```python
@pytest.fixture
def mock_paths():
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.load_config") as mock_lc:
        
        mock_cp.return_value = config_file
        yield config_file, workspace_dir
```

### 3. AsyncMock 用于异步函数
```python
async def test_something():
    with patch("module.async_function") as mock_func:
        mock_func.return_value = AsyncMock(return_value="mocked_result")
        result = await some_code()
        assert result == "mocked_result"
```

### 4. 假对象模式 (Fake Objects)
```python
class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []

    async def get_me(self):
        return SimpleNamespace(username="nanobot_test")

    async def send_message(self, **kwargs) -> None:
        self.sent_messages.append(kwargs)
```

### 5. Dummy/Doubles 模式
```python
class DummyProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)

    async def chat(self, *args, **kwargs) -> LLMResponse:
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(content="", tool_calls=[])
```

## 6. 测试模板和最佳实践

### 新建 Wiki 测试文件的推荐结构

```python
"""
Wiki 工具测试
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.agent.tools.wiki import WikiTool


class _FakeWikiClient:
    """Fake wiki client for testing."""
    
    def __init__(self) -> None:
        self.pages: dict[str, str] = {}
    
    def add_page(self, path: str, content: str) -> None:
        self.pages[path] = content
    
    async def get_page(self, path: str) -> str | None:
        return self.pages.get(path)


@pytest.fixture
def wiki_tool(tmp_path: Path) -> WikiTool:
    """Create a wiki tool instance with temp directory."""
    return WikiTool(wiki_root=tmp_path / "wiki")


@pytest.fixture
def mock_wiki_client(monkeypatch: pytest.MonkeyPatch) -> _FakeWikiClient:
    """Mock wiki client."""
    client = _FakeWikiClient()
    monkeypatch.setattr(
        "nanobot.agent.tools.wiki.WikiClient",
        lambda **kwargs: client
    )
    return client


class TestWikiTool:
    """Wiki tool test suite."""
    
    def test_init_creates_wiki_root_if_not_exists(self, tmp_path: Path) -> None:
        """Test that initialization creates wiki directory."""
        wiki_root = tmp_path / "new_wiki"
        assert not wiki_root.exists()
        
        tool = WikiTool(wiki_root=wiki_root)
        
        assert wiki_root.exists()
        assert wiki_root.is_dir()
    
    @pytest.mark.asyncio
    async def test_read_page_returns_content(
        self, 
        wiki_tool: WikiTool,
        mock_wiki_client: _FakeWikiClient
    ) -> None:
        """Test reading an existing wiki page."""
        mock_wiki_client.add_page("index.md", "# Home\n\nWelcome!")
        
        result = await wiki_tool.read_page("index.md")
        
        assert "# Home" in result
        assert "Welcome!" in result
    
    @pytest.mark.asyncio
    async def test_read_page_returns_not_found_for_missing(
        self,
        wiki_tool: WikiTool,
        mock_wiki_client: _FakeWikiClient
    ) -> None:
        """Test reading a non-existent page returns error message."""
        result = await wiki_tool.read_page("missing.md")
        
        assert "Error" in result or "not found" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_finds_matching_pages(
        self,
        wiki_tool: WikiTool,
        mock_wiki_client: _FakeWikiClient
    ) -> None:
        """Test searching wiki pages."""
        mock_wiki_client.add_page("python.md", "Python is great")
        mock_wiki_client.add_page("javascript.md", "JavaScript is async")
        
        result = await wiki_tool.search("python")
        
        assert "python.md" in result
```

### 测试设计原则

1. **单一职责**: 每个测试函数只测试一个概念
2. **显式断言**: 使用明确的断言语句，而非模糊的 `assert result`
3. **类型注解**: 所有测试函数添加返回类型注解 `-> None`
4. **文档字符串**: 测试类和测试函数都应有文档字符串
5. **临时目录**: 使用 `tmp_path` fixture 进行文件系统测试
6. **清理**: 使用 fixture 的 yield 模式或 try/finally 确保清理
7. **命名清晰**: 测试函数名描述行为和场景

### 常用 Fixtures

| Fixture | 来源 | 用途 |
|---------|------|------|
| `tmp_path` | pytest 内置 | 提供临时目录 |
| `monkeypatch` | pytest 内置 | 修改模块/对象属性 |
| `mock_paths` | 自定义 | Mock 配置路径 |
| `wiki_tool` | 自定义 | 创建工具实例 |

### 断言模式

```python
# 基本断言
assert result == expected

# 包含检查
assert "keyword" in result

# 类型检查
assert isinstance(result, str)

# 列表检查
assert len(items) == 3
assert "item" in items

# 异常检查
with pytest.raises(ValueError, match="error message"):
    function_that_raises()

# 异步异常
with pytest.raises(asyncio.CancelledError):
    await async_function_that_cancels()
```

## 7. 结论

1. **无 conftest.py**: 项目采用在每个测试文件中直接定义 fixture 的方式
2. **pytest-asyncio auto 模式**: 已配置 `asyncio_mode = "auto"`，支持自动异步检测
3. **多种 mock 模式**: monkeypatch、patch 上下文、Fake 对象、Dummy 对象等
4. **命名规范**: `test_<功能>_<场景>.py` 和 `test_<行为>_<结果>()`
5. **类型注解**: 项目要求所有函数添加类型注解

### 创建新测试的建议

1. 创建文件 `tests/test_wiki_tool.py`
2. 参考 `test_mcp_tool.py` 或 `test_cron_service.py` 的结构
3. 使用 `tmp_path` 进行文件操作测试
4. 使用 `monkeypatch` 或 `patch` 进行依赖注入
5. 使用 `_Fake*` 类模式创建假对象
6. 添加类型注解和文档字符串

---

# Task 4: 知识综合实现总结

## 完成时间
2026-04-20

## 实现内容

### 1. 新增的常量
- `PAGE_SYNTHESIS_SCHEMA`: JSON Schema定义知识综合输出结构
- `PAGE_SYNTHESIS_JSON_PROMPT`: LLM提示词模板，指导综合过程
- `PAGE_SYNTHESIS_MAX_TOKENS`: 综合操作的最大token限制

### 2. 新增的方法
`_synthesize_entity_page()` - 核心知识综合方法:
- 输入: 现有内容 + 新信息
- 输出: JSON格式的综合结果
- 功能: 
  - 使用LLM重新综合整页内容
  - 检测并记录矛盾信息
  - 处理冲突和重复信息
  - 返回结构化数据（overview, key_characteristics, significance, related_info, contradictions, sources_processed）

### 3. 修改的方法

#### `_generate_entity_page()`
- 现在使用知识综合而非简单追加
- 添加 `update_history` 到 frontmatter（JSON格式，记录每次更新的日期、来源和操作）
- 添加 `Contradictions` section到页面内容
- 保留所有历史sources引用
- 检查重复source，避免重复处理

#### `_generate_concept_page()`
- 使用相同的知识综合模式
- 重用 `_synthesize_entity_page()` 方法
- 相同的历史记录和矛盾处理
- 概念特定的页面结构（Definition, Key Aspects, Applications, Related Concepts）

### 4. 页面结构更新

#### 实体页面结构:
```markdown
# Entity Name

## Overview
[综合后的概述]

## Key Characteristics
- [特征1]
- [特征2]

## Significance
[重要性说明]

## Related Information
[相关信息]

## Contradictions
### Contradiction 1: [主题]
- **Source A**: [声明A]
- **Source B**: [声明B]
- **Resolution**: [解决方案]

---
*Sources: [[source1]], [[source2]]*
*Last updated: YYYY-MM-DD*
```

#### Frontmatter更新:
```yaml
---
title: Entity Name
created: YYYY-MM-DD
updated: YYYY-MM-DD
category: entities
tags: []
sources: [source1, source2]
update_history: '[{"date": "YYYY-MM-DD", "source": "source1", "action": "created"}]'
---
```

### 5. 测试验证
所有知识综合相关测试通过:
- test_generate_entity_page_creates_new_page ✓
- test_generate_entity_page_updates_existing ✓
- test_generate_concept_page_creates_new_page ✓
- test_generate_concept_page_updates_existing ✓

## 关键设计决策

1. **JSON结构化输出**: 使用 `_call_llm_json()` 方法确保LLM返回可解析的结构化数据
2. **错误回退**: 在综合失败时提供基本的回退内容，确保功能可用性
3. **历史记录**: 使用JSON格式存储更新历史，便于程序解析和人类阅读
4. **矛盾记录**: 在页面中显式记录矛盾，提高知识库的透明度和可信度
5. **去重机制**: 检查source是否已处理，避免重复添加相同信息

## 改进效果

相比原来的简单追加模式，新实现:
- ✓ 实现真正的知识综合而非机械追加
- ✓ 检测并记录不同来源的矛盾信息
- ✓ 维护完整的更新历史
- ✓ 保持页面结构一致性
- ✓ 保留所有历史source引用
- ✓ 防止重复处理相同source

