"""医薬品名を部品に分けるパーサー。

使い方:
    from drug_name_regex import Drug, parse_drug

    d = Drug("アムロジピンOD錠2.5mg「トーワ」")
    d.name, d.modifier, d.dosage_form, d.strength, d.unit, d.maker
    # ('アムロジピン', 'OD', '錠', '2.5', 'mg', 'トーワ')

名前は3種類ある:
    name        表記どおりの名前（空白もそのまま。屋号なしは R、CR なども名前に残す）
    group_name  グループ化用の正規化名（空白を除去。屋号ありは塩の表記を統一）
    base_name   塩を除いた名前（塩違いもまとめたいとき用）

    Drug("バルプロ酸ナトリウムSR錠200mg「アメル」")
        name='バルプロ酸ナトリウム'  group_name='バルプロ酸Na'  base_name='バルプロ酸'
    Drug("デパケンR錠200mg")
        name='デパケンR'  group_name='デパケンR'  base_name='デパケンR'

    parse_drug("デエビゴ錠2.5mg")   # 同じ内容を辞書で返す

処理の流れ（1つの巨大な正規表現にせず、外側から順にはがす）:
    1. 表記ゆれの統一（全角英数・全角かっこ → 半角、µ → μ）
    2. 先頭の ★ をはがす
    3. 末尾の [2.5g] などの包装表記をはがす
    4. 「屋号」と、その後ろの補足をはがす
    5. 残った本体を、漢方用 → 一般用 の順にパターンにかける
    6. どれにも合わなければ kind="その他" として名前だけ入れる
"""
import re
import unicodedata

# ---------------------------------------------------------------- 部品の辞書
# 剤形。増やすときはここに足す（長い順に自動で並べ替える）。
DOSAGE_FORMS = [
    # 内服（固形）
    "錠", "錠剤", "糖衣錠", "徐放錠", "腸溶錠", "舌下錠", "チュアブル錠",
    "口腔内崩壊錠", "カプセル", "粒状カプセル", "ザイディス", "フィルム",
    "細粒", "顆粒", "散", "ドライシロップ",
    # 内服（液）
    "内用液", "内用液分包", "シロップ",
    # 外用
    "軟膏", "口腔用軟膏", "クリーム", "ゲル", "ローション", "テープ", "パップ",
    "サポ", "坐剤", "点眼液", "懸濁性点眼液", "点鼻液", "うがい液",
    # 注射
    "注", "注射液", "注シリンジ", "注キット",
]

# 剤形の直前に付く修飾（放出制御・口腔内崩壊など）。
MODIFIERS = ["OD", "RPD", "SR", "CR", "LA", "LX", "TR", "ER", "XR", "R", "L", "D"]

# 屋号なし（主に先発品）でも名前から切り離す修飾。
# ここにないもの（R、D、CR、SR、LX など）は販売名の一部として名前に残す。
BRAND_SPLIT_MODIFIERS = ["OD"]

# 単位。
UNITS = ["mg/mL", "mg", "μg", "mL", "ml", "g", "%", "単位"]

# 塩。屋号つき（一般名）の名前の末尾から取り出す。
SALTS = [
    "塩酸塩", "硫酸塩", "酒石酸塩", "クエン酸塩", "マレイン酸塩", "フマル酸塩",
    "メシル酸塩", "ベシル酸塩", "臭化水素酸塩", "コハク酸塩", "リン酸塩", "酢酸塩",
    "ナトリウム", "カリウム", "カルシウム", "Na", "K", "Ca", "水和物",
]
# 塩の表記ゆれの統一先。
SALT_ALIASES = {"ナトリウム": "Na", "カリウム": "K", "カルシウム": "Ca"}

# 漢方エキス製剤のメーカー名（名前の先頭に付く）。
KAMPO_MAKERS = ["ツムラ", "クラシエ", "オースギ", "ジュンコウ", "コタロー", "三和"]


def _alt(words):
    """語のリストを「長い順の a|b|c」にする（長い語を先に試すため）。"""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


NUM = r"\d+(?:\.\d+)?"

