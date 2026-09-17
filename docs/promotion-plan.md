# Agent Regression Kit：项目宣传与发布计划

## 中文版

### 1. 先把一句话说清楚

推荐定位：

> 给 AI Agent 的回归测试：记录真实工具行为，比较 baseline 和 candidate，在 CI 中阻断悄悄发生的回归。

英文定位：

> Regression tests for AI Agents: capture real tool behavior, compare reviewed baselines with candidates, and catch silent regressions in CI.

宣传时避免把项目说成“又一个 Agent 平台”或“通用 LLM 评分器”。最容易理解、也最有差异的切入点是：**Agent 行为的单元测试和回归测试**。

### 2. 先准备好 GitHub 页面

- README 第一屏放清楚：解决的问题、30 秒流程图、五分钟 Quick Start、真实 Agent 接入方式。
- 保留一个不需要 API Key 的确定性示例，让任何人 clone 后都能跑通。
- 给仓库加清晰的 Topics，例如 `ai-agents`、`agent-evaluation`、`regression-testing`、`mcp`、`llmops`。
- 每个版本保留 Git tag、CHANGELOG 和测试结果；v2.0 的发布说明要链接到新手指南。
- 建立一个 “good first issue” 入口，例如增加框架 Adapter、补充一个 Trace fixture、改进报告格式。

### 3. 用一个真实故事宣传

不要只说“支持 60 个测试”。更适合传播的演示是：

1. 一个订单 Agent 正常调用 `get_order`；
2. 修改代码后把订单号从字符串变成数字，或者错误地把“未发货”解释成“已发货”；
3. Agent Regression Kit 在 PR 中显示具体差异并让 CI 失败；
4. 开发者修复后，PR 恢复通过。

这个故事能让读者立刻理解项目价值：它不是替模型打分，而是证明一次改动有没有破坏已经能工作的行为。

### 4. 发布节奏

建议按一个小版本一个主题发布：

- v2.0：稳定配置契约、双语文档、CI 接入和可复现示例；
- v2.1：增加一个主流 Agent 框架的官方 Adapter 示例；
- v2.2：增加更多报告集成和贡献者友好的 fixture；
- v2.3：收集真实用户反馈后再决定是否做性能、成本或语义评测。

每次发布都准备四样东西：一句话、一个 GIF 或录屏、一个最小命令、一个失败案例。先让别人成功运行，再邀请他们贡献功能。

### 5. 可以发布到哪里

- GitHub Release：发布版本、变更、测试结果和 5 分钟指南链接。
- GitHub Discussions：开一个 “Show and tell” 或 “Integrate your Agent” 讨论，收集真实接入案例。
- MCP 相关社区：展示 MCP stdio/Streamable HTTP 的录制和回归场景。
- AI 工程社区：围绕 Agent 可靠性、工具调用回归、评测工程发布技术文章。
- 目标框架社区：分别写 LangChain、Spring AI、OpenAI SDK 或自研 Agent 的接入示例，不要只发通用宣传文案。
- 个人博客或公众号：用一次具体回归事故讲清楚 baseline、candidate、diff 和 CI gate。

不要一次复制同一段广告到所有社区。每个社区都应该带一个对应的示例、问题或可运行命令，并遵守该社区的发帖规则。

### 6. 可直接使用的中文发布文案

> 我们开源了 Agent Regression Kit：一个面向 AI Agent 的框架无关回归测试工具。它会记录 Agent 的工具调用、参数、工具结果和结构化 claims，把审核过的 baseline 与新版本 candidate 做结构化比较，并在 GitHub Actions 中阻断悄悄发生的行为回归。项目包含本地确定性 Fixture，不需要 API Key，clone 后几分钟即可跑通。适合正在使用 MCP 或自研工具调用 Agent、但不想每次改 Prompt 后靠人工看答案的团队。

### 7. 用数据判断宣传是否有效

每周记录这些指标：

- GitHub stars、forks、clone 次数；
- README 到 Quick Start 的点击和完成情况；
- 新 issue 中真实集成问题的数量；
- 外部项目是否开始引用或提交 Adapter；
- 从首次安装到第一次成功比较所需的时间。

最重要的早期信号不是 star 数，而是有人把自己的 Agent 接进来，并愿意反馈一个真实回归案例。

## English version

### 1. Make the positioning concrete

Recommended positioning:

> Regression tests for AI Agents: capture real tool behavior, compare reviewed baselines with candidates, and catch silent regressions in CI.

Do not present it as another general Agent platform or universal LLM scorer. The clearest wedge is **unit tests and regression tests for Agent behavior**.

### 2. Prepare the GitHub page

- Put the problem, 30-second flow, five-minute Quick Start, and real integration example above the fold.
- Keep a deterministic example that runs without an API key after cloning.
- Add focused repository topics such as `ai-agents`, `agent-evaluation`, `regression-testing`, `mcp`, and `llmops`.
- Keep a Git tag, changelog, and test result for every release; link the v2.0 release to the getting-started guide.
- Add a “good first issue” path: a framework adapter, a new Trace fixture, or a report improvement.

### 3. Promote one concrete story

Do not lead with “60 tests.” Show this instead:

1. An order Agent correctly calls `get_order`;
2. a code change sends the order ID with the wrong type, or misreads “not shipped” as “shipped”;
3. Agent Regression Kit shows the exact diff and fails the pull request;
4. the fix makes the pull request pass again.

The story makes the value obvious: this is not a model score; it is evidence that a code change did or did not break behavior that already worked.

### 4. Release cadence

Give each small release one theme:

- v2.0: stable config contract, bilingual documentation, CI integration, and reproducible examples;
- v2.1: an official adapter example for one mainstream Agent framework;
- v2.2: more report integrations and contributor-friendly fixtures;
- v2.3: decide on performance, cost, or semantic evaluation only after collecting real feedback.

For every release prepare four assets: one sentence, one GIF or short recording, one minimal command, and one failure case. Let people succeed before asking them to contribute.

### 5. Where to share it

- GitHub Release: version notes, changes, test results, and the five-minute guide.
- GitHub Discussions: a “Show and tell” or “Integrate your Agent” thread for real examples.
- MCP communities: demonstrate stdio and Streamable HTTP capture and regression scenarios.
- AI engineering communities: write about Agent reliability, tool-call regressions, and evaluation engineering.
- Framework communities: publish a LangChain, Spring AI, OpenAI SDK, or custom-Agent example instead of one generic announcement.
- Personal blog or newsletter: explain one concrete regression incident through baseline, candidate, diff, and CI gate.

Do not paste identical promotional copy everywhere. Bring a relevant example, question, or runnable command to each community and follow its posting rules.

### 6. Reusable English announcement

> We open-sourced Agent Regression Kit, a framework-neutral regression-testing layer for AI Agents. It captures tool calls, arguments, tool results, and structured claims, compares a reviewed baseline with a candidate run, and blocks silent behavior changes in GitHub Actions. The repository includes deterministic fixtures that run without an API key, so you can clone it and see the full flow in minutes. It is designed for teams using MCP or custom tool-calling Agents that do not want to inspect model answers manually after every prompt or code change.

### 7. Measure whether promotion works

Track weekly:

- GitHub stars, forks, and clones;
- clicks from the README to Quick Start and successful completions;
- real integration issues;
- external adapters or examples;
- time from first install to first successful comparison.

The strongest early signal is not star count. It is someone connecting a real Agent and reporting a real regression case.
