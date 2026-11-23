"""オンライン請求の確定状況ファイル（fixf）のファイル名を確認する正規表現。

対象
    社保・国保: RTfixf + 提出先(1=社保, 2=国保) + 医療機関コード10桁 + 西暦の日時14桁 + .csv
        例: RTfixf2014000000020230208165259.csv
    労災:       A か R + RTfixf + r + 労災の番号8桁 + 西暦の日時14桁 + .csv
        例: ARTfixfr0140000020230609181251.csv

医療機関コード10桁 = 都道府県2桁 + 点数表番号1桁(調剤は4) + 機関コード7桁

RT 系ファイルの命名規則（実物のファイル名から把握したもの）
    [A/R] RT xxxx n コード 日付 .拡張子
    - 先頭の A / R は労災だけに付く
    - xxxx は英小文字4文字（fixf=確定状況, fmdl=振込明細, zogn/zogp=増減連絡,
      henr=返戻内訳書, skkg/skks=資格確認結果）
    - n は 1=社保, 2=国保, r=労災
    - コードは 10桁（fixf, fmdl, fmei, zogn, zogp, henr, tgfp, MT系）、
      9桁（skkg, skks, edbn。点数表番号が抜ける）、8桁（労災）
    - 日付は 14桁 西暦年月日時分秒（fixf）、6桁 西暦年月（skkg, skks, edbn）、
      5桁 元号1+和暦年2+月2（zogn, zogp, henr, fmei, tgfp, MT系。50608=令和6年8月）、
      6桁 1+元号年月5桁（社保の fmdl）、7桁 元号1+和暦年2+月日4（労災の fmdl）
"""
import re

PATTERN = re.compile(r"""
(?:
    # 社保・国保の形
    RT fixf
    (?P<支払機関番号>[12])          # 1=社保, 2=国保
    (?P<都道府県番号>[0-9]{2})
    (?P<点数表>4)                   # 調剤は 4
    (?P<医療機関番号>[0-9]{7})
  |
    # 労災の形
    (?P<労災接頭辞>[AR])            # 労災は必ず A か R が付く
    RT fixf r
    (?P<労災番号>[0-9]{8})
)
(?P<年月日>[0-9]{8})                # 西暦 YYYYMMDD
(?P<時分秒>[0-9]{6})                # hhmmss
\.csv
""", re.VERBOSE)


def pattern(name):
    """ファイル名が確定状況ファイルの形式なら Match、違えば None を返す。

    合わなかった側の名前付きグループは、groupdict() の中で None になる。
    """
    return PATTERN.fullmatch(name)


if __name__ == "__main__":
    names = [
        "RTfixf2014000000020230208165259.csv",   # 合う（国保）
        "RTfixf1014000000020230208170754.csv",   # 合う（社保）
        "RTfixf3014000000020230208165259.csv",   # 合わない（提出先が 3）
        "RTzogn2014000000020230208165259.csv",   # 合わない（fixf ではない）
        "RTfixf201400000020230208165259.csv",    # 合わない（コードが9桁）
        "RTfixf2014000000020230208165259.CSV",   # 合わない（拡張子が大文字）
        "ARTfixfr0140000020230609181251.csv",    # 合う（労災、接頭辞 A）
        "RRTfixfr0140000020231208145256.csv",    # 合う（労災、接頭辞 R）
        "RTfixfr0140000020230609181251.csv",     # 合わない（労災なのに接頭辞がない）
        "ARTfixf2014000000020230208165259.csv",  # 合わない（国保なのに接頭辞がある）
    ]
    for name in names:
        m = pattern(name)
        print(name, "->", m.groupdict() if m else None)
