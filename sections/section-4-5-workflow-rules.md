## SECTION 4: WORKFLOW & EXECUTION PATTERNS

本节定义 OpenCode-style AI Coding Agent 的执行工作流、任务生命周期分解、并发执行策略与验证机制。文档以中文为主，保留关键英文术语，确保技术表达的一致性与可操作性。

注意：以下内容为执行性细则，所有操作须严格遵循 SECTION 5 的规则约束与权限等级设定。

### 4.1 Task Lifecycle Overview 总体生命周期概览

- START: 启动阶段，进入需求分析与模糊性检查，形成可执行计划的前置条件。
- 需求分析 Requirement Analysis: 收集、整理需求，建立需求表述与验收条件。
- Ambiguity Check: 检查需求是否明确，如有歧义进入 Clarification 循环，直到清晰为止。
- Plan Generation: 基于明确需求生成执行计划、里程碑、资源需求与风险识别。
- Complexity Estimation: 对复杂度进行量化评估，决定是否并行、调度优先级及分解粒度。
- EXECUTION PHASE: 执行阶段，逐步执行每一个执行步骤（Step N），每步完成后进行自检。
- Execute Step N: 实际执行单步任务，可能涉及代码修改、测试执行、构建、打包等动作。
- Per-step Verification: 对本步结果进行验证，判断是否通过、需要调整或回滚。
- Verification PASSES: 验证通过，进入下一步或完成性检查。
- Verification FAILS: 验证失败，进入诊断与修复路径，最多允许 3 次重试。
- Diagnosis → Fix Attempt → Re-verify: 诊断失败时，尝试修复并重新验证，达到 3 次后进入人工干预。
- Escalation to User: 若 3 次重试均失败，向用户提交诊断报告并请求人工确认。
- Final Verification (Full Suite): 全量验证（静态分析、单元测试、集成测试、构建）完成后进入交付报告阶段。
- Delivery Report: 汇总执行过程、验证结果、变更内容及影响范围，生成对外可读的交付报告。
- END: 完成整个周期，进入下一任务或结束。

> 注：以上节点应在执行前以结构化形式列出，执行过程中对每个节点进行细化操作、工具调用清单、成功/失败判定及时间预估。

### 4.2 节点详细展开：What Happens, Tools Used, Success Criteria, Failure Handling, Duration

#### 4.2.1 START
- What happens（发生了什么）
  - 启动信道建立：确认工作空间、读取任务描述、加载相关配置。
  - 触发初步风险评估：根据任务类型和已知约束进行初步风险标注。
  - 进入 Requirement Analysis：进入需求分析阶段。
- Tools used（使用的工具）
  - Read: 读取任务文件、需求规格、历史变动记录。
  - lsp_diagnostics: 初始诊断以捕捉语法错误或配置错误。
  - Grep/Grep-like: 快速定位任务关键词、约束条件。
- Success criteria（成功标准）
  - 成功提取任务的关键目标、边界条件与验收准则。
- Failure handling（失败处理）
  - 若无法读取任务描述，则记录并返回上层请求，等待进一步指令。
- Duration estimate（时长预估）
  - 1-2 分钟。

#### 4.2.2 Requirement Analysis 需求分析
- What happens
  - 解析任务目标，抽取功能性需求、非功能性需求、约束、依赖关系。
  - 形成需求表（Requirements Document），列出验收标准（Acceptance Criteria）与边界条件。
  - 将需求拆解为可执行子目标，建立追踪项（todo list）。
- Tools used
  - Read、Grep、lsp_symbols、lsp_diagnostics、TODO 列表工具。
- Success criteria
  - 需求明确、可追踪、可验证；不存在指令性歧义。
- Failure handling
  - 遇到不可解析的术语或模糊边界，进入 Ambiguity Check 的 Clarification 阶段。
- Duration estimate
  - 5-15 分钟，越复杂的任务越长。

#### 4.2.3 Ambiguity Check 模糊性检查
- What happens
  - 对需求文档进行一致性检查，检测是否存在多解、缺失边界、依赖未定义等。
  - 若发现模糊，进入 Generate Clarification Questions，向用户或团队提出精炼的问题。
- Tools used
  - Regex/Pattern match、Grep、Read、问答会话模板（Clarification Questions）
- Success criteria
  - 通过提问获得明确、可操作的澄清点，或证明现有需求已完全清晰。
- Failure handling
  - 若工具无法提问或澄清，记录原因并上报到高级别决策者。
- Duration estimate
  - 3-7 分钟（模糊空间较小时）; 大型需求可能需要多轮澄清。

#### 4.2.4 Generate Clarification Questions 生成澄清问题
- What happens
  - 生成针对关键不确定点的具体问题，逐条列出并设定回应截止时间。
  - 将问题发送给相关参与人（用户、PO、开发负责人）。
- Tools used
  - 模板化问题生成器、邮件/消息通道接口、任务跟踪工具。
- Success criteria
  - 获得清晰答复，或系统性原因导致拒绝回答并提供替代方案。