# ---------------------------------------------------------------- パターン
STAR = re.compile(r"^★\s*")
PACKAGE = re.compile(r"\s*\[([^\]]*)\]\s*$")
MAKER = re.compile(r"^(?P<head>.*?)「(?P<maker>[^」]+)」\s*(?P<tail>.*)$")

KAMPO = re.compile(
    rf"""
    (?P<maker>{_alt(KAMPO_MAKERS)})\s*   # メーカー名
    (?P<name>.+?)                        # 処方名
    (?:FC)?
    (?P<form>エキス(?:顆粒|細粒|錠|G))    # 剤形
    (?:\s*\(?医療用\)?)?
    (?:\s+(?P<note>.+))?
    """,
    re.VERBOSE,
)

MAIN = re.compile(
    rf"""
    (?P<name>.+?)                                        # 名前（できるだけ短く）
    (?:(?P<pre_strength>{NUM})(?P<pre_unit>{_alt(UNITS)}))?  # 「25mg錠」型の規格
    (?P<combo>配合)?                                     # 配合剤
    (?P<modifier>{_alt(MODIFIERS)})?                     # OD、SR など
    (?P<form>徐放[A-Z]錠|{_alt(DOSAGE_FORMS)})            # 剤形（「徐放U錠」「徐放B錠」も剤形として受ける）
    (?P<suffix>[A-Z]+(?:\d+(?![\d.]|{_alt(UNITS)}))?)?   # 「錠ULD」「配合錠HD」「カプセルB50」の添字（後ろに単位が続く数字は規格なので含めない）
    (?:\(?(?P<strength>{NUM})(?P<unit>{_alt(UNITS)})?\)?)?   # 規格と単位（かっこ付きも可）
    (?:\s+(?P<note>.+))?                                 # 空白の後ろの補足
    """,
    re.VERBOSE,
)

SALT = re.compile(rf"^(?P<base>.+?)(?P<salt>(?:{_alt(SALTS)})+)$")
ONE_SALT = re.compile(_alt(SALTS))
NOTE_STRENGTH = re.compile(rf"^(?P<strength>{NUM})(?P<unit>{_alt(UNITS)})$")

FIELDS = [
    "raw", "kind", "starred", "name", "group_name", "base_name", "salt", "combo", "modifier",
    "dosage_form", "form_suffix", "strength", "unit", "maker", "note", "package",
]


# ---------------------------------------------------------------- 本体
def parse_drug(raw):
    """医薬品名を部品に分けて辞書で返す。必ず辞書を返す（None にはならない）。

    kind: "屋号あり" / "屋号なし" / "漢方" / "その他"（どのパターンにも合わなかった）
    """
    r = dict.fromkeys(FIELDS)
    r["raw"] = raw
    r["combo"] = False

    text = unicodedata.normalize("NFKC", raw).strip()

    r["starred"] = bool(STAR.match(text))
    text = STAR.sub("", text)

    m = PACKAGE.search(text)
    if m:
        r["package"] = m.group(1)
        text = text[: m.start()]

    tail = ""
    m = MAKER.match(text)
    if m:
        text, r["maker"], tail = m.group("head").strip(), m.group("maker"), m.group("tail").strip()

    # --- 漢方
    m = KAMPO.fullmatch(text)
    if m and r["maker"] is None:
        r["kind"] = "漢方"
        r["maker"] = m.group("maker")
        r["name"] = m.group("name").strip()
        r["group_name"] = r["base_name"] = _nospace(r["name"])
        r["dosage_form"] = m.group("form")
        r["note"] = _join(m.group("note"), tail)
        return r

    # --- 一般
    m = MAIN.fullmatch(text)
    if m is None:
        r["kind"] = "その他"
        r["name"] = text
        r["group_name"] = r["base_name"] = _nospace(text)
        r["note"] = tail or None
        return r

    r["kind"] = "屋号あり" if r["maker"] else "屋号なし"
    r["name"] = m.group("name").strip().rstrip("・")   # 「ピタバスタチンCa・OD錠」の中点を落とす
    r["combo"] = m.group("combo") is not None
    r["modifier"] = m.group("modifier")
    # 屋号なしは表記どおりにする: R、CR などは販売名の一部として名前に戻す
    if (r["maker"] is None and r["modifier"] and not r["combo"]
            and r["modifier"] not in BRAND_SPLIT_MODIFIERS):
        r["name"] += r["modifier"]
        r["modifier"] = None
    r["group_name"] = r["base_name"] = _nospace(r["name"])
    r["dosage_form"] = m.group("form")
    r["form_suffix"] = m.group("suffix")
    r["strength"] = m.group("pre_strength") or m.group("strength")
    r["unit"] = m.group("pre_unit") or m.group("unit")
    note = _join(m.group("note"), tail)

    # 「レキソタン錠1 1mg」「フォリアミン錠 5mg」型: 単位が補足側にあれば、そちらを規格にする
    if r["unit"] is None and note:
        n = NOTE_STRENGTH.match(note)
        if n:
            r["strength"], r["unit"], note = n.group("strength"), n.group("unit"), None
    r["note"] = note

    # 塩は、屋号つき（一般名）のときだけ末尾から取り出し、表記を統一する
    if r["maker"]:
        s = SALT.match(r["group_name"])
        if s:
            r["base_name"] = s.group("base")
            parts = ONE_SALT.findall(s.group("salt"))
            r["salt"] = "".join(SALT_ALIASES.get(p, p) for p in parts)
            r["group_name"] = r["base_name"] + r["salt"]
    return r


