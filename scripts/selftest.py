#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦社交点餐套件自检：离线模拟测试（无需 Token）。

覆盖：
  * items 守卫（拦截 600010 与静默 0 元两类高危形态）
  * 0 元哨兵（件数不符 / 应付 ≤ 0）
  * 分账算法（合计守恒、余数调平、零权重边界）
  * 时段解析（门店 reservationTimeOptions 为黄金数据源）
  * 角色归类 / 官方档位搭配
  * 代送脱敏
  * HTML 报告（XSS 转义、无外部 JS/CSS、必含免责声明）
  * 安全断言（源码不含硬编码 Token、examples 不含真实凭证）

用法：
    python scripts/selftest.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcd_mcp_client as C  # noqa: E402
import social_suite as S  # noqa: E402
import build_report as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  [OK]   %s" % name)
    except AssertionError as exc:
        FAIL.append((name, str(exc) or "断言失败"))
        print("  [FAIL] %s -> %s" % (name, exc))
    except Exception as exc:  # noqa: BLE001
        FAIL.append((name, "%r" % exc))
        print("  [FAIL] %s -> %r" % (name, exc))


# ------------------------------------------------------ 1. items 守卫

def t_guard_ok():
    out = C.normalize_items([{"productCode": "9900015602", "quantity": 2}])
    assert out == [{"productCode": "9900015602", "quantity": 2}], out


def t_guard_reject_num():
    try:
        C.normalize_items([{"productCode": "x", "quantity": 1, "num": 2}])
    except C.PriceGuardError as exc:
        assert "num" in str(exc)
        return
    raise AssertionError("未拦截 num 键")


def t_guard_reject_code():
    try:
        C.normalize_items([{"code": "9900015602", "quantity": 2}])
    except C.PriceGuardError as exc:
        assert "静默" in str(exc) or "productCode" in str(exc)
        return
    raise AssertionError("未拦截 code 键（会导致静默 0 元）")


def t_guard_require_product_code():
    try:
        C.normalize_items([{"quantity": 1}])
    except C.PriceGuardError:
        return
    raise AssertionError("未拦截缺少 productCode")


def t_guard_positive_qty():
    for bad in (0, -1):
        try:
            C.normalize_items([{"productCode": "x", "quantity": bad}])
        except C.PriceGuardError:
            continue
        raise AssertionError("未拦截 quantity=%s" % bad)


def t_guard_empty():
    try:
        C.normalize_items([])
    except C.PriceGuardError:
        return
    raise AssertionError("未拦截空 items")


def t_guard_coupon_pair():
    ok = C.normalize_items([{"productCode": "x", "quantity": 1,
                             "couponId": "A", "couponCode": "B"}])
    assert ok[0]["couponId"] == "A" and ok[0]["couponCode"] == "B"
    try:
        C.normalize_items([{"productCode": "x", "quantity": 1, "couponCode": "B"}])
    except C.PriceGuardError as exc:
        assert "couponId" in str(exc)
        return
    raise AssertionError("未拦截只带 couponCode（会触发 600010）")


def t_guard_drops_unknown_keys():
    out = C.normalize_items([{"productCode": "x", "quantity": 3, "name": "汉堡", "tag": 1}])
    assert set(out[0].keys()) == {"productCode", "quantity"}, out[0].keys()


# ------------------------------------------------------ 2. 0 元哨兵

def t_sentry_ok():
    res = {"price": 4580, "productList": [{"productCode": "x", "quantity": 2}]}
    C.assert_price_sane(res, [{"productCode": "x", "quantity": 2}])


def t_sentry_qty_mismatch():
    res = {"price": 100, "productList": []}
    try:
        C.assert_price_sane(res, [{"productCode": "x", "quantity": 2}])
    except C.PriceGuardError as exc:
        assert "静默" in str(exc) or "件" in str(exc)
        return
    raise AssertionError("未拦截件数不符")


def t_sentry_zero_price():
    res = {"price": 0, "productList": [{"productCode": "x", "quantity": 1}]}
    try:
        C.assert_price_sane(res, [{"productCode": "x", "quantity": 1}])
    except C.PriceGuardError:
        return
    raise AssertionError("未拦截应付 0 元")


# ------------------------------------------------------ 3. 分账

def t_shares_conservation():
    for total in (1, 99, 100, 4580, 10001, 33333):
        for w in ([1, 1, 1], [10, 20, 30], [1], [5, 5, 5, 5, 5, 5, 5]):
            sh = S.split_shares(total, w)
            assert sum(sh) == total, (total, w, sh, sum(sh))