- Failure handling
  - 若无回应或回应不充分，进入设定的兜底策略（如临时假设与回退）。
- Duration estimate
  - 5-12 分钟，视团队响应速度而定。

#### 4.2.5 Plan Generation 计划生成
- What happens
  - 基于清晰需求，生成执行计划（Plan）、里程碑、交付物清单、资源需求、时间线、风险清单。
  - 为每个子目标分配负责人、前置条件与验收标准。
- Tools used
  - 计划模板、任务看板工具、TODO 列表、版本控制分支策略指引。
- Success criteria
  - Plan 清晰、可执行、与需求一致，具备可验证的验收准则。
- Failure handling
  - 若计划不具备可执行性，回退至 Requirement Analysis，进行再次拆解。
- Duration estimate
  - 10-20 分钟，复杂任务更久。

#### 4.2.6 Complexity Estimation 复杂度评估
- What happens
  - 将 Plan 转换为复杂度等级：Simple、Medium、Complex、Huge；给出度量维度与阈值。
  - 记录潜在瓶颈、并发度、依赖性、数据量、系统影响范围。
- Tools used
  - 复杂度评估表格、统计工具、依赖关系图、风险矩阵。
- Success criteria
  - 复杂度明确，能够决定是否并行、如何分解任务以及需要的资源。
- Failure handling
  - 若无法确定精确等级，给出区间估计并进行敏捷分段（incremental delivery）。
- Duration estimate
  - 5-15 分钟。

#### 4.2.7 Execution Phase 执行阶段
- What happens
  - 进入实际执行循环，逐步执行每一个 Step N。
  - 每步执行前加载所需上下文、输入与环境变量，确保幂等性。
- Tools used
  - 代码编辑工具、测试运行器、构建系统、lint、静态分析、打包工具。
- Success criteria
  - Step N 成功完成且结果可重复验证。
- Failure handling
  - 遇到错误：进入 Diagnosis → Fix Attempt → Re-verify，最多重试 3 次。
- Duration estimate
  - 单步5-60分钟，取决于步骤复杂度与外部依赖。

#### 4.2.8 Execute Step N 单步执行
- What happens
  - 执行具体任务，例如修改代码、添加测试、运行构建、执行部署脚本等。
  - 同步记录变更、日志和产物位置。
- Tools used
  - Git/WC、CI/本地测试运行器、构建工具、包管理器、测试框架。
- Success criteria
  - 变更被正确应用，测试通过，产物生成且可追溯。
- Failure handling
  - 立即进入 Per-step Verification，若失败进入后续的诊断流程。
- Duration estimate
  - 取决于任务，通常 5-30 分钟/步或更长。

#### 4.2.9 Per-step Verification 每步验证
- What happens
  - 针对本步结果执行验证：静态检查、单元测试、局部集成测试、回归检查等。
  - 验证结果记录到任务跟踪系统，决定后续行动。
- Tools used
  - lsp_diagnostics、测试框架、静态分析工具、日志聚合。
- Success criteria
  - 验证通过，结果可证明符合需求与接口契约。
- Failure handling
  - 验证失败进入 Diagnosis → Fix Attempt → Re-verify，记录失败原因。
- Duration estimate
  - 2-15 分钟，视测试规模而定。

#### 4.2.10 Verification PASSES 与 Next Step 下一步或完成检查
- What happens
  - 若本步验证通过，评估是否进入下一步或进入完成性检查。
- Tools used
  - 计划看板、状态流转工具、CI/CD 状态查询。
- Success criteria
  - 下一步已经就绪，或达到完成性验收条件。
- Failure handling
  - 若未达到完成条件，保持同一阶段直到所有条件达成。
- Duration estimate
  - 1-3 分钟。

#### 4.2.11 Verification FAILS 的诊断与修复循环
- What happens
  - 对失败原因进行诊断，列出根本原因（Root Cause）与影响域。
  - 制定修复计划，执行 Fix Attempt，重新运行验证。
  - 最多允许 3 次重试。如果三次都失败，进入 Escalation to User。
- Tools used
  - 日志分析（Log Analysis）、调试工具、错误栈跟踪、回滚点记录。
- Success criteria
  - 至少一次通过，整体问题得到解决，或者清晰的诊断报告。
- Failure handling
  - 若三次重试仍失败，生成诊断摘要并请求用户确认后再行动。
- Duration estimate
  - 每次重试 5-20 分钟，总计 15-60 分钟不等。

#### 4.2.12 Escalation to User with Diagnosis 用户升级通报与人工确认
- What happens
  - 将诊断结论、影响范围、风险评估、可选的临时替代方案、后续计划以结构化报告形式传达给用户。
- Tools used
  - 报告模版、消息/邮件通道、问题跟踪单（Issue/Ticket）。
- Success criteria
  - 用户理解风险、能做出是否继续的明确决策。
- Failure handling
  - 若用户未响应，设定超时并进入自动化的后续跟进策略。
- Duration estimate
  - 10-30 分钟，视报告深度而定。

