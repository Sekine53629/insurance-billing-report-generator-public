"""RT 系ファイル（オンライン請求）のファイル名から、必要な情報を取り出す。

取り出すもの
    ファイル形式   : 英小文字4文字の種類（fixf など）と、その意味、拡張子
    支払機関       : 1=社保（支払基金）, 2=国保（国保連）, r=労災
    薬局のコード   : 医療機関コード（都道府県2桁 + 点数表1桁 + 機関番号7桁）
    送った月       : ファイル名の日付が属する年月
    前月           : 送った月の1つ前（中のデータの診療月の見込み）。1月なら前年の12月

例（入力 → 出力の一部）
    RTfixf2014000000020230208165259.csv
        → 形式 fixf（確定状況）/ 国保 / コード 0140000000 / 送った月 2023-02 / 前月 2023-01
    RTfixf1014000000020240115093000.csv
        → 形式 fixf / 社保 / 送った月 2024-01 / 前月 2023-12（年をまたぐ）
    ARTfixfr0140000020230609181251.csv
        → 形式 fixf / 労災 / 労災番号 01400000 / 送った月 2023-06 / 前月 2023-05

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
    "edbn": "edbn",          # 意味は未確認
    "fmei": "fmei",          # 意味は未確認
    "tgfp": "tgfp",          # 意味は未確認
}

PAYERS = {"1": "社保", "2": "国保", "r": "労災"}

# コードが9桁（点数表番号が抜ける）種類
NINE_DIGIT_KINDS = {"skkg", "skks", "edbn"}

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

    year, month, how = read_date(kind, date_digits)
    if not 1 <= month <= 12:
        raise ValueError(f"月が 1〜12 ではありません: {filename!r}")
    py, pm = previous_month(year, month)
    info["日付の書き方"] = how
    info["送った月"] = f"{year}-{month:02d}"
    info["前月(診療月の見込み)"] = f"{py}-{pm:02d}"
    return info


if __name__ == "__main__":
    names = [
        "RTfixf2014000000020230208165259.csv",       # 国保・fixf
        "RTfixf1014000000020240115093000.csv",       # 社保・1月送信 → 前月は前年12月
        "ARTfixfr0140000020230609181251.csv",        # 労災
        "ＲＴｆｉｘｆ１０１４０００００００２０２３０２０８１７０７５４．ＣＳＶ",  # 全角・大文字の拡張子
        "RTzogn2014000000050608.csv",                # 和暦5桁（令和6年8月）
        "RTskkg1014000000202501.csv",                # コード9桁・西暦6桁
        "RTfixf3014000000020230208165259.csv",       # 支払機関が 3 → エラー
    ]
    for name in names:
        print(name)
        try:
            for key, value in extract(name).items():
                print(f"    {key}: {value}")
        except ValueError as e:
            print("    エラー:", e)
