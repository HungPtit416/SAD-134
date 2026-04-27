from __future__ import annotations

import re
from dataclasses import dataclass

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .indexing import retrieve_similar
from .openai_client import chat_completion
from .recommendation import hydrate_products, recommend_products
from .graph_gateway import graph_context_for_rag, upsert_event_to_graph
from .sequence_predictor import predict_next_action
from .graphrag import build_graphrag_context
from ..infrastructure.models import ChatTurn


@dataclass(frozen=True)
class ChatResult:
    answer: str
    context: dict


def _keyword_score(query: str, text: str) -> float:
    q = (query or "").lower()
    t = (text or "").lower()
    if not q or not t:
        return 0.0
    toks = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) >= 2]
    if not toks:
        return 0.0
    hit = 0.0
    for w in toks[:25]:
        if w in t:
            hit += 1.0
    return hit / max(1.0, float(min(25, len(toks))))


def _filter_and_rerank_retrieved(message: str, retrieved: list[dict], limit: int = 4) -> list[dict]:
    """
    Reduce hallucination by:
    - Dropping very-low overlap chunks
    - Keeping only top-N chunks by simple lexical overlap
    """

    scored: list[tuple[float, dict]] = []
    for it in retrieved or []:
        text = f"{it.get('title','')}\n{it.get('content','')}"
        sc = _keyword_score(message, text)
        scored.append((sc, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    kept: list[dict] = []
    for sc, it in scored:
        if len(kept) >= max(1, int(limit)):
            break
        # If all chunks are low, still keep the best 1.
        if kept:
            if sc < 0.12:
                continue
        kept.append(it)
    return kept


def _parse_budget_vnd(text: str) -> tuple[int | None, int | None]:
    """
    Parse simple Vietnamese budget phrases like:
    - "dưới 7 triệu", "tầm 15-25 triệu", "dưới 10tr"
    Returns (min_budget_vnd, max_budget_vnd) if detected.
    """

    s = (text or "").lower()
    s = s.replace(",", ".")
    s = s.replace("–", "-").replace("—", "-")

    # dưới X triệu / dưới Xtr (support both dấu & không dấu)
    m = re.search(r"(dưới|duoi|<=)\s*(\d+(?:\.\d+)?)\s*(triệu|trieu|tr)\b", s)
    if m:
        return None, int(float(m.group(2)) * 1_000_000)

    # tầm/min-max triệu (support both dấu & không dấu)
    m = re.search(r"(tầm|khoảng|tam|khoang)?\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(triệu|trieu|tr)\b", s)
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


def _wants_gaming_laptop(s: str) -> bool:
    s = (s or "").lower()
    return ("gaming" in s) or bool(re.search(r"\bchơi game\b", s)) or ("game nặng" in s)


def _is_affirmative_short_reply(s: str) -> bool:
    t = (s or "").strip().lower()
    return t in {"có", "co", "ok", "oke", "yes", "y", "đúng", "dung", "ừ", "u", "uk", "được", "duoc"}


def _is_negative_short_reply(s: str) -> bool:
    t = (s or "").strip().lower()
    return t in {"không", "khong", "no", "n", "thôi", "thoi", "ko"}


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


def _infer_domain(convo_text: str) -> str | None:
    """
    Infer the user's current product domain.
    Returns one of: laptop | audio | smartphone | tablet | smartwatch | accessories | None
    """

    s = (convo_text or "").lower()
    if any(k in s for k in ["laptop", "macbook", "notebook"]):
        return "laptop"
    if any(k in s for k in ["tai nghe", "earbud", "earbuds", "airpods", "headphone", "headphones", "loa", "speaker", "anc"]):
        return "audio"
    if any(k in s for k in ["tablet", "ipad", "máy tính bảng", "may tinh bang"]):
        return "tablet"
    if any(k in s for k in ["smartwatch", "đồng hồ", "dong ho", "watch", "garmin"]):
        return "smartwatch"
    if any(
        k in s
        for k in [
            "điện thoại",
            "dien thoai",
            "smartphone",
            "phone",
            "iphone",
            "samsung",
            "galaxy",
            "xiaomi",
            "oppo",
            "realme",
            "oneplus",
            "pixel",
        ]
    ):
        return "smartphone"
    if any(k in s for k in ["phụ kiện", "phu kien", "accessories", "cáp", "cap", "cable", "sạc", "sac", "charger", "ốp", "op", "case"]):
        return "accessories"
    return None


def _product_matches_domain(p: Product, domain: str | None) -> bool:
    if not domain:
        return True
    cat = (p.category_name or "").lower()
    name = (p.name or "").lower()
    if domain == "laptop":
        return "laptop" in cat or "macbook" in name
    if domain == "audio":
        return "audio" in cat or any(k in name for k in ["airpods", "headphone", "earbud", "speaker", "loa"])
    if domain == "smartphone":
        return "smartphone" in cat or "phone" in cat
    if domain == "tablet":
        return "tablet" in cat or "ipad" in name
    if domain == "smartwatch":
        return "smartwatch" in cat or "watch" in name or "garmin" in name
    if domain == "accessories":
        return "accessories" in cat or "phụ kiện" in cat
    return True


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

    want_similar = any(k in s for k in ["tương tự", "similar", "giống"])

    if want_accessories:
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
    # Treat brand-only messages (e.g. "hãng samsung") as phone intent too.
    want_phone = any(k in s for k in ["điện thoại", "dien thoai", "smartphone", " phone "])  # avoid matching "iphone"
    if not want_phone and any(k in s for k in ["samsung", "galaxy", "iphone", "xiaomi", "redmi", "oppo", "realme", "oneplus", "pixel"]):
        want_phone = True
    want_laptop = "laptop" in s or "macbook" in s
    want_gaming_laptop = want_laptop and _wants_gaming_laptop(s)
    want_big_ram = any(k in s for k in ["ram to", "ram lớn", "ram lon", "ram cao", "nhiều ram", "nhieu ram"])
    want_big_ssd = any(k in s for k in ["ssd", "ổ cứng", "o cung", "dung lượng", "dung luong"])
    want_battery = any(k in s for k in ["pin trâu", "pin trau", "pin tốt", "pin tot", "pin lâu", "pin lau", "battery"])
    want_earbuds = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone"])
    want_tablet = any(k in s for k in ["tablet", "ipad", "máy tính bảng", "may tinh bang"])
    want_watch = any(k in s for k in ["smartwatch", "đồng hồ", "dong ho", "watch", "garmin"])
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
        # Brand hint for phones
        if "samsung" in s or "galaxy" in s:
            cand = [p for p in cand if ("samsung" in _name_key(p) or "galaxy" in _name_key(p))]
        elif "iphone" in s:
            cand = [p for p in cand if "iphone" in _name_key(p)]
        elif "xiaomi" in s or "redmi" in s:
            cand = [p for p in cand if ("xiaomi" in _name_key(p) or "redmi" in _name_key(p))]
        elif "oppo" in s:
            cand = [p for p in cand if "oppo" in _name_key(p)]
        elif "realme" in s:
            cand = [p for p in cand if "realme" in _name_key(p)]
        elif "oneplus" in s or "one plus" in s:
            cand = [p for p in cand if "oneplus" in _name_key(p)]
        elif "pixel" in s or "google" in s:
            cand = [p for p in cand if ("pixel" in _name_key(p) or "google" in _name_key(p))]
    elif want_tablet:
        cand = [p for p in cand if "tablet" in cat(p) or "ipad" in _name_key(p)]
    elif want_watch:
        cand = [p for p in cand if "smartwatch" in cat(p) or "watch" in _name_key(p) or "garmin" in _name_key(p)]
    elif want_laptop:
        cand = [p for p in cand if "laptop" in cat(p)]
        if want_gaming_laptop:
            cand = [p for p in cand if _is_gaming_laptop_name(p.name)]
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
        # Ask a single next question without repeating the generic menu.
        # Note: catalog does not store detailed specs (RAM/SSD/battery hours), so we ask clarifying questions.
        if want_laptop:
            if want_big_ram:
                lines.append("Bạn cần RAM khoảng bao nhiêu GB (ví dụ 16GB / 32GB)? Mình sẽ gợi ý theo tầm giá + dòng máy phù hợp.")
            elif want_battery:
                if want_gaming_laptop:
                    lines.append(
                        "Laptop gaming thường pin không bằng ultrabook. Bạn muốn ưu tiên pin ở mức nào "
                        "(ví dụ dùng 4–6h hay 7–10h) và ngân sách khoảng bao nhiêu?"
                    )
                else:
                    lines.append("Bạn muốn máy nhẹ (di chuyển nhiều) hay ưu tiên màn hình lớn? Và ngân sách khoảng bao nhiêu?")
            elif want_big_ssd:
                lines.append("Bạn cần SSD khoảng bao nhiêu (512GB / 1TB)? Và có cần máy nhẹ hay ưu tiên hiệu năng?")
            else:
                lines.append("Bạn ưu tiên thêm tiêu chí nào (ngân sách, hãng, màn hình, pin, hay hiệu năng)?")
        elif want_accessories and not want_phone and not want_laptop:
            lines.append("Bạn muốn ưu tiên độ bền, chiều dài cáp, hay công suất củ sạc (W)?")
        else:
            lines.append("Bạn ưu tiên thêm tiêu chí nào (ngân sách, hãng, màn hình, pin, hay hiệu năng)?")
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


def _load_recent_chat_turns(*, user_id: str, session_id: str, limit: int = 8) -> list[dict]:
    turns = (
        ChatTurn.objects.filter(user_id=str(user_id), session_id=str(session_id))
        .order_by("-created_at")[: max(0, int(limit))]
    )
    out: list[dict] = []
    for t in reversed(list(turns)):
        out.append({"message": t.message, "answer": t.answer})
    return out


def answer_chat(user_id: str, message: str, *, session_id: str = "default") -> ChatResult:
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
    recent_turns = _load_recent_chat_turns(user_id=user_id, session_id=session_id, limit=8)
    convo_text = "\n".join([msg] + [t.get("message", "") for t in recent_turns[-4:]])
    domain = _infer_domain(convo_text)
    domain_msg = _infer_domain(msg)

    # If the user clearly switches product domain in the current message, avoid carrying over
    # old-domain constraints/questions from previous turns (common cause of "laptop pin" question
    # being appended after switching to "điện thoại").
    if domain_msg and domain and domain_msg != domain:
        convo_text = msg
        domain = domain_msg

    # Keep domain stable for short constraint-only follow-ups like:
    # - "ngân sách dưới 20 triệu", "pin trâu", "ram to"
    # If the current message doesn't mention a domain but prior turns established one,
    # inject a lightweight domain keyword so heuristics don't fall back to "cheap accessories".
    logic_text = convo_text
    force_heuristic = False
    if (not domain_msg) and domain:
        s0 = (msg or "").lower()
        is_constraint = any(
            k in s0
            for k in [
                "ngân sách",
                "ngan sach",
                "hãng",
                "hang",
                "brand",
                "dưới",
                "duoi",
                "triệu",
                "trieu",
                "pin",
                "battery",
                "ram",
                "ssd",
                "ổ cứng",
                "o cung",
                "dung lượng",
                "dung luong",
                "camera",
                "chụp",
                "chup",
            ]
        )
        if is_constraint:
            dom_kw = {
                "laptop": "laptop",
                "audio": "tai nghe",
                "smartphone": "dien thoai",
                "tablet": "tablet",
                "smartwatch": "dong ho",
                "accessories": "phu kien",
            }.get(domain, "")
            if dom_kw:
                # Ensure domain keyword is present even if convo_text got trimmed by UI/session logic.
                extra = ""
                # Preserve high-signal constraints from earlier turns (e.g., gaming laptop).
                if domain == "laptop" and _wants_gaming_laptop(convo_text):
                    extra = " gaming"
                if domain == "smartphone":
                    if "samsung" in convo_text.lower() or "galaxy" in convo_text.lower():
                        extra = " samsung"
                    elif "iphone" in convo_text.lower():
                        extra = " iphone"
                logic_text = f"{dom_kw}{extra}\n{msg}"
                # Constraint-only follow-ups are better handled deterministically to avoid LLM drifting to cheap accessories.
                force_heuristic = True

    # If user replies "có/ok/yes" after the assistant asked a yes/no follow-up,
    # avoid looping and provide the next set of suggestions.
    try:
        last_answer = (recent_turns[-1].get("answer") if recent_turns else "") or ""
        la = last_answer.lower()
        if ("bạn có muốn" in la) and ("tìm thêm" in la):
            if _is_negative_short_reply(msg):
                msg = "không cần gợi ý thêm, hỏi tiêu chí khác"
            elif _is_affirmative_short_reply(msg):
                # Carry forward topic with domain keyword to prevent drifting.
                dom_kw = {
                    "laptop": "laptop",
                    "audio": "tai nghe",
                    "smartphone": "dien thoai",
                    "tablet": "tablet",
                    "smartwatch": "dong ho",
                    "accessories": "phu kien",
                }.get(domain or "", "")
                # Add “more suggestions” hint; keep any constraints from recent convo (e.g. gaming/pin).
                msg = f"goi y them {dom_kw} phu hop"
            convo_text = "\n".join([msg] + [t.get("message", "") for t in recent_turns[-4:]])
            domain = _infer_domain(convo_text)
            logic_text = convo_text
    except Exception:  # noqa: BLE001
        pass
    recs = recommend_products(user_id, limit=5)
    products = hydrate_products(recs)
    next_action = predict_next_action(user_id, seq_len=6)

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
        (e.g., laptop/audio/phone/accessories), even if personalized recommenders return unrelated items.
        """

        s = (msg or "").lower()
        want_laptop = "laptop" in s or "macbook" in s
        want_audio = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone", "chống ồn", "noise cancelling", "anc"])
        want_phone = any(
            k in s
            for k in [
                "điện thoại",
                "dien thoai",
                "smartphone",
                "phone",
                "samsung",
                "galaxy",
                "iphone",
            ]
        )
        want_accessories = any(
            k in s
            for k in [
                "phụ kiện",
                "phu kien",
                "accessories",
                "cáp",
                "cap",
                "cable",
                "usb-c",
                "type-c",
                "type c",
                "sạc",
                "sac",
                "charger",
                "củ sạc",
                "ốp",
                "op",
                "ốp lưng",
                "case",
                "bao da",
            ]
        )

        if not (want_laptop or want_audio or want_phone or want_accessories):
            return base

        budget_min, budget_max = _parse_budget_vnd(msg)
        try:
            allp = list_products()
        except Exception:  # noqa: BLE001
            allp = []

        cand: list[Product] = allp
        if want_laptop:
            cand = [p for p in cand if "laptop" in _cat(p) or "macbook" in _name_key(p)]
            if _wants_gaming_laptop(s):
                cand = [p for p in cand if _is_gaming_laptop_name(p.name)]
            if _prefer_non_gaming_laptop(s):
                cand = [p for p in cand if not _is_gaming_laptop_name(p.name)]
        elif want_audio:
            cand = [p for p in cand if "audio" in _cat(p)]
        elif want_phone:
            cand = [p for p in cand if ("smartphone" in _cat(p) or "smartphones" in _cat(p) or "phone" in _cat(p))]
            # Brand hint
            if "samsung" in s or "galaxy" in s:
                cand = [p for p in cand if ("samsung" in _name_key(p) or "galaxy" in _name_key(p))]
            elif "iphone" in s:
                cand = [p for p in cand if "iphone" in _name_key(p)]
        elif want_accessories:
            cand = [p for p in cand if "accessories" in _cat(p)]
            # If user is specific, filter within accessories.
            want_cable = any(k in s for k in ["cáp", "cap", "cable", "usb-c", "type-c", "type c"])
            want_charger = any(k in s for k in ["sạc", "sac", "charger", "củ sạc"])
            want_case = any(k in s for k in ["ốp", "op", "ốp lưng", "case", "bao da"])
            if want_case and not want_cable and not want_charger:
                cand = [p for p in cand if _is_case_product(p)]
            elif want_cable and not want_case and not want_charger:
                cand = [p for p in cand if _is_cable_product(p)]
            elif want_charger and not want_case and not want_cable:
                cand = [p for p in cand if _is_charger_product(p)]

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
        for p in cand[:10]:
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

        if not extra:
            return base

        def _base_cat_text(it: dict) -> str:
            c = it.get("category")
            if isinstance(c, dict):
                return str(c.get("name") or "").lower()
            return str(c or "").lower()

        # If user explicitly asks a category, put those candidates first to avoid
        # the recommender's default (often accessories) dominating the prompt.
        if want_phone:
            base2 = [it for it in base if ("smartphone" in _base_cat_text(it) or "phone" in _base_cat_text(it))]
            return extra + base2
        if want_laptop:
            base2 = [it for it in base if ("laptop" in _base_cat_text(it) or "macbook" in str(it.get("name") or "").lower())]
            return extra + base2
        if want_audio:
            base2 = [it for it in base if ("audio" in _base_cat_text(it) or "airpods" in str(it.get("name") or "").lower())]
            return extra + base2
        if want_accessories:
            base2 = [it for it in base if ("accessories" in _base_cat_text(it) or "phụ kiện" in _base_cat_text(it))]
            return extra + base2

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
    # Use recent conversation to keep topic continuity (e.g., user says "Samsung" then later only "dưới 30 triệu").
    picked = _augment_candidates(convo_text, picked)

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
    retrieved = _filter_and_rerank_retrieved(msg, retrieved, limit=4)

    graph_ctx_raw: dict = {}
    graph_ctx_display: dict = {"enabled": False}
    try:
        # Phase 4: GraphRAG pipeline (seed -> traverse -> rerank -> evidence).
        gr = build_graphrag_context(user_id=user_id, message=msg, evidence_limit=20)
        if gr.enabled:
            graph_ctx_display = {
                "enabled": True,
                "seed": gr.seed,
                "stats": gr.stats,
                "evidence": [
                    {
                        "type": e.type,
                        "score": float(e.score),
                        "product_id": e.product_id,
                        "path": e.path,
                        "details": e.details,
                    }
                    for e in gr.evidence
                ],
            }
        else:
            # Backward-compatible fallback context (Phase 3)
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
                        graph_products.append(
                            {"product_id": int(pid), "graph_score": float(sc) if sc is not None else None}
                        )
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
        "session_id": session_id,
        "message": msg,
        "recent_turns": recent_turns,
        "history": history,
        "predicted_next_action": {
            "enabled": next_action.enabled,
            "action": next_action.action,
            "confidence": next_action.confidence,
            "top_probs": next_action.probs,
            "note": next_action.note,
        },
        "recommended_products": picked,
        "retrieved_chunks": retrieved,
        "graph_context": graph_ctx_display,
    }

    system = (
        "Bạn là trợ lý tư vấn mua sắm của ElecShop (sàn thương mại điện tử). "
        "Luôn trả lời bằng tiếng Việt. "
        "Chỉ sử dụng thông tin trong phần ngữ cảnh được cung cấp (hành vi người dùng, đồ thị gợi ý, các chunks đã truy xuất, danh sách sản phẩm gợi ý). "
        "Tuyệt đối không bịa thông tin (giá, cấu hình, tồn kho) nếu không thấy trong ngữ cảnh. "
        "Nếu ngữ cảnh chưa đủ để trả lời chắc chắn, hãy hỏi 1-2 câu hỏi làm rõ. "
        "Tránh lặp lại cùng một câu hỏi nhiều lần; nếu người dùng trả lời 'có/ok/yes' sau khi bạn hỏi có muốn xem thêm gợi ý, hãy đưa thêm gợi ý ngay. "
        "Khi đề xuất sản phẩm, hãy đưa 2-3 lựa chọn phù hợp nhất và kèm product_id."
    )
    # Keep prompt compact to reduce off-topic answers.
    user = (
        f"Recent conversation (most recent last):\n{recent_turns}\n\n"
        f"User message:\n{msg}\n\n"
        f"User behavior:\n{history}\n\n"
        f"Graph evidence:\n{graph_ctx_display}\n\n"
        f"Retrieved chunks:\n{retrieved}\n\n"
        f"Candidate products (use these first):\n{picked[:5]}\n"
    )

    if force_heuristic or _should_use_heuristic_first(logic_text):
        answer = _fallback_answer_vi(logic_text, history=history)
    else:
        try:
            answer = chat_completion(system=system, user=user)
        except Exception:
            # OpenAI may be unavailable (quota/billing); still provide a useful in-shop answer.
            answer = _fallback_answer_vi(logic_text, history=history)

    # Guardrail: if the assistant suggests product_ids from the wrong domain, fall back to deterministic in-shop suggestions.
    try:
        ids = _extract_product_ids(answer)
        if ids and domain:
            wrong = 0
            for pid in ids[:5]:
                try:
                    p = get_product(int(pid))
                except Exception:  # noqa: BLE001
                    continue
                if not _product_matches_domain(p, domain):
                    wrong += 1
            if wrong:
                answer = _fallback_answer_vi(convo_text, history=history)
    except Exception:  # noqa: BLE001
        pass

    # Persist the chat turn (best-effort; should not break the chat response).
    try:
        ChatTurn.objects.create(user_id=str(user_id), session_id=str(session_id), message=msg, answer=answer, context=ctx)
    except Exception:  # noqa: BLE001
        pass

    return ChatResult(answer=answer, context=ctx)

