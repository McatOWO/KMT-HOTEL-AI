// ===== 設定: スライドに基づくタスク順序とチェックポイント =====
// order: 清掃ルート順序
// weight: スコア配分（重要度）
// advice: ベテランのノウハウ（チェックポイント）
const TASKS = [
  { id:"trash", label:"ゴミ回収",     order:1, weight:10, pin:{left:83, top:46}, advice:"ゴミ箱の底とデスク下の見落としに注意してください。" },
  { id:"bed",   label:"ベッドメイク", order:2, weight:30, pin:{left:45, top:28}, advice:"シーツのシワを完全に伸ばし、枕のロゴの向きを揃えてください。" },
  { id:"bath",  label:"バスルーム",   order:3, weight:20, pin:{left:70, top:22}, advice:"排水溝の髪の毛、鏡の水垢（ウロコ）がないか確認してください。" },
  { id:"sink",  label:"洗面台",       order:4, weight:15, pin:{left:80, top:22}, advice:"コップの水滴を拭き取り、アメニティを既定の位置に揃えてください。" },
  { id:"floor", label:"床（掃除機）", order:5, weight:15, pin:{left:52, top:50}, advice:"部屋の奥から入口に向かってかけ、カーペットの目を揃えてください。" },
  { id:"amen",  label:"最終確認",     order:6, weight:10, pin:{left:60, top:70}, advice:"入口から振り返り、照明の点灯チェックと忘れ物がないか確認。" },
];

const OK_CLASSES = new Set(["perfect", "good"]);
const FIX_CLASS = "bad";
const STORAGE_KEY = "ai_clean_nav_v2";

// モデル設定
const MODEL_URL = "/static/model/model.json";
const METADATA_URL = "/static/model/metadata.json";

// ===== 状態管理 =====
let model = null;
let timerInterval = null;
let state = {
  startTime: null,    // 業務開始時刻
  elapsedSeconds: 0,  // 経過秒数
  tasks: {},          // { [taskId]: { status, score, note, ... } }
  activeTaskId: null  // 現在ナビゲーション中のタスクID
};

// ===== 初期化 =====
window.addEventListener("DOMContentLoaded", async () => {
  loadState();
  
  // 初回起動時のみ初期化
  if (!state.startTime) {
    state.startTime = Date.now();
    TASKS.forEach(t => {
      state.tasks[t.id] = { status: "pending", score: 0 };
    });
    // 最初のタスクをアクティブに
    updateActiveTask();
  }

  startTimer();
  renderApp(); // 全体描画
  
  // イベントリスナー
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modalBackdrop").addEventListener("click", closeModal);
  document.getElementById("resetBtn").addEventListener("click", resetAll);
  document.getElementById("finishBtn").addEventListener("click", finishJob);

  await loadModelSafely();
});

// ===== 描画・更新ループ =====
function renderApp() {
  updateActiveTask();
  renderHUD();
  renderMap();
  renderCurrentTaskCard();
  renderTaskList();
  updateProgressButton();
}

// 1. HUD (スコアと時間)
function renderHUD() {
  // スコア計算: (各タスクのscore * weight) の合計 / weight合計
  let totalScore = 0;
  let totalWeight = 0;
  TASKS.forEach(t => {
    const s = state.tasks[t.id];
    totalScore += (s.score || 0) * t.weight;
    totalWeight += t.weight;
  });
  const finalPercent = Math.round(totalScore / totalWeight); // 100点満点換算
  
  document.getElementById("totalScore").textContent = `${finalPercent}`;
  document.getElementById("totalScore").style.color = finalPercent < 60 ? "#ef4444" : "#10b981";
}

// 2. マップとルート案内
function renderMap() {
  const pinsContainer = document.getElementById("mapPins");
  pinsContainer.innerHTML = "";
  
  // ピン描画
  TASKS.forEach(t => {
    const s = state.tasks[t.id];
    const pin = document.createElement("div");
    
    // クラス切り替え
    let statusClass = "pin--pending";
    if (s.status === "ok") statusClass = "pin--ok";
    if (s.status === "fix") statusClass = "pin--fix";
    if (t.id === state.activeTaskId && s.status === "pending") statusClass = "pin--active";

    pin.className = `pin ${statusClass}`;
    pin.style.left = t.pin.left + "%";
    pin.style.top = t.pin.top + "%";
    pin.textContent = t.order; // 番号を表示
    pin.onclick = () => openCheckModal(t.id);
    
    pinsContainer.appendChild(pin);
  });

  // ルート線描画 (SVG)
  const svg = document.getElementById("routeLines");
  svg.innerHTML = "";
  
  // タスク順に線を引く
  // 完了したルートは緑、次は青、未定はグレー
  for (let i = 0; i < TASKS.length - 1; i++) {
    const curr = TASKS[i];
    const next = TASKS[i+1];
    
    const x1 = curr.pin.left;
    const y1 = curr.pin.top;
    const x2 = next.pin.left;
    const y2 = next.pin.top;
    
    // 線の色判定
    let color = "rgba(148, 163, 184, 0.3)"; // default gray
    if (state.tasks[curr.id].status === "ok") {
      color = "rgba(16, 185, 129, 0.6)"; // done
      if (state.tasks[next.id].status === "pending") {
        color = "rgba(59, 130, 246, 0.8)"; // active path
      }
    }

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x1 + "%");
    line.setAttribute("y1", y1 + "%");
    line.setAttribute("x2", x2 + "%");
    line.setAttribute("y2", y2 + "%");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-dasharray", "5,5");
    svg.appendChild(line);
  }
}

