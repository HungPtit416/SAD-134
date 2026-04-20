from __future__ import annotations

import re
from dataclasses import dataclass

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .indexing import retrieve_similar
from .openai_client import chat_completion
from .recommendation import hydrate_products, recommend_products
from .graph_gateway import graph_context_for_rag, upsert_event_to_graph


@dataclass(frozen=True)
class ChatResult:
    answer: str
    context: dict


def _parse_budget_vnd(text: str) -> tuple[int | None, int | None]:
    """
    Parse simple Vietnamese budget phrases like:
    - "dưới 7 triệu", "tầm 15-25 triệu", "dưới 10tr"
    Returns (min_budget_vnd, max_budget_vnd) if detected.
    """

    s = (text or "").lower()
    s = s.replace(",", ".")
    s = s.replace("–", "-").replace("—", "-")

    # dưới X triệu / dưới Xtr
    m = re.search(r"(dưới|<=)\s*(\d+(?:\.\d+)?)\s*(triệu|tr)\b", s)
    if m:
        return None, int(float(m.group(2)) * 1_000_000)

    # tầm/min-max triệu
    m = re.search(r"(tầm|khoảng)?\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(triệu|tr)\b", s)
    if m:
        lo = int(float(m.group(2)) * 1_000_000)
        hi = int(float(m.group(3)) * 1_000_000)
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    return None, None


def _prefer_non_gaming_laptop(s: str) -> bool:
    """Laptop for study/office/long battery — exclude gaming SKUs unless user asks for gaming."""

    s = (s or "").lower()
    if not ("laptop" in s or "macbook" in s):
        return False
    # Explicit non-gaming / dev / study (check before substring 'chơi game' in 'không chơi game')
    if any(
        k in s
        for k in [
            "không cần gaming",
            "không gaming",
            "không chơi game",
            "học lập trình",
            "lập trình",
            "vscode",
            "docker",
            "đồ án",
        ]
    ):
        return True
    if any(k in s for k in ["học tập", "sinh viên", "văn phòng", "pin ổn"]):
        return True
    # Explicit gaming intent
    if "gaming laptop" in s or re.search(r"\bchơi game\b", s) or "game nặng" in s:
        return False
    return False


def _extract_product_ids(text: str) -> list[int]:
    """
    Parse references like:
    - "product_id: 7"
    - "product_id 7"
    - "id: 7" / "#7"
    """

    s = text or ""
    ids: list[int] = []
    for m in re.finditer(r"product_id\s*[:\s]*(\d+)", s, flags=re.I):
        ids.append(int(m.group(1)))
    for m in re.finditer(r"(?:\bid\b|#)\s*:?\s*(\d+)\b", s, flags=re.I):
        n = int(m.group(1))
        if n not in ids:
            ids.append(n)
    return ids


def _resolve_compare_pair_ids(message: str, first_id: int, products: list[Product]) -> list[int]:
    s = (message or "").lower()
    best: Product | None = None
    best_score = 0.0
    for p in products:
        if int(p.id) == first_id:
            continue
        nk = _name_key(p)
        score = 0.0
        for token in re.findall(r"[a-z0-9]+", s):
            if len(token) < 2:
                continue
            if token in nk:
                score += 1.5
        if "tuf" in s and "tuf" in nk:
            score += 5.0
        if "asus" in s and "asus" in nk:
            score += 2.0
        if "hp" in s and "hp" in nk:
            score += 2.0
        if "macbook" in s and "macbook" in nk:
            score += 4.0
        if "galaxy" in s and "galaxy" in nk:
            score += 2.0
        if score > best_score:
            best_score = score
            best = p
    if best is not None and best_score >= 2.0:
        return [first_id, int(best.id)]
    return [first_id]


def _is_gaming_laptop_name(name: str) -> bool:
    n = (name or "").lower()
    return any(
        x in n
        for x in (
            "gaming",
            "tuf",
            "strix",
            "legion",
            "rtx",
            "gtx",
            "predator",
            "nitro",
        )
    )


def _name_key(p: Product) -> str:
    return f"{p.name} {p.sku or ''}".lower()


