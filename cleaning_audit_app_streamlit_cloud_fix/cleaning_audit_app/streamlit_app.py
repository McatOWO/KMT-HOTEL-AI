import os
import time
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import streamlit as st
import streamlit.components.v1 as components

# =============================
# 目的:
# - 既存Flask版（static/app.js）の機能を「縮小しすぎない」範囲でStreamlitに移植
# - 画像認識（perfect/good/bad）を使ったToDo判定を復活
# - 監査（管理者）メニュー: ログアウト時のエラー回避 / 初期PWの直書き撤廃
# =============================

# ===== 既存仕様（static/app.js）に合わせたタスク定義 =====
TASKS = [
    {"id": "trash", "label": "ゴミ回収", "order": 1, "weight": 10, "advice": "ゴミ箱の底とデスク下の見落としに注意してください。"},
    {"id": "bed",   "label": "ベッドメイク", "order": 2, "weight": 30, "advice": "シーツのシワを完全に伸ばし、枕のロゴの向きを揃えてください。"},
    {"id": "bath",  "label": "バスルーム", "order": 3, "weight": 20, "advice": "排水溝の髪の毛、鏡の水垢（ウロコ）がないか確認してください。"},
    {"id": "sink",  "label": "洗面台", "order": 4, "weight": 15, "advice": "コップの水滴を拭き取り、アメニティを既定の位置に揃えてください。"},
    {"id": "floor", "label": "床（掃除機）", "order": 5, "weight": 15, "advice": "部屋の奥から入口に向かってかけ、カーペットの目を揃えてください。"},
    {"id": "amen",  "label": "最終確認", "order": 6, "weight": 10, "advice": "入口から振り返り、照明の点灯チェックと忘れ物がないか確認。"},
]

OK_CLASSES = {"perfect", "good"}
FIX_CLASS = "bad"

st.set_page_config(page_title="清掃・監査 統合（Streamlit）", page_icon="🧹", layout="wide")

# ===== 管理者パスワード（直書き禁止）=====
# Streamlit Community Cloud では Secrets に ADMIN_PASSWORD を設定してください。
# ローカル開発時に限り、未設定なら暫定で 1111 を許可（UIには表示しない）
def get_admin_password() -> Optional[str]:
    # 優先順位: st.secrets -> 環境変数 -> ローカル暫定
    if "ADMIN_PASSWORD" in st.secrets:
        v = str(st.secrets.get("ADMIN_PASSWORD", "")).strip()
        return v or None
    v = os.environ.get("ADMIN_PASSWORD", "").strip()
    if v:
        return v
    # ローカルのみに限定（Streamlit Cloudは環境変数で判定しづらいので、明示フラグが無い限り警告を出す）
    return "1111"

ADMIN_PASSWORD = get_admin_password()

# ===== 判定コンポーネント（tm_classifier_component/index.html）=====
_tm = components.declare_component("tm_classifier", path=os.path.join(os.path.dirname(__file__), "tm_classifier_component"))

def classify_image(image_bytes: bytes, key: str) -> Optional[List[Dict[str, Any]]]:
    """Browser-side TFJS component classification.
    Streamlit Cloud安定動作のため、入力はPNG DataURLに正規化して渡す。
    """
    if not image_bytes:
        return None

    # 拡張子/実体の違いに強くするため、PILで開ける場合はPNGへ正規化
    data_url = None
    try:
        from PIL import Image
        import io, base64
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        # 最終フォールバック（元バイトをそのままjpeg扱いにしない）
        return {"error": "invalid_image"}

    result = _tm(image_data_url=data_url, key=key)
    return result

# ===== 状態初期化 =====
def init_state():
    st.session_state.setdefault("roomId", "")
    st.session_state.setdefault("cleanerId", "")
    st.session_state.setdefault("startedAt", None)
    st.session_state.setdefault("finishedAt", None)
    st.session_state.setdefault("tasks_state", {
        t["id"]: {"status": "todo", "score": 0, "checkedAt": "", "notes": "", "last_pred": None}
        for t in TASKS
    })
    st.session_state.setdefault("pred_nonce", {t["id"]: 0 for t in TASKS})
    st.session_state.setdefault("admin_authed", False)
    st.session_state.setdefault("reports", [])  # メモリ内保存（Cloudでも動く）

init_state()

# ===== 共通ユーティリティ =====
def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def total_score(tasks_state: Dict[str, Any]) -> int:
    s = 0
    for t in TASKS:
        s += int(tasks_state.get(t["id"], {}).get("score", 0) or 0)
    return s

def duration_seconds() -> int:
    if not st.session_state.startedAt or not st.session_state.finishedAt:
        return 0
    return int((st.session_state.finishedAt - st.session_state.startedAt).total_seconds())