// 3. ナビゲーションテキスト更新
function updateActiveTask() {
  // まだ終わっていない一番若い番号のタスクを探す
  const nextTask = TASKS.find(t => state.tasks[t.id].status !== "ok");
  state.activeTaskId = nextTask ? nextTask.id : null;

  const navText = document.getElementById("navText");
  if (!nextTask) {
    navText.textContent = "全ての清掃が完了しました！報告してください。";
    document.getElementById("currentTaskPanel").style.display = "none";
  } else {
    navText.textContent = `NEXT: ${nextTask.label} へ移動してください`;
    document.getElementById("currentTaskPanel").style.display = "block";
  }
}

function renderCurrentTaskCard() {
  if (!state.activeTaskId) return;
  const t = TASKS.find(x => x.id === state.activeTaskId);
  const container = document.getElementById("activeTaskCard");
  
  container.innerHTML = `
    <div class="card" style="border-left: 4px solid var(--accent);">
      <h3>No.${t.order} ${t.label}</h3>
      <p style="color:var(--text-muted); font-size:14px;">💡 <strong>ベテランのポイント:</strong><br>${t.advice}</p>
      <button class="btn btn--primary" onclick="openCheckModal('${t.id}')">カメラ起動 / チェック開始</button>
    </div>
  `;
}

// 4. リスト描画
function renderTaskList() {
  const root = document.getElementById("taskList");
  root.innerHTML = "";
  TASKS.forEach(t => {
    const s = state.tasks[t.id];
    const div = document.createElement("div");
    div.className = "card";
    div.style.padding = "8px";
    div.style.marginBottom = "5px";
    div.style.display = "flex";
    div.style.justifyContent = "space-between";
    div.style.alignItems = "center";
    
    let icon = "⚪";
    if (s.status === "ok") icon = "✅";
    if (s.status === "fix") icon = "❗";
    
    div.innerHTML = `
      <span>${icon} ${t.label}</span>
      <span style="font-size:12px; color:#aaa;">スコア: ${s.score}点</span>
    `;
    div.onclick = () => openCheckModal(t.id);
    root.appendChild(div);
  });
}

function updateProgressButton() {
  const allDone = TASKS.every(t => state.tasks[t.id].status === "ok");
  document.getElementById("finishBtn").disabled = !allDone;
}

// ===== タイマー機能 =====
function startTimer() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    state.elapsedSeconds++;
    const min = Math.floor(state.elapsedSeconds / 60).toString().padStart(2, "0");
    const sec = (state.elapsedSeconds % 60).toString().padStart(2, "0");
    document.getElementById("timerDisplay").textContent = `${min}:${sec}`;
    saveState();
  }, 1000);
}

// ===== モーダル・AI判定 =====
function openCheckModal(taskId) {
  const t = TASKS.find(x => x.id === taskId);
  const s = state.tasks[taskId];
  
  document.getElementById("modalTitle").textContent = `Check: ${t.label}`;
  const body = document.getElementById("modalBody");
  
  body.innerHTML = `
    <div class="card">
       <p class="hint">${t.advice}</p>
       <div class="preview">
         <img id="previewImg" src="${placeholderSvg()}" />
       </div>
       <div id="predResult" style="margin-bottom:10px; font-weight:bold;"></div>
       
       <label class="btn btn--primary" for="camInput">📸 撮影して判定</label>
       <input id="camInput" type="file" accept="image/*" capture="environment" class="sr-only" />
       
       <div id="fixInputArea" style="display:none; margin-top:10px;">
         <input id="fixNote" type="text" class="input" placeholder="修正内容を入力" style="width:100%; padding:10px; margin-bottom:5px;" value="${s.note||""}" />
         <button id="saveFixBtn" class="btn btn--danger">要修正として記録</button>
       </div>
    </div>
  `;
  
  const imgEl = document.getElementById("previewImg");
  const inputEl = document.getElementById("camInput");
  
  inputEl.onchange = async (e) => {
    if(!e.target.files[0]) return;
    const url = await fileToDataURL(e.target.files[0]);
    imgEl.src = url;
    await new Promise(r => imgEl.onload = r);
    await runPrediction(taskId, imgEl);
  };
  
  // 修正保存ボタン
  document.getElementById("saveFixBtn").onclick = () => {
    const note = document.getElementById("fixNote").value;
    state.tasks[taskId] = { ...state.tasks[taskId], status: "fix", score: 40, note: note }; // badは40点固定
    saveState();
    closeModal();
    renderApp();
  };

  openModal();
}