def t_shares_zero_weights():
    sh = S.split_shares(100, [0, 0, 0, 0])
    assert sum(sh) == 100, sh
    assert max(sh) - min(sh) <= 1, sh


def t_shares_empty():
    assert S.split_shares(100, []) == []


def t_shares_single():
    assert S.split_shares(4580, [1]) == [4580]


# ------------------------------------------------------ 4. 时段解析

def t_parse_periods():
    ps = S.parse_periods("午餐(10:44至14:15)，下午茶(14:44至16:45)，夜市(17:14至21:45)")
    assert len(ps) == 3, ps
    assert ps[0] == {"name": "午餐", "start": "10:44", "end": "14:15"}, ps[0]
    assert ps[2]["name"] == "夜市"


def t_parse_periods_empty():
    assert S.parse_periods("") == []
    assert S.parse_periods(None) == []


def t_current_period_hit():
    store = {"reservationTimeOptions": [
        {"date": "2026-10-12", "today": True,
         "reservationOptionText": "午餐(10:44至14:15)，下午茶(14:44至16:45)"}]}
    p = S.current_period(store, "13:00")
    assert p and p["period"] == "午餐", p


def t_current_period_miss():
    store = {"reservationTimeOptions": [
        {"date": "2026-10-12", "today": True,
         "reservationOptionText": "午餐(10:44至14:15)"}]}
    assert S.current_period(store, "22:00") is None


def t_current_period_ignores_tomorrow():
    store = {"reservationTimeOptions": [
        {"date": "2026-10-13", "today": False,
         "reservationOptionText": "早餐(06:44至10:15)"}]}
    assert S.current_period(store, "07:00") is None


# ------------------------------------------------------ 5. 角色归类 / 档位

def t_role_classify():
    assert S.classify_role("鸡肉汉堡/卷", "麦辣鸡腿汉堡", ["套餐"]) == "主食"
    assert S.classify_role("小食", "中薯条", []) == "小食"
    assert S.classify_role("饮料", "可口可乐", []) == "饮料"


def t_tier_selection():
    rules = [r["label"] for r in S.OFFICIAL_TIER_RULES]
    assert rules[0] == "20元以下" and rules[-1] == "50元以上", rules


def t_combo_respects_avoid():
    menu = {"categories": [{"name": "小食", "meals": [{"code": "A", "tags": []}]},
                           {"name": "主食", "meals": [{"code": "B", "tags": []}]}],
            "meals": {"A": {"name": "麦辣鸡翅", "currentPrice": "12"},
                      "B": {"name": "麦香鱼汉堡", "currentPrice": "15"}}}
    c = S.build_person_combo(menu, 30, ["鸡翅"])
    codes = [i["code"] for i in c["items"]]
    assert "A" not in codes, codes


def t_combo_empty_menu():
    c = S.build_person_combo({"categories": [], "meals": {}}, 30, [])
    assert c["items"] == []


def t_combo_tier_label():
    menu = {"categories": [{"name": "主食", "meals": [{"code": "B", "tags": []}]}],
            "meals": {"B": {"name": "汉堡", "currentPrice": "20"}}}
    c = S.build_person_combo(menu, 25, [])
    assert c["tier"] == "20-30元", c["tier"]


# ------------------------------------------------------ 6. 脱敏

def t_mask_phone():
    assert S.mask_contact("13812345678") == "138****5678"


def t_mask_keeps_other():
    assert S.mask_contact("无") == "无"
    assert S.mask_contact("") == ""


# ------------------------------------------------------ 7. HTML 报告

def _demo_plan():
    return {"data_source": "mcp", "server_time": {"formatted": "2026-10-12 13:20:00"},
            "store": {"storeName": "某餐厅<script>", "storeCode": "1450104",
                      "address": "南京东路", "businessHours": "06:30-23:59"},
            "meal_period": {"period": "午餐", "window": "10:44至14:15"},
            "request": {"people": 3, "per_budget_yuan": 30.0, "avoid": ["香菜"]},
            "cart": [{"productCode": "A", "name": "汉堡", "quantity": 3, "unit_price_yuan": 20.0}],
            "coupon": None,
            "official_price": {"product_fen": 6000, "discount_fen": 0, "packing_fen": 0,
                               "delivery_fen": 0, "tableware_fen": 0, "payable_fen": 6000},
            "per_person_avg_fen": 2000,
            "roster": [{"person": "P1", "tier": "20-30元", "share_yuan": "20.00",
                        "menu_subtotal_yuan": 20.0,
                        "items": [{"name": "汉堡", "price_yuan": 20.0}]}],
            "take_way_list": [{"code": "eat-in", "title": "堂食"}],
            "settlement_note": "按菜单小计加权分摊"}


