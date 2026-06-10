"""
Chat orchestration: retrieval + optional heuristics + Gemini completion (see `chat_heuristics` docstring).
"""

from __future__ import annotations

import re

from .chat_types import ChatResult
from .chat_heuristics import (
    _extract_product_ids,
    _fallback_answer_vi,
    _filter_and_rerank_retrieved,
    _filter_books_by_query,
    _filter_fashion_by_query,
    _infer_domain,
    _is_affirmative_short_reply,
    _is_cable_product,
    _is_case_product,
    _is_charger_product,
    _is_gaming_laptop_product,
    _is_negative_short_reply,
    _load_recent_chat_turns,
    _answer_rating_rank_vi,
    _maybe_answer_catalog_list_all_vi,
    _name_key,
    _parse_budget_vnd,
    _prefer_non_gaming_laptop,
    _product_matches_domain,
    _finalize_want_accessories,
    _should_use_heuristic_first,
    _wants_book_intent,
    _wants_catalog_list_all_intent,
    _wants_fashion_intent,
    _summarize_history,
    _wants_gaming_laptop,
)
from .graph_gateway import graph_context_for_rag, upsert_event_to_graph
from .graphrag import build_graphrag_context
from .indexing import retrieve_similar
from .llm_client import chat_completion
from .product_gateway import Product, get_product, list_products
from .recommendation import hydrate_products, recommend_products
from .sequence_predictor import predict_next_action
from ..infrastructure.models import ChatTurn


