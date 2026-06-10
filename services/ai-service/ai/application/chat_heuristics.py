"""
Heuristic helpers for ElecShop chat.

The chat pipeline is hybrid: rules here narrow candidates, validate domains, and answer a few
deterministic intents; the Gemini client still generates natural-language replies from the
context bundle (RAG chunks + candidate products). Heuristics are not a replacement for the LLM;
they reduce hallucination and keep catalog constraints consistent.
"""

from __future__ import annotations

import re

from .interaction_gateway import list_events
from .product_gateway import Product, get_product, list_products
from .rating_utils import (
    format_rating_line,
    product_rating_count,
    product_rating_value,
    query_mentions_rating,
    query_wants_high_rating,
    query_wants_low_rating,
    rating_quality_score,
)
from ..infrastructure.models import ChatTurn

# Shared across chat augment + fallback + deterministic "list entire category" answers.
_CATALOG_LIST_ALL_KEYWORDS: tuple[str, ...] = (
    "tất cả",
    "tat ca",
    "liệt kê",
    "liet ke",
    "đầy đủ",
    "day du",
    "toàn bộ",
    "toan bo",
    "những mẫu",
    "nhung mau",
    "các mẫu",
    "cac mau",
    "mẫu nào",
    "mau nao",
    "mấy loại",
    "may loai",
    "bao nhiêu mẫu",
    "bao nhieu mau",
    "full list",
)


def _normalize_user_text_for_match(text: str) -> str:
    t = (text or "").lower().replace("\u00a0", " ").replace("\u2009", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _message_mentions_explicit_accessory_goods(s: str) -> bool:
    """
    True when the user clearly asks about accessories (cable, charger, case, hub, etc.).
    Used to suppress false accessory intent from weak substring matches (e.g. "op" inside "laptop").
    """

    t = _normalize_user_text_for_match(s)
    if not t:
        return False
    return bool(
        re.search(
            r"phụ\s*kiện|phu\s*kien|accessories|\bcáp\b|\bcap\b|\bcable\b|usb-?c|type-?c|"
            r"\bsạc\b|\bsac\b|charger|củ\s*sạc|ốp|ốp\s+lưng|op\s+lung|bao\s+da|\bhub\b|"
            r"chuột|chuot|ban\s+phim|bàn\s+phím|keyboard|mouse|\bcase\b",
            t,
            flags=re.I,
        )
    )


def _finalize_want_accessories(
    s: str,
    *,
    want_laptop: bool,
    want_phone: bool,
    want_tablet: bool,
    want_watch: bool,
    want_accessories: bool,
) -> bool:
    """
    If the user is clearly asking about a device category, ignore accessory intent unless the
    first line (current turn when convo is newest-first) mentions an actual accessory product.
    Prevents: (1) "op" inside "laptop"; (2) older turns about accessories hijacking a laptop query.
    """

    if not want_accessories:
        return False
    if want_laptop or want_phone or want_tablet or want_watch:
        raw_head = ((s or "").splitlines() or [""])[0]
        head = _normalize_user_text_for_match(raw_head)
        return _message_mentions_explicit_accessory_goods(head)
    return True


def _wants_catalog_list_all_intent(text: str) -> bool:
    """True when the user is asking for a full in-category catalog listing (not just 2–4 picks)."""

    t = _normalize_user_text_for_match(text)
    if not t:
        return False
    if any(k in t for k in _CATALOG_LIST_ALL_KEYWORDS):
        return True
    # Typo / spacing tolerant: "tat ca", "tất  cả"
    if re.search(r"t[aạ]t\s*c[aả]", t):
        return True
    # Common Vietnamese phrasing without the exact phrase "tất cả"
    if re.search(r"những\s+.+?\s+nào\s+trong\s+cửa\s+hàng", t):
        return True
    if re.search(r"có\s+những\s+.+?\s+nào", t):
        return True
    return False


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


def _catalog_blob(p: Product) -> str:
    """Lowercased category + name + SKU + subtype attrs for robust keyword checks."""

    base = f"{p.main_category or ''} {p.category_name or ''} {p.name or ''} {p.sku or ''}"
    if p.extra_blob:
        return f"{base} {p.extra_blob}".lower()
    return base.lower()


def _infer_domain(convo_text: str) -> str | None:
    """
    Infer the user's current product domain.
    Returns one of: book | fashion | laptop | audio | smartphone | tablet | smartwatch | accessories | None
    """

    s = (convo_text or "").lower()
    if any(
        k in s
        for k in [
            "sách",
            "sach",
            "book",
            "novel",
            "truyện",
            "truyen",
            "tác giả",
            "tac gia",
            "author",
            "isbn",
            "publisher",
            "harry potter",
            "sapiens",
            "atomic habits",
            "đắc nhân tâm",
            "dac nhan tam",
            "tiểu thuyết",
            "tieu thuyet",
            "văn học",
            "van hoc",
            "thiếu nhi",
            "thieu nhi",
            "isbn",
            "nxb",
            "nhà xuất bản",
            "nha xuat ban",
        ]
    ):
        return "book"
    if any(
        k in s
        for k in [
            "thời trang",
            "thoi trang",
            "fashion",
            "quần áo",
            "quan ao",
            "giày",
            "giay",
            "sneaker",
            "váy",
            "vay",
            "dress",
            "jeans",
            "túi xách",
            "tui xach",
            "tote bag",
            "tote",
            "áo thun",
            "ao thun",
            "uniqlo",
            "zara",
            "nike",
            "levi",
            "coach",
            "clarks",
            "size m",
            "size l",
            "cỡ ",
            "co ",
        ]
    ):
        return "fashion"
    if any(k in s for k in ["laptop", "macbook", "notebook"]):
        return "laptop"
    if any(
        k in s
        for k in [
            "tai nghe",
            "earbud",
            "earbuds",
            "airpods",
            "headphone",
            "headphones",
            "loa",
            "loa bluetooth",
            "speaker",
            "anc",
            "jbl",
            "sony wh",
            "bose",
            "sennheiser",
        ]
    ):
        return "audio"
    if any(
        k in s
        for k in [
            "tablet",
            "ipad",
            "máy tính bảng",
            "may tinh bang",
            "galaxy tab",
            "xiaomi pad",
            "may bang",
        ]
    ):
        return "tablet"
    if any(
        k in s
        for k in [
            "smartwatch",
            "đồng hồ thông minh",
            "dong ho thong minh",
            "apple watch",
            "galaxy watch",
            "garmin",
            "forerunner",
            "fitbit",
        ]
    ) or (("đồng hồ" in s or "dong ho" in s) and " tab " not in s and "tablet" not in s):
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
            "redmi",
            "oppo",
            "realme",
            "oneplus",
            "pixel",
        ]
    ):
        return "smartphone"
    if any(
        k in s
        for k in [
            "phụ kiện",
            "phu kien",
            "accessories",
            "cáp",
            "cap",
            "cable",
            "sạc",
            "sac",
            "charger",
            "ốp",
            "op lung",
            "hub",
            "bàn phím",
            "ban phim",
            "chuột",
            "chuot",
            "mouse",
            "keyboard",
        ]
    ) or bool(re.search(r"\bcase\b", s)):
        return "accessories"
    return None


