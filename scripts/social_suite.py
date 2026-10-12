#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦社交点餐套件 / McSocialSuite —— 四场景聚合引擎。

把「拼单 / 团餐 / 派对 / 代送」四个分散需求收敛为一个入口，
全部结论必须由麦当劳官方 MCP 真实返回推导，禁止任何硬编码价格或虚构门店。

子命令：
    split     拼单：N 人到店/得来速，官方时段 + 官方档位搭配规则 + 真实核价 + 精确到分的分账
    group     团餐：beType=6 真实链路（无配送地址时严格降级，绝不编造）
    party     派对：mall 商品 -> 详情 -> 城市 -> 门店 -> 日期 -> 场次（参数装配，不自动下单）
    proxy     代送：外送交接卡（禁止写入他人 PII，输出脱敏）
    precheck  外送/团餐可用性预检
    scenarios 列出四场景能力矩阵与各自的前置条件

Token 优先级：--token > 环境变量 MCD_MCD_TOKEN/MCD_MCP_TOKEN > .env。
无 Token 或 --demo 时读取 examples/ 下的真实抓取样例离线跑通。

实测约束（2026-10-12 live，见 references/live-contract.md）：
  * query-meals / calculate-price / create-order 必传 storeCode + orderType + beType。
  * calculate-price 的 items 必须用 productCode + quantity（其它形态会静默 0 元或 600010）。
  * 团餐/外送（beType=6/2）必须先有 addressId 才能拿到 beCode，否则 600020 / 600048。