def _is_cable_product(p: Product) -> bool:
    k = _name_key(p)
    return "cable" in k or "cáp" in k or ("usb" in k and "charger" not in k)


def _is_charger_product(p: Product) -> bool:
    k = _name_key(p)
    # If user asks for a cable ("cáp sạc"), treat it as cable not wall charger.
    if "cáp" in k or "cable" in k:
        return False
    return "charger" in k or "củ sạc" in k or "sạc" in k


def _is_case_product(p: Product) -> bool:
    k = _name_key(p)
    return "case" in k or "ốp" in k or "bao da" in k


def _answer_compare_vi(message: str, products: list[Product] | None = None) -> str | None:
    msg = (message or "").strip()
    s = msg.lower()
    if not any(k in s for k in ["so sánh", "compare", " vs ", " với "]):
        return None
    ids = _extract_product_ids(msg)
    if products and len(ids) == 1:
        ids = _resolve_compare_pair_ids(msg, ids[0], products)
    if len(ids) < 2:
        return None

    try:
        a = get_product(ids[0])
        b = get_product(ids[1])
    except Exception:  # noqa: BLE001
        return None

    focus_cam = any(k in s for k in ["camera", "chụp", "quay"])
    lines = [
        f"So sánh nhanh giữa **{a.name}** (product_id: {a.id}) và **{b.name}** (product_id: {b.id}):",
        f"- Giá: {a.price} {a.currency or ''} | {b.price} {b.currency or ''}",
    ]
    if focus_cam:
        lines.extend(
            [
                "",
                "Nếu bạn **ưu tiên camera**:",
                "- Dòng flagship Android (ví dụ Galaxy S24) thường linh hoạt hơn về tính năng/chế độ chụp.",
                "- iPhone thường mạnh về tính ổn định màu và quay video.",
                "",
                "Mô tả trong shop hiện tại:",
                f"- {a.name}: {(a.description or '')[:200]}",
                f"- {b.name}: {(b.description or '')[:200]}",
                "",
                f"Gợi ý nhanh: nếu muốn nhiều tuỳ chọn chụp/Android → cân nhắc **{b.name}** (product_id: {b.id}). "
                f"Nếu ưu tiên hệ sinh thái Apple/quay video ổn định → cân nhắc **{a.name}** (product_id: {a.id}).",
            ]
        )
    else:
        lines.append("")
        ca = (a.category_name or "").lower()
        cb = (b.category_name or "").lower()
        if "laptop" in ca and "laptop" in cb:
            if any(k in s for k in ["học", "lập trình", "vscode", "docker", "đồ án"]):
                lines.append(
                    "Bạn ưu tiên tiêu chí nào (RAM/SSD, pin, màn hình, hay giá) để mình chốt giúp 1 lựa chọn?"
                )
            else:
                lines.append(
                    "Bạn ưu tiên tiêu chí nào (hiệu năng, pin, màn hình, hay giá) để mình chốt giúp 1 lựa chọn?"
                )
        else:
            lines.append("Bạn ưu tiên tiêu chí nào (camera/pin/màn hình/giá) để mình chốt giúp 1 lựa chọn?")
    return "\n".join(lines)


def _tokenize_product_query(q: str) -> list[str]:
    t = re.sub(r"[^\w\s]", " ", (q or "").lower())
    stop = {
        "bản",
        "phiên",
        "phiênbản",
        "có",
        "không",
        "shop",
        "cửa",
        "hàng",
        "elecshop",
        "gb",
        "tb",
    }
    raw = [w for w in t.split() if len(w) > 1 and w not in stop]

    merged: list[str] = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw) and raw[i + 1] in ("gb", "tb"):
            merged.append(raw[i] + raw[i + 1])
            i += 2
            continue
        merged.append(raw[i])
        i += 1
    return merged