def t_report_xss_escaped():
    html = B.build(_demo_plan(), None, None)
    assert "<script>" not in html, "未转义 <script>"
    assert "&lt;script&gt;" in html


def t_report_no_external_js_css():
    html = B.build(_demo_plan(), None, None)
    assert "<script" not in html.lower(), "含 script 标签"
    assert "href=\"http" not in html, "含外部样式/脚本链接"
    assert "<style>" in html, "缺少内联样式"


def t_report_disclaimer():
    html = B.build(_demo_plan(), None, None)
    assert "非麦当劳官方产品" in html
    assert "calculate-price" in html


def t_report_party_blockers():
    party = {"spu": {"spuName": "派对", "spuId": 1779, "catName": "生日类派对"},
             "detail": {"partyPeople": "5-12", "partyAge": "4-12岁"},
             "store": {"name": "某店", "code": "1450713"}, "date": "2026-10-15",
             "party_type_label": "包场", "party_type": 1,
             "sessions": [{"timeStart": "12:00", "timeEnd": "13:30", "partyMin": 5,
                           "partyMax": 12, "leftNum": 12, "price_yuan": "50.00",
                           "fits": False, "blockers": ["人数 3 < 每场起订 5"]}],
             "recommended": None, "confirm_hint": "须显式 --confirm"}
    html = B.build(None, party, None)
    assert "不可约" in html and "每场起订" in html


def t_report_degraded_warn():
    group = {"status": "degraded", "reason_code": "NO_DELIVERY_ADDRESS",
             "message": "无配送地址", "how_to_enable": "去 App 添加",
             "verified_errors": [{"tool": "delivery-query-stores", "code": 600020,
                                  "message": "配送地址不存在"}]}
    html = B.build(None, None, None, group, None)
    assert "NO_DELIVERY_ADDRESS" in html and "600020" in html


def t_report_empty_safe():
    html = B.build(None, None, None)
    assert "<html" in html and "约束与声明" in html


# ------------------------------------------------------ 8. 安全断言

def t_no_hardcoded_token():
    pat = re.compile(r"Bearer\s+[A-Za-z0-9]{20,}")
    for base, _dirs, files in os.walk(ROOT):
        if ".git" in base:
            continue
        for f in files:
            if not f.endswith((".py", ".md", ".json", ".html")):
                continue
            path = os.path.join(base, f)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    body = fh.read()
            except OSError:
                continue
            assert not pat.search(body), "疑似硬编码 Token：%s" % path


def t_env_gitignored():
    gi = os.path.join(ROOT, ".gitignore")
    assert os.path.isfile(gi), "缺少 .gitignore"
    with open(gi, encoding="utf-8") as fh:
        assert ".env" in fh.read()


def t_mcp_config_placeholder_only():
    path = os.path.join(ROOT, "mcp-config.example.json")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    blob = json.dumps(cfg, ensure_ascii=False)
    assert "${MCD_MCP_TOKEN}" in blob, "配置示例未提供环境变量占位符"
    assert not re.search(r"[A-Za-z0-9]{28,}", blob.replace("${MCD_MCP_TOKEN}", "")), \
        "配置示例疑似含真实 Token"


def t_no_pii_in_examples():
    if not os.path.isdir(EXAMPLES):
        return
    phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    for f in os.listdir(EXAMPLES):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(EXAMPLES, f), encoding="utf-8", errors="ignore") as fh:
            body = fh.read()
        hits = [m for m in phone.findall(body) if not body[max(0, body.find(m) - 20):].count("****")]
        assert not hits, "examples/%s 疑似含未脱敏手机号" % f


# ------------------------------------------------------ 9. 常量对齐 live

def t_party_constants():
    assert S.PARTY_CAT_RULE_IDS == "1>6>20,1>6>21"
    assert S.PARTY_SHOP_ID == 5


def t_official_tier_rules_intact():
    assert len(S.OFFICIAL_TIER_RULES) == 5
    assert S.OFFICIAL_TIER_RULES[0]["label"] == "20元以下"
    assert "小食" in S.OFFICIAL_TIER_RULES[0]["roles"]


