"""RT 系ファイル（オンライン請求）のファイル名から、必要な情報を取り出す。

取り出すもの
    ファイル形式   : 英小文字4文字の種類（fixf など）と、その意味、拡張子
    支払機関       : 1=社保（支払基金）, 2=国保（国保連）, r=労災
    薬局のコード   : 医療機関コード（都道府県2桁 + 点数表1桁 + 機関番号7桁）
    ファイル名の月 : ファイル名の日付が属する年月（書いてあるそのまま）
    月の性質       : その月が何の月か。種類で違う（送信月 / 発行月 / 未確認）
    請求月         : レセプトを請求した月。ファイル名から決められる種類だけ入る
    診療月(見込み) : レセプトの診療月。ファイル名から決められる種類だけ入る

    ファイル名の月・請求月・診療月は別の値として持つ（同じ変数を使い回さない）。
        送信月（fixf）   : 薬局が請求を送った月。請求月 = ファイル名の月、
                           診療月 = その前月（1月なら前年の12月。月遅れ請求は中の明細で確認する）
                           ※ 一括ダウンロードの名前の14桁は、公式にはダウンロードした日時。
                             請求を確定した日はファイルの中のヘッダにある（同じ月にダウンロードする前提で読んでいる）
        発行月（fmdl, fmei, zogn, zogp, henr）
                         : 支払機関が帳票を出した月。1つのファイルにいろいろな診療月の
                           レセプトが入る（取引の記録に近い）ので、請求月も診療月も
                           ファイル名からは決めない。中の明細で決める
        未確認（それ以外）: 何の月か確かめていないので、同じく決めない

例（入力 → 出力の一部）
    RTfixf2014000000020230208165259.csv
        → fixf（確定状況）/ 国保 / コード 0140000000
          / ファイル名の月 2023-02（送信月）/ 請求月 2023-02 / 診療月 2023-01
    RTfixf1014000000020240115093000.csv
        → fixf / 社保 / ファイル名の月 2024-01（送信月）/ 請求月 2024-01 / 診療月 2023-12（年をまたぐ）
    RTzogn2014000000050608.csv
        → zogn（増減連絡）/ 国保 / ファイル名の月 2024-08（発行月）/ 請求月 なし / 診療月 なし

命名規則は rt_filename_regex.py の先頭の説明を参照。
ファイル名は rt_filename_regex.normalize() で全角・空白・拡張子の大文字をそろえてから読む。
"""
import re

from rt_filename_regex import normalize

# 種類（英小文字4文字）の意味
KINDS = {
    "fixf": "確定状況",
    "fmdl": "振込明細",
    "zogn": "増減連絡",
    "zogp": "増減連絡",
    "henr": "返戻内訳書",
    "skkg": "資格確認結果",
    "skks": "資格確認結果",
    "edbn": "枝番特定結果",
    "fmei": "振込額明細",
    "tgfp": "tgfp",          # 意味は未確認
}

PAYERS = {"1": "社保", "2": "国保", "r": "労災"}

# コードが9桁（点数表番号が抜ける）種類
NINE_DIGIT_KINDS = {"skkg", "skks", "edbn"}

# ファイル名の月が何の月か（種類ごと）。ここにない種類は「未確認」
MONTH_SENT = "送信月"        # 薬局が請求を送った月
MONTH_ISSUED = "発行月"      # 支払機関が帳票を出した月
MONTH_UNKNOWN = "未確認"
MONTH_ROLES = {
    "fixf": MONTH_SENT,
    "fmdl": MONTH_ISSUED,
    "fmei": MONTH_ISSUED,
    "zogn": MONTH_ISSUED,
    "zogp": MONTH_ISSUED,
    "henr": MONTH_ISSUED,
}

# 元号の番号 → その元号の元年の前の年（西暦 = これ + 和暦の年）
ERAS = {"4": ("平成", 1988), "5": ("令和", 2018)}

# 名前全体の形: [A/R] RT 種類4文字 支払機関 数字の並び . 拡張子
NAME = re.compile(r"""
    (?P<接頭辞>[AR]?)
    RT
    (?P<種類>[a-z]{4})
    (?P<支払機関>[12r])
    (?P<数字>[0-9]+)
    \.(?P<拡張子>[a-z0-9]+)
""", re.VERBOSE)


def previous_month(year, month):
    """1つ前の年月を返す。1月なら前年の12月。

    例: (2023, 2) → (2023, 1)、(2024, 1) → (2023, 12)
    """
    if month == 1:
        return year - 1, 12
    return year, month - 1


def receipt_months(kind, file_year, file_month):
    """ファイル名の月から (月の性質, 請求月, 診療月の見込み) を出す。

    請求月と診療月は (年, 月)。ファイル名から決められない種類は None。
    ファイル名の月そのものは変えずに、別の値として返す。

    例: ("fixf", 2024, 1) → ("送信月", (2024, 1), (2023, 12))
        ("zogn", 2024, 8) → ("発行月", None, None)
    """
    role = MONTH_ROLES.get(kind, MONTH_UNKNOWN)
    if role == MONTH_SENT:
        billing_month = (file_year, file_month)
        treatment_month = previous_month(file_year, file_month)
        return role, billing_month, treatment_month
    # 発行月・未確認: 中の明細ごとに違うので、ここでは決めない
    return role, None, None


