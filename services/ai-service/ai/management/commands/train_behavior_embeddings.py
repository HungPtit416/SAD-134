from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from ...application.interaction_gateway import list_recent_events
from ...infrastructure.models import ProductEmbedding, UserEmbedding


class Command(BaseCommand):
    help = "Train simple product/user embeddings from behavior events (skip-gram)."

    def add_arguments(self, parser):
        parser.add_argument("--dim", type=int, default=64)
        parser.add_argument("--epochs", type=int, default=5)
        parser.add_argument("--window", type=int, default=2)
        parser.add_argument("--min-count", type=int, default=1)
        parser.add_argument("--limit-events", type=int, default=5000)

    def handle(self, *args, **opts):
        dim = int(opts["dim"])
        epochs = int(opts["epochs"])
        window = int(opts["window"])
        min_count = int(opts["min_count"])
        limit_events = int(opts["limit_events"])

        import numpy as np

        events = list_recent_events(limit=limit_events)
        by_user: dict[str, list[int]] = defaultdict(list)
        for e in sorted(events, key=lambda x: x.created_at):
            if e.product_id is None:
                continue
            # Include click as a product interaction signal (required in the assignment behaviors).
            if e.event_type not in {"view", "click", "add_to_cart", "purchase"}:
                continue
            by_user[e.user_id].append(int(e.product_id))

        # Build product counts and vocab
        counts: dict[int, int] = defaultdict(int)
        for seq in by_user.values():
            for pid in seq:
                counts[pid] += 1
        vocab = [pid for pid, c in counts.items() if c >= min_count]
        if len(vocab) < 2:
            self.stdout.write(self.style.WARNING("Not enough product interactions to train embeddings."))
            return
        pid_to_idx = {pid: i for i, pid in enumerate(vocab)}
        idx_to_pid = {i: pid for pid, i in pid_to_idx.items()}

        pairs: list[tuple[int, int]] = []
        for seq in by_user.values():
            seq_idx = [pid_to_idx[pid] for pid in seq if pid in pid_to_idx]
            for i, t in enumerate(seq_idx):
                lo = max(0, i - window)
                hi = min(len(seq_idx), i + window + 1)
                for j in range(lo, hi):
                    if j == i:
                        continue
                    pairs.append((t, seq_idx[j]))

        if not pairs:
            self.stdout.write(self.style.WARNING("No training pairs generated."))
            return

        # Skip-gram with negative sampling (numpy SGD)
        rng = np.random.default_rng(42)
        in_emb = (rng.standard_normal((len(vocab), dim)).astype(np.float32) * 0.01)
        out_emb = (rng.standard_normal((len(vocab), dim)).astype(np.float32) * 0.01)

        # Unigram distribution for negatives
        weights = np.array([counts[idx_to_pid[i]] ** 0.75 for i in range(len(vocab))], dtype=np.float64)
        weights = weights / np.maximum(weights.sum(), 1e-9)

        batch_size = 256
        neg_k = 8
        lr = 0.05

        def batches():
            for i in range(0, len(pairs), batch_size):
                yield pairs[i : i + batch_size]

        def sigmoid(x):
            return 1.0 / (1.0 + np.exp(-x))

        for ep in range(epochs):
            total_loss = 0.0
            n = 0
            for batch in batches():
                t = np.array([x[0] for x in batch], dtype=np.int64)
                c = np.array([x[1] for x in batch], dtype=np.int64)

                v_t = in_emb[t]  # (B, D)
                v_c = out_emb[c]  # (B, D)
                pos_score = np.sum(v_t * v_c, axis=1)  # (B,)
                pos_sig = sigmoid(pos_score)
                pos_loss = -np.log(np.maximum(pos_sig, 1e-9))

                neg = rng.choice(len(vocab), size=(len(batch), neg_k), replace=True, p=weights)
                v_n = out_emb[neg]  # (B, K, D)
                neg_score = np.einsum("bkd,bd->bk", v_n, v_t)  # (B, K)
                neg_sig = sigmoid(-neg_score)
                neg_loss = -np.log(np.maximum(neg_sig, 1e-9)).sum(axis=1)

                loss = (pos_loss + neg_loss).mean()

                # Gradients
                # Positive: dL/ds = (sigmoid(s) - 1)
                g_pos = (pos_sig - 1.0).astype(np.float32)  # (B,)
                grad_vt = (g_pos[:, None] * v_c).astype(np.float32)
                grad_vc = (g_pos[:, None] * v_t).astype(np.float32)

                # Negative: for -log(sigmoid(-s)) => dL/ds = sigmoid(s)
                g_neg = sigmoid(neg_score).astype(np.float32)  # (B, K)
                grad_vt += np.einsum("bk,bkd->bd", g_neg, v_n).astype(np.float32)
                grad_vn = (g_neg[:, :, None] * v_t[:, None, :]).astype(np.float32)  # (B, K, D)

                # SGD updates (with index accumulation)
                for i, idx in enumerate(t):
                    in_emb[idx] -= lr * grad_vt[i]
                for i, idx in enumerate(c):
                    out_emb[idx] -= lr * grad_vc[i]
                # negatives
                for i in range(len(batch)):
                    for j in range(neg_k):
                        out_emb[neg[i, j]] -= lr * grad_vn[i, j]

                total_loss += float(loss) * len(batch)
                n += len(batch)
            self.stdout.write(f"epoch={ep+1}/{epochs} loss={total_loss/max(n,1):.4f}")

        # Save embeddings
        prod_vecs = in_emb.astype(np.float32).tolist()

        with transaction.atomic():
            ProductEmbedding.objects.all().delete()
            UserEmbedding.objects.all().delete()

            ProductEmbedding.objects.bulk_create(
                [ProductEmbedding(product_id=idx_to_pid[i], embedding=prod_vecs[i]) for i in range(len(vocab))],
                batch_size=500,
            )

            # User embedding = mean of interacted product embeddings
            user_rows = []
            for user_id, seq in by_user.items():
                idxs = [pid_to_idx[pid] for pid in seq if pid in pid_to_idx]
                if not idxs:
                    continue
                # mean
                vec = [0.0] * dim
                for ii in idxs[:200]:
                    v = prod_vecs[ii]
                    for k in range(dim):
                        vec[k] += float(v[k])
                denom = float(len(idxs[:200]))
                vec = [x / denom for x in vec]
                user_rows.append(UserEmbedding(user_id=user_id, embedding=vec))
            UserEmbedding.objects.bulk_create(user_rows, batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Saved {len(vocab)} product embeddings and {len(user_rows)} user embeddings."))