def _product_matches_domain(p: Product, domain: str | None) -> bool:
    if not domain:
        return True
    main = (p.main_category or "").upper()
    cat = (p.category_name or "").lower()
    blob = _catalog_blob(p)
    if domain == "book":
        if main == "BOOK":
            return True
        return any(k in blob for k in ("book", "sách", "sach", "author", "publisher", "fiction", "novel"))
    if domain == "fashion":
        if main == "FASHION":
            return True
        return any(
            k in blob
            for k in (
                "fashion",
                "clothing",
                "shoes",
                "dress",
                "jeans",
                "sneaker",
                "tote",
                "uniqlo",
                "zara",
                "nike",
                "levi",
                "coach",
            )
        )
    if domain == "laptop":
        return "laptop" in cat or "macbook" in blob
    if domain == "audio":
        if "audio" in cat:
            return True
        return any(
            k in blob
            for k in (
                "airpods",
                "headphone",
                "headphones",
                "earbud",
                "earbuds",
                "speaker",
                "soundlink",
                "jbl",
                "sony wh",
                "bose",
                "sennheiser",
                "momentum",
                "loa",
                "flip",
            )
        )
    if domain == "smartphone":
        if "tablet" in cat or "laptop" in cat or "watch" in cat or "smartwatch" in cat:
            return False
        if "smartphone" in cat or "phones" in cat:
            return True
        if "phone" in cat and "headphone" not in cat and "earphone" not in cat:
            return True
        return any(
            k in blob
            for k in (
                "iphone",
                "pixel ",
                "galaxy a",
                "galaxy s",
                "galaxy z",
                "xiaomi",
                "redmi",
                "oppo ",
                "realme",
                "oneplus",
            )
        )
    if domain == "tablet":
        if "tablet" in cat:
            return True
        return any(k in blob for k in ("ipad", "galaxy tab", "xiaomi pad"))
    if domain == "smartwatch":
        if "smartwatch" in cat:
            return True
        return any(
            k in blob
            for k in (
                "apple watch",
                "galaxy watch",
                "garmin",
                "forerunner",
                "watch se",
                "watch ultra",
                "fitbit",
            )
        )
    if domain == "accessories":
        if "accessories" in cat or "accessory" in cat or "phụ kiện" in cat:
            return True
        return any(
            k in blob
            for k in (
                "cable",
                "charger",
                " hub",
                "case",
                "keyboard",
                "mouse",
                "power bank",
                "powercore",
                "ốp",
                "adapter",
            )
        )
    return True