def answer_chat(user_id: str, message: str, *, session_id: str = "default") -> ChatResult:
    """
    RAG chat (LLM + pgvector) with graceful fallback:
    - Uses behavior context from interaction-service.
    - Retrieves relevant product documents from pgvector.
    - Calls Gemini via `llm_client.chat_completion` for a grounded answer.
    - If the LLM is unavailable, falls back to deterministic catalog heuristics.
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
                "tác giả",
                "tac gia",
                "author",
                "tiếng việt",
                "tieng viet",
                "tiếng anh",
                "tieng anh",
                "size",
                "cỡ",
                "co ",
                "giới tính",
                "gioi tinh",
                "nam",
                "nữ",
                "nu ",
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
                "book": "sach",
                "fashion": "thoi trang",
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
                    "book": "sach",
                    "fashion": "thoi trang",
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

    def _product_dict(p: Product) -> dict:
        row = {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "main_category": p.main_category,
            "category": p.category_name,
            "price": p.price,
            "currency": p.currency,
            "ratings": p.ratings,
            "no_of_ratings": p.no_of_ratings,
            "description": (p.description or "")[:240],
        }
        if p.book:
            row["book"] = {
                "author": p.book.author,
                "publisher": p.book.publisher,
                "language": p.book.language,
                "isbn": p.book.isbn,
            }
        if p.electronics:
            row["electronics"] = {
                "brand": p.electronics.brand,
                "color": p.electronics.color,
                "warranty_months": p.electronics.warranty_months,
            }
        if p.fashion:
            row["fashion"] = {
                "brand": p.fashion.brand,
                "size": p.fashion.size,
                "color": p.fashion.color,
                "gender": p.fashion.gender,
            }
        return row

    def _augment_candidates(msg: str, base: list[dict]) -> list[dict]:
        """
        Ensure the context always contains category-relevant candidates when the user asks explicitly
        (e.g., laptop/audio/phone/tablet/watch/accessories), even if personalized recommenders return unrelated items.
        """

        s = (msg or "").lower()
        aug_lines = [ln.strip() for ln in (msg or "").splitlines() if ln.strip()]
        s_focus = aug_lines[0].lower() if aug_lines else s
        want_laptop = "laptop" in s or "macbook" in s
        want_audio = any(
            k in s
            for k in [
                "tai nghe",
                "earbud",
                "airpods",
                "headphone",
                "chống ồn",
                "noise cancelling",
                "anc",
                "loa",
                "speaker",
                "jbl",
                "sony",
                "bose",
                "sennheiser",
            ]
        )
        want_phone = any(
            k in s
            for k in [
                "điện thoại",
                "dien thoai",
                "smartphone",
                "iphone",
                "samsung",
                "galaxy",
                "galaxy s",
                "galaxy a",
                "galaxy z",
                "xiaomi",
                "redmi",
                "oppo",
                "realme",
                "oneplus",
                "pixel",
            ]
        )
        # Avoid treating "galaxy tab" as phone (tablet branch wins first).
        if want_phone and any(k in s for k in ["galaxy tab", "ipad", "tablet", "máy tính bảng", "may tinh bang", "xiaomi pad"]):
            want_phone = False
        want_tablet = any(k in s for k in ["tablet", "ipad", "máy tính bảng", "may tinh bang", "galaxy tab", "xiaomi pad"])
        want_watch = any(
            k in s
            for k in [
                "smartwatch",
                "apple watch",
                "galaxy watch",
                "garmin",
                "forerunner",
                "fitbit",
                "đồng hồ thông minh",
                "dong ho thong minh",
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
                "ốp lưng",
                "op lung",
                "bao da",
                "hub",
                "bàn phím",
                "ban phim",
                "chuột",
                "chuot",
                "mouse",
                "keyboard",
            ]
        ) or bool(re.search(r"\bcase\b", s))

        want_accessories = _finalize_want_accessories(
            s,
            want_laptop=want_laptop,
            want_phone=want_phone,
            want_tablet=want_tablet,
            want_watch=want_watch,
            want_accessories=want_accessories,
        )
        want_book = _wants_book_intent(s)
        want_fashion = _wants_fashion_intent(s)

        if not (want_laptop or want_audio or want_phone or want_tablet or want_watch or want_accessories or want_book or want_fashion):
            return base

        budget_min, budget_max = _parse_budget_vnd(msg)
        try:
            allp = list_products()
        except Exception:  # noqa: BLE001
            allp = []

        cand: list[Product] = allp
        if want_laptop:
            cand = [p for p in cand if "laptop" in _cat(p) or "macbook" in _name_key(p)]
            if _wants_gaming_laptop(s_focus):
                cand = [p for p in cand if _is_gaming_laptop_product(p)]
            if _prefer_non_gaming_laptop(s_focus):
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
        elif want_audio:
            cand = [p for p in cand if "audio" in _cat(p)]
        elif want_phone:
            cand = [p for p in cand if ("smartphone" in _cat(p) or "smartphones" in _cat(p) or "phone" in _cat(p))]
            # Brand hint
            if "samsung" in s or ("galaxy" in s and "tab" not in s):
                cand = [p for p in cand if ("samsung" in _name_key(p) or "galaxy" in _name_key(p)) and "tab" not in _name_key(p)]
            elif "iphone" in s:
                cand = [p for p in cand if "iphone" in _name_key(p)]
            elif "xiaomi" in s or "redmi" in s:
                cand = [p for p in cand if ("xiaomi" in _name_key(p) or "redmi" in _name_key(p))]
            elif "oppo" in s:
                cand = [p for p in cand if "oppo" in _name_key(p)]
            elif "pixel" in s or "google" in s:
                cand = [p for p in cand if ("pixel" in _name_key(p) or "google" in _name_key(p))]
            elif "oneplus" in s:
                cand = [p for p in cand if "oneplus" in _name_key(p)]
            elif "realme" in s:
                cand = [p for p in cand if "realme" in _name_key(p)]
        elif want_tablet:
            cand = [p for p in cand if "tablet" in _cat(p) or "ipad" in _name_key(p) or "galaxy tab" in _name_key(p) or "pad" in _name_key(p)]
        elif want_watch:
            cand = [p for p in cand if "smartwatch" in _cat(p) or "watch" in _name_key(p) or "garmin" in _name_key(p)]
        elif want_accessories:
            cand = [p for p in cand if "accessories" in _cat(p)]
            # If user is specific, filter within accessories.
            want_cable = any(k in s for k in ["cáp", "cap", "cable", "usb-c", "type-c", "type c"])
            want_charger = any(k in s for k in ["sạc", "sac", "charger", "củ sạc"])
            want_case = (
                any(k in s for k in ["ốp", "ốp lưng", "bao da"])
                or bool(re.search(r"\bop\s+lung\b", s, flags=re.I))
                or bool(re.search(r"\bcase\b", s))
            )
            if want_case and not want_cable and not want_charger:
                cand = [p for p in cand if _is_case_product(p)]
            elif want_cable and not want_case and not want_charger:
                cand = [p for p in cand if _is_cable_product(p)]
            elif want_charger and not want_case and not want_cable:
                cand = [p for p in cand if _is_charger_product(p)]
        elif want_book:
            cand = _filter_books_by_query(cand, s, focus=s_focus)
        elif want_fashion:
            cand = _filter_fashion_by_query(cand, s, focus=s_focus)

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

        want_list_all = _wants_catalog_list_all_intent(msg)
        explicit_cat = want_laptop or want_audio or want_phone or want_tablet or want_watch or want_accessories or want_book or want_fashion
        gaming = want_laptop and _wants_gaming_laptop(s_focus)
        list_all_mode = explicit_cat and want_list_all
        if gaming and want_list_all:
            max_extra, scan_n = 80, 500
        elif gaming:
            max_extra, scan_n = 10, 25
        elif list_all_mode:
            max_extra, scan_n = 80, 500
        elif explicit_cat:
            max_extra, scan_n = 8, 30
        else:
            max_extra, scan_n = 3, 25

        have = {int(x.get("id")) for x in base if x.get("id") is not None}
        extra: list[dict] = []
        scan_slice = cand if list_all_mode else cand[:scan_n]
        for p in scan_slice:
            if int(p.id) in have:
                continue
            extra.append(_product_dict(p))
            have.add(int(p.id))
            if len(extra) >= max_extra:
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
        if want_tablet:
            base2 = [
                it
                for it in base
                if ("tablet" in _base_cat_text(it) or "ipad" in str(it.get("name") or "").lower() or "tab" in str(it.get("name") or "").lower())
            ]
            return extra + base2
        if want_watch:
            base2 = [it for it in base if ("smartwatch" in _base_cat_text(it) or "watch" in str(it.get("name") or "").lower())]
            return extra + base2
        if want_accessories:
            base2 = [it for it in base if ("accessories" in _base_cat_text(it) or "phụ kiện" in _base_cat_text(it))]
            return extra + base2
        if want_book:
            base2 = [it for it in base if str(it.get("main_category") or "").upper() == "BOOK"]
            return extra + base2
        if want_fashion:
            base2 = [it for it in base if str(it.get("main_category") or "").upper() == "FASHION"]
            return extra + base2

        return base + extra

    # Build short textual context using product descriptions
    picked: list[dict] = []
    for p in products[:3]:
        try:
            full = get_product(int(p["id"]))
            picked.append(_product_dict(full))
        except Exception:  # noqa: BLE001
            picked.append(p)
    # Use recent conversation to keep topic continuity (e.g., user says "Samsung" then later only "dưới 30 triệu").
    picked = _augment_candidates(f"{msg}\n{convo_text}", picked)

    catalog_list_answer = _maybe_answer_catalog_list_all_vi(f"{msg}\n{convo_text}", focus_message=msg)
    rating_rank_answer = _answer_rating_rank_vi(msg)

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
        "Bạn là trợ lý tư vấn mua sắm của ElecShop (bán điện tử, sách và thời trang). "
        "Luôn trả lời bằng tiếng Việt. "
        "Chỉ sử dụng thông tin trong phần ngữ cảnh được cung cấp (hành vi người dùng, đồ thị gợi ý, các chunks đã truy xuất, danh sách sản phẩm gợi ý). "
        "Tuyệt đối không bịa thông tin (giá, cấu hình, tồn kho) nếu không thấy trong ngữ cảnh. "
        "Nếu ngữ cảnh chưa đủ để trả lời chắc chắn, hãy hỏi 1-2 câu hỏi làm rõ. "
        "Tránh lặp lại cùng một câu hỏi nhiều lần; nếu người dùng trả lời 'có/ok/yes' sau khi bạn hỏi có muốn xem thêm gợi ý, hãy đưa thêm gợi ý ngay. "
        "Khi đề xuất sản phẩm, ưu tiên các mục trong Candidate products; nếu người dùng yêu cầu liệt kê đầy đủ "
        "thì liệt kê tất cả các mục đó (kèm product_id). Nếu không, đưa 2–4 lựa chọn phù hợp nhất. "
        "Với sách: nêu tác giả/ngôn ngữ/thể loại nếu có trong ngữ cảnh. "
        "Với thời trang: nêu brand/size/gender/màu nếu có. "
        "Với điện tử: nêu hãng/dòng máy nếu có. "
        "Khi người dùng hỏi rating cao/thấp nhất trong category, chỉ dùng điểm rating và số lượt đánh giá trong ngữ cảnh."
    )
    # Keep prompt compact to reduce off-topic answers.
    user = (
        f"Recent conversation (most recent last):\n{recent_turns}\n\n"
        f"User message:\n{msg}\n\n"
        f"User behavior:\n{history}\n\n"
        f"Graph evidence:\n{graph_ctx_display}\n\n"
        f"Retrieved chunks:\n{retrieved}\n\n"
        f"Candidate products (use these first):\n{picked[:45]}\n"
    )

    if catalog_list_answer is not None:
        answer = catalog_list_answer
    elif rating_rank_answer is not None:
        answer = rating_rank_answer
    elif force_heuristic or _should_use_heuristic_first(logic_text):
        answer = _fallback_answer_vi(logic_text, history=history)
    else:
        try:
            answer = chat_completion(system=system, user=user)
        except Exception:
            # LLM may be unavailable (quota/billing); still provide a useful in-shop answer.
            answer = _fallback_answer_vi(logic_text, history=history)

    # Guardrail: if the assistant suggests product_ids from the wrong domain, fall back to deterministic in-shop suggestions.
    # Skip when we already answered from full-catalog heuristics: `domain` may still reflect an older turn (e.g. laptop)
    # while the deterministic list used the domain from the current question (e.g. smartphone).
    if catalog_list_answer is None and rating_rank_answer is None:
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

