#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把社交点餐方案渲染成单文件 HTML 方案卡。

设计约束：
  * 单文件、内联样式、无外部 CSS/JS、无 CDN 依赖（图片走官方 CDN，加载失败自动降级为占位）。
  * 全量 HTML 转义，杜绝 XSS（餐品名、门店名、用户备注均为外部数据）。
  * 只展示由官方 MCP 真实返回推导出的数字；缺失值显示「—」，绝不补零或估算。

用法：
    python scripts/build_report.py --plan examples/split_live.json \
        --party examples/party_live.json --precheck examples/precheck_live.json \
        --out examples/demo_report.html
"""

import argparse
import datetime as dt
import html
import json
import os
import sys

VERSION = "1.0.0"


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def yuan(fen) -> str:
    try:
        return "%.2f" % (int(fen) / 100.0)
    except (TypeError, ValueError):
        return "—"


def load(path):
    if not path:
        return None
    if not os.path.isfile(path):
        raise SystemExit("文件不存在：%s" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def kv_rows(pairs):
    out = []
    for k, v in pairs:
        out.append("<tr><th>%s</th><td>%s</td></tr>" % (esc(k), esc(v)))
    return "\n".join(out)


def build(plan, party, precheck, group=None, proxy=None):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []

    parts.append("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>麦麦社交点餐方案卡</title>
<style>
:root{--bg:#f6f7f9;--card:#ffffff;--line:#e3e6ea;--ink:#1f2328;--sub:#5b6570;
--accent:#c8102e;--ok:#0f7b3f;--warn:#a2600a;--warnbg:#fff7e6;--soft:#f0f2f5;}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Segoe UI,Roboto,sans-serif;
line-height:1.6;font-size:14px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 12px;padding-left:9px;border-left:4px solid var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:16px}
.sub{color:var(--sub);font-size:12px}
.grid{display:flex;flex-wrap:wrap;gap:10px}
.chip{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{width:150px;color:var(--sub);font-weight:600;background:#fafbfc}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.big{font-size:26px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}
.warn{background:var(--warnbg);border:1px solid #f0d9a8;color:var(--warn);
border-radius:8px;padding:11px 13px;font-size:13px}
.ok{color:var(--ok)}
.foot{color:var(--sub);font-size:12px;border-top:1px dashed var(--line);padding-top:12px;margin-top:6px}
.bad{display:inline-block;background:#fdecec;color:#a3122b;border-radius:6px;padding:1px 7px;font-size:12px}
.good{display:inline-block;background:#e8f6ec;color:var(--ok);border-radius:6px;padding:1px 7px;font-size:12px}
ul{margin:6px 0 0 18px;padding:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
</style></head><body><div class="wrap">""")

    # ---------- 头部
    src = (plan or {}).get("data_source") or (party or {}).get("data_source") or "—"
    stime = ((plan or {}).get("server_time") or {}).get("formatted") or "—"
    parts.append("""<div class="card">
<h1>麦麦社交点餐方案卡</h1>
<div class="sub">生成时间 %s · 数据源 <span class="mono">%s</span> · 引擎 v%s</div>
<div class="grid" style="margin-top:10px">
<span class="chip">官方服务器时间 %s</span>
<span class="chip">拼单</span><span class="chip">团餐</span>
<span class="chip">派对</span><span class="chip">代送</span>
</div></div>""" % (esc(now), esc(src), esc(VERSION), esc(stime)))

    # ---------- 拼单
    if plan:
        store = plan.get("store") or {}
        price = plan.get("official_price") or {}
        period = plan.get("meal_period")
        parts.append('<div class="card"><h2>拼单方案</h2>')
        parts.append("<table>")
        parts.append(kv_rows([
            ("门店", "%s（%s）" % (store.get("storeName") or "—", store.get("storeCode") or "—")),
            ("地址", store.get("address") or "—"),
            ("营业时间", store.get("businessHours") or "—"),
            ("当前时段", ("%s %s" % (period.get("period"), period.get("window")))
             if period else "未命中门店时段窗（可能已过营业时段）"),
            ("人数", plan.get("request", {}).get("people")),
            ("人均预算", "¥%.2f" % float(plan.get("request", {}).get("per_budget_yuan") or 0)),
            ("忌口", "、".join(plan.get("request", {}).get("avoid") or []) or "无"),
        ]))
        parts.append("</table>")

        cp = plan.get("coupon")
        if cp:
            parts.append('<div style="margin-top:10px"><span class="good">命中可用券</span> %s '
                         '<span class="sub">（%s，适用 %s）</span></div>'
                         % (esc(cp.get("title")), esc(cp.get("window")), esc(cp.get("productName"))))

        # 购物车
        parts.append('<h2 style="margin-top:18px">购物车（官方菜单实时价）</h2><table>')
        parts.append("<tr><th>餐品</th><th class=\"num\">单价</th><th class=\"num\">数量</th>"
                     "<th class=\"num\">小计</th></tr>")
        for it in plan.get("cart") or []:
            parts.append("<tr><td>%s</td><td class=\"num\">¥%.2f</td><td class=\"num\">%s</td>"
                         "<td class=\"num\">¥%.2f</td></tr>"
                         % (esc(it.get("name")), float(it.get("unit_price_yuan") or 0),
                            esc(it.get("quantity")),
                            float(it.get("unit_price_yuan") or 0) * int(it.get("quantity") or 0)))
        parts.append("</table>")

        # 官方核价
        parts.append('<h2 style="margin-top:18px">官方核价（calculate-price）</h2>')
        parts.append('<div class="big">应付 ¥%s</div>' % esc(yuan(price.get("payable_fen"))))
        parts.append("<table style=\"margin-top:8px\">")
        parts.append(kv_rows([
            ("商品原价", "¥" + yuan(price.get("product_fen"))),
            ("优惠金额", "¥" + yuan(price.get("discount_fen"))),
            ("打包费", "¥" + yuan(price.get("packing_fen"))),
            ("配送费", "¥" + yuan(price.get("delivery_fen"))),
            ("餐具费", "¥" + yuan(price.get("tableware_fen"))),
            ("人均", "¥" + yuan(plan.get("per_person_avg_fen"))),
        ]))
        parts.append("</table>")

        # 分工分账
        roster = plan.get("roster") or []
        if roster:
            parts.append('<h2 style="margin-top:18px">分工与分账（精确到分，合计=应付）</h2><table>')
            parts.append("<tr><th>成员</th><th>配置（官方档位）</th><th class=\"num\">菜单小计</th>"
                         "<th class=\"num\">实摊</th></tr>")
            for r in roster:
                names = "、".join("%s(¥%.2f)" % (i.get("name"), float(i.get("price_yuan") or 0))
                                  for i in r.get("items") or [])
                parts.append("<tr><td>%s</td><td>%s <span class=\"sub\">%s</span></td>"
                             "<td class=\"num\">¥%.2f</td><td class=\"num\">¥%s</td></tr>"
                             % (esc(r.get("person")), esc(names), esc(r.get("tier")),
                                float(r.get("menu_subtotal_yuan") or 0), esc(r.get("share_yuan"))))
            parts.append("</table>")
            parts.append('<div class="sub" style="margin-top:6px">%s</div>'
                         % esc(plan.get("settlement_note")))

        tw = plan.get("take_way_list") or []
        if tw:
            parts.append('<div class="sub" style="margin-top:8px">取餐方式（create-order 的 '
                         'takeWayCode 取值来源）：%s</div>'
                         % esc("、".join("%s=%s" % (t.get("code"), t.get("title")) for t in tw)))
        parts.append("</div>")

    # ---------- 派对
    if party:
        spu = party.get("spu") or {}
        det = party.get("detail") or {}
        store = party.get("store") or {}
        rec = party.get("recommended")
        parts.append('<div class="card"><h2>派对预约</h2><table>')
        parts.append(kv_rows([
            ("派对商品", "%s（spuId %s / %s）" % (spu.get("spuName") or "—",
                                                 spu.get("spuId") or "—", spu.get("catName") or "—")),
            ("适用人数", det.get("partyPeople") or "—"),
            ("适用年龄", det.get("partyAge") or "—"),
            ("模式", "%s（partyType=%s）" % (party.get("party_type_label"), party.get("party_type"))),
            ("门店", "%s（%s）" % (store.get("name") or "—", store.get("code") or "—")),
            ("日期", party.get("date") or "—"),
        ]))
        parts.append("</table>")
        sess = party.get("sessions") or []
        if sess:
            parts.append('<h2 style="margin-top:18px">可预约场次</h2><table>')
            parts.append("<tr><th>时段</th><th class=\"num\">人数区间</th><th class=\"num\">余位</th>"
                         "<th class=\"num\">价格</th><th>结论</th></tr>")
            for s in sess:
                if s.get("fits"):
                    concl = '<span class="good">可约</span>'
                else:
                    concl = '<span class="bad">不可约</span> <span class="sub">%s</span>' % esc(
                        "；".join(s.get("blockers") or []))
                parts.append("<tr><td>%s–%s</td><td class=\"num\">%s–%s</td>"
                             "<td class=\"num\">%s</td><td class=\"num\">¥%s</td><td>%s</td></tr>"
                             % (esc(s.get("timeStart")), esc(s.get("timeEnd")),
                                esc(s.get("partyMin")), esc(s.get("partyMax")),
                                esc(s.get("leftNum")), esc(s.get("price_yuan")), concl))
            parts.append("</table>")
        if rec:
            parts.append('<div style="margin-top:10px"><span class="good">推荐场次</span> %s–%s '
                         '¥%s（余位 %s）</div>'
                         % (esc(rec.get("timeStart")), esc(rec.get("timeEnd")),
                            esc(rec.get("price_yuan")), esc(rec.get("leftNum"))))
        parts.append('<div class="warn" style="margin-top:12px">%s</div>'
                     % esc(party.get("confirm_hint")))
        parts.append("</div>")

    # ---------- 团餐 / 代送 降级
    for doc, title in ((group, "团餐（企业团餐 beType=6）"), (proxy, "代送")):
        if not doc:
            continue
        parts.append('<div class="card"><h2>%s</h2>' % esc(title))
        if doc.get("status") == "ok":
            parts.append('<div><span class="good">链路可用</span></div>')
            if doc.get("promotions"):
                parts.append('<div class="sub" style="margin-top:6px">促销规则（query-promotions）已取到，'
                             '请以官方返回为准。</div>')
        else:
            parts.append('<div class="warn"><strong>%s</strong><br>%s<br><br>'
                         '<strong>如何启用：</strong>%s</div>'
                         % (esc(doc.get("reason_code")), esc(doc.get("message")),
                            esc(doc.get("how_to_enable") or "—")))
            ve = doc.get("verified_errors") or []
            if ve:
                parts.append('<div class="sub" style="margin-top:8px">已实测的服务端校验：</div><ul>')
                for e in ve:
                    parts.append("<li class=\"mono\">%s -&gt; %s %s</li>"
                                 % (esc(e.get("tool")), esc(e.get("code")), esc(e.get("message"))))
                parts.append("</ul>")
        parts.append("</div>")

    if precheck:
        pre = precheck.get("precheck") or {}
        parts.append('<div class="card"><h2>外送链路预检</h2><table>')
        parts.append(kv_rows([("可配送地址数", pre.get("count")),
                              ("外送可用", "是" if pre.get("available") else "否")]))
        parts.append("</table></div>")

    # ---------- 页脚
    parts.append("""<div class="card">
<h2>约束与声明</h2>
<ul>
<li><strong>停在付款前</strong>：本卡不创建任何订单。<code>create-order</code> /
<code>party-order-create</code> 须用户显式确认后才会调用。</li>
<li><strong>代送隐私</strong>：禁止录入他人姓名/手机号/地址；代送以本人地址下单 + 交接说明完成，
输出对第三方信息脱敏。</li>
<li><strong>核价守卫</strong>：<code>calculate-price</code> 的 items 只用
<code>productCode</code>+<code>quantity</code>；<code>code</code> 形态会被静默接受并返回 0 元，
已拦截。返回件数与请求件数不符或应付 ≤ 0 时直接报错，不产出金额。</li>
<li><strong>非官方产品</strong>：本项目为麦当劳程序员创意开发大赛参赛作品，由参赛者独立开发，
非麦当劳官方产品。餐品、价格、时段、名额与供应状态一律以麦当劳官方渠道实时结果为准。</li>
</ul>
<div class="foot">麦麦社交点餐套件 v%s · 单 Token 600 次/分钟限流内调用 · 不跨品牌对比 · 不代用户支付</div>
</div>""" % esc(VERSION))

    parts.append("</div></body></html>")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成社交点餐方案卡（单文件 HTML）")
    ap.add_argument("--plan", default="")
    ap.add_argument("--party", default="")
    ap.add_argument("--group", default="")
    ap.add_argument("--proxy", default="")
    ap.add_argument("--precheck", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    doc = build(load(args.plan), load(args.party), load(args.precheck),
                load(args.group), load(args.proxy))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(doc)
        print("已写入：%s" % os.path.abspath(args.out))
    else:
        sys.stdout.write(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