def t_tools_doc_matches_live():
    """文档不得把官方已淘汰的工具名当作可用工具来写。

    允许在「说明官方表格写错了」的告警行里点名旧写法（这是留痕需要），
    但不允许出现在其它语境。
    """
    bad = ("query-partystore-date", "query-partystore-session")
    # 允许的语境：明确标注这是官方表格的过期写法
    allow_markers = ("官方 README", "官方表格", "过期", "真实工具名", "已淘汰")
    for rel in ("SKILL.md", "references/mcp-tools.md", "README.md", "MCP_INTEGRATION.md",
                "references/live-contract.md", "CHANGELOG.md"):
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        for ln in lines:
            for b in bad:
                if b in ln and not any(m in ln for m in allow_markers):
                    raise AssertionError("%s 仍把已淘汰工具名 %s 当作可用写法：%s"
                                         % (rel, b, ln.strip()[:80]))


def main() -> int:
    print("麦麦社交点餐套件自检（离线，无需 Token）")
    print("-" * 60)

    print("\n[1] items 守卫（拦截 600010 / 静默 0 元）")
    for n, f in [("合法 productCode+quantity", t_guard_ok),
                 ("拦截 num 键", t_guard_reject_num),
                 ("拦截 code 键（静默0元）", t_guard_reject_code),
                 ("缺 productCode 拦截", t_guard_require_product_code),
                 ("quantity<=0 拦截", t_guard_positive_qty),
                 ("空 items 拦截", t_guard_empty),
                 ("券必须 couponId+couponCode 成对", t_guard_coupon_pair),
                 ("未知键被剔除", t_guard_drops_unknown_keys)]:
        check(n, f)

    print("\n[2] 0 元哨兵")
    for n, f in [("正常结果放行", t_sentry_ok),
                 ("件数不符拦截", t_sentry_qty_mismatch),
                 ("应付0元拦截", t_sentry_zero_price)]:
        check(n, f)

    print("\n[3] 分账算法")
    for n, f in [("合计守恒", t_shares_conservation),
                 ("零权重边界", t_shares_zero_weights),
                 ("空名单", t_shares_empty),
                 ("单人", t_shares_single)]:
        check(n, f)

    print("\n[4] 时段解析（reservationTimeOptions）")
    for n, f in [("解析时段窗", t_parse_periods),
                 ("空输入", t_parse_periods_empty),
                 ("命中当前时段", t_current_period_hit),
                 ("未命中返回 None", t_current_period_miss),
                 ("忽略非今日", t_current_period_ignores_tomorrow)]:
        check(n, f)

    print("\n[5] 角色归类 / 官方档位")
    for n, f in [("角色归类", t_role_classify),
                 ("官方档位规则", t_tier_selection),
                 ("忌口过滤", t_combo_respects_avoid),
                 ("空菜单边界", t_combo_empty_menu),
                 ("档位标签", t_combo_tier_label)]:
        check(n, f)

    print("\n[6] 代送脱敏")
    for n, f in [("手机号打码", t_mask_phone), ("非手机号保持", t_mask_keeps_other)]:
        check(n, f)

    print("\n[7] HTML 报告")
    for n, f in [("XSS 转义", t_report_xss_escaped),
                 ("无外部 JS/CSS", t_report_no_external_js_css),
                 ("必含免责声明", t_report_disclaimer),
                 ("派对不可约原因回显", t_report_party_blockers),
                 ("降级告警回显", t_report_degraded_warn),
                 ("空输入安全", t_report_empty_safe)]:
        check(n, f)

    print("\n[8] 安全断言")
    for n, f in [("源码无硬编码 Token", t_no_hardcoded_token),
                 (".env 已 gitignore", t_env_gitignored),
                 ("配置示例仅占位符", t_mcp_config_placeholder_only),
                 ("examples 无未脱敏手机号", t_no_pii_in_examples)]:
        check(n, f)

    print("\n[9] 常量与 live 对齐")
    for n, f in [("派对类目常量", t_party_constants),
                 ("官方档位规则未被篡改", t_official_tier_rules_intact),
                 ("文档无已淘汰工具名", t_tools_doc_matches_live)]:
        check(n, f)

    print("\n" + "-" * 60)
    print("通过 %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        for n, m in FAIL:
            print("  FAIL: %s -> %s" % (n, m))
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
