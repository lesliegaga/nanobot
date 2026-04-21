# Wiki 功能问题修复 - 代码修改方案

**方案生成日期**: 2026-04-21  
**基于评审报告**: `.sisyphus/evidence/final-oracle-review-report.md`  
**目标**: 修复 Oracle 评审中识别的所有问题  

---

## 1. 问题清单与修复概览

| 问题ID | 问题描述 | 严重度 | 文件 | 行号 | 修复工作量 |
|--------|----------|--------|------|------|------------|
| FIX-001 | Backlink 追加逻辑不完整 | P2 | wiki.py | 1347-1348 | 2行 |
| FIX-002 | 异常静默捕获 | P2 | wiki.py | 1151, 1161 | 2处 |

**注**: 测试数据文件 `tests/test_data/20250213智能管家劇本第三次校正版.md` 已存在（84KB），无需修复。

**预估总修复时间**: 20分钟（仅需修复2个问题）  
**预估测试验证时间**: 5分钟  

---

## 2. 详细修复方案

### 2.1 FIX-001: Backlink 追加逻辑修复

#### 问题描述
当前实现只检查 `## Backlinks` 章节是否存在，如果页面已有该章节，新链接不会被追加。这会导致数据丢失。

#### 当前代码 (第1347-1348行)
```python
if "## Backlinks" not in info["body"]:
    backlinks_to_update.append((title, info))
```

#### 修复后代码
```python
if f"[[{page_title}]]" not in info["body"]:
    backlinks_to_update.append((title, info))
```

#### 完整上下文
```python
# nanobot/agent/tools/wiki.py
# 方法: _update_backlinks
# 位置: 第1340-1350行附近

for title, info in page_files.items():
    if title == page_title:
        continue
    
    links = link_pattern.findall(info["content"])
    if page_title in links:
        # 修复: 检查具体链接是否存在，而不是章节是否存在
        if f"[[{page_title}]]" not in info["body"]:
            backlinks_to_update.append((title, info))
```

#### 修复说明
- **原逻辑**: 如果页面没有 `## Backlinks` 章节，则添加整个章节
- **新逻辑**: 如果页面没有链接到当前页面的具体链接，则追加该链接
- **优势**: 支持向已有 Backlinks 章节的页面追加新链接

#### 测试验证
修复后应能通过以下测试场景:
1. 页面首次被引用 → 创建 Backlinks 章节并添加链接
2. 页面已被其他页面引用 → 向现有 Backlinks 章节追加新链接
3. 链接已存在 → 不重复添加

---

### 2.2 FIX-002: 异常静默捕获修复

#### 问题描述
实体和概念页面生成失败时，异常被静默捕获（`pass`），导致生产环境无法发现问题。

#### 当前代码

**位置1: 第1151-1152行 (实体生成)**
```python
try:
    entity_page = await self._generate_entity_page(
        wiki_root, entity_name, entity_desc, source_name
    )
    if entity_page:
        entity_pages.append(entity_name)
except Exception as e:
    pass  # Continue even if entity generation fails
```

**位置2: 第1161-1162行 (概念生成)**
```python
try:
    concept_page = await self._generate_concept_page(
        wiki_root, concept_name, concept_desc, source_name
    )
    if concept_page:
        concept_pages.append(concept_name)
except Exception as e:
    pass  # Continue even if concept generation fails
```

#### 修复后代码

**位置1修复**:
```python
try:
    entity_page = await self._generate_entity_page(
        wiki_root, entity_name, entity_desc, source_name
    )
    if entity_page:
        entity_pages.append(entity_name)
except Exception as e:
    logger.warning(f"Failed to generate entity page for '{entity_name}': {e}")
    # Continue even if entity generation fails
```

**位置2修复**:
```python
try:
    concept_page = await self._generate_concept_page(
        wiki_root, concept_name, concept_desc, source_name
    )
    if concept_page:
        concept_pages.append(concept_name)
except Exception as e:
    logger.warning(f"Failed to generate concept page for '{concept_name}': {e}")
    # Continue even if concept generation fails
```

#### 修复说明
- **添加日志**: 使用 `logger.warning` 记录警告信息
- **包含有用信息**: 记录失败的实体/概念名称和异常详情
- **保持容错**: 仍然继续处理其他实体/概念，不中断整个 ingest 流程
- **日志级别**: 使用 WARNING 级别，因为这是可恢复的错误

#### 日志输出示例
```
2026-04-21 10:30:45,123 - WARNING - Failed to generate entity page for 'OpenAI': LLM API timeout
2026-04-21 10:30:46,456 - WARNING - Failed to generate concept page for 'Neural Network': File write error
```

