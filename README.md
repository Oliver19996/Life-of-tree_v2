# Tree of Life（TOF）MVP

要件定義書 v0.4.3（未来の生命体UI）に基づく Web アプリです。正式なサービス名・ロゴ・ドメインは未決のため、画面上は作業名 Tree of Life を使います。

## 起動

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

ブラウザで http://127.0.0.1:8000 を開き、開発用デモログインで始めます。

環境変数はプロジェクト直下の `.env` に置きます（Git管理外）。ひな形は `.env.example` です。`IMAGE_API_KEY` 未設定時は SVG が正式な木です。

```bash
cp .env.example .env
# IMAGE_API_KEY や Google の値を .env に記入
uvicorn app.main:app --reload --port 8000
```

管理者にするには、デモログインのメールを `something@local.test` にしてください。

## テスト

```bash
pytest -q
```

## 正本

`docs/要件定義書_v0.4.3.md`
