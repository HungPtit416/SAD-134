## ML models (RNN / LSTM / BiLSTM) — input/output rõ ràng

### Bài toán

Từ chuỗi hành vi của user theo thời gian, dự đoán **hành vi kế tiếp** (8 lớp).

### Input (đầu vào)

- File CSV: `data/data_user500.csv`
- Cột (đúng theo ảnh đề bài): `user_id`, `product_id`, `action`, `timestamp`
- Nhãn lớp (`action`) dùng **8 behaviors**:
  - `view`, `click`, `add_to_cart`, `purchase`, `search`, `browse_products`, `browse_recommended`, `checkout`

### Cách tạo dataset cho mô hình

Với mỗi user:
- Sort theo `timestamp`
- Mã hoá `action` → integer token
- Lấy cửa sổ độ dài `seq_len` làm \(X\), và action tiếp theo làm \(y\)

Split **theo user_id** (train/val/test) để tránh leakage.

### Setup môi trường

```bash
python -m venv .venv-ml
.venv-ml\\Scripts\\activate
pip install -r ml/requirements.txt
```

### Train riêng từng mô hình (3 file độc lập, không dùng code chung)

Mỗi mô hình sẽ lưu output vào `ml/artifacts/<kind>/`:

```bash
# RNN
python ml/train_rnn.py --csv data/data_user500.csv --out ml/artifacts --seq-len 6 --epochs 10

# LSTM
python ml/train_lstm.py --csv data/data_user500.csv --out ml/artifacts --seq-len 6 --epochs 10

# BiLSTM
python ml/train_bilstm.py --csv data/data_user500.csv --out ml/artifacts --seq-len 6 --epochs 10
```

### Output (đầu ra)

Với mỗi mô hình (`<kind>` = `rnn|lstm|bilstm`):
- `ml/artifacts/<kind>/model_<kind>.keras`: model đã train
- `ml/artifacts/<kind>/results.json`: metrics (Accuracy, Macro-F1) + hyperparams
- `ml/artifacts/<kind>/label_map.json`: mapping action→id
- `ml/artifacts/<kind>/plots/<kind>_curves.png`: learning curves
- `ml/artifacts/<kind>/plots/<kind>_confusion.png`: confusion matrix (normalized)

### Chọn `model_best` (đánh giá bằng lời)

- Dùng **Macro-F1** để so sánh vì dữ liệu hành vi thường **mất cân bằng lớp**.
- Model có Macro-F1 cao nhất được chọn là `model_best`.