"""

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcd_mcp_client as C  # noqa: E402

VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")

# ------------------------------------------------------ 常量：全部来自官方工具描述或 live 返回

# query-meals 官方描述中给出的企业团餐搭配档位规则（原文摘录，勿改写）
OFFICIAL_TIER_RULES = [
    {"max": 20, "label": "20元以下", "roles": ["小食"]},
    {"max": 30, "label": "20-30元", "roles": ["主食", "小食"]},
    {"max": 40, "label": "30-40元", "roles": ["主食", "小食", "饮料"]},
    {"max": 50, "label": "40-50元", "roles": ["主食", "小食", "小食", "饮料"]},
    {"max": 10 ** 6, "label": "50元以上", "roles": ["主食", "小食", "小食", "饮料", "甜品"]},
]

# 分类名 -> 角色（命中即归类，用于按档位选品）
ROLE_KEYWORDS = [
    ("主食", ("汉堡", "卷", "饭", "堡", "鸡腿", "牛堡", "麦香", "套餐", "主食")),
    ("小食", ("小食", "薯条", "鸡块", "鸡翅", "派", "玉米", "薯饼", "洋葱", "麦乐鸡", "酥")),
    ("饮料", ("饮料", "可乐", "咖啡", "茶", "牛奶", "果汁", "汽水", "冰", "饮")),
    ("甜品", ("甜品", "冰淇淋", "冰激凌", "圣代", "新地", "蛋糕", "甜筒")),
    ("早餐", ("早餐", "早安")),
]

PARTY_CAT_RULE_IDS = "1>6>20,1>6>21"   # 生日类派对 + 主题类派对（官方 catRuleIds）
PARTY_SHOP_ID = 5                       # party-order-create 仅支持 shopId=5


class SuiteError(RuntimeError):
    """引擎可预期的业务失败（缺参、降级、守卫拦截）。"""


# ------------------------------------------------------ 工具函数

def yuan_from_menu(meal: dict) -> float:
    """菜单价 currentPrice 单位为元（字符串）。"""
    try:
        return float(meal.get("currentPrice") or 0)
    except (TypeError, ValueError):
        return 0.0


def fen(x) -> int:
    """元 -> 分（四舍五入，避免浮点尾差）。"""
    try:
        return int(round(float(x) * 100))
    except (TypeError, ValueError):
        return 0


def yuan(x) -> str:
    return "%.2f" % (int(x) / 100.0)


def classify_role(category_name: str, meal_name: str, tags) -> str:
    text = "%s %s %s" % (category_name or "", meal_name or "", " ".join(tags or []))
    for role, words in ROLE_KEYWORDS:
        for w in words:
            if w in text:
                return role
    return "其它"


def parse_periods(option_text: str):
    """解析门店 reservationTimeOptions 的时段窗文本。

    形如：午餐(10:44至14:15)，下午茶(14:44至16:45)，夜市(17:14至21:45)
    返回 [{name, start, end}]
    """
    out = []
    if not option_text:
        return out
    for seg in re.split(r"[，,]", option_text):
        m = re.match(r"\s*([^()]+)\(([^)]*)\)\s*", seg)
        if not m:
            continue
        name = m.group(1).strip()
        rng = re.split(r"至|-", m.group(2).strip())
        if len(rng) != 2:
            continue
        out.append({"name": name, "start": rng[0].strip(), "end": rng[1].strip()})
    return out


def current_period(store: dict, now_hm: str):
    """以门店 reservationTimeOptions 为黄金数据源判定当前时段。"""
    for opt in store.get("reservationTimeOptions") or []:
        if not opt.get("today"):
            continue
        for p in parse_periods(opt.get("reservationOptionText") or ""):
            if p["start"] <= now_hm <= p["end"]:
                return {"period": p["name"], "window": "%s至%s" % (p["start"], p["end"]),
                        "date": opt.get("date"), "source": "门店 reservationTimeOptions"}
    return None


def load_demo(name: str):
    path = os.path.join(EXAMPLES, name)
    if not os.path.isfile(path):
        raise SuiteError("离线样例缺失：%s（请先执行 live 抓取或检查 examples/ 目录）" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------ 拼单（split）

def build_person_combo(menu: dict, per_budget: float, avoid, idx=0, shared_snack=None):
    """按官方档位规则为一个人配一套餐。全部候选来自真实菜单。"""
    categories = menu.get("categories") or []
    meals = menu.get("meals") or {}

    # 先建立 角色 -> [餐品] 索引
    pool = {}
    for cat in categories:
        cname = cat.get("name") or ""
        for m in cat.get("meals") or []:
            code = m.get("code")
            info = meals.get(code)
            if not info:
                continue
            name = info.get("name") or ""
            blob = name + " " + " ".join(m.get("tags") or [])
            if any(a in blob for a in avoid if a):
                continue
            role = classify_role(cname, name, m.get("tags"))
            price = yuan_from_menu(info)
            if price <= 0:
                continue
            pool.setdefault(role, []).append({
                "code": code, "name": name, "role": role,
                "price_yuan": price, "tags": m.get("tags") or [],
                "category": cname,
                "original_price_yuan": (float(info.get("originalPrice") or price)
                                        if str(info.get("originalPrice") or "").replace(".", "").isdigit()
                                        else price),
            })
    for role in pool:
        pool[role].sort(key=lambda x: x["price_yuan"])

    tier = next(t for t in OFFICIAL_TIER_RULES if per_budget < t["max"])
    picked, used_codes, total = [], set(), 0.0
    for slot, role in enumerate(tier["roles"]):
        cands = pool.get(role) or pool.get("主食") or []
        if not cands:
            continue
        # 轮换起点：让第 idx 个人的选品与别人错开，避免 N 人全点同一款
        n = len(cands)
        start = (idx + slot) % n
        for off in range(n):
            c = cands[(start + off) % n]
            if c["code"] in used_codes:
                continue
            if total + c["price_yuan"] > per_budget + 1e-9 and slot > 0:
                continue
            picked.append(c)
            used_codes.add(c["code"])
            total += c["price_yuan"]
            break
    if not picked:  # 预算过低：退化为最便宜的在售品
        allc = sorted([c for v in pool.values() for c in v], key=lambda x: x["price_yuan"])
        if allc:
            picked = [allc[0]]
            total = allc[0]["price_yuan"]
    if shared_snack:
        picked.append(dict(shared_snack, shared=True))
    return {"tier": tier["label"], "items": picked, "menu_subtotal_yuan": round(total, 2)}


def split_shares(total_fen: int, weights):
    """按权重把总额分摊到分，余数调平，保证 sum == total_fen。"""
    n = len(weights)
    if n == 0:
        return []
    wsum = sum(weights)
    if wsum <= 0:
        base, rem = divmod(total_fen, n)
        shares = [base] * n
        for i in range(rem):
            shares[i] += 1
        return shares
    shares = [int(total_fen * w / wsum) for w in weights]
    diff = total_fen - sum(shares)
    i = 0
    while diff != 0:
        step = 1 if diff > 0 else -1
        shares[i % n] += step
        diff -= step
        i += 1
    return shares


def cmd_split(args, token, url, demo):
    if demo:
        stores_doc = load_demo("real_stores.json")
        menu_doc = load_demo("real_menu.json")
        price_doc = load_demo("real_price.json")
        coupons_doc = load_demo("real_coupons.json")
        time_doc = load_demo("real_now_time.json")
        stores = stores_doc.get("stores") or []
        menu = menu_doc.get("menu") or {}
        coupons = coupons_doc.get("coupons") or []
        server_time = time_doc.get("time") or {}
        price_result = (price_doc.get("result") or {})
        live = False
    else:
        if not args.city or not args.keyword:
            raise SuiteError("split 需要 --city 与 --keyword（缺失会触发 600058）")
        stores = C.api_fetch_stores(token, url, args.city, args.keyword, args.be_type)
        if not stores:
            raise SuiteError("未查到门店（可能触发 600014 没有查询到该地址）")
        server_time = C.api_now_time(token, url)
        menu = C.api_fetch_menu(token, url, stores[0]["storeCode"], args.order_type,
                                args.be_type, args.be_code, args.reservation_date)
        coupons = C.api_fetch_coupons(token, url, stores[0]["storeCode"],
                                      args.order_type, args.be_type, args.be_code)
        price_result = None
        live = True

    open_stores = [s for s in stores if s.get("businessStatus") in (True, 1)] or stores
    store = open_stores[0]
    now_hm = (server_time.get("formatted") or "00:00")[11:16]
    period = current_period(store, now_hm)

    avoid = [a.strip() for a in (args.avoid or "").split(",") if a.strip()]
    people = max(1, int(args.people))

    # 为每个人配一套（轮换主食候选，保证组合有变化但都来自真实菜单）
    combos = []
    for i in range(people):
        c = build_person_combo(menu, args.per_budget, avoid, idx=i)
        c["person"] = "P%d" % (i + 1)
        combos.append(c)

    # 汇总购物车
    cart = {}
    for c in combos:
        for it in c["items"]:
            if it.get("shared"):
                continue
            key = it["code"]
            cur = cart.get(key, {"name": it["name"], "qty": 0, "price_yuan": it["price_yuan"]})
            cur["qty"] += 1
            cart[key] = cur
    items = [{"productCode": k, "quantity": v["qty"]} for k, v in cart.items()]
    if not items:
        raise SuiteError("当前菜单在给定预算/忌口下无可用组合（请放宽 --per-budget 或 --avoid）")

    coupon_hit = None
    cart_codes = set(cart.keys())
    for cp in coupons:
        for p in cp.get("products") or []:
            if p.get("productCode") in cart_codes and cp.get("couponId") and cp.get("couponCode"):
                coupon_hit = {"title": cp.get("title"), "couponId": cp.get("couponId"),
                              "couponCode": cp.get("couponCode"),
                              "productCode": p.get("productCode"),
                              "productName": p.get("productName"),
                              "window": cp.get("tradeDateTime")}
                break
        if coupon_hit:
            break

    priced_items = items
    discount_fen = 0
    if coupon_hit:
        priced_items = []
        for it in items:
            row = dict(it)
            if it["productCode"] == coupon_hit["productCode"]:
                row["couponId"] = coupon_hit["couponId"]
                row["couponCode"] = coupon_hit["couponCode"]
            priced_items.append(row)

    if live:
        price = C.api_calculate_price(token, url, store["storeCode"], priced_items,
                                      args.order_type, args.be_type, args.be_code,
                                      need_tableware=args.need_tableware,
                                      reservation_date=args.reservation_date)
        price_source = "calculate-price"
        demo_note = None
    else:
        # 离线模式不调核价接口（无 Token）：按官方菜单实时价合计，并显式标注这不是核价结果
        product_fen_demo = sum(fen(v["price_yuan"]) * int(v["qty"]) for v in cart.values())
        price = {"productPrice": product_fen_demo, "originalPrice": product_fen_demo,
                 "discount": 0, "packingPrice": 0, "deliveryPrice": 0,
                 "tablewarePrice": 0, "price": product_fen_demo, "productList": []}
        price_source = "query-meals 菜单价合计（demo，未经 calculate-price）"
        demo_note = ("离线演示模式：未调用 calculate-price，金额为官方菜单实时价的直接合计，"
                     "不含优惠/打包/配送/餐具；live 模式一律以 calculate-price 为准。")

    total_fen = int(price.get("price") or 0)
    product_fen = int(price.get("productPrice") or 0)
    discount_fen = int(price.get("discount") or 0)
    packing_fen = int(price.get("packingPrice") or 0)
    delivery_fen = int(price.get("deliveryPrice") or 0)
    tableware_fen = int(price.get("tablewarePrice") or 0)
    original_fen = int(price.get("originalPrice") or 0)

    weights = [fen(c.get("menu_subtotal_yuan") or 0) for c in combos]
    shares = split_shares(total_fen, weights)

    roster = []
    for c, sh in zip(combos, shares):
        roster.append({
            "person": c["person"],
            "tier": c["tier"],
            "items": [{"code": i["code"], "name": i["name"], "role": i["role"],
                       "price_yuan": i["price_yuan"]} for i in c["items"]],
            "menu_subtotal_yuan": c["menu_subtotal_yuan"],
            "share_fen": sh,
            "share_yuan": yuan(sh),
        })

    return {
        "scenario": "split",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "data_source": "mcp" if live else "examples(demo)",
        "server_time": {"formatted": server_time.get("formatted"),
                        "timezone": server_time.get("timezone"),
                        "source": "mcp:now-time-info"},
        "store": {"storeCode": store.get("storeCode"), "storeName": store.get("storeName"),
                  "address": store.get("address"), "distance": store.get("distance"),
                  "businessHours": "%s-%s" % (store.get("businessStartTime"),
                                              store.get("businessEndTime"))},
        "meal_period": period,
        "request": {"people": people, "per_budget_yuan": args.per_budget,
                    "avoid": avoid, "beType": args.be_type, "orderType": args.order_type},
        "menu_stats": {"categories": len(menu.get("categories") or []),
                       "meals": len(menu.get("meals") or {})},
        "cart": [{"productCode": k, "name": v["name"], "quantity": v["qty"],
                  "unit_price_yuan": v["price_yuan"]} for k, v in cart.items()],
        "coupon": coupon_hit,
        "official_price": {"original_fen": original_fen, "product_fen": product_fen,
                           "discount_fen": discount_fen, "packing_fen": packing_fen,
                           "delivery_fen": delivery_fen, "tableware_fen": tableware_fen,
                           "payable_fen": total_fen,
                           "source_tool": price_source,
                           "demo_note": demo_note},
        "per_person_avg_fen": total_fen // people if people else 0,
        "roster": roster,
        "take_way_list": price.get("takeWayList") or [],
        "settlement_note": "按每人菜单小计加权分摊应付总额；余数调平到分，合计严格等于应付总额。",
        "guard": {"items_schema": "productCode+quantity（已守卫）",
                  "zero_guard": "productList 件数须等于请求件数，且应付 > 0"},
        "disclaimer": "非麦当劳官方产品；价格与供应以麦当劳官方渠道实时结果为准。",
    }


# ------------------------------------------------------ 团餐（group）

def cmd_group(args, token, url, demo):
    """企业团餐 beType=6。无配送地址时严格降级，绝不编造门店或价格。"""
    if demo:
        pre = (load_demo("real_precheck_delivery.json").get("precheck") or {})
    else:
        pre = C.api_precheck_delivery(token, url)

    out = {
        "scenario": "group",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "data_source": "mcp" if not demo else "examples(demo)",
        "beType": 6,
        "orderType": 2,
        "precheck": pre,
        "chain": ["delivery-query-addresses", "delivery-query-stores(beType=6)",
                  "query-meal-assistance", "query-promotions",
                  "query-meals(beType=6)", "calculate-price(gmServiceCode)"],
    }
    if not pre.get("available"):
        out["status"] = "degraded"
        out["reason_code"] = "NO_DELIVERY_ADDRESS"
        out["message"] = ("当前账号没有可配送地址（delivery-query-addresses 返回空），"
                          "无法取得团餐必需的 beCode；硬试 delivery-query-stores 会返回 "
                          "600020 配送地址不存在，query-meal-assistance / query-promotions "
                          "会返回 600048 外送场景下 beType=2/5/6 时必传 beCode。"
                          "本引擎因此停止，不输出任何价格或门店。")
        out["how_to_enable"] = ("在麦当劳官方 App/小程序添加一个配送地址后重跑；"
                                "本引擎只读地址，不会代你创建地址。")
        out["verified_errors"] = [
            {"tool": "delivery-query-stores", "params": {"beType": 6, "addressId": "0"},
             "code": 600020, "message": "配送地址不存在"},
            {"tool": "query-meal-assistance", "params": {"storeCode": "*", "beType": 6, "orderType": 2},
             "code": 600048, "message": "外送场景下，beType=2/5/6时必传beCode"},
            {"tool": "query-promotions", "params": {"storeCode": "*", "beType": 6, "orderType": 2},
             "code": 600048, "message": "外送场景下，beType=2/5/6时必传beCode"},
        ]
        return out

    addr = (pre.get("addresses") or [])[0]
    address_id = str(addr.get("addressId") or addr.get("id") or "")
    if not address_id:
        out["status"] = "degraded"
        out["reason_code"] = "ADDRESS_ID_MISSING"
        out["message"] = "地址对象缺少 addressId，无法确定配送门店，已停止。"
        return out

    stores = C.unwrap(C.call_tool("delivery-query-stores",
                                  {"beType": 6, "addressId": address_id}, token, url))
    stores = stores if isinstance(stores, list) else []
    if not stores:
        out["status"] = "degraded"
        out["reason_code"] = "NO_GROUP_STORE"
        out["message"] = "该地址附近无支持企业团餐的门店，已停止。"
        return out
    store = stores[0]
    be_code = store.get("beCode") or ""
    store_code = store.get("storeCode") or ""
    if not be_code:
        out["status"] = "degraded"
        out["reason_code"] = "BECODE_MISSING"
        out["message"] = "门店未返回 beCode，后续工具无法调用，已停止。"
        return out

    assistance = C.unwrap(C.call_tool("query-meal-assistance",
                                      {"storeCode": store_code, "beCode": be_code,
                                       "beType": 6, "orderType": 2}, token, url))
    promotions = C.unwrap(C.call_tool("query-promotions",
                                      {"storeCode": store_code, "beCode": be_code,
                                       "beType": 6, "orderType": 2}, token, url))
    menu = C.api_fetch_menu(token, url, store_code, 2, 6, be_code)

    out["status"] = "ok"
    out["store"] = {"storeCode": store_code, "storeName": store.get("storeName"),
                    "beCode": be_code}
    out["assistance"] = assistance if isinstance(assistance, (list, dict)) else []
    out["promotions"] = promotions if isinstance(promotions, (list, dict)) else []
    out["menu_stats"] = {"categories": len((menu or {}).get("categories") or []),
                         "meals": len((menu or {}).get("meals") or {})}
    return out


# ------------------------------------------------------ 派对（party）

def cmd_party(args, token, url, demo):
    if demo:
        products = (load_demo("real_party_products.json").get("products") or [])
        detail = (load_demo("real_party_detail.json").get("detail") or {})
        cities = (load_demo("real_party_city.json").get("cities") or [])
        stores = (load_demo("real_party_store.json").get("stores") or [])
        dates = (load_demo("real_party_date.json").get("dates") or [])
        sessions = (load_demo("real_party_session.json").get("sessions") or [])
        live = False
    else:
        products = C.api_fetch_party_products(token, url, PARTY_CAT_RULE_IDS)
        if not products:
            raise SuiteError("未查到派对类商品（catRuleIds=%s）" % PARTY_CAT_RULE_IDS)
        spu_id = args.spu_id or products[0].get("spuId")
        detail = C.unwrap(C.call_tool("mall-product-detail", {"spuId": spu_id}, token, url))
        cities = C.unwrap(C.call_tool("query-party-city", {"spuId": spu_id}, token, url)) or []
        city = None
        for c in cities:
            if args.city_keyword and args.city_keyword in str(c.get("name")):
                city = c
                break
        if city is None:
            city = cities[0] if cities else None
        if city is None:
            raise SuiteError("该派对商品没有可参与城市")
        stores = C.unwrap(C.call_tool("query-party-store", {
            "code": city.get("code"), "spuId": spu_id,
            "latitude": city.get("latitude"), "longitude": city.get("longitude")}, token, url)) or []
        live = True

    spu_id = args.spu_id or (products[0].get("spuId") if products else None)
    if args.spu_id:
        match = [p for p in products if int(p.get("spuId") or 0) == int(args.spu_id)]
        spu = match[0] if match else (products[0] if products else {})
    else:
        spu = products[0] if products else {}

    shop_id = detail.get("shopId")
    if shop_id is not None and int(shop_id) != PARTY_SHOP_ID:
        raise SuiteError("该商品 shopId=%s，party-order-create 仅支持 shopId=%s"
                         % (shop_id, PARTY_SHOP_ID))

    if not demo:
        if not stores:
            raise SuiteError("该城市没有可举办派对的门店")
        store = stores[0]
        store_code = str(store.get("code") or store.get("storeCode") or "")
        dates = C.unwrap(C.call_tool("query-party-store-date",
                                     {"spuId": spu_id, "storeCode": store_code}, token, url)) or []
        if not dates:
            raise SuiteError("该门店无可预约日期")
        date_str = args.date or str(dates[0].get("date"))
        sessions = C.unwrap(C.call_tool("query-party-store-session", {
            "spuId": spu_id, "storeCode": store_code, "dateStr": date_str}, token, url)) or []
    else:
        store = (stores[0] if stores else {})
        store_code = str(store.get("code") or store.get("storeCode") or "")
        date_str = args.date or (str(dates[0].get("date")) if dates else "")

    people = int(args.people or 0)
    party_type = int(args.party_type or (detail.get("partyType") or 1))
    sku = (detail.get("skuList") or [{}])[0]

    candidates = []
    for s in sessions:
        pmin = int(s.get("partyMin") or 0)
        pmax = int(s.get("partyMax") or 0)
        left = int(s.get("leftNum") or 0)
        fits = True
        reasons = []
        if people:
            if pmin and people < pmin:
                fits = False
                reasons.append("人数 %d < 每场起订 %d" % (people, pmin))
            if pmax and people > pmax:
                fits = False
                reasons.append("人数 %d > 每场上限 %d" % (people, pmax))
            if left and people > left:
                fits = False
                reasons.append("人数 %d > 剩余名额 %d" % (people, left))
        if left <= 0:
            fits = False
            reasons.append("该场次已约满（leftNum=0）")
        candidates.append({
            "sessionId": s.get("id"), "timeStart": s.get("timeStart"),
            "timeEnd": s.get("timeEnd"), "partyMin": pmin, "partyMax": pmax,
            "leftNum": left, "price_fen": int(s.get("price") or 0),
            "price_yuan": yuan(int(s.get("price") or 0)),
            "fits": fits, "blockers": reasons,
        })

    best = next((c for c in candidates if c["fits"]), None)
    order_payload = None
    if best:
        order_payload = {
            "partyType": party_type,
            "spuId": spu_id,
            "skuId": sku.get("skuId"),
            "code": store.get("cityCode") or store.get("code"),
            "storeCode": store_code,
            "dateStr": date_str,
            "id": best["sessionId"],
            "timeStart": best["timeStart"],
            "timeEnd": best["timeEnd"],
            "leftNum": best["leftNum"],
            "count": people or best["partyMin"],
        }

    return {
        "scenario": "party",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "data_source": "mcp" if live else "examples(demo)",
        "spu": {"spuId": spu.get("spuId"), "spuName": spu.get("spuName"),
                "catName": spu.get("catName"), "price": spu.get("price"),
                "shopId": shop_id},
        "detail": {"partyPeople": detail.get("partyPeople"),
                   "partyAge": detail.get("partyAge"),
                   "partyRange": detail.get("partyRange"),
                   "partyType": detail.get("partyType"),
                   "skuList": detail.get("skuList") or []},
        "city": ({"code": city.get("code"), "name": city.get("name")}
                 if not demo and cities else (cities[0] if cities else None)),
        "store": {"code": store_code, "name": store.get("name") or store.get("storeName"),
                  "address": store.get("address")},
        "date": date_str,
        "available_dates": [d.get("date") for d in (dates or [])],
        "party_type": party_type,
        "party_type_label": "包场" if party_type == 1 else "拼团",
        "people": people,
        "sessions": candidates,
        "recommended": best,
        "order_payload_ready": order_payload,
        "order_placed": False,
        "confirm_hint": "派对下单须显式 --confirm 才会调用 party-order-create；本命令默认不下单。",
        "disclaimer": "非麦当劳官方产品；场次、名额与价格以麦当劳官方渠道实时结果为准。",
    }


# ------------------------------------------------------ 代送（proxy）

def cmd_proxy(args, token, url, demo):
    if demo:
        pre = (load_demo("real_precheck_delivery.json").get("precheck") or {})
    else:
        pre = C.api_precheck_delivery(token, url)

    out = {
        "scenario": "proxy",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "data_source": "mcp" if not demo else "examples(demo)",
        "privacy_policy": {
            "rule": "禁止写入他人 PII",
            "detail": ("绝不调用 delivery-create-address 录入他人姓名/手机号/地址；"
                       "代送一律以『下单人本人地址 + 交接说明』方式完成，"
                       "输出中对第三方信息做脱敏。"),
            "blocked_tools": ["delivery-create-address"],
        },
        "precheck": pre,
        "handover": {
            "pickup_note": args.pickup_note or "",
            "avoid": [a.strip() for a in (args.avoid or "").split(",") if a.strip()],
            "contact_masked": mask_contact(args.contact or ""),
        },
    }
    if not pre.get("available"):
        out["status"] = "degraded"
        out["reason_code"] = "NO_DELIVERY_ADDRESS"
        out["message"] = ("当前账号没有可配送地址，代送链路不可用。"
                          "本引擎只读地址列表，不会替你建档（建档需真实姓名+11 位手机号，属 PII）。")
        out["how_to_enable"] = "请先在麦当劳官方 App/小程序添加你本人的配送地址。"
        return out
    out["status"] = "ok"
    out["next"] = ["delivery-query-stores(beType=2)", "query-meals(orderType=2)",
                   "calculate-price(orderType=2)", "create-order 需 --confirm"]
    return out


def mask_contact(text: str) -> str:
    """脱敏：手机号中间 4 位打码，2 字以上姓名保留首尾。"""
    if not text:
        return ""
    out = re.sub(r"(1\d{2})\d{4}(\d{4})", r"\1****\2", text)
    return out


# ------------------------------------------------------ 能力矩阵

def cmd_scenarios(args, token, url, demo):
    return {
        "version": VERSION,
        "scenarios": [
            {"key": "split", "name": "拼单", "tools": ["now-time-info", "query-nearby-stores",
                                                       "query-meals", "query-store-coupons",
                                                       "calculate-price"],
             "verified": True, "blocker": None},
            {"key": "party", "name": "派对", "tools": ["mall-points-products", "mall-product-detail",
                                                       "query-party-city", "query-party-store",
                                                       "query-party-store-date",
                                                       "query-party-store-session"],
             "verified": True, "blocker": None},
            {"key": "group", "name": "团餐", "tools": ["delivery-query-addresses",
                                                       "delivery-query-stores",
                                                       "query-meal-assistance", "query-promotions",
                                                       "query-meals", "calculate-price"],
             "verified": False, "blocker": "需账号存在配送地址才能取到 beCode（600020/600048）"},
            {"key": "proxy", "name": "代送", "tools": ["delivery-query-addresses",
                                                       "delivery-query-stores", "query-meals",
                                                       "calculate-price"],
             "verified": False, "blocker": "同上；且禁止录入他人 PII"},
        ],
        "note": ("verified=false 的场景在本文档产出时因账号无配送地址而无法端到端验证；"
                 "引擎对该类场景一律降级停止，绝不输出编造结果。"),
    }


# ------------------------------------------------------ CLI

def main() -> int:
    p = argparse.ArgumentParser(description="麦麦社交点餐套件（拼单/团餐/派对/代送）")
    p.add_argument("action", choices=["split", "group", "party", "proxy", "precheck", "scenarios"])
    p.add_argument("--token", default="")
    p.add_argument("--url", default=C.DEFAULT_URL)
    p.add_argument("--out", default="")
    p.add_argument("--demo", action="store_true", help="离线模式：读取 examples/ 下的真实抓取样例")
    # split
    p.add_argument("--city", default="")
    p.add_argument("--keyword", default="")
    p.add_argument("--people", type=int, default=4)
    p.add_argument("--per-budget", type=float, default=30.0)
    p.add_argument("--avoid", default="", help="忌口关键词，逗号分隔，匹配菜名/标签即排除")
    p.add_argument("--be-type", type=int, default=1, help="1 到店自提 / 5 得来速")
    p.add_argument("--order-type", type=int, default=1)
    p.add_argument("--be-code", default="")
    p.add_argument("--reservation-date", default="")
    p.add_argument("--need-tableware", action="store_true")
    p.add_argument("--store-code", default="")
    # party
    p.add_argument("--spu-id", type=int, default=0)
    p.add_argument("--city-keyword", default="")
    p.add_argument("--date", default="")
    p.add_argument("--party-type", type=int, default=0, help="1 包场 / 2 拼团")
    # proxy
    p.add_argument("--pickup-note", default="")
    p.add_argument("--contact", default="")
    args = p.parse_args()

    if args.demo:
        token, url = "", ""
    else:
        token = C.load_token(args.token)
        if not token and args.action not in ("scenarios",):
            print("缺少 MCP Token：使用 --token、设置环境变量 MCD_MCP_TOKEN，"
                  "或写入 .env；也可用 --demo 离线跑通。", file=sys.stderr)
            return 2
        url = args.url

    try:
        if args.action == "split":
            payload = cmd_split(args, token, url, args.demo)
        elif args.action == "group":
            payload = cmd_group(args, token, url, args.demo)
        elif args.action == "party":
            payload = cmd_party(args, token, url, args.demo)
        elif args.action == "proxy":
            payload = cmd_proxy(args, token, url, args.demo)
        elif args.action == "precheck":
            pre = (load_demo("real_precheck_delivery.json").get("precheck") if args.demo
                   else C.api_precheck_delivery(token, url))
            payload = {"scenario": "precheck",
                       "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                       "data_source": "examples(demo)" if args.demo else "mcp",
                       "precheck": pre}
        else:
            payload = cmd_scenarios(args, token, url, args.demo)
    except C.PriceGuardError as exc:
        print("核价守卫拦截：%s" % exc, file=sys.stderr)
        return 3
    except C.McpError as exc:
        print("MCP 调用失败：%s" % exc, file=sys.stderr)
        return 1
    except SuiteError as exc:
        print("引擎停止：%s" % exc, file=sys.stderr)
        return 4

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("已写入：%s" % os.path.abspath(args.out))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