def _book_blob(p: Product) -> str:
    b = p.book
    if not b:
        return _catalog_blob(p)
    return f"{_catalog_blob(p)} {b.author or ''} {b.publisher or ''} {b.language or ''} {b.isbn or ''}".lower()


def _fashion_blob(p: Product) -> str:
    f = p.fashion
    if not f:
        return _catalog_blob(p)
    return f"{_catalog_blob(p)} {f.brand or ''} {f.size or ''} {f.color or ''} {f.gender or ''}".lower()


def _format_catalog_line(p: Product, dom: str | None = None) -> str:
    line = f"**{p.name}** (product_id: {p.id}) — {p.price} {p.currency or 'VND'}"
    dom_key = (dom or p.main_category or "").lower()
    if dom_key == "book" and p.book:
        bits: list[str] = []
        if p.book.author:
            bits.append(f"tác giả {p.book.author}")
        if p.book.language:
            bits.append(p.book.language)
        if p.category_name:
            bits.append(p.category_name)
        if bits:
            line += f" ({'; '.join(bits)})"
    elif dom_key == "fashion" and p.fashion:
        bits = []
        if p.fashion.brand:
            bits.append(p.fashion.brand)
        if p.fashion.size:
            bits.append(f"size {p.fashion.size}")
        if p.fashion.gender:
            bits.append(p.fashion.gender)
        if bits:
            line += f" ({'; '.join(bits)})"
    elif p.electronics and p.electronics.brand:
        line += f" (hãng {p.electronics.brand})"
    return line.strip()


def _filter_books_by_query(products: list[Product], s: str, *, focus: str | None = None) -> list[Product]:
    s0 = _normalize_user_text_for_match(focus or s)
    cand = [p for p in products if _product_matches_domain(p, "book")]

    def bcat(p: Product) -> str:
        return (p.category_name or "").lower()

    if any(k in s0 for k in ["phi hư cấu", "phi hu cau", "non-fiction", "non fiction", "kỹ năng", "ky nang", "lịch sử", "lich su", "sapiens"]):
        narrowed = [p for p in cand if "non-fiction" in bcat(p) or "non fiction" in bcat(p)]
        cand = narrowed if narrowed else cand
    elif any(k in s0 for k in ["thiếu nhi", "thieu nhi", "children", "trẻ em", "tre em"]):
        narrowed = [p for p in cand if "children" in bcat(p)]
        cand = narrowed if narrowed else cand
    elif any(k in s0 for k in ["tiểu thuyết", "tieu thuyet", "fiction", "truyện", "truyen", "novel", "dune"]):
        narrowed = [p for p in cand if bcat(p) == "fiction" or bcat(p).endswith(" fiction")]
        cand = narrowed if narrowed else cand

    author_rules: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
        (("harry potter", "rowling"), ("harry", "rowling")),
        (("herbert", "dune"), ("herbert", "dune")),
        (("orwell", "1984"), ("orwell", "1984")),
        (("harari", "sapiens"), ("harari", "sapiens")),
        (("james clear", "atomic"), ("clear", "atomic")),
        (("dale carnegie", "đắc nhân", "dac nhan"), ("carnegie", "dac nhan", "đắc nhân")),
    ]
    for triggers, keys in author_rules:
        if any(t in s0 for t in triggers):
            tmp = [p for p in cand if any(k in _book_blob(p) for k in keys)]
            if tmp:
                cand = tmp
                break

    if any(k in s0 for k in ["tiếng việt", "tieng viet", "vietnamese", "bản tiếng việt"]):
        tmp = [p for p in cand if p.book and "viet" in (p.book.language or "").lower()]
        cand = tmp if tmp else cand
    elif any(k in s0 for k in ["tiếng anh", "tieng anh", "english"]):
        tmp = [p for p in cand if p.book and "english" in (p.book.language or "").lower()]
        cand = tmp if tmp else cand

    return cand