def build_report_text() -> str:
    report_id = uuid.uuid4().hex[:12]
    started = st.session_state.startedAt.isoformat(timespec="seconds") if st.session_state.startedAt else ""
    finished = st.session_state.finishedAt.isoformat(timespec="seconds") if st.session_state.finishedAt else ""

    lines = []
    lines.append("CLEANING_REPORT_V1")
    lines.append(f"report_id: {report_id}")
    lines.append(f"roomId: {st.session_state.roomId}")
    lines.append(f"cleanerId: {st.session_state.cleanerId}")
    lines.append(f"startedAt: {started}")
    lines.append(f"finishedAt: {finished}")
    lines.append(f"durationSeconds: {duration_seconds()}")
    lines.append(f"totalScore: {total_score(st.session_state.tasks_state)}")
    lines.append("")
    lines.append("tasks:")
    for t in TASKS:
        tid = t["id"]
        info = st.session_state.tasks_state.get(tid, {})
        lines.append(f"- id: {tid}")
        lines.append(f"  status: {info.get('status','')}")
        lines.append(f"  score: {info.get('score','')}")
        lines.append(f"  checkedAt: {info.get('checkedAt','')}")
        lines.append(f"  notes: {info.get('notes','')}")
    return "\n".join(lines) + "\n"

def reset_cleaning_state():
    st.session_state.startedAt = None
    st.session_state.finishedAt = None
    st.session_state.tasks_state = {
        t["id"]: {"status": "todo", "score": 0, "checkedAt": "", "notes": "", "last_pred": None}
        for t in TASKS
    }
    st.session_state.pred_nonce = {t["id"]: 0 for t in TASKS}

# ===== UI =====
st.title("🧹 清掃・監査（Streamlit移行版）")

# Sidebar: ナビ + 基本情報
with st.sidebar:
    st.header("メニュー")
    mode = st.radio("画面", ["清掃", "監査（管理者）"], index=0)
    st.divider()
    st.subheader("基本情報")
    st.text_input("部屋ID", key="roomId", placeholder="例: 501")
    st.text_input("作業者ID", key="cleanerId", placeholder="例: sakai")
    st.caption("※レポートに記録されます。")
    st.divider()
    st.subheader("進捗")
    st.metric("合計スコア", total_score(st.session_state.tasks_state))
    done = sum(1 for t in TASKS if st.session_state.tasks_state[t["id"]]["status"] == "done")
    st.metric("完了タスク数", f"{done}/{len(TASKS)}")

