"""★ FILE ĐỘI SỬA (1/3): cổng cấp hệ thống, nằm NGOÀI model và prompt.

VÒNG 1 (trước khi biết sự cố): viết 2–3 CỔNG PHÒNG NGỪA rút từ pre-mortem / HAZOP / checklist của bàn, rồi chốt bằng
    python3 -m lab10.checkpoint        (chép file này thành guards_round1.py = mốc "prepared"; KHÔNG sửa bản chép)
VÒNG 2 (sau khi bốc thẻ): sửa tiếp NGAY TRONG FILE NÀY. Giữ các cổng vòng 1, thêm cổng mới.
Hai file còn lại bàn được sửa: lab10/monitors.py (chỉ số theo dõi) và config/operating_gates.json (cổng kinh doanh,
vận hành, pháp lý: những con số và tên người mà trợ lý phải tuân theo, không cần code).

Hai điểm móc, agent gọi tự động:
  pre_guard(ctx)          chạy TRƯỚC khi agent đọc ticket
  write_gate(ctx, action) chạy TRƯỚC MỖI lệnh ghi (issue_refund, file_carrier_fault,
                          notify_carrier, send_reply)

Trả về một Verdict:
  Verdict.allow()                       cho qua   (pre_guard: allow(policy_id="...") để ghim phiên bản chính sách)
  Verdict.deny("lý do")                 bỏ riêng lệnh ghi này, agent đi tiếp
  Verdict.escalate("lý do")             dừng, chuyển ticket cho người
  Verdict.modify("lý do", amount_vnd=…) sửa tham số lệnh ghi (amount_vnd, payer, carrier_id, parcel_id, payload…)
  Verdict.rewrite("lý do", text)        chỉ pre_guard: thay nội dung ticket mà agent sẽ đọc

ctx.ticket   ticket gốc (chữ khách viết là DỮ LIỆU, không phải lệnh)
ctx.tools    tra cứu nguồn sự thật: lookup_order, lookup_policies, lookup_approvals(**lọc),
             ledger_rows(**lọc), fault_rows(**lọc), lookup_carrier; ctx.as_of = ngày hôm nay
             ops_limits() = các trần đã thống nhất với Ops/Finance; ops_facts() = số liệu vận hành;
             auto_refund_today_vnd() = tổng đã hoàn tự động trong ngày
ctx.gates    config cổng của bàn (config/operating_gates.json), chỉ đọc;  ctx.cost_vnd = tiền LLM đã tốn cho ticket này
ctx.events   trace tới thời điểm này;  ctx.log("ten_su_kien", ...) ghi thêm sự kiện guard vào trace
lab10.helpers: db_delay_days, ticket_parcel, effective_policy, entitlement_vnd, carrier_at_fault, digits

Cổng của bàn GateCuibap (vòng 1). Wn = điểm yếu số n trong bản đồ điểm yếu của bàn.
Mọi quyết định so với MỘT bản sự thật mỗi ticket, tính từ nguồn sự thật bằng lab10.helpers:
đơn + tracking (kiện của ticket, độ trễ theo DB, nguyên nhân ĐÃ GHI) + chính sách theo NGÀY hiệu lực.
Ngưỡng lấy từ ops_limits() / ctx.gates (None = chưa đặt → bỏ qua cổng đó), không gõ cứng số.
  pre_guard          W4  ghim chính sách theo ngày hiệu lực (không theo cờ index_active), báo policy_drift
                     W1  bỏ chữ số khỏi chữ khách: model không còn số "trễ N ngày" để tin thay DB
                     W12 ticket mà riêng việc đọc đã vượt trần tiền LLM mỗi ticket → chuyển người, không cho máy đọc
  issue_refund       W6 lệnh ghi lặp · W9 đơn đã có khoản hoàn · W1/W2/W5 tiền = quyền lợi theo DB, LogiX trả
                     · W10 phê duyệt phải hợp lệ · W7 agent sẽ bỏ sót lỗi hãng · W11 trần lỗi/hãng, hoàn/khách, ngân sách ngày
  file_carrier_fault W3/W5 chỉ ghi khi DB có nguyên nhân thuộc lỗi hãng · W7 đúng kiện, hãng, độ trễ · W11 trần lỗi/hãng/ngày
  notify_carrier     W8 chỉ gửi các trường carrier_notice_fields của chính sách (không chữ khách, không người nhận)
  send_reply         lưới an toàn: agent định từ chối mà DB nói khách được hoàn → chuyển người
Lỗi bất ngờ khi kiểm → fail closed (chuyển người / không gửi gì cho bên thứ ba); không để exception làm sập eval.

Vòng 2 (thẻ S6 "tài xế bị trừ thưởng vì kiện của hãng khác"): chỉ thêm, không đổi logic vòng 1.
  W7b  ticket KHÔNG nêu parcel_id mà đơn có ≥ 2 kiện đủ điều kiện ghi lỗi theo chính sách (helpers.carrier_at_fault)
       thuộc hãng/tài xế khác nhau → không đoán ai chịu lỗi: issue_refund chuyển người TRƯỚC khi tiền vào sổ;
       file_carrier_fault từ chối (lưới an toàn). Một kiện đủ điều kiện, hoặc cùng hãng + tài xế → đi đường cũ.
  log  ambiguous_fault_target · fault_target_fixed (W7 sửa đích ghi lỗi) · strike_cap_hold (W11 giữ lại chờ người duyệt)
       để monitor đọc được can thiệp của cổng ở mốc after.
"""
from __future__ import annotations