def _filter_fashion_by_query(products: list[Product], s: str, *, focus: str | None = None) -> list[Product]:
    s0 = _normalize_user_text_for_match(focus or s)
    cand = [p for p in products if _product_matches_domain(p, "fashion")]

    def fcat(p: Product) -> str:
        return (p.category_name or "").lower()

    if any(k in s0 for k in ["giày", "giay", "sneaker", "sneakers", "loafer", "dép", "dep", "shoes"]):
        narrowed = [p for p in cand if "shoe" in fcat(p) or any(k in _fashion_blob(p) for k in ("sneaker", "loafer", "shoe"))]
        cand = narrowed if narrowed else cand
    elif any(k in s0 for k in ["váy", "vay", "dress", "áo", "ao", "quần", "quan", "jeans", "t-shirt", "tee", "clothing"]):
        narrowed = [p for p in cand if "clothing" in fcat(p) or any(k in _fashion_blob(p) for k in ("dress", "jeans", "t-shirt", "shirt"))]
        cand = narrowed if narrowed else cand
    elif any(k in s0 for k in ["túi", "tui", "bag", "tote"]):
        narrowed = [p for p in cand if "bag" in fcat(p) or "tote" in _fashion_blob(p)]
        cand = narrowed if narrowed else cand

    for brand in ("nike", "uniqlo", "zara", "levi", "coach", "clarks"):
        if brand in s0:
            tmp = [p for p in cand if brand in _fashion_blob(p)]
            cand = tmp if tmp else cand
            break

    if any(k in s0 for k in ["nam", "men", "đàn ông", "dan ong"]):
        tmp = [p for p in cand if p.fashion and (p.fashion.gender or "").lower() in ("men", "man", "male", "nam")]
        cand = tmp if tmp else cand
    elif any(k in s0 for k in ["nữ", "nu", "women", "woman", "phụ nữ", "phu nu"]):
        tmp = [p for p in cand if p.fashion and (p.fashion.gender or "").lower() in ("women", "woman", "female", "nữ", "nu")]
        cand = tmp if tmp else cand

    sm = re.search(r"(?:size|cỡ|co)\s*([mslx]|\d{2})", s0, flags=re.I)
    if sm:
        sz = sm.group(1).upper()
        tmp = [p for p in cand if p.fashion and sz in (p.fashion.size or "").upper()]
        cand = tmp if tmp else cand

    return cand


def _wants_book_intent(s: str) -> bool:
    return _infer_domain(s) == "book"


def _wants_fashion_intent(s: str) -> bool:
    return _infer_domain(s) == "fashion"


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


def _is_gaming_laptop_name(name: str, sku: str | None = None, description: str | None = None) -> bool:
    """
    Detect gaming SKUs from name, SKU, and description (catalog often says "gaming" only in description).
    """

    n = f"{name or ''} {sku or ''} {(description or '')}".lower()
    if any(
        x in n
        for x in (
            "gaming",
            "tuf",
            "strix",
            "rog",
            "zephyrus",
            "flow",
            "scar",
            "legion",
            "loq",
            "rtx",
            "gtx",
            "predator",
            "nitro",
            "alienware",
            "omen",
            "victus",
            "crosshair",
            "pulse",
            "katana",
            "stealth",
            "vector",
            "gf63",
            "gf65",
            "gf75",
            "ideapad gaming",
        )
    ):
        return True
    # Dell G15 / MSI GF65 style model codes in name or SKU
    if re.search(r"\bg\d{2}\b", n):
        return True
    return False


def _is_gaming_laptop_product(p: Product) -> bool:
    return _is_gaming_laptop_name(p.name, p.sku, p.description)


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


def _infer_domain_for_catalog_list_query(text: str) -> str | None:
    """
    Infer domain for "list entire catalog" answers. Prefer the first non-empty line (current user
    message is prepended first in chat_answer) so a long history mentioning laptop does not make
    `_infer_domain` latch to laptop when the user is clearly asking about smartphones now.
    """

    s = (text or "").strip()
    if not s:
        return None
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    for ln in lines[:3]:
        d = _infer_domain(ln)
        if d:
            return d
    return _infer_domain(s)


