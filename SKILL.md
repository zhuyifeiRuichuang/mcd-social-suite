---
name: mcd-social-suite
description: 麦当劳「麦麦社交点餐套件」Skill。把拼单、团餐、派对、代送四个分散的多人场景收敛成一个入口，用官方 MCP 真实数据产出「谁点什么、各摊多少、能不能办派对、怎么交接」的方案卡。适用于“8 人聚餐怎么点划算”“拼单点什么”“能不能办生日派对”“异地给朋友代送一份”“团餐怎么配”等需求。
---

# 麦麦社交点餐套件 / McSocialSuite

多人吃麦当劳的需求天然是散的：拼单要算人头、团餐要看满减、派对要查场次余位、代送要交接。
本 Skill 把它们收敛成一个入口，**全部结论由麦当劳官方 MCP 真实返回推导**，
并给出可直接执行的分工与分账方案。

## 何时使用

- 用户说：多人聚餐怎么点、N 人聚餐划算、拼单、团餐、能不能办派对、异地代送、AA 怎么算
- 用户有**多人/社交**场景的点餐、预约或履约需求

## 前置条件

- 麦当劳中国 MCP Token（https://open.mcd.cn/mcp），配置 `mcd-mcp`（见 `mcp-config.example.json`，
  Token 用环境变量 `MCD_MCP_TOKEN` 占位，**禁止硬编码**）
- 无 Token 时可用 `--demo` 读取 `examples/` 下的真实抓取样例跑通全流程

## 核心原则

1. **一入口四场景**：拼单 / 团餐 / 派对 / 代送统一入口，不各说各话。
2. **真实数据**：菜单、价格、时段、场次、余位一律来自官方 MCP，不估算、不补零。
3. **真实履约**：派对走 `query-party-*` 六级链，核价走 `calculate-price`，不做假流程。
4. **核价守卫**：`items` 只用 `productCode`+`quantity`；返回件数不符或应付 ≤ 0 直接报错。
5. **停在付款前**：任何下单/支付须用户明确确认。
6. **隐私脱敏**：禁止录入他人 PII；手机号一律打码。

## 标准工作流

### 第 1 步：识别场景与约束

问清：人数、预算（人均）、场景（拼单/团餐/派对/代送）、忌口、城市与位置。
四场景的分流规则见「场景路由」一节。

### 第 2 步：定位门店与时段

```
now-time-info                 → 官方服务器时间
query-nearby-stores           → 门店（beType 1 到店 / 5 得来速）
   └─ reservationTimeOptions  → 当前时段（唯一可信时段源）
```

### 第 3 步：按场景取数

| 场景 | 工具链 |
|---|---|
| 拼单 | `query-meals` → `query-store-coupons` → `calculate-price` |
| 团餐 | `delivery-query-addresses` → `delivery-query-stores(beType=6)` → `query-meal-assistance` → `query-promotions` → `query-meals(beType=6)` → `calculate-price(gmServiceCode)` |
| 派对 | `mall-points-products(catRuleIds=1>6>20,1>6>21)` → `mall-product-detail` → `query-party-city` → `query-party-store` → `query-party-store-date` → `query-party-store-session` |
| 代送 | `delivery-query-addresses` →（有地址才继续）`delivery-query-stores(beType=2)` → `query-meals(orderType=2)` → `calculate-price` |

### 第 4 步：产出方案卡

```
python scripts/social_suite.py split --city 上海市 --keyword 南京东路 \
    --people 8 --per-budget 30 [--avoid 香菜,花生] --out plan.json
python scripts/social_suite.py party --spu-id 1779 --city-keyword 上海市 \
    --date 2026-10-15 --people 8 --party-type 2 --out party.json
python scripts/build_report.py --plan plan.json --party party.json \
    --group group.json --proxy proxy.json --precheck precheck.json --out report.html
```

方案卡含：门店与时段、购物车、官方核价、**分工与分账（精确到分）**、
派对场次与不可约原因、团餐/代送降级告警。

### 第 5 步：停在付款前

> 方案已就绪，未下单。`create-order` / `party-order-create` 须你明确确认后才会调用。

**未经确认绝不调用任何下单工具。**

## 场景路由

| 场景 | 触发词 | 已 live 验证 | 前置条件 |
|---|---|---|---|
| 拼单 `split` | 拼单、AA、一起吃、几个人点 | ✅ | 门店（city + keyword） |
| 派对 `party` | 生日派对、主题派对、办派对、拼团/包场 | ✅ | 派对商品 spuId（默认取列表首个） |
| 团餐 `group` | 团餐、企业团餐、公司订餐 | ⚠️ 降级 | **账号须有配送地址** |
| 代送 `proxy` | 代送、给朋友点一份、异地送 | ⚠️ 降级 | **账号须有配送地址**；且禁止录入他人 PII |

⚠️ 的场景在无配送地址时**停止并回显已实测错误码**（`600020` / `600048`），
绝不输出编造的门店或价格。用户添加本人配送地址后自动恢复完整链路。

## 硬约束（违反即为缺陷）

1. `calculate-price` 的 `items` **必须** `{productCode, quantity}`。
   `{code, quantity}` 会被服务端**静默接受并返回 ¥0.00** —— 已由守卫拦截。
2. 用券必须同一 item 内同时带 `couponId` 与 `couponCode`，只带其一 → `600010`。
3. `query-meals` / `query-meal-detail` / `query-store-coupons` / `calculate-price` /
   `create-order` 均必传 `storeCode` + `orderType` + `beType`。
4. 派对工具真实名为 **`query-party-store-date`** / **`query-party-store-session`**；
   官方 README 表格里的 `query-partystore-*` 是**过期写法**，不可用。
5. `party-order-create` 仅支持 `shopId=5` 的商品，且必传 `partyType`（1 包场 / 2 拼团）。
6. **禁止**调用 `delivery-create-address` 录入他人姓名/手机号/地址。
7. 不输出他人明文手机号/住址到可分享内容；手机号一律 `1XX****XXXX`。
8. 不跨品牌对比；不代用户支付；单 Token ≤ 600 次/分钟。

## 输出要求

- 必须区分场景并给出对应履约路径。
- 团餐/代送在降级时必须显式说明「为什么停」以及「如何恢复」。
- 每次输出含：非官方产品、价格与供应以官方实时为准、不跨品牌对比。

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本工作流定义 |
| `MCP_INTEGRATION.md` | MCP 接入说明 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方文件，内容不可改） |
| `mcp-config.example.json` | 配置示例（仅环境变量占位符） |
| `references/live-contract.md` | **live 实测契约**（禁止凭记忆修改） |
| `references/mcp-tools.md` | 由 `tools/list` 程序化生成的工具清单 |
| `scripts/mcd_mcp_client.py` | MCP 客户端 + items 守卫 + 0 元哨兵 |
| `scripts/social_suite.py` | 四场景聚合引擎 |
| `scripts/build_report.py` | 单文件 HTML 方案卡生成器 |
| `scripts/selftest.py` | 离线自检（40 项） |
| `examples/` | 2026-10-12 真实抓取样例与方案卡 |