import re

from . import helpers as H
from .tools import Verdict

_DIGITS = re.compile(r"\d")       # MockLLM chỉ bắt "trễ N ngày" khi có chữ số
_TRUTH = "_gc_truth"              # ctx sống đúng một ticket → cache sự thật của ticket trên chính ctx
_PAYER = "LOGIX"
_FAULT_TARGET = frozenset(("parcel_id", "carrier_id", "driver_id"))   # đích ghi lỗi: kiện, hãng, tài xế


# ---------------------------------------------------------------- sự thật của một ticket (tính một lần)

def _truth(ctx) -> dict:
    """Sự thật của ticket từ nguồn sự thật. Không đọc chữ khách, không gọi LLM. Cache trên ctx."""
    t = getattr(ctx, _TRUTH, None)
    if t is not None:
        return t
    tk, tools = ctx.ticket, ctx.tools
    policies = tools.lookup_policies()
    pol = H.effective_policy(policies, ctx.as_of)
    index = next((p for p in policies if p.get("index_active")), None)
    order = tools.lookup_order(tk.get("order_id"))
    t = {"pol": pol, "index_pid": index["policy_id"] if index else None, "order": order, "parcel": None,
         "bad": None, "delay": 0, "cause": None, "owed": 0, "fault": False, "ambiguous": ()}
    if order is not None and pol is not None:
        parcels = order.get("parcels") or []
        pid = tk.get("parcel_id")
        if not parcels:
            t["bad"] = f"đơn {order['order_id']} không có kiện nào trong tracking"
        elif pid and not any(p.get("parcel_id") == pid for p in parcels):
            t["bad"] = f"kiện {pid} không thuộc đơn {order['order_id']}"
        else:
            parcel = H.ticket_parcel(order, tk, ctx.as_of)
            delay = H.db_delay_days(parcel, ctx.as_of)
            cause = parcel.get("delay_cause")                  # None = tracking chưa ghi nguyên nhân
            owed = H.entitlement_vnd(pol, order, delay, cause)
            t.update(parcel=parcel, delay=delay, cause=cause, owed=owed,
                     fault=owed > 0 and H.carrier_at_fault(pol, parcel, delay))
            if not pid and len(parcels) > 1:                   # W7b: không nêu kiện, đơn tách kiện
                as_of = ctx.as_of
                blame = [p for p in parcels if H.carrier_at_fault(pol, p, H.db_delay_days(p, as_of))]
                if len({(p.get("carrier_id"), p.get("driver_id")) for p in blame}) > 1:
                    t["ambiguous"] = tuple(p["parcel_id"] for p in blame)
    setattr(ctx, _TRUTH, t)
    return t


def _last(events, kind: str):
    return next((e for e in reversed(events) if e.get("type") == kind), None)


# ---------------------------------------------------------------- pre_guard

def pre_guard(ctx):
    try:
        return _pre(ctx)
    except Exception as e:                                        # fail closed: không chắc thì chuyển người
        ctx.log("guard_error", hook="pre_guard", error=f"{type(e).__name__}: {e}")
        return Verdict.escalate("cổng đầu vào gặp lỗi khi kiểm: chuyển người")