async function runPrediction(taskId, imgEl) {
  const resDiv = document.getElementById("predResult");
  resDiv.textContent = "AI判定中...";
  
  if (!model) {
    resDiv.textContent = "モデル読込エラー";
    return;
  }
  
  const preds = await model.predict(imgEl);
  // 最高確率のクラス
  const best = preds.reduce((a,b)=>a.probability>b.probability?a:b);
  
  // スコア算出ロジック: 確率 * 100 (ただしperfectは100, goodは80, badは40等の重みづけも可)
  // ここでは単純に確率ベースだが、クラスに応じて補正する
  let score = Math.round(best.probability * 100);
  let status = "pending";
  
  if (OK_CLASSES.has(best.className)) {
    status = "ok";
    if (best.className === "good") score = Math.min(score, 85); // goodはMAX85点など
    resDiv.innerHTML = `<span style="color:var(--success)">判定: ${best.className} (スコア:${score})</span>`;
    
    // 状態保存
    state.tasks[taskId] = { status: "ok", score: score, note: "" };
    saveState();
    
    // 1秒後に閉じる
    setTimeout(() => {
      closeModal();
      renderApp();
    }, 1000);
    
  } else {
    // Bad
    status = "fix";
    score = 30; // Badは低得点
    resDiv.innerHTML = `<span style="color:var(--danger)">判定: ${best.className} (要修正)</span><br>修正指示を入力してください。`;
    document.getElementById("fixInputArea").style.display = "block";
  }
}

// ===== 業務完了・レポート =====
async function finishJob() {
  const report = {
    roomId: "101",
    cleanerId: "USER_01",
    startedAt: new Date(state.startTime).toISOString(),
    finishedAt: new Date().toISOString(),
    durationSeconds: state.elapsedSeconds,
    totalScore: document.getElementById("totalScore").textContent,
    tasks: state.tasks
  };
  
  const modal = document.getElementById("reportModal");
  document.getElementById("reportData").textContent = JSON.stringify(report, null, 2);
  modal.setAttribute("aria-hidden", "false");
  modal.style.display = "flex";
  
  // ===== サーバーへ送信しつつ、テキストファイルを生成 =====
  try {
    const resp = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
    });
    const result = await resp.json();

    // 送信結果 + ダウンロードURLをレポート欄に追記
    report._server = result;
    document.getElementById("reportData").textContent = JSON.stringify(report, null, 2);

    // ダウンロードリンクを追加（既にあれば作り直し）
    let dl = document.getElementById("reportDownloadLink");
    if (!dl) {
      dl = document.createElement("a");
      dl.id = "reportDownloadLink";
      dl.className = "btn btn--primary";
      dl.style.marginTop = "12px";
      dl.textContent = "テキストレポートをダウンロード";
      document.querySelector("#reportModal .modal__body").appendChild(dl);
    }
    dl.href = result.download_url;
  } catch (e) {
    report._server = { ok:false, error: String(e) };
    document.getElementById("reportData").textContent = JSON.stringify(report, null, 2);
  }
  // ローカルデータクリア
  localStorage.removeItem(STORAGE_KEY);
}

// ===== ユーティリティ =====
function openModal() {
  const m = document.getElementById("modal");
  m.setAttribute("aria-hidden", "false");
  m.style.display = "flex";
}
function closeModal() {
  const m = document.getElementById("modal");
  m.setAttribute("aria-hidden", "true");
  m.style.display = "none";
}
function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) state = JSON.parse(raw);
}
function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
function resetAll() {
  if(!confirm("リセットしますか？")) return;
  localStorage.removeItem(STORAGE_KEY);
  location.reload();
}
async function loadModelSafely() {
  try {
    model = await tmImage.load(MODEL_URL, METADATA_URL);
  } catch(e) { console.error("Model Error", e); }
}
function fileToDataURL(file) {
  return new Promise(r => {
    const fr=new FileReader(); fr.onload=()=>r(fr.result); fr.readAsDataURL(file);
  });
}
function placeholderSvg() {
  return "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iODAiPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9IiMzMzMiLz48L3N2Zz4=";
}