def _maybe_answer_catalog_list_all_vi(text: str, *, focus_message: str | None = None) -> str | None:
    """
    When the user asks to list every item in a category (e.g. all smartphones), return a complete
    catalog-backed answer so the LLM cannot compress the list to a few picks.
    """

    raw = (text or "").strip()
    s = _normalize_user_text_for_match(raw)
    if not _wants_catalog_list_all_intent(raw):
        return None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    s0 = _normalize_user_text_for_match(lines[0]) if lines else s
    fm = (focus_message or "").strip()
    dom = _infer_domain_for_catalog_list_query(fm) if fm else None
    if not dom:
        dom = _infer_domain_for_catalog_list_query(raw)
    if not dom:
        return None
    try:
        allp = list_products()
    except Exception:  # noqa: BLE001
        return None
    if not allp:
        return None

    budget_min, budget_max = _parse_budget_vnd(raw)

    def cat(p: Product) -> str:
        return (p.category_name or "").lower()

    def price_vnd(p: Product) -> int | None:
        try:
            return int(float(p.price)) if p.price is not None else None
        except Exception:  # noqa: BLE001
            return None

    out = [p for p in allp if _product_matches_domain(p, dom)]

    if dom == "laptop":
        pre_laptop = list(out)
        narrowed = [p for p in out if "laptop" in cat(p) or "macbook" in _name_key(p)]
        out = narrowed if narrowed else pre_laptop
        # Use the current question line only — joining older turns can wrongly re-inject "gaming"
        # into a follow-up like "có tất cả những laptop nào trong cửa hàng".
        s_laptop_focus = s0
        if _wants_gaming_laptop(s_laptop_focus):
            out = [p for p in out if _is_gaming_laptop_product(p)]
        elif _prefer_non_gaming_laptop(s_laptop_focus):
            out = [p for p in out if not _is_gaming_laptop_product(p)]
    elif dom == "audio":
        narrowed = [p for p in out if "audio" in cat(p)]
        out = narrowed if narrowed else out
    elif dom == "smartphone":
        narrowed = [
            p
            for p in out
            if (
                "smartphone" in cat(p)
                or "smartphones" in cat(p)
                or "phone" in cat(p)
                or "điện thoại" in cat(p)
                or "dien thoai" in cat(p)
                or "mobile" in cat(p)
            )
        ]
        base_phones = narrowed if narrowed else out
        out = base_phones
        # Brand hints: use the first line only so older turns (e.g. "Samsung") do not narrow a "list all" question.
        if "samsung" in s0 or ("galaxy" in s0 and "tab" not in s0):
            out = [p for p in out if ("samsung" in _name_key(p) or "galaxy" in _name_key(p)) and "tab" not in _name_key(p)]
        elif "iphone" in s0:
            out = [p for p in out if "iphone" in _name_key(p)]
        elif "xiaomi" in s0 or "redmi" in s0:
            out = [p for p in out if ("xiaomi" in _name_key(p) or "redmi" in _name_key(p))]
        elif "oppo" in s0:
            out = [p for p in out if "oppo" in _name_key(p)]
        elif "pixel" in s0 or "google" in s0:
            out = [p for p in out if ("pixel" in _name_key(p) or "google" in _name_key(p))]
        elif "oneplus" in s0:
            out = [p for p in out if "oneplus" in _name_key(p)]
        elif "realme" in s0:
            out = [p for p in out if "realme" in _name_key(p)]
    elif dom == "tablet":
        narrowed = [p for p in out if "tablet" in cat(p) or "ipad" in _name_key(p) or "galaxy tab" in _name_key(p) or "pad" in _name_key(p)]
        out = narrowed if narrowed else out
    elif dom == "smartwatch":
        narrowed = [p for p in out if "smartwatch" in cat(p) or "watch" in _name_key(p) or "garmin" in _name_key(p)]
        out = narrowed if narrowed else out
    elif dom == "accessories":
        narrowed = [p for p in out if "accessories" in cat(p)]
        out = narrowed if narrowed else out
        want_cable = any(k in s0 for k in ["cáp", "cap", "cable", "usb-c", "type-c", "type c"])
        want_charger = any(k in s0 for k in ["sạc", "sac", "charger", "củ sạc"])
        want_case = (
            any(k in s0 for k in ["ốp", "ốp lưng", "bao da"])
            or bool(re.search(r"\bop\s+lung\b", s0, flags=re.I))
            or bool(re.search(r"\bcase\b", s0))
        )
        if want_case and not want_cable and not want_charger:
            out = [p for p in out if _is_case_product(p)]
        elif want_cable and not want_case and not want_charger:
            out = [p for p in out if _is_cable_product(p)]
        elif want_charger and not want_case and not want_cable:
            out = [p for p in out if _is_charger_product(p)]
    elif dom == "book":
        out = _filter_books_by_query(out, raw, focus=s0)
    elif dom == "fashion":
        out = _filter_fashion_by_query(out, raw, focus=s0)

    if budget_min is not None or budget_max is not None:
        tmp: list[Product] = []
        for p in out:
            pv = price_vnd(p)
            if pv is None:
                continue
            if budget_min is not None and pv < budget_min:
                continue
            if budget_max is not None and pv > budget_max:
                continue
            tmp.append(p)
        out = tmp

    if not out:
        return None

    out.sort(key=lambda p: int(p.id))
    label = {
        "laptop": "laptop",
        "smartphone": "smartphone",
        "audio": "tai nghe / âm thanh",
        "tablet": "máy tính bảng",
        "smartwatch": "đồng hồ thông minh",
        "accessories": "phụ kiện",
        "book": "sách",
        "fashion": "thời trang",
    }.get(dom, dom)
    reply_lines = [f"Dưới đây là **toàn bộ** các mẫu **{label}** trong catalog ElecShop ({len(out)} mẫu):"]
    for i, p in enumerate(out, 1):
        reply_lines.append(f"{i}. {_format_catalog_line(p, dom)}")
    reply_lines.append("")
    reply_lines.append("Bạn muốn mình gợi ý thêm theo ngân sách hoặc thương hiệu không?")
    return "\n".join(reply_lines)


def _filter_pool_by_category_hint(products: list[Product], message: str) -> list[Product]:
    """Narrow to products whose category name appears in the user message."""

    s = _normalize_user_text_for_match(message)
    if not s:
        return products
    matched: list[Product] = []
    for p in products:
        cn = (p.category_name or "").lower().strip()
        if cn and cn in s:
            matched.append(p)
    if matched:
        return matched
    # Slug-style hints: smartphone, laptop, fiction, shoes, ...
    for p in products:
        cn = (p.category_name or "").lower()
        if not cn:
            continue
        tokens = [t for t in re.split(r"[^a-z0-9]+", cn) if len(t) >= 3]
        if any(t in s for t in tokens):
            matched.append(p)
    return matched if matched else products


