from __future__ import annotations

from .chat_types import ChatResult
from .chat_heuristics import (
    _extract_product_ids,
    _fallback_answer_vi,
    _filter_and_rerank_retrieved,
    _infer_domain,
    _is_affirmative_short_reply,
    _is_cable_product,
    _is_case_product,
    _is_charger_product,
    _is_gaming_laptop_name,
    _is_negative_short_reply,
    _load_recent_chat_turns,
    _name_key,
    _parse_budget_vnd,
    _prefer_non_gaming_laptop,
    _product_matches_domain,
    _should_use_heuristic_first,
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
            # LLM may be unavailable (quota/billing); still provide a useful in-shop answer.
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

