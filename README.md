# 麦麦社交点餐套件 / `mcd-social-suite`

> 麦当劳程序员创意开发大赛参赛作品 · 版本 v1.0.0 · 状态：✅ 已 live 联调

把「拼单 / 团餐 / 派对 / 代送」四个分散的多人场景收敛成一个入口，
用麦当劳官方 MCP 的真实数据产出**谁点什么、各摊多少、能不能办派对、怎么交接**的方案卡。

## 一、项目介绍

多人吃麦当劳的需求天然是散的：拼单要算人头、团餐要看满减、派对要查场次余位、代送要交接。
本 Skill 用一个入口处理四件事：

- **拼单**：按官方五档搭配规则配餐 → `calculate-price` 真实核价 → 按菜单小计加权分摊**到分**
- **团餐**：`beType=6` 真实链路（助餐服务 + 促销规则 + 核价），无配送地址时严格降级
- **派对**：六级链全通（商品 → 详情 → 城市 → 门店 → 日期 → 场次），自动校验人数区间与余位
- **代送**：外送交接卡，禁止录入他人 PII，手机号脱敏

所有数字来自官方 MCP，缺失显示「—」，**绝不补零或估算**。

## 二、目标用户

聚餐组织者、拼单党、团餐经办人、想办生日派对的家长、异地代送需求者。

## 三、安装与配置

1. 申请麦当劳中国 MCP Token：https://open.mcd.cn/mcp
2. 在 MCP Client 中配置 `mcd-mcp`（参考 `mcp-config.example.json`，
   Token 用环境变量 `MCD_MCP_TOKEN` 占位，禁止硬编码）
3. 安装依赖：**无需任何第三方依赖**，仅 Python 3 标准库
4. 无 Token 时可用 `--demo` 读取 `examples/` 下的真实抓取样例跑通全流程

## 四、使用示例

```bash
# 拼单：8 人到店，人均 30 元，忌口香菜
python scripts/social_suite.py split --city 上海市 --keyword 南京东路 \
    --people 8 --per-budget 30 --avoid 香菜 --out plan.json

# 派对：生日派对，8 人，拼团模式
python scripts/social_suite.py party --spu-id 1779 --city-keyword 上海市 \
    --date 2026-10-15 --people 8 --party-type 2 --out party.json

# 团餐 / 代送 / 预检
python scripts/social_suite.py group    --out group.json
python scripts/social_suite.py proxy    --pickup-note "放前台，取餐码 8812" --out proxy.json
python scripts/social_suite.py precheck --out precheck.json

# 生成单文件 HTML 方案卡
python scripts/build_report.py --plan plan.json --party party.json \
    --group group.json --proxy proxy.json --precheck precheck.json --out report.html

# 离线自检（无需 Token，40 项）
python scripts/selftest.py
```

**用户**：8 个人聚餐怎么点划算，顺便看下能不能办生日派对

**助手**：给出 8 人分工与精确到分的分账、官方核价明细，
并列出该门店可预约日期与场次（含人数区间校验结果），停在付款前等你确认。

## 五、使用的麦当劳 MCP 工具

18 个（完整清单与入参见 `references/mcp-tools.md`，由 `tools/list` 程序化生成）：

`now-time-info`、`query-nearby-stores`、`query-meals`、`query-meal-detail`、
`query-store-coupons`、`calculate-price`、`mall-points-products`、`mall-product-detail`、
`query-party-city`、`query-party-store`、`query-party-store-date`、`query-party-store-session`、
`delivery-query-addresses`、`delivery-query-stores`、`query-meal-assistance`、`query-promotions`、
`create-order`（仅缺参预检）、`party-order-create`（仅缺参预检）。

> ⚠️ 派对日期/场次的真实工具名是 **`query-party-store-date`** / **`query-party-store-session`**；
> 官方 README 表格里的 `query-partystore-*` 是过期写法，按它调用会直接失败。

## 六、已验证范围（如实标注）

| 场景 | 状态 | 说明 |
|---|---|---|
| 拼单 | ✅ 端到端验证 | 门店 → 菜单 → 券 → 真实核价 → 分账 |
| 派对 | ✅ 六级链全通 | 未下单；`party-order-create` 只做缺参预检 |
| 团餐 | ⚠️ 降级停止 | 本账号无配送地址（`delivery-query-addresses` 返回空），拿不到 beCode |
| 代送 | ⚠️ 降级停止 | 同上；且禁止录入他人 PII |

降级场景会**停止计算并回显实测错误码**（`600020 配送地址不存在`、
`600048 外送场景下 beType=2/5/6 时必传 beCode`），不输出任何编造的门店或价格。
用户在麦当劳官方 App/小程序添加本人配送地址后，链路自动恢复。

## 七、合规要点

- 涉及他人信息一律脱敏（手机号 `1XX****XXXX`）；**禁止**调用 `delivery-create-address` 录入他人 PII。
- 代送须被代送人授权；任何下单/支付须用户明确确认，本项目自测**未创建任何真实订单**。
- 不跨品牌对比；不代用户支付；单 Token ≤ 600 次/分钟。
- 配置文件仅含环境变量占位符；`selftest.py` 持续断言源码与样例中无硬编码 Token、无未脱敏手机号。

## 八、项目结构

```
SKILL.md                      工作流定义
MCP_INTEGRATION.md            MCP 接入说明
CONTEST_DECLARATION.md        参赛声明（官方文件，内容不可改）
mcp-config.example.json       配置示例（仅环境变量占位符）
workbuddy.md                  WorkBuddy 开发上下文
references/live-contract.md   live 实测契约（禁止凭记忆修改）
references/mcp-tools.md       由 tools/list 程序化生成的工具清单
scripts/mcd_mcp_client.py     MCP 客户端 + items 守卫 + 0 元哨兵
scripts/social_suite.py       四场景聚合引擎
scripts/build_report.py       单文件 HTML 方案卡生成器
scripts/selftest.py           离线自检（40 项）
examples/                     2026-10-12 真实抓取样例与方案卡
```

## 声明

参赛项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。
输出仅供参考，不构成任何专业建议；餐品信息、价格、时段、场次余位及供应状态
以麦当劳官方渠道实时结果为准。
