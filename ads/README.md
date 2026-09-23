# ads — リスティング広告運用CLI

たむらこどもクリニック 看護師募集ページ（https://tamurakodomo-kyujin.web.app/ ）の
Google 広告を CLI から操作する `gads` コマンド。

勾当台夕方内科クリニック（`koutoudai-yugata-naika-clinic/ads`）の `gads` と同じ作りで、
キャンペーンの初期構築を `config.json` から一括で行う `gads setup` を足している。

> Python 独立環境。pnpm のビルドやデプロイ（GitHub Actions）とは無関係。

## アカウント構成

| 種別 | ID | 備考 |
|------|-----|------|
| MCC（慧陽社） | `362-015-4244` | 開発者トークンの発行元。web-production と共通 |
| 広告アカウント | `853-224-9376` | たむらこどもクリニック（JPY / 日本時間）。支払い設定済み |

> 広告アカウントは MCC の画面から作ったが、**MCC の配下にはリンクされていない**（単独アカウント）。
> そのため `GOOGLE_ADS_LOGIN_CUSTOMER_ID` も MCC ではなく `8532249376` 自身にする。
> MCC の ID を入れると `User doesn't have permission to access customer` で弾かれる。

## 現在のキャンペーン

| 項目 | ID |
|------|-----|
| キャンペーン「看護師パート募集_検索」 | `24275154705` |
| 広告グループ「看護師パート_一般」 | `204061232761` |

2026-09-23 に `gads setup` で PAUSED 作成。

## セットアップ

### 1. Python 環境

```bash
cd ads
uv venv && uv pip install -e .      # または python3 -m venv .venv && .venv/bin/pip install -e .
```

### 2. 認証情報（.env）

開発者トークンと OAuth クライアントは GCP `keiyousya-sites-prod` の Secret Manager にあるので、
そこから `.env` を作る（`gcloud auth login` 済みであること）:

```bash
./scripts/pull_secrets.sh
```

続けてリフレッシュトークンを発行する:

```bash
.venv/bin/python scripts/regen_refresh_token.py   # ブラウザで承認 → .env が自動更新される
```

承認する Google アカウントは広告アカウント 853-224-9376 にアクセスできるもの（tamurakeito@keiyousya.com）を使う。
`RefreshError: invalid_grant` が出たら同じスクリプトで取り直す。

### 3. 疎通確認

```bash
.venv/bin/gads report --preset campaign --date-range LAST_7_DAYS
```

## キャンペーンの初期構築

キャンペーン・地域・除外キーワード・広告グループ・キーワード・広告文は `config.json` に書く。

```bash
.venv/bin/gads setup --dry-run   # 検証と内容表示だけ（認証不要）
.venv/bin/gads setup             # PAUSED で一括作成
```

- 全体を1リクエストで送るので、1件でも弾かれたら何も作られない
- キャンペーンは **PAUSED** で作る。管理画面で審査状況を確認してから配信を始める:
  `gads budget status --campaign-id … --state ENABLED`
- 同名キャンペーンがあると止まる（二重作成防止）
- 地域は `radius`（中心座標＋半径km）か `locations`（geo target の `canonical_name`、
  例: `Maebashi,Gunma,Japan`）で書く。ターゲティングは「所在地のみ」（関心ベースで県外に出るのを防ぐ）
- 文字数は Google 広告の数え方（全角=2）で検証する。見出しは全角15字、説明文は全角45字まで

`setup` は初回構築専用。作成後の変更は下の個別コマンドで行い、変更したら `config.json` も
合わせて直しておく（今どうなっているかの控えとして使うため）。

## 日々の操作

```bash
# レポート（表示が列落ちするので確認時は --csv 推奨）
gads report --preset campaign --date-range LAST_7_DAYS
gads report --preset keyword --csv
gads report --csv --query "SELECT search_term_view.search_term, metrics.clicks, metrics.cost_micros FROM search_term_view WHERE segments.date DURING LAST_7_DAYS ORDER BY metrics.clicks DESC"

# 予算・配信 ON/OFF
gads budget set --campaign-id … --amount 2000
gads budget status --campaign-id … --state PAUSED

# 配信エリア（クリニック中心の半径。既存の地域指定は置き換え）
gads campaign radius --campaign-id … --km 10

# 採用が決まったら / 募集締切日で自動停止
gads campaign end-date --campaign-id … --date 2027-03-31
gads campaign end-date --campaign-id … --clear

# キーワード
gads keyword list
gads keyword add --ad-group-id … --text "看護師 パート 前橋" --match PHRASE
gads keyword add --ad-group-id … --text "派遣" --negative
gads keyword pause --ad-group-id … --criterion-id …

# 広告文の追加（A/Bテスト）
gads ad create-rsa --ad-group-id … --final-url https://tamurakodomo-kyujin.web.app/ \
  --headline "…" --headline "…" --headline "…" --description "…" --description "…"

# コンバージョン（応募フォーム送信・電話タップ）
gads conversion list
gads conversion create --name "応募フォーム送信" --category SUBMIT_LEAD_FORM
gads conversion tag --conversion-id …    # サイトに貼るタグを表示
```

全コマンド共通で `--customer-id` を渡すと `.env` の既定アカウントを上書きできる。
変更系は確認プロンプトが出る（`--yes` でスキップ）。

## コンバージョン計測

| 名前 | ID | カテゴリ | 発火タイミング |
|------|-----|---------|----------------|
| 応募フォーム送信 | `7789585132` | SUBMIT_LEAD_FORM | `/api/apply` が成功したとき（`ApplyForm.astro`） |
| 電話タップ | `7789586314` | CONTACT | `tel:` リンクのタップ（`Layout.astro` で全リンクを拾う） |

- タグ ID・send_to は `src/config/ads.ts` に集約。`gads conversion tag --id …` で再確認できる
- 電話タップは「タップした」だけで、実際に通話したかは分からない。応募数の実数は応募メールで数える
- どちらも主要コンバージョン。手動CPCなので入札には影響せず、レポートの CV 列に載る

## 構成

```
ads/
├── README.md
├── config.json              # キャンペーン設定（setup の入力 / 現状の控え）
├── pyproject.toml           # 依存と gads コマンド定義
├── .env.example
├── scripts/
│   ├── pull_secrets.sh          # Secret Manager から .env を生成
│   └── regen_refresh_token.py   # リフレッシュトークン発行
└── src/gads/
    ├── client.py            # GoogleAdsClient 初期化・全角幅計算
    ├── cli.py
    └── commands/            # setup / report / budget / keyword / campaign / ad / conversion
```
