from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Interaction:
    user_id: str
    product_id: int
    weight: float


def build_index_map(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        if v not in out:
            out[v] = len(out)
    return out


def build_index_map_int(values: Iterable[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for v in values:
        if v not in out:
            out[v] = len(out)
    return out


def train_lightgcn_bpr(
    *,
    interactions: list[Interaction],
    num_users: int,
    num_items: int,
    dim: int = 64,
    layers: int = 2,
    epochs: int = 5,
    lr: float = 1e-2,
    reg: float = 1e-4,
    seed: int = 42,
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Minimal LightGCN-style training using BPR loss.
    Returns (user_embeddings, item_embeddings) as Python lists for DB storage.

    Notes:
    - This is intentionally compact for a final-term report.
    - For large-scale production you would use sparse ops and dataloaders.
    """

    import random

    import numpy as np

    rng = np.random.default_rng(int(seed))
    random.seed(int(seed))

    # The caller remaps ids; here we expect interactions already remapped to int indices in string fields.
    by_user: list[list[int]] = [[] for _ in range(num_users)]
    for it in interactions:
        by_user[int(it.user_id)].append(int(it.product_id))

    # Base embeddings
    U = (rng.standard_normal((num_users, dim)).astype(np.float32) * 0.01)
    I = (rng.standard_normal((num_items, dim)).astype(np.float32) * 0.01)

    all_items = list(range(num_items))

    def sigmoid(x: float) -> float:
        return 1.0 / (1.0 + np.exp(-x))

    def propagate(u0: np.ndarray, i0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        LightGCN propagation (mean aggregator) implemented with plain Python/numpy loops.
        Suitable for small datasets used in the course project.
        """

        u_list = [u0]
        i_list = [i0]
        u = u0
        i = i0
        for _ in range(max(1, int(layers))):
            u_next = u.copy()
            i_next = i.copy()

            # item -> users adjacency
            item_users: list[list[int]] = [[] for _ in range(num_items)]
            for uid in range(num_users):
                for pid in by_user[uid]:
                    item_users[pid].append(uid)

            # update users
            for uid in range(num_users):
                neigh = by_user[uid]
                if not neigh:
                    continue
                i_mat = i[np.array(neigh, dtype=np.int64)]
                u_next[uid] = i_mat.mean(axis=0)

            # update items
            for pid in range(num_items):
                us = item_users[pid]
                if not us:
                    continue
                u_mat = u[np.array(us, dtype=np.int64)]
                i_next[pid] = u_mat.mean(axis=0)

            u = u_next
            i = i_next
            u_list.append(u)
            i_list.append(i)

        u_final = np.stack(u_list, axis=0).mean(axis=0)
        i_final = np.stack(i_list, axis=0).mean(axis=0)
        return u_final.astype(np.float32), i_final.astype(np.float32)

    # Training pairs (u, pos) with weights
    pairs: list[tuple[int, int, float]] = [(int(it.user_id), int(it.product_id), float(it.weight)) for it in interactions]
    if not pairs:
        return [[0.0] * dim for _ in range(num_users)], [[0.0] * dim for _ in range(num_items)]

    for _ep in range(max(1, int(epochs))):
        random.shuffle(pairs)

        # Use propagated embeddings for scoring
        u_emb, i_emb = propagate(U, I)

        for uid, pos, w in pairs:
            user_pos = set(by_user[uid])
            neg = random.choice(all_items)
            tries = 0
            while neg in user_pos and tries < 25:
                neg = random.choice(all_items)
                tries += 1

            uvec = u_emb[uid]
            pvec = i_emb[pos]
            nvec = i_emb[neg]

            x = float(np.dot(uvec, pvec - nvec))
            s = sigmoid(x)
            # BPR loss: -log(sigmoid(x))
            g = (s - 1.0) * float(max(0.1, w))

            # Gradients (SGD on base embeddings U/I)
            # Update base embeddings rather than propagated ones (compact approximation).
            U[uid] -= float(lr) * (g * (pvec - nvec) + float(reg) * U[uid])
            I[pos] -= float(lr) * (g * uvec + float(reg) * I[pos])
            I[neg] -= float(lr) * (-g * uvec + float(reg) * I[neg])

    u_final, i_final = propagate(U, I)
    return u_final.astype("float32").tolist(), i_final.astype("float32").tolist()