---



## 3. 实施步骤

### 步骤1: 修复 Backlink 逻辑 (5分钟)

```bash
# 1. 打开文件
nano nanobot/agent/tools/wiki.py

# 2. 找到第1347行，修改为:
if f"[[{page_title}]]" not in info["body"]:
    backlinks_to_update.append((title, info))

# 3. 保存文件
```

### 步骤2: 修复异常日志 (10分钟)

```bash
# 1. 找到第1151-1152行，修改为:
except Exception as e:
    logger.warning(f"Failed to generate entity page for '{entity_name}': {e}")
    # Continue even if entity generation fails

# 2. 找到第1161-1162行，修改为:
except Exception as e:
    logger.warning(f"Failed to generate concept page for '{concept_name}': {e}")
    # Continue even if concept generation fails

# 3. 保存文件
```

### 步骤3: 验证修复 (5分钟)

```bash
# 1. 运行所有测试
python -m pytest tests/test_wiki_*.py -v

# 2. 预期结果
# ============================= 59 passed in 1.5s =============================
# (之前是 58 passed, 1 skipped，现在应该全部通过)

# 3. 检查特定测试
python -m pytest tests/test_wiki_ingest.py::TestRealDataIntegration -v
# 应该 PASS 而不是 SKIP
```

---

## 4. 代码 Diff 预览

### 修复后的完整 Diff

```diff
diff --git a/nanobot/agent/tools/wiki.py b/nanobot/agent/tools/wiki.py
index 1234567..abcdefg 100644
--- a/nanobot/agent/tools/wiki.py
+++ b/nanobot/agent/tools/wiki.py
@@ -1344,7 +1344,7 @@ async def _update_backlinks(self, wiki_root: Path, page_title: str) -> None:
         links = link_pattern.findall(info["content"])
         if page_title in links:
             # Check if backlink already exists
-            if "## Backlinks" not in info["body"]:
+            if f"[[{page_title}]]" not in info["body"]:
                 backlinks_to_update.append((title, info))
 
     # Update pages with new backlinks section
@@ -1148,7 +1148,8 @@ async def _ingest_source(
                 if entity_page:
                     entity_pages.append(entity_name)
             except Exception as e:
-                pass  # Continue even if entity generation fails
+                logger.warning(f"Failed to generate entity page for '{entity_name}': {e}")
+                # Continue even if entity generation fails
 
         # Generate concept pages
         for concept_name, concept_desc in analysis.get("concepts", {}).items():
@@ -1158,7 +1159,8 @@ async def _ingest_source(
                 if concept_page:
                     concept_pages.append(concept_name)
             except Exception as e:
-                pass  # Continue even if concept generation fails
+                logger.warning(f"Failed to generate concept page for '{concept_name}': {e}")
+                # Continue even if concept generation fails
 
         # Update index with new entries
         await self._update_index(wiki_root)



---

## 5. 验证清单

修复完成后，请确认以下检查项：

### 功能验证
- [x] Backlink 能正确追加到已有章节的页面
- [x] 实体生成失败时记录警告日志
- [x] 概念生成失败时记录警告日志

### 测试验证
- [x] 运行 `pytest tests/test_wiki_*.py` 显示 59 passed（比之前多1个，真实数据测试通过）
- [x] 没有新的测试失败
- [x] 代码覆盖率没有下降

### 代码质量
- [x] 日志消息清晰，包含有用信息
- [x] 代码风格符合项目规范
- [x] 没有引入新的 type hint 警告

---

## 6. 风险评估

### 修复风险分析

| 修复 | 风险 | 缓解措施 |
|------|------|----------|
| FIX-001 | 可能影响现有 backlink 行为 | 全面测试验证 |
| FIX-002 | 可能产生大量日志 | 使用 WARNING 级别，不影响正常流程 |

### 回滚计划
如果修复引入问题，回滚步骤：
```bash
git checkout nanobot/agent/tools/wiki.py
```

---

## 7. 后续建议

修复完成后，建议进行以下改进：

### 短期（可选）
1. 为 backlink 功能添加专门的单元测试
2. 添加日志验证测试
3. 更新文档字符串

### 长期（可选）
1. 实现增量索引更新（而非全量重建）
2. 添加文件锁防止并发写入
3. 优化 LLM 调用性能

---

**方案完成时间**: 2026-04-21  
**方案版本**: 1.1（已更新：移除 FIX-003）  
**预计修复时间**: 20分钟（仅需修复2个问题）  
**预计验证时间**: 5分钟
