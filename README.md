# Tree of Life (TOF)

同じ割れ目を生きた人に会うための、無料Webアプリ。フィードはない。中央の木で大枝・枝脈・木目を選び、同じ枝の人へ手紙を送る。

## ローカル

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

http://127.0.0.1:8000

- **森に入る** — デモログイン（公開検証用）
- **メール** — SMTPが無いときは画面にマジックリンクが出る
- **Google** — `.env` に `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` と `APP_BASE_URL`

自撮りからアニメ風肖像はサーバ側で画像をポスタライズする（APIキー不要）。回数は無料2回。

## 環境変数

`.env.example` を参照。`ALLOW_DEMO_LOGIN=true` で公開デモが可能。

## スタック

Python / FastAPI / SQLite。発見は役割付きテキストのベクトル（自前埋め込み、外部LLMなし）。
