from __future__ import annotations

GRAINS = [
    {"id": "greenwood", "ja": "青木", "en": "Greenwood", "hint": "まだ割れていない"},
    {"id": "wedge", "ja": "楔", "en": "Wedge", "hint": "割れ目を入れる"},
    {"id": "sap", "ja": "樹液", "en": "Sap", "hint": "只中"},
    {"id": "ring", "ja": "年輪", "en": "Ring", "hint": "一区切りのあと"},
    {"id": "graft", "ja": "接ぎ", "en": "Graft", "hint": "次の株へ渡す"},
]

LIMBS = [
    {
        "id": "work",
        "ja": "仕事と天職",
        "en": "Work",
        "boughs": [
            "初職・インターン",
            "業種スイッチ",
            "昇進と管理職",
            "燃え尽き",
            "解雇・再編",
            "独立・フリー",
            "育休・病休からの復帰",
            "ハラスメントと毒性職場",
            "引退と第二の仕事",
            "複業・ポートフォリオ",
        ],
    },
    {
        "id": "money",
        "ja": "金と生存",
        "en": "Money",
        "boughs": [
            "借金と再生",
            "初めての投資",
            "相続",
            "住宅ローン",
            "収入の急落",
            "副収入",
            "離婚の金",
            "税務・調査",
            "仕送りと扶養",
            "早期リタイアの試み",
        ],
    },
    {
        "id": "home",
        "ja": "住まいと土地",
        "en": "Place",
        "boughs": [
            "初めての一人暮らし",
            "買うか借りるか",
            "都会と地方",
            "シェアと同居",
            "災害後の再建",
            "家主との対立",
            "隣人・町内",
            "移動しながら住む",
            "実家・空き家",
            "地元を出る",
        ],
    },
    {
        "id": "love",
        "ja": "恋と伴侶",
        "en": "Love",
        "boughs": [
            "初めての本気",
            "遠距離",
            "相手へのカミングアウト",
            "結婚するかどうか",
            "不貞のあと",
            "別れと離婚",
            "再婚と継家族",
            "子を持つか持たないか",
            "二人での介護",
            "伴侶を亡くす",
        ],
    },
    {
        "id": "kin",
        "ja": "血縁と家族",
        "en": "Kin",
        "boughs": [
            "絶縁と距離",
            "家族へのカミングアウト",
            "義家族",
            "兄弟での親の分担",
            "家業の承継",
            "養子・里親",
            "継家族の子",
            "家族の秘密が開く",
            "海外に家族がいる",
            "葬儀と遺産の対立",
        ],
    },
    {
        "id": "body",
        "ja": "身体と病",
        "en": "Body",
        "boughs": [
            "慢性の診断",
            "手術を受けるか",
            "妊活・生殖医療",
            "妊娠と出産",
            "障害の始まり",
            "がん治療の選択",
            "見えない痛み",
            "身体の大きな移行",
            "リハビリと回復",
            "自分の最期の備え",
        ],
    },
    {
        "id": "mind",
        "ja": "心の天候",
        "en": "Mind",
        "boughs": [
            "うつとの初遭遇",
            "不安とパニック",
            "発達の遅れてきた名前",
            "依存と回復",
            "悲嘆",
            "外傷のあと",
            "支援を受け始める",
            "薬とのつきあい",
            "ひきこもりと孤立",
            "回復のあとの生き方",
        ],
    },
    {
        "id": "child",
        "ja": "子どもと養育",
        "en": "Raising",
        "boughs": [
            "授かりを待つ",
            "新生児の一年",
            "ひとり親の開始",
            "学校を選ぶ",
            "発達と支援",
            "いじめ",
            "思春期の衝突",
            "子どもの病",
            "別居後の共同養育",
            "巣立ち",
        ],
    },
    {
        "id": "border",
        "ja": "移動と国境",
        "en": "Borders",
        "boughs": [
            "留学",
            "就労・技能の越境",
            "結婚による移動",
            "庇護と強制移動",
            "帰国子女・帰郷",
            "ことばの壁",
            "資格が通じない",
            "市民権・永住",
            "在留の切れ目",
            "国境をまたぐ子育て",
        ],
    },
    {
        "id": "learn",
        "ja": "学びと資格",
        "en": "Learning",
        "boughs": [
            "受験",
            "進学先",
            "中退と休学",
            "学び直し",
            "専門資格",
            "留学という学び",
            "落ちてからもう一度",
            "学費と奨学金",
            "社会人入学",
            "教える側に回る",
        ],
    },
    {
        "id": "care",
        "ja": "老いと介護",
        "en": "Care",
        "boughs": [
            "初めての付き添い",
            "認知の変化",
            "施設を選ぶ",
            "遠距離介護",
            "兄弟の意見が割れる",
            "仕事を辞めて看る",
            "看取り",
            "死後の事務",
            "育児と介護の同時",
            "自分の老いの備え",
        ],
    },
    {
        "id": "make",
        "ja": "創ること",
        "en": "Making",
        "boughs": [
            "副業から事業へ",
            "初めて雇う",
            "閉業と失敗",
            "資金を集める",
            "ひとりで作る",
            "店と職人の承継",
            "作品で生きる",
            "社会を変える試み",
            "共同創業の決裂",
            "拠点を移す",
        ],
    },
    {
        "id": "meaning",
        "ja": "意味と信仰",
        "en": "Meaning",
        "boughs": [
            "信仰を離れる",
            "入信・改宗",
            "聖職を辞める",
            "成功のあとの空虚",
            "実践の共同体",
            "喪失のあとの意味",
            "政治的な目覚め",
            "人生をボランティアへ",
            "巡礼と長期の引きこもり的修行",
            "価値観を次に渡す",
        ],
    },
    {
        "id": "law",
        "ja": "法と制度",
        "en": "Law",
        "boughs": [
            "初めての争いと法廷",
            "会社を法的に始める",
            "被害のあと",
            "親権と監護",
            "労働の争い",
            "手当・福祉の初申請",
            "戸籍と氏名",
            "立ち退き",
            "内部告発",
            "行政の窓口を一人で通る",
        ],
    },
    {
        "id": "belong",
        "ja": "出自と所属",
        "en": "Belonging",
        "boughs": [
            "カミングアウト",
            "混血・複数のルーツ",
            "障害を名乗る",
            "階級の移動",
            "少数として働く",
            "名前と性別の公的記録",
            "ルーツへ戻る",
            "閉じた集団を出る",
            "なまりと言語のアイデンティティ",
            "血縁ではない家族",
        ],
    },
]


