import os
import re
import uuid
from datetime import datetime, timezone
import streamlit as st

# ===== 設定（既存仕様に合わせる）=====
AUDITOR_PASSWORD = "1111"  # 要件どおり初期PW固定

TASKS = [
  {
    "id": "trash",
    "label": "ゴミ回収",
    "order": 1,
    "weight": 10,
    "advice": "ゴミ箱の底とデスク下の見落としに注意してください。"
  },
  {
    "id": "bed",
    "label": "ベッドメイク",
    "order": 2,
    "weight": 30,
    "advice": "シーツのシワを完全に伸ばし、枕のロゴの向きを揃えてください。"
  },
  {
    "id": "bath",
    "label": "バスルーム",
    "order": 3,
    "weight": 20,
    "advice": "排水溝の髪の毛、鏡の水垢（ウロコ）がないか確認してください。"
  },
  {
    "id": "sink",
    "label": "洗面台",
    "order": 4,
    "weight": 15,
    "advice": "コップの水滴を拭き取り、アメニティを既定の位置に揃えてください。"
  },
  {
    "id": "floor",
    "label": "床（掃除機）",
    "order": 5,
    "weight": 15,
    "advice": "部屋の奥から入口に向かってかけ、カーペットの目を揃えてください。"
  },
  {
    "id": "amen",
    "label": "最終確認",
    "order": 6,
    "weight": 10,
    "advice": "入口から振り返り、照明の点灯チェックと忘れ物がないか確認。"
  }
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ===== ユーティリティ（既存app.pyに合わせた形式）=====
def _now_iso():
    # Streamlit Cloudでも扱いやすいよう、UTCでISO文字列
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def build_report_text(report_id: str, room_id: str, cleaner_id: str, started_at: str, finished_at: str,
                      duration_seconds: int, total_score: int, tasks_state: dict) -> str:
    lines = []
    lines.append("CLEANING_REPORT_V1")
    lines.append(f"report_id: {report_id}")
    lines.append(f"roomId: {room_id}")
    lines.append(f"cleanerId: {cleaner_id}")
    lines.append(f"startedAt: {started_at}")
    lines.append(f"finishedAt: {finished_at}")
    lines.append(f"durationSeconds: {duration_seconds}")
    lines.append(f"totalScore: {total_score}")
    lines.append("")
    lines.append("tasks:")
    for t in sorted(TASKS, key=lambda x: x["order"]):
        tid = t["id"]
        tinfo = tasks_state.get(tid, {})
        lines.append(f"- id: {tid}")
        lines.append(f"  status: {tinfo.get('status','')}")
        lines.append(f"  score: {tinfo.get('score','')}")
        lines.append(f"  checkedAt: {tinfo.get('checkedAt','')}")
        lines.append(f"  notes: {tinfo.get('notes','')}")
    return "\n".join(lines) + "\n"

def parse_meta(text: str):
    meta = {"roomId":"", "cleanerId":"", "totalScore":"", "finishedAt":""}
    for line in text.splitlines()[:40]:
        line = line.strip()
        if line.startswith("roomId:"):
            meta["roomId"] = line.split(":",1)[1].strip()
        elif line.startswith("cleanerId:"):
            meta["cleanerId"] = line.split(":",1)[1].strip()
        elif line.startswith("totalScore:"):
            meta["totalScore"] = line.split(":",1)[1].strip()
        elif line.startswith("finishedAt:"):
            meta["finishedAt"] = line.split(":",1)[1].strip()
    return meta

def safe_filename(name: str) -> str:
    name = (name or "").strip()
    if not name.endswith(".txt"):
        name += ".txt"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)

# ===== Streamlit UI =====
st.set_page_config(page_title="AI清掃ナビゲーター", page_icon="🧹", layout="wide")

if "started_at" not in st.session_state:
    st.session_state.started_at = ""
if "start_ts" not in st.session_state:
    st.session_state.start_ts = None
if "tasks_state" not in st.session_state:
    st.session_state.tasks_state = {
        t["id"]: {"status":"pending", "score":0, "checkedAt":"", "notes":""} for t in TASKS
    }
if "auditor_ok" not in st.session_state:
    st.session_state.auditor_ok = False

tabs = st.tabs(["🧹 清掃", "🔒 監査（要パスワード）"])

