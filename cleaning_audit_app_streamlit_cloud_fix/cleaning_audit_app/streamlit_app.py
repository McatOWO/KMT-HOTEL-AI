
import streamlit as st
from PIL import Image
import io
import base64
import time
from pathlib import Path
import streamlit.components.v1 as components

# ---------------- Page config ----------------
st.set_page_config(page_title="清掃状況 判定", layout="wide")

# ---------------- Session init (Cloud-safe) ----------------
# pred_pending: tid -> {"started": float}
if "pred_pending" not in st.session_state:
    st.session_state.pred_pending = {}

# pred_nonce: tid -> int   (IMPORTANT: dict, not int)
if "pred_nonce" not in st.session_state:
    st.session_state.pred_nonce = {}

# last prediction cache (optional, defensive)
if "pred_last" not in st.session_state:
    st.session_state.pred_last = {}

# ----------------------------------------------------------

# ---------------- Component declare ----------------
_component_path = (
    Path(__file__).parent
    / "tm_classifier_component"
)

tm_classifier = components.declare_component(
    "tm_classifier",
    path=str(_component_path)
)

# ---------------- Utils ----------------
def image_to_data_url(file):
    try:
        img = Image.open(file).convert("RGB")
    except Exception:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# ---------------- UI ----------------
st.title("清掃状況 AI 判定")

uploaded = st.file_uploader(
    "画像をアップロード（拡張子不問）",
    type=None
)

pred = None
tid = "default_task"

# ---------------- Prediction flow ----------------
if uploaded:
    data_url = image_to_data_url(uploaded)

    if data_url is None:
        pred = {"error": "画像として読み込めませんでした"}
    else:
        # init pending state per tid
        if tid not in st.session_state.pred_pending:
            st.session_state.pred_pending[tid] = {
                "started": time.time()
            }

        # init nonce per tid
        if tid not in st.session_state.pred_nonce:
            st.session_state.pred_nonce[tid] = 0

        # call component
        pred = tm_classifier(
            image_data=data_url,
            key=f"tm_{tid}_{st.session_state.pred_nonce[tid]}"
        )

        # timeout (4 seconds)
        elapsed = time.time() - st.session_state.pred_pending[tid]["started"]
        if pred is None and elapsed > 4:
            pred = {"error": "判定がタイムアウトしました（4秒）"}
            # reset state
            del st.session_state.pred_pending[tid]
            st.session_state.pred_nonce[tid] += 1

# ---------------- Result render ----------------
if pred is None:
    st.info("判定中です…")

elif isinstance(pred, dict) and pred.get("error"):
    st.error(pred["error"])

else:
    st.success(f"判定結果: {pred}")
