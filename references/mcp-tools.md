# 麦当劳 MCP 工具清单（由 live `tools/list` 程序化生成）

> 生成时间：2026-10-12　·　来源：`tools/list` 实调（**35 个工具**）　·　接入地址 `https://mcp.mcd.cn`　·　协议 Streamable HTTP
>
> ⚠️ 官方 README 的工具表格存在两处过期，以本文件为准：
>
> 1. 官方表格写作 `query-partystore-date` / `query-partystore-session`，**真实工具名为 `query-party-store-date` / `query-party-store-session`**（含连字符）。
> 2. 官方表格未收录 `query-promotions`、`query-survey-coupon`。
>
> 本文件由脚本从 `tools/list` 真实响应生成，禁止手抄或凭记忆修改。

| Tool | 说明 | 必填入参 |
|---|---|---|
| `auto-bind-coupons` | 自动领取麦麦省所有当前可用的麦当劳优惠券。无需指定具体的优惠券和couponId，系统会自动领取用户可领的所有券。当用户说"帮我领券"、"自动领取优惠券"、"一键领券"时使用此工具… | — |
| `available-coupons` | 查询用户当前可领取的麦麦省的优惠券列表。返回券名称、图片、状态和促销标签。当用户询问有什么优惠、可以领什么券时使用此工具。 | — |
| `calculate-price` | 计算商品的价格（含优惠），支持到店自提(orderType=1)和外送(orderType=2)两种场景 | `storeCode`, `orderType`, `beType` |
| `campaign-calendar` | 查询麦当劳中国当月的营销活动日历，返回进行中、往期和未来日期的活动。适用于查看用户进行中和即将到来的可参与活动，还可查询用户对活动的订阅状态。 | — |
| `cancel-order` | 取消订单，非商城订单 | `orderId`, `cancelReasonCode` |
| `create-order` | 创建麦当劳订单，支持到店(orderType=1)和外送(orderType=2)两种场景下单, 必须先确定订单类型，必填 (1：到店，2外送) | `storeCode`, `orderType`, `beType` |
| `delivery-create-address` | 创建用户配送地址 | `address`, `addressDetail`, `city`, `contactName`, `phone` |
| `delivery-query-addresses` | 外送场景下，查询用户配送地址列表 | — |
| `delivery-query-stores` | 外送场景下，用户选择完地址后，需要根据地址ID，查询用户当前地址可配送的门店 | `beType`, `addressId` |
| `draw-lottery` | 使用后台配置的抽奖消耗规则参加一次当前积分抽奖并返回结果，服务端原子完成次数或积分扣减与抽奖。 | — |
| `list-nutrition-foods` | 获取麦当劳常见餐品的营养成分数据，包括能量、蛋白质、脂肪、碳水化合物、钠、钙等信息，当用户咨询麦当劳餐品的热量、营养，帮助用户搭配指定热量套餐时有用 | — |
| `mall-create-order` | 创建积分兑换订单，仅支持shopId=2（从 mall-product-detail 获取） - 当用户询问"用积分兑换这个商品"、"兑换这个券"、用户确认兑换商品时使用,切记：如… | `skuId`, `spuCategory` |
| `mall-order-detail` | 查询麦麦商城订单详情 | `orderId` |
| `mall-order-list` | 查询麦麦商城订单列表 | — |
| `mall-points-products` | 查询可兑换餐品券列表 - 当用户询问"有哪些积分兑换商品"、"积分可以兑换什么"、"查看积分商城"时使用 | — |
| `mall-product-detail` | 查询积分兑换商品详情 - 当用户询问"这个商品详情是什么"、"查看商品详细信息"、用户点击商品查看详情时使用 | `spuId` |
| `now-time-info` | 获取当前时间信息 - 返回当前服务器的完整时间信息，包括： | — |
| `order-list` | 查询麦当劳历史订单，非商城订单，商城订单需要使用mall-order-list | — |
| `party-order-create` | 创建生日类派对/主题类派对/麦麦体验营/品鉴会/读书会/积分兑换活动, 仅支持shopId=5（从 mall-product-detail 获取）的调用， | `partyType` |
| `query-lottery-info` | 查看当前积分抽奖活动信息，包括活动基本信息、抽奖消耗规则、单次所需积分、剩余可抽次数、当前可用积分与公开奖品列表，不执行抽奖。 | — |
| `query-meal-assistance` | 仅支持企业团餐场景(beType=6)在calculate-price前需要获取当前门店可用的助餐服务 | `storeCode` |
| `query-meal-detail` | 餐品详情, 支持到店自提(orderType=1)和外送(orderType=2)两种场景 | `storeCode`, `orderType`, `beType`, `code` |
| `query-meals` | 餐品列表, 支持到店自提(orderType=1)和外送(orderType=2)两种场景 | `storeCode`, `orderType`, `beType` |
| `query-my-account` | 查询用户积分账户详情 - 当用户询问"我有多少积分"、"查下我的积分"、"积分余额"、"查询过期积分"时使用 | — |
| `query-my-coupons` | 获取用户卡包中的优惠券资产信息，用于“我有什么券 / 券详情查看”等展示与管理场景。 注意：该接口返回的是用户拥有的券，不进行门店、渠道、配送方式等下单规则校验，因此不承诺可用于当… | — |
| `query-my-prizes` | 查询当前登录会员通过积分抽奖获得的本期及历史奖品（可用/已使用/已过期/已领取/已失效）。 | — |
| `query-nearby-stores` | 到店场景下，查询用户可点餐门店，需要用户明确是到店自取还是车道取餐 | `beType`, `searchType` |
| `query-order` | 查询订单详细信息 | `orderId` |
| `query-party-city` | 活动派对商品配置场次城市列表, 必须先确定spuId(从 mall-points-products 获取）或查询商品详情（从 mall-product-detail 获取) | `spuId` |
| `query-party-store` | 查询指定城市下支持主题派对的门店列表。当用户选择了城市后，需要查看该城市有哪些门店可举办生日类派对/主题类派对/麦麦体验营/品鉴会/读书会/积分兑换活动时使用 | `code` |
| `query-party-store-date` | 查询指定门店支持生日类派对/主题类派对/麦麦体验营/品鉴会/读书会/积分兑换活动的可预约日期列表。当用户选择了门店后，需要查看该门店哪些日期可预约时使用。 | `spuId`, `storeCode` |
| `query-party-store-session` | 查询指定门店、指定日期下的生日类派对/主题类派对/麦麦体验营/品鉴会/读书会/积分兑换活动场次列表。当用户选择了日期后，需要查看当天有哪些场次可预约时使用。 | `spuId`, `storeCode`, `dateStr` |
| `query-promotions` | 查询当前门店企业团餐场景下可用的促销规则（满减/满折），仅返回当前时间有效且适用在售餐品的规则原始数据 | `storeCode`, `orderType`, `beType` |
| `query-store-coupons` | 查询【指定门店+订单类型】下可使用的优惠券，支持到店(orderType=1,含到店自取和得来速)和外送(orderType=2,含麦乐送和团餐) | `orderType`, `beType`, `storeCode` |
| `query-survey-coupon` | 按订单号查询当前 MCP 用户本人订单的 CSAT 满意度答卷，并返回该订单关联奖券的标题、核销时间、核销状态和点餐方式。 | `orderId` |