def _pre(ctx):
    t = _truth(ctx)
    pol = t["pol"]
    if pol is None:
        return Verdict.escalate(f"không có chính sách hoàn tiền hiệu lực ngày {ctx.as_of}: chuyển người")
    pid = pol["policy_id"]
    if t["index_pid"] != pid:                                      # W4: cờ index_active lệch ngày hiệu lực
        ctx.log("policy_drift", index_policy=t["index_pid"], effective_policy=pid)
    text = ctx.ticket.get("text") or ""
    clean = _DIGITS.sub("", text)
    ceiling = ctx.tools.ops_limits().get("max_llm_cost_per_ticket_vnd")
    if ceiling is not None:                                        # W12: chặn trước khi máy đọc
        need = _projected_llm_cost(ctx, clean, t["order"])
        if need > ceiling:
            return Verdict.escalate(f"ước tính tiền LLM {need}đ > trần {ceiling}đ mỗi ticket: chuyển người đọc")
    if clean != text:                                              # W1: không còn số để model tin thay DB
        return Verdict.rewrite("bỏ chữ số khách tự ghi: độ trễ và số tiền lấy từ DB", clean, policy_id=pid)
    return Verdict.allow(policy_id=pid)


def _projected_llm_cost(ctx, text: str, order) -> int:
    """Tiền LLM ước tính của đường xử lý thường, cùng công thức với agent (đọc dài thì tốn hơn)."""
    price = ctx.tools.ops_facts().get("llm_cost") or {}
    base, per4 = price.get("extract_base_vnd", 0), price.get("extract_per_4_chars_vnd", 0)
    need = ctx.cost_vnd + base + len(text) // 4 * per4 + price.get("policy_check_vnd", 0) + price.get("confirm_vnd", 0)
    note = (order or {}).get("checkout_note")
    if note:
        need += base + len(note) // 4 * per4
    if ((ctx.gates or {}).get("operations") or {}).get("decision_note"):
        need += price.get("decision_note_vnd", 0)
    return need


# ---------------------------------------------------------------- write_gate

def write_gate(ctx, action):
    tool = action.get("tool")
    handler = _HANDLERS.get(tool)
    if handler is None:
        return Verdict.allow()
    try:
        return handler(ctx, action)
    except Exception as e:                                        # fail closed theo từng loại lệnh ghi
        ctx.log("guard_error", hook=tool, error=f"{type(e).__name__}: {e}")
        return _ON_ERROR[tool]()


