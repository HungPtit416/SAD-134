from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, f1_score
from sklearn.model_selection import train_test_split

#B22DCCN416 Nguyen Tuan Hung
BEHAVIORS_8 = [
    "view",
    "click",
    "add_to_cart",
    "purchase",
    "search",
    "browse_products",
    "browse_recommended",
    "checkout",
]


@dataclass(frozen=True)
class Dataset:
    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    label_to_id: dict[str, int]
    id_to_label: dict[int, str]


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"user_id", "product_id", "action", "timestamp"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["user_id", "action", "timestamp"]).copy()
    df["user_id"] = df["user_id"].astype(str)
    df["action"] = df["action"].astype(str)
    return df


def build_next_action_dataset(df: pd.DataFrame, *, seq_len: int, seed: int) -> Dataset:
    label_to_id = {b: i for i, b in enumerate(BEHAVIORS_8)}
    id_to_label = {i: b for b, i in label_to_id.items()}

    df = df[df["action"].isin(label_to_id.keys())].copy()
    df = df.sort_values(["user_id", "timestamp"], ascending=True)
    df["label_id"] = df["action"].map(label_to_id).astype(int)

    users = df["user_id"].drop_duplicates().tolist()
    u_train, u_tmp = train_test_split(users, test_size=0.30, random_state=seed, shuffle=True)
    u_val, u_test = train_test_split(u_tmp, test_size=0.50, random_state=seed, shuffle=True)

    def to_xy(uids: set[str]) -> tuple[np.ndarray, np.ndarray]:
        x_list: list[list[int]] = []
        y_list: list[int] = []
        for _, g in df[df["user_id"].isin(uids)].groupby("user_id", sort=False):
            seq = g["label_id"].tolist()
            if len(seq) <= seq_len:
                continue
            for i in range(seq_len, len(seq)):
                x_list.append(seq[i - seq_len : i])
                y_list.append(seq[i])
        if not x_list:
            return np.zeros((0, seq_len), dtype=np.int32), np.zeros((0,), dtype=np.int32)
        return np.asarray(x_list, dtype=np.int32), np.asarray(y_list, dtype=np.int32)

    x_train, y_train = to_xy(set(u_train))
    x_val, y_val = to_xy(set(u_val))
    x_test, y_test = to_xy(set(u_test))

    if x_train.shape[0] < 1000:
        raise RuntimeError(
            f"Not enough training samples after split. Got x_train={x_train.shape}. "
            "Increase events per user or decrease seq_len."
        )

    return Dataset(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        x_test=x_test,
        y_test=y_test,
        label_to_id=label_to_id,
        id_to_label=id_to_label,
    )


def build_model_lstm(*, vocab_size: int, seq_len: int, embed_dim: int, rnn_units: int, num_classes: int):
    import tensorflow as tf

    inputs = tf.keras.Input(shape=(seq_len,), dtype="int32")
    x = tf.keras.layers.Embedding(input_dim=vocab_size, output_dim=embed_dim, name="action_embedding")(inputs)
    x = tf.keras.layers.LSTM(rnn_units, name="lstm")(x)
    x = tf.keras.layers.Dense(64, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="lstm_next_action")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def plot_curves(history, *, out_path: Path, title: str) -> None:
    plt.figure(figsize=(9, 4))
    plt.subplot(1, 2, 1)
    plt.plot(history.history.get("loss", []), label="train")
    plt.plot(history.history.get("val_loss", []), label="val")
    plt.title(f"{title} loss")
    plt.xlabel("epoch")
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(history.history.get("accuracy", []), label="train")
    plt.plot(history.history.get("val_accuracy", []), label="val")
    plt.title(f"{title} accuracy")
    plt.xlabel("epoch")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_confusion(*, y_true: np.ndarray, y_pred: np.ndarray, labels: list[str], out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay.from_predictions(
        y_true,
        y_pred,
        display_labels=labels,
        xticks_rotation=45,
        colorbar=False,
        ax=ax,
        normalize="true",
    )
    ax.set_title(f"{title} confusion matrix (normalized)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="Train LSTM model for next-action (8-class) classification.")
    ap.add_argument("--csv", type=str, default=str(Path("data") / "data_user500.csv"))
    ap.add_argument("--out", type=str, default=str(Path("ml") / "artifacts"))
    ap.add_argument("--seq-len", type=int, default=6)
    ap.add_argument("--embed-dim", type=int, default=16)
    ap.add_argument("--rnn-units", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out_dir = Path(args.out) / "lstm"
    plots_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    import tensorflow as tf

    tf.random.set_seed(int(args.seed))
    np.random.seed(int(args.seed))

    df = load_csv(Path(args.csv))
    ds = build_next_action_dataset(df, seq_len=int(args.seq_len), seed=int(args.seed))

    model = build_model_lstm(
        vocab_size=len(BEHAVIORS_8),
        seq_len=int(args.seq_len),
        embed_dim=int(args.embed_dim),
        rnn_units=int(args.rnn_units),
        num_classes=len(BEHAVIORS_8),
    )

    callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=2, restore_best_weights=True)]
    history = model.fit(
        ds.x_train,
        ds.y_train,
        validation_data=(ds.x_val, ds.y_val),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        verbose=2,
        callbacks=callbacks,
    )

    probs = model.predict(ds.x_test, batch_size=512, verbose=0)
    y_pred = probs.argmax(axis=1).astype(np.int32)

    metrics = {
        "accuracy": float(accuracy_score(ds.y_test, y_pred)),
        "macro_f1": float(f1_score(ds.y_test, y_pred, average="macro")),
    }

    labels = [ds.id_to_label[i] for i in range(len(BEHAVIORS_8))]
    plot_curves(history, out_path=plots_dir / "lstm_curves.png", title="lstm")
    plot_confusion(
        y_true=ds.y_test,
        y_pred=y_pred,
        labels=labels,
        out_path=plots_dir / "lstm_confusion.png",
        title="lstm",
    )

    meta = {
        "task": "next_action_prediction",
        "model_kind": "lstm",
        "label_space": BEHAVIORS_8,
        "seq_len": int(args.seq_len),
        "embed_dim": int(args.embed_dim),
        "rnn_units": int(args.rnn_units),
        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "seed": int(args.seed),
        "metrics": metrics,
        "selection_note": "Use macro_f1 when comparing models because class distribution is imbalanced.",
    }

    (out_dir / "results.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "label_map.json").write_text(json.dumps(ds.label_to_id, ensure_ascii=False, indent=2), encoding="utf-8")
    model.save(out_dir / "model_lstm.keras")

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

