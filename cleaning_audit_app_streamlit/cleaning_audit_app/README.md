# Hotel Cleaning ToDo (Map)

## Features
- Map with pins near relevant locations.
- Click a pin to open that task UI (camera -> Teachable Machine inference).
- perfect/good => OK (pin becomes ✅)
- bad => Fix required (pin becomes ❗, note required)
- Images are NOT uploaded or stored. Only results are saved in browser localStorage.

## Setup (Windows)
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install flask
flask --app app run --debug
```

Open:
http://127.0.0.1:5000/

## Files
- static/room_map.png : room floor plan image
- static/model/ : teachable machine model files (model.json, metadata.json, weights.bin)


## Streamlit Community Cloud への移行（最小構成）

- エントリポイント: `streamlit_app.py`
- 必要ファイル: `streamlit_app.py`, `requirements.txt`

### ローカル実行
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Streamlit Cloud
1. このフォルダをGitHubにpush
2. Streamlit Community Cloudでリポジトリ選択
3. Main file path を `streamlit_app.py` に指定して Deploy