def _answer_availability_vi(message: str, products: list[Product]) -> str | None:
    msg = (message or "").strip()
    s = msg.lower()
    # Do not treat generic "phụ kiện ..." as stock lookup — that is accessory advice.
    if any(k in s for k in ["phụ kiện", "phu kien"]):
        return None
    # Do not treat recommendation-style questions as stock lookup.
    if any(k in s for k in ["gợi ý", "tư vấn", "phù hợp", "đáng mua"]):
        return None

    m = re.search(r"\bshop\s+có\s+(.+?)(?:\s+không|\?|$)", s, flags=re.I)
    if not m:
        m = re.search(r"\bcó\s+(.+?)\s+không\b", s, flags=re.I)
    if not m:
        return None

    q = m.group(1).strip()
    # Avoid generic queries like "mẫu nào phù hợp" / "sản phẩm nào" which are not SKU/name checks.
    if any(k in q for k in ["mẫu nào", "san pham nao", "sản phẩm nào", "loại nào", "nào phù hợp", "phù hợp"]):
        return None
    tokens = _tokenize_product_query(q)
    if not tokens:
        return None

    def score(p: Product) -> float:
        text = _name_key(p).replace(" ", "")
        sc = 0.0
        for t in tokens:
            if t in text:
                sc += 2.0
        return sc

    ranked = sorted(products, key=lambda p: score(p), reverse=True)
    best = ranked[0] if ranked else None
    if not best or score(best) < 2:
        return (
            f"Mình không thấy sản phẩm khớp rõ ràng với “{q}” trong catalog hiện tại. "
            "Bạn thử nhắc SKU hoặc product_id, hoặc mô tả ngắn hơn (ví dụ: iPhone 15 Pro Max)."
        )

    # Example: user asks "256GB" but catalog contains "1TB"
    ask_storage = None
    sm = re.search(r"(\d+)\s*(gb|tb)\b", q, flags=re.I)
    if sm:
        ask_storage = (sm.group(1) + sm.group(2)).lower()
    best_key = _name_key(best).replace(" ", "")
    if ask_storage and ask_storage not in best_key:
        return (
            f"Theo catalog hiện tại, shop có sản phẩm gần nhất là **{best.name}** (product_id: {best.id}), "
            f"nhưng **không thấy đúng bản {ask_storage.upper()}** trong tên/mô tả hiện có. "
            "Bạn mở trang chi tiết để xác nhận cấu hình, hoặc chọn phiên bản đang có sẵn."
        )

    return f"Có — trong catalog có **{best.name}** (product_id: {best.id}), giá {best.price} {best.currency or ''}."


def _should_use_heuristic_first(message: str) -> bool:
    """
    When True, answer with catalog heuristics instead of OpenAI so behavior is deterministic
    (compare, stock check, accessories, non-gaming laptop, similar products).
    """

    msg = (message or "").strip()
    s = msg.lower()
    try:
        prods = list_products()
    except Exception:  # noqa: BLE001
        prods = []
    if _answer_compare_vi(msg, prods if prods else None):
        return True
    if prods and _answer_availability_vi(msg, prods):
        return True

    want_cable = any(k in s for k in ["cáp", "cable", "usb-c", "type c", "type-c", "type‑c"])
    want_charger = (
        any(k in s for k in ["sạc", "charger", "fast charger", "33w", "65w", "củ sạc"]) and not want_cable
    )
    want_case = any(k in s for k in ["ốp", "ốp lưng", "case", "bao da", "op lung"])
    want_accessories = any(k in s for k in ["phụ kiện", "accessory", "phu kien"]) or want_charger or want_cable or want_case

    want_laptop = "laptop" in s or "macbook" in s
    want_audio = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone", "chống ồn", "noise cancelling", "anc"])
    want_similar = any(k in s for k in ["tương tự", "similar", "giống"])

    if want_accessories:
        return True
    if want_audio:
        return True
    if want_laptop and _prefer_non_gaming_laptop(s):
        return True
    if want_similar:
        return True
    return False