# ===== 清掃タブ =====
with tabs[0]:
    st.title("AI清掃ナビゲーター（Streamlit版）")

    col_a, col_b, col_c = st.columns([1,1,1])
    with col_a:
        room_id = st.text_input("部屋ID", value=st.session_state.get("room_id","101"))
        st.session_state.room_id = room_id
    with col_b:
        cleaner_id = st.text_input("清掃者ID", value=st.session_state.get("cleaner_id",""))
        st.session_state.cleaner_id = cleaner_id
    with col_c:
        if st.session_state.start_ts is None:
            if st.button("▶ 開始", use_container_width=True):
                st.session_state.start_ts = datetime.now(timezone.utc).timestamp()
                st.session_state.started_at = _now_iso()
        else:
            if st.button("⏹ リセット", use_container_width=True):
                st.session_state.start_ts = None
                st.session_state.started_at = ""
                st.session_state.tasks_state = {
                    t["id"]: {"status":"pending", "score":0, "checkedAt":"", "notes":""} for t in TASKS
                }

    # 経過表示（自動更新はしない：必要ならブラウザ更新でOK）
    if st.session_state.start_ts is not None:
        elapsed = int(datetime.now(timezone.utc).timestamp() - st.session_state.start_ts)
        mm = elapsed // 60
        ss = elapsed % 60
        st.info(f"開始: {st.session_state.started_at} / 経過: {mm:02d}:{ss:02d}")
    else:
        st.warning("まだ開始していません。『開始』を押してください。")

    st.subheader("タスクチェック")
    total = 0
    for t in sorted(TASKS, key=lambda x: x["order"]):
        tid = t["id"]
        state = st.session_state.tasks_state[tid]

        with st.expander(f"{t['order']}. {t['label']}（配点 {t['weight']}）", expanded=(t["order"]==1)):
            st.caption(f"チェックポイント: {t['advice']}")
            status = st.radio(
                "状態",
                options=["pending","good","perfect","bad"],
                index=["pending","good","perfect","bad"].index(state.get("status","pending")),
                horizontal=True,
                key=f"status_{tid}"
            )
            notes = st.text_area("メモ（任意）", value=state.get("notes",""), key=f"notes_{tid}")

            # スコア算出：good/perfectは満点、bad/pendingは0（既存UIの意図に合わせる）
            score = t["weight"] if status in ("good","perfect") else 0
            checked_at = state.get("checkedAt","")
            if status != state.get("status"):
                checked_at = _now_iso() if status != "pending" else ""

            st.session_state.tasks_state[tid] = {
                "status": status,
                "score": score,
                "checkedAt": checked_at,
                "notes": notes
            }

            st.write(f"このタスクのスコア: **{score}**")

        total += st.session_state.tasks_state[tid]["score"]

    st.metric("合計スコア", total)

    st.divider()
    st.subheader("完了 → レポート出力")

    if st.session_state.start_ts is None:
        st.write("開始していないため、完了できません。")
    else:
        if st.button("✅ 完了してレポート生成", type="primary"):
            report_id = uuid.uuid4().hex[:12]
            finished_at = _now_iso()
            duration_seconds = int(datetime.now(timezone.utc).timestamp() - st.session_state.start_ts)

            text = build_report_text(
                report_id=report_id,
                room_id=st.session_state.get("room_id",""),
                cleaner_id=st.session_state.get("cleaner_id",""),
                started_at=st.session_state.started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                total_score=total,
                tasks_state=st.session_state.tasks_state
            )

            filename = safe_filename(f"cleaning_report_{report_id}.txt")
            path = os.path.join(REPORTS_DIR, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

            st.success(f"保存しました: {filename}")
            st.download_button(
                "⬇ レポートをダウンロード",
                data=text.encode("utf-8"),
                file_name=filename,
                mime="text/plain"
            )

# ===== 監査タブ =====
with tabs[1]:
    st.title("監査モード")

    if not st.session_state.auditor_ok:
        pw = st.text_input("パスワード", type="password")
        if st.button("ログイン"):
            if (pw or "").strip() == AUDITOR_PASSWORD:
                st.session_state.auditor_ok = True
                st.success("ログインしました。")
            else:
                st.error("パスワードが違います。")
        st.caption("初期パスワード: 1111")
    else:
        col_l, col_r = st.columns([3,1])
        with col_r:
            if st.button("ログアウト"):
                st.session_state.auditor_ok = False
                st.experimental_rerun()

        files = [fn for fn in sorted(os.listdir(REPORTS_DIR), reverse=True) if fn.endswith(".txt")]

        if not files:
            st.info("まだレポートがありません。清掃タブで生成してください。")
        else:
            selected = st.selectbox("レポートを選択", options=files)
            path = os.path.join(REPORTS_DIR, selected)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

            meta = parse_meta(text)
            st.write("### メタ情報")
            st.json(meta, expanded=False)

            st.write("### 本文")
            st.code(text, language="text")

            st.download_button(
                "⬇ このレポートをダウンロード",
                data=text.encode("utf-8"),
                file_name=selected,
                mime="text/plain"
            )
