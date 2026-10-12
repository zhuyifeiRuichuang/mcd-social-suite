# MCP 接入说明 / `mcd-social-suite`

## MCP Server

- 名称：`mcd-mcp`
- 接入地址：`https://mcp.mcd.cn`
- 协议：Streamable HTTP
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`（Token 通过环境变量注入，禁止硬编码）
- 限流：单 Token 600 次/分钟；本引擎扇出时保持 ≥0.15s 间隔

配置示例见 `mcp-config.example.json`：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

## 使用的工具（全部 2026-10-12 live 验证）

| 工具 | 在本项目中的作用 | 验证状态 |
|---|---|---|
| `now-time-info` | 取官方服务器时间，用于时段判定 | ✅ |
| `query-nearby-stores` | 拼单/拼桌的门店定位（beType 1 到店 / 5 得来速） | ✅ |
| `query-meals` | 菜单与实时价；工具描述自带的五档搭配规则是拼单算法的依据 | ✅ |
| `query-meal-detail` | 套餐真实组成（rounds），用于核对「一份套餐到底有什么」 | ✅ |
| `query-store-coupons` | 门店可用券，命中购物车后做用券核价对比 | ✅ |
| `calculate-price` | **唯一**可信金额来源（商品/优惠/打包/配送/餐具/应付） | ✅ |
| `mall-points-products` | 派对商品发现（`catRuleIds=1>6>20,1>6>21`） | ✅ |
| `mall-product-detail` | 派对商品详情（`shopId=5` 校验、`partyPeople/partyAge`、`skuList`） | ✅ |
| `query-party-city` | 派对可参与城市 | ✅ |
| `query-party-store` | 派对可举办门店（**返回真实经纬度**） | ✅ |
| `query-party-store-date` | 门店可预约日期 | ✅ |
| `query-party-store-session` | 日期下场次（含 `partyMin/partyMax/leftNum/price`） | ✅ |
| `delivery-query-addresses` | 外送/团餐/代送可用性预检（只读） | ✅（返回空=不可用） |
| `delivery-query-stores` | 团餐(beType=6)/麦乐送(beType=2) 可配送门店与 beCode | ⚠️ 需 addressId |
| `query-meal-assistance` | 团餐助餐服务码 `gmServiceCode` | ⚠️ 需 beCode |
| `query-promotions` | 团餐满减/满折规则 | ⚠️ 需 beCode |
| `create-order` | 下单（**默认不调用**，须显式确认） | 缺参预检 ✅ |
| `party-order-create` | 派对下单（**默认不调用**，须显式确认） | 缺参预检 ✅ |

> ⚠️ = 依赖账号存在配送地址；本账号 `delivery-query-addresses` 返回空，
> 因此这三条腿只做到「预检 + 降级停止」，不产出任何编造结论。

## 调用流程

```
now-time-info ─┐
               ├─→ query-nearby-stores ─→ query-meals ─→ query-store-coupons ─→ calculate-price ─→ 分工分账
拼单 ──────────┘

派对 ─→ mall-points-products ─→ mall-product-detail ─→ query-party-city
     ─→ query-party-store ─→ query-party-store-date ─→ query-party-store-session ─→ 参数装配（不下单）

团餐 ─→ delivery-query-addresses ─→ delivery-query-stores(6) ─→ query-meal-assistance
     ─→ query-promotions ─→ query-meals(beType=6) ─→ calculate-price(gmServiceCode)

代送 ─→ delivery-query-addresses ─→（有地址才继续）delivery-query-stores(2) ─→ query-meals ─→ calculate-price
```

## 业务价值

多人吃麦当劳的四类需求（拼单、团餐、派对、代送）在官方 MCP 里分散在
**17 个工具、6 级派对链、4 种 beType 组合**之中，普通人根本拼不起来。
本 Skill 的价值是把这些真实数据收敛成一个可直接执行的决策结果：

- **拼单**：按官方五档搭配规则给出每人配置，并用 `calculate-price` 真实核价，
  再按每人菜单小计加权分摊到分（合计严格等于应付）。
- **派对**：六级链全通，自动校验人数是否落在 `partyMin/partyMax/leftNum` 区间，
  并把「不可约」的原因原样回显，不为凑数放宽规则。
- **团餐/代送**：无地址时**明确停止**并回显实测错误码，而不是编一个价格出来。

## 依据 live 修正的旧配置

| # | 旧配置（错误/过期） | live 真实 | 修正 |
|:---:|---|---|---|
| 1 | `query-partystore-date` / `query-partystore-session`（照抄官方表格） | 真实名 `query-party-store-date` / `query-party-store-session` | 全量改名，并由 selftest 持续断言 |
| 2 | 工具清单 33 个 | live **35** 个，官方表格漏 `query-promotions`、`query-survey-coupon` | 工具清单由 `tools/list` 程序化生成 |
| 3 | `query-meals(storeCode)` 单参 | 必传 `storeCode`+`orderType`+`beType` | 三参齐发 |
| 4 | 未定义 `items` 形态 | 必须 `productCode`+`quantity`；`code`+`quantity` 会**静默返回 ¥0** | 客户端守卫 + 0 元哨兵双重拦截 |
| 5 | 「团餐：给出人均与组合」的假流程 | 团餐需 `beType=6` + `beCode` + `gmServiceCode` + `query-promotions` | 接真实链路；无地址时降级停止 |
| 6 | 代送「取用户地址下单」 | 账号无地址；建档需他人 PII | 改为只读预检 + 禁止录入他人 PII + 脱敏交接 |
| 7 | 派对未校验人数 | 场次有 `partyMin/partyMax/leftNum` | 人数区间校验 + 不可约原因回显 |
| 8 | 未提 `partyType` | `party-order-create` 必填 `partyType`（1 包场 / 2 拼团） | 参数装配补齐 |

## 速率与合规

- 单 Token 每分钟上限 600 次请求；批量拆解/扇出时保持 ≥0.15s 间隔。
- 不输出真实 Token / 个人信息；配置文件仅用环境变量占位符。
- 餐品、价格、时段、场次、余位一律以官方实时结果为准。
- 涉及下单（`create-order` / `party-order-create` / `mall-create-order`）必须经用户明确确认，
  绝不代操作支付；本项目自测只做缺参预检，未创建任何真实订单。
- 代送场景禁止录入他人姓名/手机号/地址；输出中手机号一律 `1XX****XXXX` 脱敏。