def _fallback_answer_vi(message: str, history: dict | None = None) -> str:
    msg = (message or "").strip()
    budget_min, budget_max = _parse_budget_vnd(msg)
    products = []
    try:
        products = list_products()
    except Exception:  # noqa: BLE001
        products = []

    cmp = _answer_compare_vi(msg)
    if cmp:
        return cmp

    avail = _answer_availability_vi(msg, products)
    if avail:
        return avail

    # Basic intent heuristics
    s = msg.lower()
    want_phone = any(k in s for k in ["điện thoại", "smartphone", " phone "])  # avoid matching "iphone"
    want_laptop = "laptop" in s or "macbook" in s
    want_earbuds = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone"])
    want_cable = any(k in s for k in ["cáp", "cable", "usb-c", "type c", "type-c", "type‑c"])
    # If message includes "cáp sạc" we should prioritize cable over wall charger.
    want_charger = (any(k in s for k in ["sạc", "charger", "fast charger", "33w", "65w", "củ sạc"]) and not want_cable)
    want_case = any(k in s for k in ["ốp", "case", "bao da"])
    want_accessories = any(k in s for k in ["phụ kiện", "accessory", "phu kien"]) or want_charger or want_cable or want_case

    want_similar = any(k in s for k in ["tương tự", "similar", "giống"]) and history is not None

    # Filter by category name if present
    def cat(p):
        return (p.category_name or "").lower()

    cand = products
    # Similar-products request: use last viewed product to propose same-category items.
    if want_similar:
        viewed_ids = (history or {}).get("recent_viewed_product_ids") or []
        if viewed_ids:
            try:
                last_id = int(viewed_ids[0])
                last = get_product(last_id)
                if last.category_id is not None:
                    cand = [p for p in cand if p.category_id == last.category_id and int(p.id) != last_id]
            except Exception:  # noqa: BLE001
                pass

    # Accessories intent should win even if the message contains "iPhone".
    if want_accessories:
        cand = [p for p in cand if "accessories" in cat(p)]

        iphone15_ctx = "iphone 15" in s or "ip15" in s
        if iphone15_ctx:
            # Don't over-filter: chargers/cables can still be relevant even if not explicitly labeled "iPhone 15".
            cand = [
                p
                for p in cand
                if ("iphone 15" in _name_key(p) or "ip15" in _name_key(p) or _is_cable_product(p) or _is_charger_product(p))
            ]

        # If asking both case + cable, return both categories mixed.
        if want_case and want_cable:
            cases = [p for p in cand if _is_case_product(p)]
            cables = [p for p in cand if _is_cable_product(p)]
            merged: list[Product] = []
            seen: set[int] = set()
            for group in (cases, cables):
                for p in group:
                    if int(p.id) not in seen:
                        seen.add(int(p.id))
                        merged.append(p)
            cand = merged if merged else cand
        elif want_case and not want_cable and not want_charger:
            cand = [p for p in cand if _is_case_product(p)]
        elif want_cable and not want_case and not want_charger:
            cand = [p for p in cand if _is_cable_product(p)]
        elif want_charger and not want_case and not want_cable:
            cand = [p for p in cand if _is_charger_product(p)]

    elif want_phone:
        cand = [p for p in cand if "smartphone" in cat(p)]
    elif want_laptop:
        cand = [p for p in cand if "laptop" in cat(p)]
        if _prefer_non_gaming_laptop(s):
            cand = [p for p in cand if not _is_gaming_laptop_name(p.name)]
    elif want_earbuds:
        cand = [p for p in cand if "audio" in cat(p)]

    # Budget filter
    if budget_min is not None or budget_max is not None:
        def price_vnd(p):
            try:
                return int(float(p.price)) if p.price is not None else None
            except Exception:  # noqa: BLE001
                return None

        cand2 = []
        for p in cand:
            pv = price_vnd(p)
            if pv is None:
                continue
            if budget_min is not None and pv < budget_min:
                continue
            if budget_max is not None and pv > budget_max:
                continue
            if budget_min is None and budget_max is not None and pv > budget_max:
                continue
            if budget_min is not None and budget_max is None and pv < budget_min:
                continue
            # passed range check
            if budget_max is None or pv <= budget_max:
                cand2.append(p)
        cand = cand2

    cand = cand[:5]

    if cand:
        lines = ["Mình gợi ý vài sản phẩm trong shop phù hợp nhu cầu của bạn:"]
        for p in cand:
            lines.append(f"- {p.name} (product_id: {p.id}) — {p.price} {p.currency or ''}".strip())
        lines.append("")
        if want_accessories and not want_phone and not want_laptop:
            lines.append("Bạn muốn ưu tiên độ bền, chiều dài cáp, hay công suất củ sạc (W)?")
        elif want_laptop:
            lines.append("Bạn ưu tiên thêm tiêu chí nào: hãng, RAM/SSD, pin, hay màn hình?")
        else:
            lines.append("Bạn ưu tiên thêm tiêu chí nào: hãng, màn hình, pin, camera, hay chơi game?")
        return "\n".join(lines)

    # If no match, ask clarifying questions
    qs = [
        "Bạn cho mình biết ngân sách khoảng bao nhiêu (VD: dưới 7 triệu / 10–15 triệu)?",
        "Bạn muốn dùng cho nhu cầu chính nào (học tập, chơi game, chụp ảnh, pin trâu)?",
    ]
    return f"Mình chưa tìm được sản phẩm khớp ngay trong dữ liệu shop hiện tại.\n- {qs[0]}\n- {qs[1]}"