def _wants_rating_rank_intent(text: str) -> bool:
    s = _normalize_user_text_for_match(text)
    if not query_mentions_rating(s) and "sao" not in s:
        return False
    if query_wants_high_rating(s) or query_wants_low_rating(s):
        return True
    if re.search(r"(cao|thấp|thap|tốt|tot|kém|kem)\s+nhất", s):
        return True
    if re.search(r"rating\s+(cao|thấp|thap)", s):
        return True
    return False


def _answer_rating_rank_vi(message: str) -> str | None:
    """
    Answer questions like: smartphone nào rating cao nhất / sách đánh giá thấp nhất trong category.
    """

    raw = (message or "").strip()
    if not _wants_rating_rank_intent(raw):
        return None

    s = _normalize_user_text_for_match(raw)
    want_low = query_wants_low_rating(s)
    want_high = query_wants_high_rating(s) or not want_low

    try:
        allp = list_products()
    except Exception:  # noqa: BLE001
        return None
    if not allp:
        return None

    dom = _infer_domain(raw)
    pool = [p for p in allp if _product_matches_domain(p, dom)] if dom else list(allp)
    pool = _filter_pool_by_category_hint(pool, raw)

    if dom == "book":
        pool = _filter_books_by_query(pool, raw, focus=s)
    elif dom == "fashion":
        pool = _filter_fashion_by_query(pool, raw, focus=s)

    rated = [p for p in pool if product_rating_value(p) > 0]
    if not rated:
        scope = (pool[0].category_name if len(pool) == 1 and pool[0].category_name else dom or "phạm vi bạn hỏi")
        return f"Trong **{scope}** hiện chưa có sản phẩm nào có rating (điểm đánh giá > 0)."

    def sort_key(p: Product) -> tuple:
        return (product_rating_value(p), product_rating_count(p), -int(p.id))

    rated.sort(key=sort_key, reverse=want_high)
    direction = "cao nhất" if want_high else "thấp nhất"
    scope_parts = []
    if dom:
        scope_parts.append(
            {
                "laptop": "laptop",
                "smartphone": "smartphone",
                "audio": "âm thanh",
                "tablet": "máy tính bảng",
                "smartwatch": "đồng hồ thông minh",
                "accessories": "phụ kiện",
                "book": "sách",
                "fashion": "thời trang",
            }.get(dom, dom)
        )
    cat_hint = _filter_pool_by_category_hint(pool, raw)
    if len(cat_hint) < len(pool) and cat_hint and cat_hint[0].category_name:
        scope_parts.append(cat_hint[0].category_name)
    scope = " / ".join(scope_parts) if scope_parts else "catalog"

    best = rated[0]
    lines = [
        f"Sản phẩm **rating {direction}** trong **{scope}** là:",
        f"- {format_rating_line(best)}",
    ]
    if len(rated) > 1:
        lines.append("")
        lines.append(f"Top {min(3, len(rated))} theo rating {'giảm dần' if want_high else 'tăng dần'}:")
        for i, p in enumerate(rated[:3], 1):
            lines.append(f"{i}. {format_rating_line(p)}")
    lines.append("")
    lines.append("Bạn muốn lọc thêm theo ngân sách hoặc thương hiệu không?")
    return "\n".join(lines)