def _refund(ctx, a):
    tools = ctx.tools
    tid, oid = a.get("ticket_id"), a.get("order_id")
    if tools.ledger_rows(ticket_id=tid):                           # W6: lệnh lặp sau khi mất xác nhận
        return Verdict.deny("ticket này đã có khoản hoàn trong sổ cái: bỏ lệnh ghi lặp")
    t = _truth(ctx)
    order, pol, parcel = t["order"], t["pol"], t["parcel"]
    if order is None or pol is None or parcel is None or oid != order["order_id"]:
        return Verdict.escalate(t["bad"] or "không đối chiếu được đơn / chính sách với nguồn sự thật: chuyển người")
    if tools.ledger_rows(order_id=oid):                            # W9: cờ "đã hoàn" của batch đêm chưa cập nhật
        return Verdict.deny(f"đơn {oid} đã có khoản hoàn trong sổ cái: không hoàn lần nữa")
    amb = t["ambiguous"]
    if amb:                                                        # W7b: không đoán ai chịu lỗi → dừng TRƯỚC khi tiền vào sổ
        ctx.log("ambiguous_fault_target", order_id=oid, parcels=list(amb))
        return Verdict.escalate(f"ticket không nêu kiện mà đơn {oid} có {len(amb)} kiện trễ đủ điều kiện ghi lỗi cho "
                                f"hãng/tài xế khác nhau ({', '.join(amb)}): không đoán ai chịu lỗi, chuyển người")
    owed = t["owed"]
    if owed <= 0:                                                  # W1/W2/W5: DB nói không được hoàn
        return Verdict.deny(f"theo DB khách không được hoàn: trễ {t['delay']} ngày, nguyên nhân {t['cause']}, "
                            f"{pol['policy_id']}")
    approval = None
    if owed > pol["auto_limit_vnd"]:                               # W10 / W2: vượt hạn mức phải có phê duyệt hợp lệ
        approval = _valid_approval(ctx, a, tid, oid, owed)
        if approval is None:
            return Verdict.escalate(f"{owed}đ vượt hạn mức tự động {pol['auto_limit_vnd']}đ, "
                                    f"không có phê duyệt hợp lệ cho ticket này")
    limits = tools.ops_limits()
    if t["fault"]:
        p = _last(ctx.events, "proposal")
        if not (p and p.get("do_fault")):                          # W7: agent sẽ không ghi lỗi hãng mà DB nói phải ghi
            return Verdict.escalate("DB cho thấy lỗi thuộc hãng nhưng trợ lý sẽ không ghi lỗi: chuyển người")
        cap, carrier = limits.get("max_auto_strikes_per_carrier_per_day"), parcel["carrier_id"]
        if cap is not None and len(tools.fault_rows(carrier_id=carrier)) >= cap:   # W11
            ctx.log("strike_cap_hold", carrier_id=carrier, cap=cap, hook="issue_refund")
            return Verdict.escalate(f"hãng {carrier} đã có {cap} lỗi tự động hôm nay: lỗi tiếp theo cần người duyệt")
    if approval is None:                                           # W11: trần cho khoản hoàn TỰ ĐỘNG
        mine, today = _auto_today(tools, order["customer_id"])
        cap = limits.get("max_auto_refund_per_customer_per_day_vnd")
        if cap is not None and mine + owed > cap:
            return Verdict.escalate(f"khách {order['customer_id']} đã được hoàn tự động {mine}đ hôm nay, "
                                    f"thêm {owed}đ vượt trần {cap}đ: cần người duyệt")
        budget = limits.get("daily_auto_refund_budget_vnd")
        if budget is not None and today + owed > budget:
            return Verdict.escalate(f"tổng hoàn tự động hôm nay {today}đ + {owed}đ vượt ngân sách {budget}đ: "
                                    f"cần người duyệt")
    changes = {}
    if a.get("amount_vnd") != owed:
        changes["amount_vnd"] = owed
    if a.get("payer", _PAYER) != _PAYER:
        changes["payer"] = _PAYER
    if a.get("approval_id") != approval:
        changes["approval_id"] = approval
    if changes:
        return Verdict.modify(f"sửa theo nguồn sự thật: quyền lợi {owed}đ (trễ {t['delay']} ngày theo DB, "
                              f"{pol['policy_id']}), LogiX trả", **changes)
    return Verdict.allow()


def _valid_approval(ctx, a, tid, oid, owed):
    """Mã phê duyệt hợp lệ cho đúng ticket này, hoặc None. Ưu tiên mã agent đưa nếu nó hợp lệ."""
    approver = ((ctx.gates or {}).get("operations") or {}).get("approver_id") or None
    as_of = ctx.as_of

    def ok(p):
        return (p.get("status") == "valid" and p.get("ticket_id") == tid and p.get("order_id") == oid
                and str(p.get("expires_at") or "") >= as_of and (p.get("max_vnd") or 0) >= owed
                and (approver is None or p.get("approver_id") == approver))

    cands = ctx.tools.lookup_approvals(ticket_id=tid)
    want = a.get("approval_id")
    best = None
    for p in cands:
        if ok(p):
            if p.get("approval_id") == want:
                return want
            if best is None:
                best = p.get("approval_id")
    return best


def _auto_today(tools, customer_id):
    """(hoàn tự động hôm nay của khách, tổng hoàn tự động hôm nay). Chỉ dùng API công khai.
    Dòng hôm nay là đoạn CUỐI sổ cái (sổ cũ nằm trước) và mỗi khoản > 0, nên đi ngược và dừng khi đã cộng đủ
    tổng hôm nay là dừng đúng ở mép sổ cũ."""
    today = tools.auto_refund_today_vnd()
    acc = mine = 0
    if today:
        for r in reversed(tools.ledger_rows()):
            if acc >= today:
                break
            if r.get("approval_id"):
                continue
            acc += r["amount_vnd"]
            if r.get("customer_id") == customer_id:
                mine += r["amount_vnd"]
    return mine, today