def catalog() -> dict:
    limbs = []
    for limb in LIMBS:
        boughs = [{"id": f"b{i+1:02d}", "ja": name} for i, name in enumerate(limb["boughs"])]
        limbs.append({"id": limb["id"], "ja": limb["ja"], "en": limb["en"], "boughs": boughs})
    return {"limbs": limbs, "grains": GRAINS}


def labels(limb_id: str, bough_id: str, grain_id: str) -> tuple[str, str, str]:
    limb = next((x for x in catalog()["limbs"] if x["id"] == limb_id), None)
    if not limb:
        return limb_id, bough_id, grain_id
    bough = next((x for x in limb["boughs"] if x["id"] == bough_id), None)
    grain = next((x for x in GRAINS if x["id"] == grain_id), None)
    return limb["ja"], bough["ja"] if bough else bough_id, grain["ja"] if grain else grain_id


def compose_role_input(
    display_name: str,
    limb_id: str,
    bough_id: str,
    grain_id: str,
    blurb: str | None,
    city: str | None,
) -> str:
    limb, bough, grain = labels(limb_id, bough_id, grain_id)
    intent = {
        "greenwood": "探す側。同じ割れ目を先に生きた人を求めている。",
        "wedge": "決断の只中。楔を打ち込む人。",
        "sap": "いまその枝の樹液の中にいる。",
        "ring": "一区切りのあと。振り返れる。",
        "graft": "経験を貸す側。次の株へ接ぐ。",
    }[grain_id]
    parts = [
        "role:system_identity TOFの発見用。助言の資格者ではなく、この木目を生きている人。",
        f"role:person {display_name}",
        f"role:tree 大枝={limb} 枝脈={bough} 木目={grain}",
        f"role:grain_intent {intent}",
    ]
    if blurb:
        parts.append(f"role:optional_blurb {blurb.strip()[:140]}")
    if city:
        parts.append(f"role:place {city.strip()[:40]}")
    return "\n".join(parts)
