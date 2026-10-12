#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳 MCP Streamable HTTP 客户端（仅标准库，零第三方依赖）。

对 https://mcp.mcd.cn 做 JSON-RPC 直连：
    initialize -> tools/list -> tools/call

子命令：
    ping                     校验 Token 与连通性
    tools-list               列出全部工具（可 --out 导出含入参 schema）
    call <tool> '<json>'     调用任意工具
    now-time                 获取服务器当前时间
    fetch-stores             查询门店（city + keyword，beType 1 到店 / 5 得来速）
    fetch-menu               查询门店菜单（categories + meals 字典）
    fetch-detail             查询餐品详情（套餐组成 rounds）
    fetch-coupons            查询门店可用券
    price                    真实核价（强制 productCode/quantity，含 0 元哨兵）
    fetch-party              派对商品列表（catRuleIds 过滤）
    precheck-delivery        外送/团餐可用性预检

Token 读取优先级：--token > 环境变量 MCD_MCP_TOKEN > .env 文件。
Token 只用于请求头，不会写入任何输出文件。

实测契约（2026-10-12 live 校验，勿凭记忆修改）：
  * 响应同时带 content[].text 与 structuredContent，优先取 structuredContent。
  * 业务体为 {success, code, message, datetime, traceId, data}；
    success=false 时 code 携带业务错误码
    （600010 缺参/券缺 couponId+couponCode、600020 配送地址不存在、
      600048 外送 beType=2/5/6 必传 beCode、600058 城市或关键词为空）。
  * query-meals / query-meal-detail / query-store-coupons / calculate-price /
    create-order 均**必传** storeCode + orderType + beType，缺一即 600010。
  * calculate-price 的 items **必须**用 productCode + quantity：
    - 用 code + num  -> 600010「缺少商品code或者商品数量quantity不正确」
    - 用 code + quantity -> **success:true 但金额全为 0**（静默错价，最危险）
    - 用券时 item 内必须同时带 couponId 与 couponCode，只带其一 -> 600010
  * query-nearby-stores 单次最多返回 5 家门店，无分页参数；longitude/latitude 恒 0.0。
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 40
RETRY = 3
RETRY_SLEEP = 1.0
USER_AGENT = "mcd-social-suite/1.0.0"

# 官方限流：单 Token 600 次/分钟。扇出时保持温和间隔。
DEFAULT_THROTTLE = 0.15