def _nospace(text):
    """空白（全角も含む）をすべて取り除く。"""
    return re.sub(r"\s+", "", text)


def _join(a, b):
    """補足の文字列2つをつなぐ。両方なければ None。"""
    parts = [p for p in (a, b) if p]
    return " ".join(parts) if parts else None


class Drug:
    """医薬品名1件。Drug("名前") で作ると、部品が属性に入る。"""

    def __init__(self, raw):
        parts = parse_drug(raw)
        self.raw = parts["raw"]                  # 元の文字列
        self.kind = parts["kind"]                # 屋号あり / 屋号なし / 漢方 / その他
        self.starred = parts["starred"]          # 先頭に ★ があったか
        self.name = parts["name"]                # 名前（表記どおり）
        self.group_name = parts["group_name"]    # グループ化用の正規化名（空白除去、塩の表記統一）
        self.base_name = parts["base_name"]      # 塩を除いた名前
        self.salt = parts["salt"]                # 塩（Na などに統一）
        self.combo = parts["combo"]              # 配合剤か
        self.modifier = parts["modifier"]        # OD、SR など
        self.dosage_form = parts["dosage_form"]  # 剤形
        self.form_suffix = parts["form_suffix"]  # 剤形の後ろの添字（ULD、B50）
        self.strength = parts["strength"]        # 規格（文字列）
        self.unit = parts["unit"]                # 単位
        self.maker = parts["maker"]              # 屋号（漢方はメーカー名）
        self.note = parts["note"]                # 補足
        self.package = parts["package"]          # [ ] の中の包装表記

    @property
    def parsed(self):
        """どれかのパターンに合ったか。"""
        return self.kind != "その他"

    def __repr__(self):
        shown = [f"{k}={getattr(self, k)!r}" for k in FIELDS[3:] if getattr(self, k) not in (None, False)]
        return f"Drug[{self.kind}]({', '.join(shown)})"


if __name__ == "__main__":
    samples = [
        "アムロジピン錠5mg「サワイ」",
        "アムロジピンOD錠2.5mg「トーワ」",
        "ロキソプロフェンNa錠60mg「トーワ」",
        "デエビゴ錠2.5mg",
        "デパケンR錠200mg",
        "バルプロ酸ナトリウムSR錠200mg「アメル」",
        "セフカペン ピボキシル塩酸塩錠100mg「SW」",
        "セロクエル25mg錠",
        "レキソタン錠1 1mg",
        "ヒルナミン錠（25mg）",
        "ツムラ抑肝散エキス顆粒(医療用) [2.5g]",
        "リスペリドン内用液1mg/mL「杏林」 0.1% [0.5mL]",
        "★ロキソニンS",
    ]
    for s in samples:
        print(Drug(s))