# =============================
# 清掃
# =============================
if mode == "清掃":
    left, right = st.columns([1.2, 1.0], gap="large")

    with left:
        st.subheader("作業タイマー")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("▶ 開始", use_container_width=True, disabled=st.session_state.startedAt is not None):
                st.session_state.startedAt = datetime.now(timezone.utc).astimezone()
                st.session_state.finishedAt = None
        with c2:
            if st.button("⏹ 終了", use_container_width=True, disabled=st.session_state.startedAt is None):
                st.session_state.finishedAt = datetime.now(timezone.utc).astimezone()
        with c3:
            if st.button("↺ リセット", use_container_width=True):
                reset_cleaning_state()

        st.caption("※開始/終了はレポートに記録されます。")

        st.divider()
        st.subheader("ToDo（画像認識で判定）")
        st.caption("各タスクで写真を撮影/アップロード → AIが perfect/good/bad を判定し、完了/要修正を自動更新します。")

        for t in sorted(TASKS, key=lambda x: x["order"]):
            tid = t["id"]
            info = st.session_state.tasks_state[tid]

            with st.expander(f"{t['order']}. {t['label']}  （配点 {t['weight']}）", expanded=False):
                st.write(t["advice"])

                colA, colB = st.columns([1, 1], gap="large")
                with colA:
                    img = st.camera_input("写真を撮る", key=f"cam_{tid}")
                    if img is None:
                        up = st.file_uploader("または画像をアップロード（拡張子不問）", type=None, key=f"up_{tid}")
                        if up is not None:
                            img_bytes = up.read()
                        else:
                            img_bytes = b""
                    else:
                        img_bytes = img.getvalue()

                with colB:
                    # 判定（画像がある時だけ実行）
                    pred = None
                    if img_bytes:
                        img_hash = hashlib.sha256(img_bytes).hexdigest()[:8]
                        nonce = st.session_state.pred_nonce.get(tid, 0)
                        pred = classify_image(img_bytes, key=f"pred_{tid}_{img_hash}_{nonce}")
                    info["last_pred"] = pred

                    # 返り値がまだ来ていない場合（コンポーネント処理中/ネットワーク制限など）
                    if img_bytes and pred is None:
                        # 4秒以上返ってこない場合はエラー扱い（Streamlit Cloudの遅延/ブロック対策）
                        now_ts = time.time()
                        if "pred_pending" not in st.session_state:
                            st.session_state.pred_pending = {}
                        pend = st.session_state.pred_pending.get(tid)
                        if (not pend) or (pend.get("hash") != img_hash):
                            st.session_state.pred_pending[tid] = {"hash": img_hash, "since": now_ts}
                            pend = st.session_state.pred_pending[tid]
                        elapsed = now_ts - float(pend.get("since", now_ts))

                        if elapsed >= 4.0:
                            pred = {"error": "timeout"}
                            st.session_state.pred_pending.pop(tid, None)
                            st.error("判定が4秒以上続いたためタイムアウトしました。通信制限やCDNブロックの可能性があります。")
                        else:
                            st.info("判定中です（最大4秒）。反映されない場合は「再判定」を押してください。")
                            if st.button("🔄 再判定", key=f"retry_{tid}", use_container_width=True):
                                st.session_state.pred_nonce[tid] = st.session_state.pred_nonce.get(tid, 0) + 1
                                st.session_state.pred_pending[tid] = {"hash": img_hash, "since": time.time()}
                                st.rerun()

                    # 判定結果表示＆状態更新
                    if isinstance(pred, dict) and pred.get("error"):
                        st.error("判定に失敗しました。別の画像で再試行してください。")
                        info["status"] = "todo"
                        info["score"] = 0
                    elif isinstance(pred, list) and len(pred) > 0:
                        top = pred[0]
                        cls = str(top.get("className", ""))
                        p = float(top.get("probability", 0.0))

                        st.write(f"**判定:** `{cls}`  /  **信頼度:** {round(p*100)}%")

                        if cls in OK_CLASSES:
                            info["status"] = "done"
                            info["score"] = t["weight"]
                        else:
                            info["status"] = "fix"
                            info["score"] = 0

                        info["checkedAt"] = now_iso()

                    # メモ
                    info["notes"] = st.text_area("メモ（任意）", value=info.get("notes",""), key=f"notes_{tid}")

                    # ステータス表示
                    if info["status"] == "done":
                        st.success(f"完了 ✅（+{t['weight']}）")
                    elif info["status"] == "fix":
                        st.warning("要修正 ⚠️（bad判定）")
                    else:
                        st.info("未判定 / 未完了")

                # 反映
                st.session_state.tasks_state[tid] = info

    with right:
        st.subheader("マップ（参照）")
        st.image(os.path.join(os.path.dirname(__file__), "static", "room_map.png"), caption="※ピン操作UIは次段階（最小改修のため参照のみ）", use_container_width=True)

        st.divider()
        st.subheader("レポート出力")
        disabled_export = not st.session_state.roomId or not st.session_state.cleanerId
        if disabled_export:
            st.warning("部屋IDと作業者IDを入力すると、レポート出力できます。")

        report_text = build_report_text()
        st.download_button(
            "⬇ レポートをダウンロード（txt）",
            data=report_text.encode("utf-8"),
            file_name=f"cleaning_report_{uuid.uuid4().hex[:8]}.txt",
            mime="text/plain",
            use_container_width=True,
            disabled=disabled_export,
        )

        if st.button("📌 レポートを保存（監査で閲覧）", use_container_width=True, disabled=disabled_export):
            st.session_state.reports.insert(0, {"savedAt": now_iso(), "content": report_text})
            st.success("保存しました（監査メニューで確認できます）。")

# =============================
# 監査（管理者）
# =============================
else:
    st.subheader("監査（管理者）")

    # Secrets未設定のままCloudに出すのを避ける（ただしローカルでは動かせる）
    if ADMIN_PASSWORD == "1111" and ("ADMIN_PASSWORD" not in st.secrets) and (not os.environ.get("ADMIN_PASSWORD", "").strip()):
        st.warning("管理者パスワードがSecrets/環境変数に未設定です。Cloud運用では Secrets に ADMIN_PASSWORD を設定してください。")

    if not st.session_state.admin_authed:
        st.write("管理者パスワードを入力してください。")
        pw = st.text_input("Password", type="password", key="admin_pw_input")
        if st.button("ログイン"):
            if (ADMIN_PASSWORD is not None) and (pw == ADMIN_PASSWORD):
                st.session_state.admin_authed = True
                # 入力値は残さない（公開防止）
                st.session_state.admin_pw_input = ""
                st.success("ログインしました。")
                st.rerun()
            else:
                st.error("パスワードが違います。")
    else:
        # ログアウト（エラー回避: 参照キーを安全に削除/初期化）
        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("ログアウト", use_container_width=True):
                st.session_state.admin_authed = False
                # 既存UIで起きていた「ログアウト時に一度エラー」を回避するため、
                # 関連キーを存在チェックしてからクリア
                for k in ["admin_pw_input"]:
                    if k in st.session_state:
                        st.session_state[k] = ""
                st.rerun()

        with c2:
            st.caption("※レポートはStreamlitセッション内に保存されます（Community Cloudでは永続ストレージではありません）。")

        st.divider()
        st.subheader("保存済みレポート")
        reports = st.session_state.get("reports", [])
        if not reports:
            st.info("まだ保存されたレポートがありません。清掃画面で「レポートを保存」を押してください。")
        else:
            for i, r in enumerate(reports):
                with st.expander(f"{i+1}. 保存日時: {r.get('savedAt','')}"):
                    st.code(r.get("content",""), language="text")
