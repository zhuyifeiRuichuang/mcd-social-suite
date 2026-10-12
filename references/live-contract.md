# Live 实测契约（2026-10-12，禁止凭记忆修改）

> 本文档记录 `mcd-social-suite` 对麦当劳 MCP（`https://mcp.mcd.cn`，Streamable HTTP）
> 的**真实调用结论**。所有字段名、语义、边界均以 live 返回为唯一事实来源；
> 与官方 README、历史骨架或记忆冲突时，以本文档为准并在此留痕。

## 1. 协议层

| 项 | live 事实 |
|---|---|
| initialize | `protocolVersion: 2025-06-18` 通过；服务端**无状态**，initialize 不下发 `mcp-session-id` |
| 鉴权 | 单头 `Authorization: Bearer <TOKEN>` 即可通过账户/门店/点餐/派对全部工具 |
| 响应形态 | 同时带 `content[].text` 与 `structuredContent`；**优先取 `structuredContent`**，文本解析仅兜底 |
| 业务体 | `{success, code, message, datetime, traceId, data}`；`success=false` 时 `code` 携带业务错误码 |
| 工具数量 | **35**（官方 README 表格为 33，漏 `query-promotions`、`query-survey-coupon`） |
| 限流 | 单 Token 600 次/分钟；批量扇出保持 ≥0.15s 间隔 |

## 2. 工具名陷阱（旧骨架最大的错）

| 官方 README 表格（过期写法，不可用） | **live 真实工具名（唯一可用）** |
|---|---|
| `query-partystore-date`（过期写法） | **`query-party-store-date`** |
| `query-partystore-session`（过期写法） | **`query-party-store-session`** |

按官方表格的名字调用会直接失败。`mcd-social-suite` 的 `SKILL.md`、
`references/mcp-tools.md`、`MCP_INTEGRATION.md` 已全部改为真实名，
并由 `scripts/selftest.py` 的「文档无已淘汰工具名」用例持续断言。

## 3. 必填入参（缺一即失败）

| 工具 | 必填 |
|---|---|
| `query-meals` | `storeCode` + `orderType` + `beType` |
| `query-meal-detail` | `storeCode` + `orderType` + `beType` + `code` |
| `query-store-coupons` | `storeCode` + `orderType` + `beType` |
| `calculate-price` | `storeCode` + `orderType` + `beType` |
| `create-order` | `storeCode` + `orderType` + `beType`（另：`orderType=1` 必传 `takeWayCode`；`orderType=2` 必传 `addressId`） |
| `query-party-city` | `spuId` |
| `query-party-store` | `code`（城市 code，配合 `spuId` + 经纬度） |
| `query-party-store-date` | `spuId` + `storeCode` |
| `query-party-store-session` | `spuId` + `storeCode` + `dateStr` |
| `party-order-create` | `partyType` |

`beType` 枚举：`1` 到店自提 / `2` 麦乐送到家 / `5` 得来速 / `6` 企业团餐。
`orderType` 枚举：`1` 到店（含到店自取 + 得来速）/ `2` 外送（含麦乐送 + 企业团餐）。

## 4. calculate-price：items 形态与静默故障（本项目最高危项）

| items 形态 | live 结果 |
|---|---|
| `{"productCode": "…", "quantity": n}` | ✅ 正确核价 |
| `{"code": "…", "num": n}` | ❌ `600010 缺少商品code或者商品数量quantity不正确` |
| `{"code": "…", "quantity": n}` | ⚠️ **`success:true`，但 `price=0`、`productList=[]`** |

第三条是**静默错价**：服务端不报错，直接返回一个看似正常的「应付 ¥0.00」。
若直接采信会把 ¥114 的单报成 ¥0。证据见 `examples/real_price_faults.json`。

因此本项目在客户端硬编码两道防线：

1. `normalize_items()`：出现 `num` 或 `code` 键直接抛 `PriceGuardError`，并剔除未知键；
2. `assert_price_sane()`：`productList` 件数必须等于请求件数，且 `price > 0`，否则拒绝产出金额。

**用券核价**：券必须成对写在 item 内 —— `couponId` **且** `couponCode`。
只带 `couponCode` → `600010 使用优惠券需要couponId和couponCode`。
实测样本（`examples/real_price_coupon.json`）：中薯条买一送一
`productOriginalPrice=2700` → `productPrice=1350`，`discount=1350`。

### 返回字段与单位

`productOriginalPrice / productPrice / deliveryOriginalPrice / deliveryPrice /
packingOriginalPrice / packingPrice / tablewarePrice / originalPrice / discount / price`
**单位全部为分**；`productList[]` = `{productCode, productName, quantity, originalSubtotal, subtotal}`；
`takeWayList[]` = `{code, title, subtitle}`，实测到店场景返回
`eat-in`（堂食）与 `take-in-store`（外带）。

> 单位口径差异：`query-meals` 的 `currentPrice`/`originalPrice` 是**元**（字符串），
> `calculate-price` 是**分**。跨工具换算必须显式 ÷/×100。

## 5. query-meals