## 关键入参速查（本项目实际调用的工具）

### `now-time-info`

- 必填：无（无必填）

### `query-nearby-stores`

- 必填：`beType`, `searchType`
- `beType`（必填）：beType必传，1：到店自提, 5-得来速车道取餐(Drive Through)　取值 `[1, 5]`
- `city`：城市名
- `keyword`：关键词
- `searchType`（必填）：searchType=2 按位置进行搜索， searchType=1 搜索收藏餐厅，默认searchType=1　取值 `[1, 2]`

### `query-meals`

- 必填：`beType`, `orderType`, `storeCode`
- `beCode`：业务编码，与storeCode 配对使用，从query-nearby-stores或delivery-query-stores返回结果中获取。得来速(beType=5)/外送(orderType=2)/团餐场景必传，到店自取(beType=1)场景不传
- `beType`（必填）：1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐　取值 `[1, 2, 5, 6]`
- `orderType`（必填）：订单类型，1-到店（含到店自取+得来速车道取餐），2-外送（含麦乐送+企业团餐）　取值 `[1, 2]`
- `reservationDate`：预约场景必传，非预约场景不传。格式:yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码（storeCode）, 不能为空

### `query-meal-detail`

- 必填：`beType`, `code`, `orderType`, `storeCode`
- `beCode`：业务编码，与storeCode 配对使用，从query-nearby-stores或delivery-query-stores返回结果中获取。得来速(beType=5)/外送(orderType=2)/团餐场景必传，到店自取(beType=1)场景不传
- `beType`（必填）：1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐　取值 `[1, 2, 5, 6]`
- `code`（必填）：餐品唯一编码，快餐门店内唯一标识单个餐品的编码
- `orderType`（必填）：到店自提场景:orderType=1 && beCode 是个无效参数，不要传，传了会报错；外送场景:orderType=2 && beCode 为delivery-query-address中的beCode；得来速(DT)场景：orderType=1 && beCode 为query-nearby-store中的be…　取值 `[1, 2]`
- `reservationDate`：预约场景必传，非预约场景不传。格式:yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码（storeCode）, 不能为空

### `query-store-coupons`

- 必填：`beType`, `orderType`, `storeCode`
- `beCode`：业务编码，与storeCode 配对使用，从query-nearby-stores或delivery-query-stores返回结果中获取。得来速(beType=5)/外送(orderType=2)/团餐场景必传，到店自取(beType=1)场景不传
- `beType`（必填）：1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐　取值 `[1, 2, 5, 6]`
- `orderType`（必填）：订单类型, 1-到店（含到店自取+得来速车道取餐），2-外送（含麦乐送+企业团餐）　取值 `[1, 2]`
- `reservationDate`：预约场景必传，非预约场景不传。格式 yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码必须全部由数字组成

