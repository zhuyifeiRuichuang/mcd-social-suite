# 更新日志 / Changelog

## v1.0.0 — 2026-10-12

首个正式版本。基于有效 Token 完成麦当劳 MCP 真实联调
（initialize → tools/list → 核心工具全量 tools/call），并依据真实返回重写全部字段口径、
判定规则与降级策略。

### 新增

- `scripts/mcd_mcp_client.py`：MCP Streamable HTTP 客户端（仅标准库，零依赖）。
  支持 `ping` / `tools-list` / `call` / `now-time` / `fetch-stores` / `fetch-menu` /
  `fetch-detail` / `fetch-coupons` / `price` / `fetch-party` / `precheck-delivery`；
  优先读取 `structuredContent`；401/429 明确提示，5xx 与网络错误自动重试；
  Token 优先级 `--token` > 环境变量 > `.env`。
  **新增两道防线**：`normalize_items()` 入参守卫 + `assert_price_sane()` 0 元哨兵。
- `scripts/social_suite.py`：四场景聚合引擎。
  - `split` 拼单：官方五档搭配规则 + `calculate-price` 真实核价 + 加权分摊到分（合计守恒）
  - `group` 团餐：`beType=6` 真实链路，无地址时严格降级停止
  - `party` 派对：六级链全通 + 人数区间/余位校验 + `party-order-create` 参数装配（不下单）
  - `proxy` 代送：只读预检 + 禁止他人 PII + 手机号脱敏交接卡
  - `precheck` / `scenarios`：外送可用性与能力矩阵
  - 全部子命令支持 `--demo` 离线模式（读 `examples/` 真实抓取样例）
- `scripts/build_report.py`：单文件 HTML 方案卡生成器（内联样式、无外部 CSS/JS、
  全量 HTML 转义防 XSS、缺失值显示「—」）。
- `scripts/selftest.py`：40 项离线测试（入参守卫 / 0 元哨兵 / 分账守恒 / 时段解析 /
  档位搭配 / 脱敏 / HTML 安全 / 凭证与 PII 断言 / 文档无过期工具名）。
- `references/live-contract.md`：live 实测契约（字段、语义、陷阱、降级证据）。
- `references/mcp-tools.md`：由 `tools/list` 响应**程序化生成**的工具清单（35 个）。
- `examples/`：2026-10-12 真实抓取数据 + 方案卡 + 两类故障留证。

### 依据真实接口修正（清除旧骨架的落后配置）

| # | 旧配置（错误/缺失） | live 真实接口事实 | 修正 |
|:---:|---|---|---|
| 1 | `SKILL.md` / `references/mcp-tools.md` 写 `query-partystore-date`、`query-partystore-session` | 真实工具名 **`query-party-store-date` / `query-party-store-session`**（官方 README 表格本身写错） | 全量改名；工具清单改为程序化生成；selftest 持续断言 |
| 2 | 工具清单 33 个（手抄官方表格） | live 实际 **35** 个，表格漏 `query-promotions`、`query-survey-coupon` | 由 `tools/list` 重建清单；补齐团餐促销源 |
| 3 | 工作流写 `query-meals(storeCode)` | 必传 `storeCode` + `orderType` + `beType` | 三参齐发，缺一不可 |
| 4 | 未定义 `items` 形态 | 必须 `productCode` + `quantity` | 守卫归一化；危险形态直接拒绝 |
| 5 | 未识别静默错价 | `items` 用 `code`+`quantity` → **`success:true` 且 `price=0`、`productList=[]`** | 新增 0 元哨兵：件数不符或应付 ≤ 0 直接报错 |
| 6 | 「拼单/团餐：给出人均与组合」的假流程 | 团餐是 `beType=6`，须 `delivery-query-stores` → `beCode` → `query-meal-assistance` → `query-promotions` → `calculate-price(gmServiceCode)` | 接真实链路；无地址时降级停止并回显 `600020`/`600048` |
| 7 | 代送「取用户地址下单」 | 账号无地址；`delivery-create-address` 需真实姓名+11 位手机号（他人 PII） | 改为只读预检；**禁止录入他人 PII**；手机号 `1XX****XXXX` 脱敏 |
| 8 | 派对未校验人数 | 场次返回 `partyMin` / `partyMax` / `leftNum` | 人数区间与余位校验，不可约原因原样回显 |
| 9 | 未提 `partyType` | `party-order-create` 必填 `partyType`（1 包场 / 2 拼团），且仅支持 `shopId=5` | 参数装配补齐并校验 shopId |
| 10 | 未用 `query-promotions` | 团餐满减/满折唯一真实来源 | 纳入团餐链路 |
| 11 | 未做缺参预检 | `create-order` 缺 `items` → `600010`；`orderType=1` 缺 `takeWayCode` → `600042`；`party-order-create` 缺参 → `400` | 用不完整参数验证服务端校验，全链路**未创建任何真实订单** |

### 验证记录（2026-10-12，有效 Token）

- `initialize` 通过（`protocolVersion 2025-06-18`，服务端无状态无 session-id）；`tools/list` 35 个工具。
- `now-time-info`：`2026-10-12 13:13:52`，`timezone GMT+08:00`。
- `query-nearby-stores`：上海市 + 南京东路 → 5 家；`longitude/latitude` 恒 `0.0` 已确认；
  `reservationTimeOptions` 命中「午餐 10:44至14:15」。
- `query-meals`：门店 1450104，分类若干 / **118 件餐品**；`currentPrice` 单位为元。
- `query-store-coupons`：2 张可用券（中薯条买一送一、王牌小食拼）。
- `calculate-price`：2 份大堡口福三件套 → `productPrice=4580` 分；
  用券核价 `2700 → 1350`，`discount=1350`。
- 故障留证：`code`+`num` → `600010`；`code`+`quantity` → **被接受且 `price=0`**（静默错价）。
- 派对六级链：spuId 1779（麦当劳奇妙生日派对，`shopId=5`，`partyPeople=5-12`，
  `partyAge=4-12`）→ 上海市(310100) → 华旭国际大厦餐厅(1450713，真实经纬度)
  → 2026-10-15~10-21 → 12:00-13:30 / 18:30-20:00，`price=5000` 分，`leftNum=12`。
- 拼单端到端：4 人 × 人均 30 → 应付 **¥114.00**，分摊 28.50/29.50/27.00/29.00（合计守恒）。
- 降级留证：`delivery-query-stores` `600020`；`query-meal-assistance` / `query-promotions` `600048`。
- 下单预检：`create-order` `600010` / `600042`；`party-order-create` `400`；均未建单。
- `selftest.py`：40/40 通过。