def format_month(year_month):
    """(年, 月) を "2024-01" の形にする。None はそのまま None。"""
    if year_month is None:
        return None
    year, month = year_month
    return f"{year}-{month:02d}"


def wareki_to_year(era_digit, yy):
    """元号の番号1桁と和暦の年2桁から西暦の年を出す。例: ("5", "06") → 2024"""
    if era_digit not in ERAS:
        raise ValueError(f"知らない元号の番号です: {era_digit}")
    return ERAS[era_digit][1] + int(yy)


def read_date(kind, digits):
    """日付の数字を (年, 月, 日付の説明) にする。

    桁数で書き方が違う。
        14桁 西暦の年月日時分秒   20230208165259 → 2023年2月（送信日時）
        6桁  西暦の年月           202408         → 2024年8月（skkg, skks, edbn）
        6桁  1 + 和暦の年月5桁    150608         → 令和6年8月（社保の fmdl）
        5桁  和暦の年月           50608          → 令和6年8月
        7桁  和暦の年 + 月日      5060815        → 令和6年8月（労災の fmdl）
    """
    n = len(digits)
    if n == 14:
        return int(digits[0:4]), int(digits[4:6]), "西暦の送信日時14桁"
    if n == 6 and kind in NINE_DIGIT_KINDS:
        return int(digits[0:4]), int(digits[4:6]), "西暦の年月6桁"
    if n == 6 and digits[0] == "1":
        digits = digits[1:]          # 先頭の 1 を外すと5桁の和暦と同じ
        n = 5
    if n == 5:
        return wareki_to_year(digits[0], digits[1:3]), int(digits[3:5]), "和暦の年月5桁"
    if n == 7:
        return wareki_to_year(digits[0], digits[1:3]), int(digits[3:5]), "和暦の年月日7桁"
    raise ValueError(f"日付の桁数が想定外です: {digits}（{n}桁）")


def extract(filename):
    """ファイル名から情報を取り出して dict で返す。形が違えば ValueError。"""
    name = normalize(filename)
    m = NAME.fullmatch(name)
    if m is None:
        raise ValueError(f"RT 系ファイルの名前ではありません: {filename!r}")

    prefix, kind, payer, digits, ext = m.group("接頭辞", "種類", "支払機関", "数字", "拡張子")

    # 労災だけ先頭に A/R が付く。合っていなければ形がおかしい
    if (payer == "r") != (prefix != ""):
        raise ValueError(f"労災の接頭辞 A/R と支払機関が合いません: {filename!r}")

    # コードの桁数は支払機関と種類で決まる。残りが日付
    if payer == "r":
        code_len = 8
    elif kind in NINE_DIGIT_KINDS:
        code_len = 9
    else:
        code_len = 10
    code, date_digits = digits[:code_len], digits[code_len:]
    if len(code) < code_len or not date_digits:
        raise ValueError(f"数字の桁数が足りません: {filename!r}")

    info = {
        "ファイル名": name,
        "種類": kind,
        "種類の意味": KINDS.get(kind, "不明"),
        "拡張子": ext,
        "支払機関": PAYERS[payer],
        "コード": code,
    }

    # コードを分ける
    if code_len == 10:
        info["都道府県番号"] = code[0:2]
        info["点数表"] = code[2]          # 4 なら調剤（薬局）
        info["機関番号"] = code[3:10]
        info["薬局か"] = code[2] == "4"
    elif code_len == 9:
        info["都道府県番号"] = code[0:2]
        info["機関番号"] = code[2:9]

    file_year, file_month, how = read_date(kind, date_digits)
    if not 1 <= file_month <= 12:
        raise ValueError(f"月が 1〜12 ではありません: {filename!r}")
    role, billing_month, treatment_month = receipt_months(kind, file_year, file_month)
    info["日付の書き方"] = how
    info["ファイル名の月"] = format_month((file_year, file_month))
    info["月の性質"] = role
    info["請求月"] = format_month(billing_month)
    info["診療月(見込み)"] = format_month(treatment_month)
    return info


if __name__ == "__main__":
    names = [
        "RTfixf2014000000020230208165259.csv",       # 国保・fixf
        "RTfixf1014000000020240115093000.csv",       # 社保・1月送信 → 診療月は前年12月
        "ARTfixfr0140000020230609181251.csv",        # 労災
        "ＲＴｆｉｘｆ１０１４０００００００２０２３０２０８１７０７５４．ＣＳＶ",  # 全角・大文字の拡張子
        "RTzogn2014000000050608.csv",                # 和暦5桁（令和6年8月）。発行月 → 請求月・診療月は決めない
        "RTfmdl10140000000150608.csv",               # 社保の振込明細（1 + 和暦5桁）。発行月
        "RTskkg1014000000202501.csv",                # コード9桁・西暦6桁。月の性質は未確認
        "RTfixf3014000000020230208165259.csv",       # 支払機関が 3 → エラー
    ]
    for name in names:
        print(name)
        try:
            for key, value in extract(name).items():
                print(f"    {key}: {value}")
        except ValueError as e:
            print("    エラー:", e)