### `calculate-price`

- 必填：`beType`, `orderType`, `storeCode`
- `beCode`：业务编码，与storeCode 配对使用，从query-nearby-stores或delivery-query-stores返回结果中获取。得来速(beType=5)/外送(orderType=2)/团餐场景必传，到店自取(beType=1)场景不传
- `beType`（必填）：1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐　取值 `[1, 2, 5, 6]`
- `gmServiceCode`：团餐-助餐服务码
- `items`：待价格计算的商品列表
- `needTableware`：是否需要餐具，true需要，false不需要
- `orderType`（必填）：订单类型，1-到店（含到店自取+得来速车道取餐），2-外送（含麦乐送+企业团餐）　取值 `[1, 2]`
- `reservationDate`：预约场景必传，非预约场景不传。格式:yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码（storeCode）, 不能为空
- `withOrder`：随单购商品

### `create-order`

- 必填：`beType`, `orderType`, `storeCode`
- `addressId`：配送地址id，外送or团餐的地址
- `beCode`：业务编码，与storeCode 配对使用，从query-nearby-stores或delivery-query-stores返回结果中获取。得来速(beType=5)/外送(orderType=2)/团餐场景必传，到店自取(beType=1)场景不传
- `beType`（必填）：1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐　取值 `[1, 2, 5, 6]`
- `gmServiceCode`：企业团餐场景(beType=6)下，必传，参数来自query-meal-assistance
- `items`：待价格计算的商品列表
- `needTableware`：是否需要餐具，true需要，false不需要
- `orderType`（必填）：订单类型，1-到店（含到店自取+得来速车道取餐），2-外送（含麦乐送+企业团餐）　取值 `[1, 2]`
- `remark`：订单备注（选填，最多50字），如"无接触配送"，仅orderType=2场景下需要引导用户填写
- `reservationDate`：预约场景必传，非预约场景不传。格式:yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码（storeCode）, 不能为空
- `takeWayCode`：到店/得来速场景(orderType=1)必传，外送/团餐场景(orderType=2)不传。值从 calculate-price 返回的takeWayList[].code 中选取
- `withOrder`：随单购商品

### `delivery-query-addresses`

- 必填：无（无必填）

### `delivery-query-stores`

- 必填：`addressId`, `beType`
- `addressId`（必填）：地址ID，来源delivery-query-address
- `beType`（必填）：beType：2: 麦乐送，6：团餐

### `query-meal-assistance`

- 必填：`storeCode`
- `beCode`：BE编码（Business Entity Code）
- `beType`：固定传 6（企业团餐），此接口仅团餐场景使用　取值 `[6]`
- `orderType`：到店自提场景: orderType=1 && beCode 是个无效参数，不要传，传了会报错
- `reservationDate`：预约时间，仅当用户要预约下单时，该字段必传，格式形如 2020-08-08 09:30
- `storeCode`（必填）：门店编码（storeCode）, 不能为空

### `query-promotions`

- 必填：`beType`, `orderType`, `storeCode`
- `beCode`：业务编码，与storeCode 配对使用，团餐场景必传（从 delivery-query-stores 获取）
- `beType`（必填）：业务类型，固定传 6（企业团餐）　取值 `[6]`
- `orderType`（必填）：订单类型，团餐场景固定传 2（外送）　取值 `[2]`
- `reservationDate`：预约场景必传，非预约场景不传。格式:yyyy-MM-dd HH:mm
- `storeCode`（必填）：门店编码（storeCode）, 不能为空

### `mall-points-products`

- 必填：无（无必填）
- `catRuleIds`：类目规则筛选，支持多选（逗号分隔），非必传，不传时默认查询所有类型。

### `mall-product-detail`

- 必填：`spuId`
- `spuId`（必填）：商品SPU ID，需要从查询可兑换餐品券列表让用户选择一个spu才可以

### `query-party-city`

- 必填：`spuId`
- `spuId`（必填）：spuId

### `query-party-store`

- 必填：`code`
- `code`（必填）：城市code
- `latitude`：纬度，从 query-party-city 返回结果的 data[].latitude 获取
- `longitude`：经度，从 query-party-city 返回结果的 data[].longitude 获取
- `spuId`：spuId，从 mall-points-products 或 mall-product-detail 获取

### `query-party-store-date`

- 必填：`spuId`, `storeCode`
- `spuId`（必填）：spuId
- `storeCode`（必填）：门店code

### `query-party-store-session`

- 必填：`dateStr`, `spuId`, `storeCode`
- `dateStr`（必填）：门店日期
- `spuId`（必填）：spuId
- `storeCode`（必填）：门店code

### `party-order-create`

- 必填：`partyType`
- `code`：城市code
- `count`：count
- `dateStr`：店铺日期
- `id`：场次Id
- `leftNum`：场次余位
- `partyTimeInfo`：场次信息
- `partyType`（必填）：派对类型，1-包场，2-拼团
- `skuId`：skuId
- `spuId`：spuId
- `storeCode`：门店
- `timeEnd`：场次结束时间
- `timeStart`：场次开始时间