| 项 | live 事实 |
|---|---|
| 返回结构 | `{categories: [{name, meals:[{code, tags[]}]}], meals: {code: {name, image, currentPrice, originalPrice, discountType, canWithOrder}}}` |
| 实测规模 | 上海黄浦悦荟广场餐厅（1450104）：分类若干、**118 件餐品** |
| 价格单位 | **元**（字符串），如 `currentPrice: "33.5"` |
| tags | 本次 live **有返回** tags（如 `套餐`、`麦金卡`、`上新`）；但不可依赖，缺 tag 时按分类名归类 |
| 官方搭配档位 | 工具描述原文给出企业团餐搭配规则：20 元以下=小食；20-30=汉堡+小食 或 汉堡+饮料；30-40=汉堡+薯条/小食+饮料；40-50=汉堡+薯条+小食+饮料；50 以上=丰富组合且不重复小食。**本项目据此实现 `OFFICIAL_TIER_RULES`** |

## 6. 门店与时段

| 项 | live 事实 |
|---|---|
| `query-nearby-stores` | 单次**恒返回 5 家**，无分页；`longitude/latitude` **恒为 `0.0`**，不可用于地图渲染 |
| 入参 | `beType`（1/5）、`searchType`（1 收藏 / 2 按位置）、`city`、`keyword`；`searchType=2` 时 city+keyword 必填，缺 → `600058` |
| 时段黄金源 | `reservationTimeOptions[].{date, today, reservationOptionText}`，窗形如 `午餐(10:44至14:15)，下午茶(14:44至16:45)`；**今日已过时段不返回** |
| 实测 | 2026-10-12 13:13 命中「午餐 10:44至14:15」；次日条目含早餐 |

## 7. 派对链（六级，全通）

`mall-points-products(catRuleIds)` → `mall-product-detail(spuId)` → `query-party-city(spuId)`
→ `query-party-store(code, spuId, lat, lng)` → `query-party-store-date(spuId, storeCode)`
→ `query-party-store-session(spuId, storeCode, dateStr)`

| 环节 | live 事实 |
|---|---|
| 派对类目 | `catRuleIds=1>6>20`（生日类派对）、`1>6>21`（主题类派对）；实测返回 6 件 |
| 详情 | `mall-product-detail` 返回 `shopId`（**须为 5**）、`skuList[{skuId, price, points}]`、以及文档未强调的 `partyPeople`（`5-12`）、`partyAge`（`4-12`）、`partyRange`、`partyType` |
| 城市 | `data[] = {code, name, latitude, longitude}`；上海市 `code=310100` |
| 门店 | `data[] = {code, name, address, cityCode, distance, latitude, longitude}`，**派对域经纬度是真实值**（与 `query-nearby-stores` 的 0.0 不同） |
| 日期 | `data[] = {date, storeCode}`；实测 2026-10-15 ~ 10-21 |
| 场次 | `data[] = {id, timeStart, timeEnd, partyMin, partyMax, price, leftNum}`；`price` **单位分**（5000 = ¥50）；实测 `partyMin=5 / partyMax=12 / leftNum=12` |

`party-order-create` 必填 `partyType`：`1` 包场 / `2` 拼团；
完整入参 `partyType / spuId / skuId / code / storeCode / dateStr / id / timeStart / timeEnd / leftNum / count`。

## 8. 外送 / 团餐 / 代送：不可用与降级

| 工具 | live 结果 |
|---|---|
| `delivery-query-addresses` | 本账号返回 `{"addresses": []}` —— **没有任何可配送地址** |
| `delivery-query-stores(beType=6, addressId=…)` | `600020 配送地址不存在` |
| `query-meal-assistance(beType=6, 无 beCode)` | `600048 外送场景下，beType=2/5/6时必传beCode` |
| `query-promotions(beType=6, 无 beCode)` | `600048 外送场景下，beType=2/5/6时必传beCode` |

结论：团餐/麦乐送/代送三条腿**必须先有 addressId 才能拿到 beCode**，
在本文档产出时无法端到端验证。引擎对该类场景一律：

- 停止计算，**不输出任何门店、价格或可用性结论**；
- 回显已实测的错误码作为证据（`examples/real_group_errors.json`）；
- 提示用户去麦当劳官方 App/小程序添加本人地址后重跑。

## 9. 下单工具的缺参预检（停在付款前）

只发不完整参数以验证服务端校验确实存在，**从未发送过完整下单参数**：

| 用例 | live 结果 |
|---|---|
| `create-order` 缺 `items` | `600010 检查必填参数`（未建单） |
| `create-order` 有 `items` 缺 `takeWayCode`（orderType=1） | `600042 orderType=1时必须传takeWayCode`（未建单） |
| `party-order-create` 只有 `partyType` | `400 请求的数据格式错误`（未建单） |

证据见 `examples/real_order_precheck.json`。

## 10. 本项目判定规则（均可由上述证据复核）

1. **人数 vs 场次**：`people < partyMin` / `people > partyMax` / `people > leftNum` / `leftNum <= 0`
   任一成立即判「不可约」，并把原因回显到方案卡；不为凑数放宽规则。
2. **拼单档位**：直接采用 `query-meals` 官方描述中的五档搭配规则，不自行发明。
3. **分账**：以每人菜单小计加权分摊 `calculate-price` 的应付总额，
   余数逐分调平，**保证各人分摊之和严格等于应付总额**（`selftest.py` 有守恒断言）。
4. **时段**：仅采信门店 `reservationTimeOptions` 中 `today=true` 的窗口。
5. **代送**：禁止调用 `delivery-create-address` 录入他人姓名/手机号/地址；
   手机号一律 `1XX****XXXX` 脱敏。
6. **下单**：`create-order` / `party-order-create` 默认不调用，须用户显式确认。