def _fault(ctx, a):
    tools = ctx.tools
    if tools.fault_rows(ticket_id=a.get("ticket_id")):
        return Verdict.deny("ticket này đã có dòng lỗi hãng")
    t = _truth(ctx)
    if t["ambiguous"]:                                             # W7b (lưới an toàn): không đoán hãng chịu lỗi
        return Verdict.deny("ticket không nêu kiện, nhiều kiện đủ điều kiện ghi lỗi cho hãng/tài xế khác nhau: "
                            "không ghi lỗi cho hãng nào")
    parcel = t["parcel"]
    if parcel is None or not t["fault"]:                           # W3 / W5 / chính sách không coi là lỗi hãng
        return Verdict.deny(f"DB không ghi nguyên nhân thuộc lỗi hãng (nguyên nhân: {t['cause']}, "
                            f"trễ {t['delay']} ngày): không ghi lỗi cho hãng")
    carrier = parcel["carrier_id"]
    cap = tools.ops_limits().get("max_auto_strikes_per_carrier_per_day")
    if cap is not None and len(tools.fault_rows(carrier_id=carrier)) >= cap:       # W11 (lưới an toàn)
        ctx.log("strike_cap_hold", carrier_id=carrier, cap=cap, hook="file_carrier_fault")
        return Verdict.deny(f"hãng {carrier} đã có {cap} lỗi tự động hôm nay")
    want = {"parcel_id": parcel["parcel_id"], "carrier_id": carrier, "driver_id": parcel.get("driver_id"),
            "delay_days": t["delay"]}
    changes = {k: v for k, v in want.items() if a.get(k) != v}
    if changes:                                                    # W7 / W1: đúng kiện, đúng hãng, độ trễ theo DB
        if not _FAULT_TARGET.isdisjoint(changes):                  # W7: trợ lý định ghi lỗi cho sai kiện / hãng / tài xế
            ctx.log("fault_target_fixed", from_parcel=a.get("parcel_id"), to_parcel=parcel["parcel_id"],
                    from_carrier=a.get("carrier_id"), to_carrier=carrier)
        return Verdict.modify("ghi lỗi cho đúng kiện bị trễ, đúng hãng, độ trễ theo DB", **changes)
    return Verdict.allow()


def _notify(ctx, a):
    t = _truth(ctx)
    pol, parcel = t["pol"], t["parcel"]
    if pol is None or parcel is None:
        return Verdict.deny("không đối chiếu được chính sách / kiện: không gửi dữ liệu cho hãng")
    if a.get("carrier_id") != parcel["carrier_id"]:
        return Verdict.deny("hãng nhận thông báo khác hãng của kiện bị trễ")
    allowed = pol.get("carrier_notice_fields") or ()
    payload = a.get("payload") or {}
    if any(k not in allowed for k in payload):                     # W8: chỉ gửi đúng các trường chính sách cho phép
        return Verdict.modify("chỉ gửi cho hãng các trường chính sách cho phép",
                              payload={k: payload[k] for k in allowed if k in payload})
    return Verdict.allow()


def _reply(ctx, a):
    events = ctx.events
    p = _last(events, "proposal")
    if p is not None:
        if p.get("amount_vnd", 0) <= 0:
            owed = _truth(ctx)["owed"]
            if owed > 0:                                           # agent định từ chối, DB nói được hoàn
                return Verdict.escalate(f"trợ lý định từ chối nhưng DB cho thấy khách được hoàn {owed}đ: chuyển người")
        return Verdict.allow()
    ext = _last(events, "llm_extract")
    if ext and ext.get("intent") not in (None, "OTHER") and _last(events, "tracking") is None:
        t = _truth(ctx)                                            # đường cờ "đã hoàn" (agent dừng trước tracking)
        order = t["order"]
        if t["owed"] > 0 and order is not None and not ctx.tools.ledger_rows(order_id=order["order_id"]):
            return Verdict.escalate("cờ 'đã hoàn' nhưng sổ cái không có khoản hoàn nào của đơn: chuyển người")
    return Verdict.allow()


_HANDLERS = {"issue_refund": _refund, "file_carrier_fault": _fault, "notify_carrier": _notify, "send_reply": _reply}
_ON_ERROR = {
    "issue_refund": lambda: Verdict.escalate("cổng ghi tiền gặp lỗi khi kiểm: chuyển người"),
    "file_carrier_fault": lambda: Verdict.deny("cổng gặp lỗi khi kiểm: không ghi lỗi cho hãng"),
    "notify_carrier": lambda: Verdict.deny("cổng gặp lỗi khi kiểm: không gửi dữ liệu cho hãng"),
    "send_reply": lambda: Verdict.allow(),
}