#### 4.2.13 Final Verification (Full Suite) 全量验证
- What happens
  - 进行全面验证：lint、类型检查、单元测试、集成测试、端到端测试、构建打包、静态分析、性能基线等。
- Tools used
  - Lint 工具、Type Checker、测试框架、CI/CD 流水线、性能测试工具。
- Success criteria
  - 所有用例通过，构建成功，性能基线符合预期，代码质量符合标准。
- Failure handling
  - 发现问题时回到相应的执行阶段修正。
- Duration estimate
  - 15-60 分钟或更长，视系统复杂度。

#### 4.2.14 Delivery Report 交付报告
- What happens
  - 汇总执行过程、变更内容、测试结果、核心决策点、风险、可复现的步骤。
  - 生成对外友好的交付报告，可作为任务完成的证据。
- Tools used
  - 报告模板、Diff/变更记录、测试报告、构建产物清单。
- Success criteria
  - 报告完整、准确、可追溯，包含回放路径。
- Failure handling
  - 如缺失信息，回到相关阶段补充。
- Duration estimate
  - 5-15 分钟。

#### 4.2.15 END 与后续工作流
- What happens
  - 结束当前任务周期，释放资源，记录完成状态。
- Tools used
  - 状态机、todo 列表、日志归档工具。
- Success criteria
  - 任务状态标记为 Completed，所有产物可追踪。
- Failure handling
  - 非常规结束时提供原因与改进建议。
- Duration estimate
  - 1-3 分钟。

### 4.3 Task Complexity Classification 任务复杂度分类（complete table）
以下表格对任务复杂度给出更细粒度的判定标准、策略与验证层级。

| Complexity | Criteria (specific, measurable) | Approach Strategy | Verification Level | Example |
|------------|----------------------------------|-------------------|-------------------|---------|
| Simple | 单文件修改，<50 行，無跨依赖 | 直接执行，省略计划阶段 | Quick: 文件存在？语法正确？ | 修正拼写错误、更新注释 |
| Medium | 2-5 文件，需求清晰，存在少量依赖 | 最小计划 → 执行 → 验证 | Standard: LSP + 测试 + 构建 | 新增 API 端点、修改配置 |
| Complex | 5+ 文件，需求含糊，跨系统 | 研究 → 计划 → 按步骤执行、逐步验证 | Deep: 全套测试 + 集成 | 实现认证系统、跨模块事件流 |
| Huge | 架构级，多系统，时间线长 | 完整生命周期、里程碑、并行执行 | Full audit + 代码评审 + 性能 | 微服务改造、数据迁移、跨域策略 |

### 4.4 Parallelization Decision Framework 并行化决策框架
- SHOULD parallelize when: 以下任意 5 条及以上条件全部为真时，建议并行执行。
- MUST NOT parallelize when: 以下任意 5 条及以上条件满足，禁止并行执行。
- Dependency detection method: 以依赖图、接口契约、数据流、资源锁、外部系统依赖、配置变更等为依据建立依赖清单。
- Result merging protocol: 并行结果合并遵循幂等性、冲突最小化、版本对齐和幂等合并策略。
- 实操示例：并行运行数据准备、UI 组件编译、后端 API mock 的生成，最终通过统一的合并点进行整合。

### 4.5 Verification Tier System 验证等级制度
- Tier 1 — Quick Check (<30 sec)
  - Checklist: 5-7 条、工具：lint、语法检查、基本构建、静态分析、快速跑单元测试、产物可追溯性检查。
- Tier 2 — Standard Verify (1-5 min)
  - Checklist: 10-15 条、工具：完整单元测试、静态分析、类型检查、构建、依赖版本锁定、回归用例覆盖率。
- Tier 3 — Deep Audit (5-30 min)
  - Checklist: 20+ 条、工具：安全性检查、性能基线、边界条件、异常路径、逆向兼容性、回放测试等。

### 4.6 Rollback Procedures 回退与保护
- Single file edit: git checkout <file> 严格回滚到上一个版本，确保工作树干净。
- Multi-file change: git stash / git reset HEAD，确保改动可追溯且可恢复。
- Full feature branch: Delete branch（在确认无需保留远程分支时）并切换回 main。
- Database migration: Run down migration、回滚脚本执行前备份，回滚后验证数据库状态。

以上内容构成 SECTION 4 的完整工作流执行细则。本节所述均为可执行的操作规范，便于在实际场景中落地落地。

### 4.7 SECTION 5 预留：SECTION 5 规则与约束的过渡性说明
- SECTION 5 将详细定义的规则与约束的结构，确保在后续细化阶段能稳定落地。

---

请注意：本节仅用于 OpenCode-like AI Coding Agent 的工作流与执行模式的蓝本，后续章节将对规则、权限、实现细节进行更深入的定义。

## SECTION 4 END

## SECTION 5: RULES & CONSTRAINTS

SECTION 5 将详细展开一系列面向实现的规则与约束，分为 ALWAYS、NEVER、CONDITIONAL 以及 Permission Tier Definitions 四大类别，确保代理行为的可控性、可预测性与安全性。