class McpError(RuntimeError):
    """MCP 调用失败：携带 code / message，便于上层区分业务错误与网络错误。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class PriceGuardError(RuntimeError):
    """核价守卫失败：参数形态或返回值异常，宁可报错也不产出可疑金额。"""


# ------------------------------------------------------ Token

def load_token(cli_token: str = "") -> str:
    if cli_token:
        return cli_token
    env = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if env:
        return env
    roots = (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.getcwd())
    for base in roots:
        env_path = os.path.join(base, ".env")
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("MCD_MCP_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ------------------------------------------------------ items 守卫

def normalize_items(items):
    """把任意形态的购物车条目统一成官方要求形态，并拦截已知静默故障形态。

    官方要求（live 实测）：
        items[i] = {productCode: str, quantity: int[, couponId, couponCode]}

    拦截：
        * 出现 `num` 键                    -> 600010，直接拒绝
        * 出现 `code` 键（而非 productCode）-> success:true 且金额全 0，静默错价，直接拒绝
    """
    if not isinstance(items, list) or not items:
        raise PriceGuardError("items 必须是非空数组")
    out = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise PriceGuardError("items[%d] 必须是对象" % idx)
        for bad in ("num",):
            if bad in raw:
                raise PriceGuardError(
                    "items[%d] 含键 `%s`；官方只识别 `quantity`，传 `%s` 会触发 600010" % (idx, bad, bad))
        if "code" in raw:
            raise PriceGuardError(
                "items[%d] 含键 `code`；官方只识别 `productCode`。"
                "`code`+`quantity` 会被静默接受并返回金额 0，属高危错价形态，已拦截" % idx)
        pcode = raw.get("productCode")
        if not pcode:
            raise PriceGuardError("items[%d] 缺少 productCode" % idx)
        try:
            qty = int(raw.get("quantity", 0))
        except (TypeError, ValueError):
            raise PriceGuardError("items[%d] 的 quantity 不是整数" % idx)
        if qty <= 0:
            raise PriceGuardError("items[%d] 的 quantity 必须 > 0，当前 %s" % (idx, qty))
        item = {"productCode": str(pcode), "quantity": qty}
        if raw.get("couponId") or raw.get("couponCode"):
            if not (raw.get("couponId") and raw.get("couponCode")):
                raise PriceGuardError(
                    "items[%d] 用券必须同时提供 couponId 与 couponCode，"
                    "只带其一会触发 600010" % idx)
            item["couponId"] = raw["couponId"]
            item["couponCode"] = raw["couponCode"]
        out.append(item)
    return out


def assert_price_sane(result, items):
    """0 元哨兵：拦截「参数被静默吞掉导致金额全 0」的核价结果。"""
    if not isinstance(result, dict):
        return result
    requested = sum(i["quantity"] for i in items)
    plist = result.get("productList") or []
    got = sum(int(p.get("quantity") or 0) for p in plist)
    price = int(result.get("price") or 0)
    if got != requested:
        raise PriceGuardError(
            "核价守卫：请求 %d 件，productList 只回 %d 件，参数可能被静默丢弃，拒绝产出金额"
            % (requested, got))
    if price <= 0:
        raise PriceGuardError("核价守卫：应付金额 %d 分 <= 0，拒绝产出可疑结果" % price)
    return result


# ------------------------------------------------------ 协议

def rpc(method: str, params: dict, token: str, url: str) -> dict:
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10 ** 9, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + token,
        "User-Agent": USER_AGENT,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_exc = None
    for attempt in range(RETRY):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            raw = resp.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 401:
                raise McpError("401 Token 无效、已过期或未提供，请检查 MCD_MCP_TOKEN。", 401)
            if exc.code == 429:
                raise McpError("429 触发限流（600 次/分钟），请降低调用频率。", 429)
            if 500 <= exc.code < 600 and attempt < RETRY - 1:
                last_exc = "HTTP %s：%s" % (exc.code, detail[:200])
                time.sleep(RETRY_SLEEP)
                continue
            raise McpError("HTTP %s：%s" % (exc.code, detail[:400]), exc.code)
        except urllib.error.URLError as exc:
            if attempt < RETRY - 1:
                last_exc = "网络错误：%r" % (exc,)
                time.sleep(RETRY_SLEEP)
                continue
            raise McpError("网络错误：%r（若需代理请检查系统代理设置）" % (exc,))
    else:  # pragma: no cover - 仅当重试全部耗尽
        raise McpError(str(last_exc))

    raw = raw.strip()
    if not raw:
        return {}
    # 兼容 SSE 形态响应
    if raw.startswith("event:") or raw.startswith("data:") or "\ndata:" in raw:
        raw = "\n".join(ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:"))
    try:
        msg = json.loads(raw)
    except ValueError:
        raise McpError("响应不是合法 JSON：%s" % raw[:300])
    if "error" in msg:
        err = msg["error"]
        raise McpError("MCP 错误 %s：%s" % (err.get("code"), err.get("message")), err.get("code"))
    return msg.get("result", {})


def initialize(token: str, url: str) -> dict:
    return rpc("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "mcd-social-suite", "version": "1.0.0"},
    }, token, url)


def tools_list(token: str, url: str) -> list:
    return rpc("tools/list", {}, token, url).get("tools", [])


def call_tool(name: str, arguments: dict, token: str, url: str) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments or {}}, token, url)


# ------------------------------------------------------ 响应解析

def extract_json(text):
    """兜底：从「说明文字 + JSON」混合体里抠出 JSON。"""
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    starts = [i for i in (stripped.find('{"'), stripped.find("[{")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    open_ch = stripped[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stripped[start:idx + 1])
                except ValueError:
                    break
    return None


def unwrap(result: dict):
    """把 MCP 工具返回统一成 Python 业务对象。

    实测：structuredContent 已是规整的 {success, code, message, data}，
    优先取它；缺省时才回退到 content[].text 解析。
    """
    if not isinstance(result, dict):
        return result

    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        if not structured.get("success", True):
            raise McpError("接口返回失败 code=%s：%s" % (
                structured.get("code"), structured.get("message")), structured.get("code"))
        data = structured.get("data")
        inner = extract_json(data) if isinstance(data, str) else data
        return inner if inner is not None else data

    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(texts).strip()
    parsed = extract_json(joined)
    if parsed is None:
        if result.get("isError"):
            raise McpError("工具调用失败：%s" % joined[:300])
        return joined
    if isinstance(parsed, dict) and "success" in parsed:
        if not parsed.get("success"):
            raise McpError("接口返回失败 code=%s：%s" % (
                parsed.get("code"), parsed.get("message")), parsed.get("code"))
        data = parsed.get("data")
        inner = extract_json(data) if isinstance(data, str) else data
        return inner if inner is not None else data
    if result.get("isError"):
        raise McpError("工具调用失败：%s" % joined[:300])
    return parsed


# ------------------------------------------------------ 业务封装

def api_fetch_stores(token, url, city, keyword, be_type=1, throttle=DEFAULT_THROTTLE):
    params = {"beType": be_type, "searchType": 2, "city": city, "keyword": keyword}
    data = unwrap(call_tool("query-nearby-stores", params, token, url))
    time.sleep(throttle)
    return data if isinstance(data, list) else []


def api_fetch_menu(token, url, store_code, order_type=1, be_type=1, be_code="",
                   reservation_date="", throttle=DEFAULT_THROTTLE):
    params = {"storeCode": store_code, "orderType": order_type, "beType": be_type}
    if be_code:
        params["beCode"] = be_code
    if reservation_date:
        params["reservationDate"] = reservation_date
    data = unwrap(call_tool("query-meals", params, token, url))
    time.sleep(throttle)
    return data if isinstance(data, dict) else {}


def api_fetch_detail(token, url, store_code, code, order_type=1, be_type=1, be_code="",
                     throttle=DEFAULT_THROTTLE):
    params = {"storeCode": store_code, "orderType": order_type, "beType": be_type, "code": code}
    if be_code:
        params["beCode"] = be_code
    data = unwrap(call_tool("query-meal-detail", params, token, url))
    time.sleep(throttle)
    return data if isinstance(data, dict) else {}


def api_fetch_coupons(token, url, store_code, order_type=1, be_type=1, be_code="",
                      throttle=DEFAULT_THROTTLE):
    params = {"storeCode": store_code, "orderType": order_type, "beType": be_type}
    if be_code:
        params["beCode"] = be_code
    data = unwrap(call_tool("query-store-coupons", params, token, url))
    time.sleep(throttle)
    return data if isinstance(data, list) else []


def api_calculate_price(token, url, store_code, items, order_type=1, be_type=1, be_code="",
                        gm_service_code="", need_tableware=False, reservation_date="",
                        guard=True, throttle=DEFAULT_THROTTLE):
    """真实核价。items 经守卫归一化后再发送；返回前再做 0 元哨兵校验。"""
    norm = normalize_items(items)
    params = {
        "storeCode": store_code,
        "orderType": order_type,
        "beType": be_type,
        "items": norm,
        "needTableware": bool(need_tableware),
    }
    if be_code:
        params["beCode"] = be_code
    if gm_service_code:
        params["gmServiceCode"] = gm_service_code
    if reservation_date:
        params["reservationDate"] = reservation_date
    result = unwrap(call_tool("calculate-price", params, token, url))
    time.sleep(throttle)
    if guard and isinstance(result, dict):
        assert_price_sane(result, norm)
    return result


def api_precheck_delivery(token, url, throttle=DEFAULT_THROTTLE):
    """外送/团餐可用性预检：只读地址列表，绝不创建任何地址。"""
    data = unwrap(call_tool("delivery-query-addresses", {}, token, url))
    time.sleep(throttle)
    if isinstance(data, dict):
        addrs = data.get("addresses") or []
    elif isinstance(data, list):
        addrs = data
    else:
        addrs = []
    return {"available": bool(addrs), "count": len(addrs), "addresses": addrs}


def api_fetch_party_products(token, url, cat_rule_ids="1>6>20,1>6>21", page=1, page_size=20,
                             throttle=DEFAULT_THROTTLE):
    params = {"catRuleIds": cat_rule_ids, "page": page, "pageSize": page_size}
    data = unwrap(call_tool("mall-points-products", params, token, url))
    time.sleep(throttle)
    return data if isinstance(data, list) else []


def api_now_time(token, url):
    return unwrap(call_tool("now-time-info", {}, token, url))


# ------------------------------------------------------ 子命令

def dump(payload, out_path):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("已写入：%s" % os.path.abspath(out_path))
    else:
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="麦当劳 MCP Streamable HTTP 客户端（mcd-social-suite）")
    parser.add_argument("action", choices=["ping", "tools-list", "call", "now-time",
                                           "fetch-stores", "fetch-menu", "fetch-detail",
                                           "fetch-coupons", "price", "fetch-party",
                                           "precheck-delivery"])
    parser.add_argument("tool_or_args", nargs="?", default="")
    parser.add_argument("arguments", nargs="?", default="{}")
    parser.add_argument("--token", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="")
    # 通用
    parser.add_argument("--store-code", default="")
    parser.add_argument("--order-type", type=int, default=1)
    parser.add_argument("--be-type", type=int, default=1)
    parser.add_argument("--be-code", default="")
    parser.add_argument("--reservation-date", default="")
    parser.add_argument("--items", default="", help='JSON 数组，如 [{"productCode":"x","quantity":2}]')
    parser.add_argument("--need-tableware", action="store_true")
    parser.add_argument("--no-guard", action="store_true", help="关闭 0 元哨兵（仅供调测复现故障用）")
    # fetch-stores
    parser.add_argument("--city", default="")
    parser.add_argument("--keyword", default="")
    # fetch-detail
    parser.add_argument("--code", default="")
    # fetch-party
    parser.add_argument("--cat-rule-ids", default="1>6>20,1>6>21")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    args = parser.parse_args()

    token = load_token(args.token)
    if not token:
        print("缺少 MCP Token：使用 --token、设置环境变量 MCD_MCP_TOKEN，或写入 .env。", file=sys.stderr)
        return 2

    try:
        if args.action == "ping":
            print(json.dumps(initialize(token, args.url), ensure_ascii=False))
            return 0
        if args.action == "tools-list":
            tools = tools_list(token, args.url)
            print("工具数量：%d" % len(tools))
            for t in tools:
                print("- %s | %s" % (t.get("name"), (t.get("description") or "").split("\n")[0][:70]))
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(tools, fh, ensure_ascii=False, indent=2)
                print("已写入：%s" % os.path.abspath(args.out))
            return 0
        if args.action == "call":
            try:
                params = json.loads(args.arguments or "{}")
            except ValueError as exc:
                print("参数不是合法 JSON：%r" % (exc,), file=sys.stderr)
                return 2
            result = unwrap(call_tool(args.tool_or_args, params, token, url=args.url))
            if args.out:
                dump(result, args.out)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2)
                      if isinstance(result, (dict, list)) else str(result))
            return 0
        if args.action == "now-time":
            dump({"source_tool": "now-time-info", "time": api_now_time(token, args.url)}, args.out)
            return 0
        if args.action == "fetch-stores":
            if not args.city or not args.keyword:
                print("fetch-stores 需要同时提供 --city 与 --keyword（缺失会触发 600058）。",
                      file=sys.stderr)
                return 2
            stores = api_fetch_stores(token, args.url, args.city, args.keyword, args.be_type)
            dump({"source_tool": "query-nearby-stores", "params": {
                "city": args.city, "keyword": args.keyword, "beType": args.be_type},
                "count": len(stores), "stores": stores}, args.out)
            return 0
        if args.action == "fetch-menu":
            if not args.store_code:
                print("fetch-menu 需要 --store-code。", file=sys.stderr)
                return 2
            menu = api_fetch_menu(token, args.url, args.store_code, args.order_type,
                                  args.be_type, args.be_code, args.reservation_date)
            meals = menu.get("meals") or {}
            dump({"source_tool": "query-meals", "store_code": args.store_code,
                  "category_count": len(menu.get("categories") or []),
                  "meal_count": len(meals), "menu": menu}, args.out)
            if not args.out:
                print("分类 %d 个 / 餐品 %d 件" % (len(menu.get("categories") or []), len(meals)))
            return 0
        if args.action == "fetch-detail":
            if not args.store_code or not args.code:
                print("fetch-detail 需要 --store-code 与 --code。", file=sys.stderr)
                return 2
            detail = api_fetch_detail(token, args.url, args.store_code, args.code,
                                      args.order_type, args.be_type, args.be_code)
            dump({"source_tool": "query-meal-detail", "detail": detail}, args.out)
            return 0
        if args.action == "fetch-coupons":
            if not args.store_code:
                print("fetch-coupons 需要 --store-code。", file=sys.stderr)
                return 2
            coupons = api_fetch_coupons(token, args.url, args.store_code,
                                        args.order_type, args.be_type, args.be_code)
            dump({"source_tool": "query-store-coupons", "count": len(coupons),
                  "coupons": coupons}, args.out)
            return 0
        if args.action == "price":
            if not args.store_code or not args.items:
                print("price 需要 --store-code 与 --items。", file=sys.stderr)
                return 2
            items = json.loads(args.items)
            result = api_calculate_price(token, args.url, args.store_code, items,
                                         args.order_type, args.be_type, args.be_code,
                                         need_tableware=args.need_tableware,
                                         reservation_date=args.reservation_date,
                                         guard=not args.no_guard)
            dump({"source_tool": "calculate-price", "store_code": args.store_code,
                  "items": normalize_items(items), "result": result}, args.out)
            return 0
        if args.action == "fetch-party":
            products = api_fetch_party_products(token, args.url, args.cat_rule_ids,
                                                args.page, args.page_size)
            dump({"source_tool": "mall-points-products", "catRuleIds": args.cat_rule_ids,
                  "count": len(products), "products": products}, args.out)
            return 0
        if args.action == "precheck-delivery":
            pre = api_precheck_delivery(token, args.url)
            dump({"source_tool": "delivery-query-addresses", "precheck": pre}, args.out)
            print("可配送地址数：%d（0 = 外送/团餐/代送链路不可用，将走降级路径）" % pre["count"])
            return 0
    except PriceGuardError as exc:
        print("核价守卫拦截：%s" % exc, file=sys.stderr)
        return 3
    except McpError as exc:
        print("MCP 调用失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