def _summarize_history(user_id: str) -> dict:
    events = list_events(user_id, limit=50)
    viewed = [e.product_id for e in events if e.event_type == "view" and e.product_id is not None]
    carted = [e.product_id for e in events if e.event_type == "add_to_cart" and e.product_id is not None]
    searched = [e.query for e in events if e.event_type == "search" and (e.query or "").strip()]
    return {
        "recent_viewed_product_ids": viewed[:10],
        "recent_cart_product_ids": carted[:10],
        "recent_queries": searched[:10],
    }


def answer_chat(user_id: str, message: str) -> ChatResult:
    """
    RAG chat (OpenAI + pgvector) with graceful fallback:
    - Uses behavior context from interaction-service.
    - Retrieves relevant product documents from pgvector.
    - Calls OpenAI for an answer grounded in retrieved context.
    - If OpenAI is not configured, falls back to the earlier heuristic answer.
    """

    msg = (message or "").strip()
    if not msg:
        return ChatResult(answer="Please enter a message.", context={})

    # Best-effort: treat message as a query signal into the graph.
    try:
        upsert_event_to_graph(user_id=user_id, event_type="search", query=msg)
    except Exception:  # noqa: BLE001
        pass

    history = _summarize_history(user_id)
    recs = recommend_products(user_id, limit=5)
    products = hydrate_products(recs)

    def _price_vnd(p: Product) -> int | None:
        try:
            return int(float(p.price)) if p.price is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _cat(p: Product) -> str:
        return (p.category_name or "").lower()

    def _augment_candidates(msg: str, base: list[dict]) -> list[dict]:
        """
        Ensure the context always contains category-relevant candidates when the user asks explicitly
        (e.g., laptop/audio), even if personalized recommenders return unrelated items.
        """

        s = (msg or "").lower()
        want_laptop = "laptop" in s or "macbook" in s
        want_audio = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone", "chống ồn", "noise cancelling", "anc"])

        if not (want_laptop or want_audio):
            return base

        budget_min, budget_max = _parse_budget_vnd(msg)
        try:
            allp = list_products()
        except Exception:  # noqa: BLE001
            allp = []

        cand: list[Product] = allp
        if want_laptop:
            cand = [p for p in cand if "laptop" in _cat(p) or "macbook" in _name_key(p)]
            if _prefer_non_gaming_laptop(s):
                cand = [p for p in cand if not _is_gaming_laptop_name(p.name)]
        elif want_audio:
            cand = [p for p in cand if "audio" in _cat(p)]

        if budget_min is not None or budget_max is not None:
            tmp: list[Product] = []
            for p in cand:
                pv = _price_vnd(p)
                if pv is None:
                    continue
                if budget_min is not None and pv < budget_min:
                    continue
                if budget_max is not None and pv > budget_max:
                    continue
                tmp.append(p)
            cand = tmp

        # Add up to 3 items not already in base.
        have = {int(x.get("id")) for x in base if x.get("id") is not None}
        extra: list[dict] = []
        for p in cand[:6]:
            if int(p.id) in have:
                continue
            extra.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "sku": p.sku,
                    "category": p.category_name,
                    "price": p.price,
                    "currency": p.currency,
                    "description": (p.description or "")[:240],
                }
            )
            have.add(int(p.id))
            if len(extra) >= 3:
                break

        return base + extra

    # Build short textual context using product descriptions
    picked: list[dict] = []
    for p in products[:3]:
        try:
            full = get_product(int(p["id"]))
            picked.append(
                {
                    "id": full.id,
                    "name": full.name,
                    "sku": full.sku,
                    "category": full.category_name,
                    "price": full.price,
                    "currency": full.currency,
                    "description": (full.description or "")[:240],
                }
            )
        except Exception:  # noqa: BLE001
            picked.append(p)
    picked = _augment_candidates(msg, picked)

    retrieved = []
    try:
        chunks = retrieve_similar(query=msg, limit=6)
        for c in chunks:
            retrieved.append(
                {
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                    "title": c.title,
                    "content": c.content[:800],
                    "metadata": c.metadata,
                }
            )
    except Exception:  # noqa: BLE001
        retrieved = []

    graph_ctx_raw: dict = {}
    graph_ctx_display: dict = {"enabled": False}
    try:
        graph_ctx_raw = graph_context_for_rag(user_id, limit=8)
        if graph_ctx_raw.get("enabled"):
            graph_products: list[dict] = []
            _g_ids = graph_ctx_raw.get("cooccurrence_product_ids") or []
            _g_scores = graph_ctx_raw.get("cooccurrence_scores") or []
            for i, pid in enumerate(_g_ids):
                sc = _g_scores[i] if i < len(_g_scores) else None
                try:
                    p = get_product(int(pid))
                    graph_products.append(
                        {
                            "product_id": p.id,
                            "name": p.name,
                            "category": p.category_name,
                            "price": p.price,
                            "graph_score": float(sc) if sc is not None else None,
                        }
                    )
                except Exception:  # noqa: BLE001
                    graph_products.append({"product_id": int(pid), "graph_score": float(sc) if sc is not None else None})
            graph_ctx_display = {
                "enabled": True,
                "searched_queries": graph_ctx_raw.get("searched_queries") or [],
                "cooccurrence_candidates": graph_products,
                "user_category_names": graph_ctx_raw.get("user_category_names") or [],
            }
    except Exception:  # noqa: BLE001
        graph_ctx_display = {"enabled": False}

    ctx = {
        "user_id": user_id,
        "message": msg,
        "history": history,
        "recommended_products": picked,
        "retrieved_chunks": retrieved,
        "graph_context": graph_ctx_display,
    }

    system = (
        "Bạn là trợ lý tư vấn mua sắm của ElecShop (sàn thương mại điện tử). "
        "Luôn trả lời bằng tiếng Việt. "
        "Chỉ sử dụng thông tin trong phần ngữ cảnh được cung cấp (hành vi người dùng, đồ thị gợi ý, các chunks đã truy xuất, danh sách sản phẩm gợi ý). "
        "Nếu ngữ cảnh chưa đủ để trả lời chắc chắn, hãy hỏi 1-2 câu hỏi làm rõ. "
        "Khi nhắc đến một sản phẩm, hãy kèm product_id."
    )
    user = (
        f"User message:\n{msg}\n\n"
        f"User behavior context:\n{history}\n\n"
        f"Graph-aware signals (Neo4j):\n{graph_ctx_display}\n\n"
        f"Retrieved knowledge chunks:\n{retrieved}\n\n"
        f"Candidate recommended products:\n{picked}\n"
    )

    if _should_use_heuristic_first(msg):
        answer = _fallback_answer_vi(msg, history=history)
    else:
        try:
            answer = chat_completion(system=system, user=user)
        except Exception:
            # OpenAI may be unavailable (quota/billing); still provide a useful in-shop answer.
            answer = _fallback_answer_vi(msg, history=history)

    return ChatResult(answer=answer, context=ctx)