def _answer_top_rated_suggestions_vi(message: str, products: list[Product] | None = None) -> str | None:
    """Gợi ý sản phẩm rating cao (không hỏi cao/thấp nhất tuyệt đối)."""

    s = _normalize_user_text_for_match(message)
    if not query_mentions_rating(s) or _wants_rating_rank_intent(message):
        return None
    if not query_wants_high_rating(s) and not any(k in s for k in ["đánh giá tốt", "danh gia tot", "rating tot"]):
        return None

    prods = products if products is not None else list_products()
    dom = _infer_domain(message)
    pool = [p for p in prods if _product_matches_domain(p, dom)] if dom else list(prods)
    pool = _filter_pool_by_category_hint(pool, message)
    if dom == "book":
        pool = _filter_books_by_query(pool, message)
    elif dom == "fashion":
        pool = _filter_fashion_by_query(pool, message)

    rated = [p for p in pool if product_rating_value(p) > 0]
    if not rated:
        return None
    rated.sort(key=lambda p: (rating_quality_score(p), product_rating_value(p)), reverse=True)
    picks = rated[:5]
    lines = ["Mình gợi ý các sản phẩm **được đánh giá cao** phù hợp câu hỏi của bạn:"]
    for p in picks:
        lines.append(f"- {format_rating_line(p)}")
    lines.append("")
    lines.append("Bạn muốn xem thêm theo ngân sách hoặc thương hiệu cụ thể không?")
    return "\n".join(lines)


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
    if (a.main_category or "").upper() == "BOOK" or (b.main_category or "").upper() == "BOOK":
        for label, p in (("A", a), ("B", b)):
            if p.book:
                if p.book.author:
                    lines.append(f"- {label} tác giả: {p.book.author}")
                if p.book.language:
                    lines.append(f"- {label} ngôn ngữ: {p.book.language}")
        lines.append("")
        lines.append("Bạn muốn ưu tiên thể loại (fiction/non-fiction), ngôn ngữ hay ngân sách để chốt 1 cuốn?")
        return "\n".join(lines)
    if (a.main_category or "").upper() == "FASHION" or (b.main_category or "").upper() == "FASHION":
        for label, p in (("A", a), ("B", b)):
            if p.fashion:
                bits = [x for x in (p.fashion.brand, p.fashion.size, p.fashion.gender, p.fashion.color) if x]
                if bits:
                    lines.append(f"- {label}: {', '.join(bits)}")
        lines.append("")
        lines.append("Bạn muốn ưu tiên size, màu hay thương hiệu để chốt 1 mẫu?")
        return "\n".join(lines)
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
    When True, answer with catalog heuristics instead of the LLM so behavior is deterministic
    (compare, stock check, accessories, non-gaming laptop, similar products).
    """

    msg = (message or "").strip()
    if _wants_catalog_list_all_intent(msg):
        return False
    s = msg.lower()
    if _wants_rating_rank_intent(msg):
        return True
    try:
        prods = list_products()
    except Exception:  # noqa: BLE001
        prods = []
    if _answer_rating_rank_vi(msg):
        return True
    if _answer_top_rated_suggestions_vi(msg, prods if prods else None):
        return True
    if _answer_compare_vi(msg, prods if prods else None):
        return True
    if prods and _answer_availability_vi(msg, prods):
        return True

    want_cable = any(k in s for k in ["cáp", "cable", "usb-c", "type c", "type-c", "type‑c"])
    want_charger = (
        any(k in s for k in ["sạc", "charger", "fast charger", "33w", "65w", "củ sạc"]) and not want_cable
    )
    want_case = (
        any(k in s for k in ["ốp", "ốp lưng", "bao da"])
        or bool(re.search(r"\bop\s+lung\b", s, flags=re.I))
        or bool(re.search(r"\bcase\b", s))
    )
    want_accessories = any(k in s for k in ["phụ kiện", "accessory", "phu kien"]) or want_charger or want_cable or want_case
    want_laptop = "laptop" in s or "macbook" in s
    want_phone = any(k in s for k in ["điện thoại", "dien thoai", "smartphone", " phone "]) or any(
        k in s for k in ["samsung", "galaxy", "iphone", "xiaomi", "redmi", "oppo", "realme", "oneplus", "pixel"]
    )
    want_tablet = any(k in s for k in ["tablet", "ipad", "máy tính bảng", "may tinh bang"])
    want_watch = any(k in s for k in ["smartwatch", "đồng hồ", "dong ho", "watch", "garmin"])
    want_book = _wants_book_intent(s)
    want_fashion = _wants_fashion_intent(s)
    want_accessories = _finalize_want_accessories(
        s,
        want_laptop=want_laptop,
        want_phone=want_phone,
        want_tablet=want_tablet,
        want_watch=want_watch,
        want_accessories=want_accessories,
    )

    want_similar = any(k in s for k in ["tương tự", "similar", "giống"])

    if want_accessories:
        return True
    if want_book or want_fashion:
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

    rank = _answer_rating_rank_vi(msg)
    if rank:
        return rank

    top_rated = _answer_top_rated_suggestions_vi(msg, products)
    if top_rated:
        return top_rated

    cmp = _answer_compare_vi(msg)
    if cmp:
        return cmp

    avail = _answer_availability_vi(msg, products)
    if avail:
        return avail

    full_catalog = _maybe_answer_catalog_list_all_vi(msg, focus_message=msg)
    if full_catalog:
        return full_catalog

    # Basic intent heuristics
    s = msg.lower()
    # Treat brand-only messages (e.g. "hãng samsung") as phone intent too.
    want_phone = any(k in s for k in ["điện thoại", "dien thoai", "smartphone", " phone "])  # avoid matching "iphone"
    if not want_phone and any(k in s for k in ["samsung", "galaxy", "iphone", "xiaomi", "redmi", "oppo", "realme", "oneplus", "pixel"]):
        want_phone = True
    want_laptop = "laptop" in s or "macbook" in s
    s_head = (msg.splitlines()[0] or msg).lower().strip() if msg else s
    want_gaming_laptop = want_laptop and _wants_gaming_laptop(s_head)
    want_big_ram = any(k in s for k in ["ram to", "ram lớn", "ram lon", "ram cao", "nhiều ram", "nhieu ram"])
    want_big_ssd = any(k in s for k in ["ssd", "ổ cứng", "o cung", "dung lượng", "dung luong"])
    want_battery = any(k in s for k in ["pin trâu", "pin trau", "pin tốt", "pin tot", "pin lâu", "pin lau", "battery"])
    want_earbuds = any(k in s for k in ["tai nghe", "earbud", "airpods", "headphone"])
    want_tablet = any(k in s for k in ["tablet", "ipad", "máy tính bảng", "may tinh bang"])
    want_watch = any(k in s for k in ["smartwatch", "đồng hồ", "dong ho", "watch", "garmin"])
    want_book = _wants_book_intent(s)
    want_fashion = _wants_fashion_intent(s)
    want_cable = any(k in s for k in ["cáp", "cable", "usb-c", "type c", "type-c", "type‑c"])
    # If message includes "cáp sạc" we should prioritize cable over wall charger.
    want_charger = (any(k in s for k in ["sạc", "charger", "fast charger", "33w", "65w", "củ sạc"]) and not want_cable)
    want_case = (
        any(k in s for k in ["ốp", "ốp lưng", "bao da"])
        or bool(re.search(r"\bop\s+lung\b", s, flags=re.I))
        or bool(re.search(r"\bcase\b", s))
    )
    want_accessories = any(k in s for k in ["phụ kiện", "accessory", "phu kien"]) or want_charger or want_cable or want_case
    want_accessories = _finalize_want_accessories(
        s,
        want_laptop=want_laptop,
        want_phone=want_phone,
        want_tablet=want_tablet,
        want_watch=want_watch,
        want_accessories=want_accessories,
    )

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
            cand = [p for p in cand if _is_gaming_laptop_product(p)]
        if _prefer_non_gaming_laptop(s_head):
            cand = [p for p in cand if not _is_gaming_laptop_product(p)]
        if re.search(r"\basus\b", s, flags=re.I):
            tmp = [p for p in cand if "asus" in _name_key(p)]
            cand = tmp if tmp else cand
        elif re.search(r"\bdell\b", s, flags=re.I):
            tmp = [p for p in cand if "dell" in _name_key(p)]
            cand = tmp if tmp else cand
        elif re.search(r"\bhp\b", s, flags=re.I):
            tmp = [p for p in cand if re.search(r"\bhp\b", _name_key(p), flags=re.I)]
            cand = tmp if tmp else cand
        elif re.search(r"\blenovo\b", s, flags=re.I):
            tmp = [p for p in cand if "lenovo" in _name_key(p)]
            cand = tmp if tmp else cand
        elif re.search(r"\bmsi\b", s, flags=re.I):
            tmp = [p for p in cand if "msi" in _name_key(p)]
            cand = tmp if tmp else cand
        elif re.search(r"\bacer\b", s, flags=re.I):
            tmp = [p for p in cand if "acer" in _name_key(p)]
            cand = tmp if tmp else cand
    elif want_earbuds:
        cand = [p for p in cand if "audio" in cat(p)]
    elif want_book:
        cand = _filter_books_by_query(cand, s, focus=s_head)
    elif want_fashion:
        cand = _filter_fashion_by_query(cand, s, focus=s_head)
    elif query_mentions_rating(s) and query_wants_high_rating(s):
        rated = [p for p in cand if product_rating_value(p) > 0]
        cand = sorted(rated, key=lambda p: (rating_quality_score(p), product_rating_value(p)), reverse=True) if rated else cand

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

    want_list_all = _wants_catalog_list_all_intent(msg)
    if want_list_all:
        cap = 80
    elif want_laptop and want_gaming_laptop:
        cap = 12
    else:
        cap = 5
    cand = cand[:cap]

    if cand:
        lines = ["Mình gợi ý vài sản phẩm trong shop phù hợp nhu cầu của bạn:"]
        dom_hint = "book" if want_book else "fashion" if want_fashion else None
        for p in cand:
            lines.append(f"- {_format_catalog_line(p, dom_hint)}")
        lines.append("")
        # Ask a single next question without repeating the generic menu.
        # Note: catalog does not store detailed specs (RAM/SSD/battery hours), so we ask clarifying questions.
        if want_book:
            lines.append("Bạn muốn sách tiếng Việt hay tiếng Anh, thể loại fiction/non-fiction, hay có tác giả cụ thể nào?")
        elif want_fashion:
            lines.append("Bạn muốn ưu tiên size, màu, giới tính (nam/nữ) hay thương hiệu nào?")
        elif want_laptop:
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
    if want_book:
        qs = [
            "Bạn muốn sách thể loại nào (fiction, non-fiction, thiếu nhi)?",
            "Bạn ưu tiên tiếng Việt hay tiếng Anh, và ngân sách khoảng bao nhiêu?",
        ]
    elif want_fashion:
        qs = [
            "Bạn đang tìm quần áo, giày hay túi xách?",
            "Bạn cần size/giới tính nào và ngân sách khoảng bao nhiêu?",
        ]
    else:
        qs = [
            "Bạn cho mình biết ngân sách khoảng bao nhiêu (VD: dưới 7 triệu / 10–15 triệu)?",
            "Bạn muốn mua điện tử, sách hay thời trang — và nhu cầu chính là gì?",
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


