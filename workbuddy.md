# workbuddy.md

> 本文件为使用腾讯 WorkBuddy 开发本项目的对话上下文记录，用于核验 WorkBuddy 专项奖励条件。
> 由 WorkBuddy 会话上下文整理而成。

## 项目

- 名称：麦麦社交点餐套件（mcd-social-suite）
- 定位：基于麦当劳中国官方 MCP 的「拼单 / 团餐 / 派对 / 代送」四场景统一社交点餐 Skill
- 开发环境：腾讯 WorkBuddy（Agent 模式）
- 联调日期：2026-10-12（**全部工具均用有效 Token 完成真实调用**）
- 交付版本：v1.0.0

---

## 一、需求起点

用户提出：分析已有项目 `mcd-social-suite`（社交点餐套件），要求——

1. 使用麦当劳 MCP 真实调测，确认功能真实可用且无故障，并完善功能；
2. 完整检查功能、模拟测试确认可用，排查并解决功能与安全隐患，把旧配置更新到最新适配版本；
3. 推送发布到 GitHub 新建仓库，带版本号发布正式 release，并严格按官方要求提交报名。

用户明确约束：**禁止猜测，禁止使用过时落后被淘汰的旧配置，必须是真实有效的配置，
必须在麦当劳参考文档与 MCP 开发指导中真实查询到。**

## 二、调研与决策过程（WorkBuddy 完成）

1. 读取竞赛主仓库 README「开发 Skill」章节，确认参赛必需文件清单：
   README.md、CONTEST_DECLARATION.md（内容不可改）、MCP_INTEGRATION.md、源代码、workbuddy.md；
   报名 Issue 格式为「【参赛申请】+ 项目名称/项目地址/项目简介」，
   标题与正文间不加换行、地址不用 Markdown 链接。
2. 读取麦当劳 MCP Server 官方 README（`M-China/mcd-mcp-server`）与接入指南
   `https://open.mcd.cn/mcp/doc`，取得官方公布的工具表与配置 JSON。
3. 用有效 Token 直连 `https://mcp.mcd.cn` 做真实探测：
   `initialize` → `tools/list`（**35 个工具**）→ 核心工具逐个 `tools/call`，
   **以接口真实返回作为唯一事实来源**。
4. 以 grill-me 方式对四个关键分支逐项拍板（用户全部采纳推荐项）：
   - 外送/团餐/代送无法 live 验证 → **严格降级 + 预检**，绝不编造价格或门店；
   - 代送隐私 → **禁止写入他人 PII**，只做本人地址下单 + 脱敏交接；
   - 真实下单 → **停在付款前 + 缺参预检**，不创建真实订单；
   - 交付形态 → 沿用既有项目的 scripts + examples + references 范式。

## 三、关键转折：真实联调推翻了骨架的多条核心假设

| # | 骨架假设 | live 真实事实 |
|:---:|---|---|
| 1 | 工具名 `query-partystore-date` / `query-partystore-session` | **真实名 `query-party-store-date` / `query-party-store-session`**；官方 README 表格本身写错 |
| 2 | 工具共 33 个 | **35 个**；官方表格漏 `query-promotions`、`query-survey-coupon` |
| 3 | `query-meals(storeCode)` 单参即可 | 必传 `storeCode` + `orderType` + `beType` |
| 4 | `items` 形态无所谓 | 必须 `productCode` + `quantity`；`code`+`quantity` 会**静默返回 ¥0**（最危险） |
| 5 | 团餐只需「给人均和组合」 | 团餐是 `beType=6`，须先有 addressId 才能取 beCode，否则 `600020` / `600048` |
| 6 | 代送可以取地址直接下单 | 账号无地址；建档需真实姓名 + 11 位手机号（他人 PII） |
| 7 | 派对只需查到场次 | 场次有 `partyMin/partyMax/leftNum`，须校验人数区间；`party-order-create` 必填 `partyType` |

## 四、WorkBuddy 完成的实现

- `scripts/mcd_mcp_client.py`：协议层 + **items 入参守卫** + **0 元哨兵**。
  守卫直接拒绝 `num` / `code` 形态的 items，并在返回件数不符或应付 ≤ 0 时抛错，
  把「静默错价」这一高危故障挡在产出之前。
- `scripts/social_suite.py`：四场景引擎。拼单按 `query-meals` 官方描述中的
  **五档搭配规则**配餐，用 `calculate-price` 真实核价，再按菜单小计**加权分摊到分**
  （余数调平，合计严格守恒）。派对走六级链并校验人数区间。
  团餐/代送在无配送地址时**停止并回显实测错误码**。
- `scripts/build_report.py`：单文件 HTML 方案卡（内联样式、无外部依赖、全量转义）。
- `scripts/selftest.py`：40 项离线自检，含「文档无已淘汰工具名」的持续断言。
- `references/live-contract.md`：把全部 live 结论固化为契约，禁止凭记忆修改。

## 五、验证结论

- 拼单、派对两条链路端到端验证通过（真实门店、真实菜单、真实核价、真实场次）。
- 团餐、代送因账号无配送地址无法端到端验证，已如实标注并在引擎中实现降级停止。
- 下单工具只做缺参预检（`600010` / `600042` / `400`），**全链路未创建任何真实订单**。
- `selftest.py` 40/40 通过。

## 六、合规

- Token 仅在 `.env`（已 gitignore）与命令行参数中使用，未写入任何产出文件；
  selftest 持续断言源码与样例中无硬编码 Token、无未脱敏手机号。
- `CONTEST_DECLARATION.md` 使用官方原文，未作任何修改。
- 不跨品牌对比、不代用户支付、不录入他人个人信息。
