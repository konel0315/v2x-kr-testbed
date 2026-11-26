"""IEEE 1609.2 / 1609.2.1 ASN.1 파일을 pycrate가 읽을 수 있게 다듬는다 (인코딩 결과에는 영향 없음).

1. 글자 인코딩을 UTF-8로 바꾼다 (원본 일부가 cp1252).
2. 주석을 지운다.
3. 두 줄로 나뉜 정의(이름 / 클래스 ::=)를 한 줄로 붙인다.
4. WITH COMPONENTS 제약을 지운다. 값의 모양만 제한하는 제약이라 COER 바이트에는 영향이 없다.
5. pycrate가 풀지 못하는 상대 참조 제약({@.id} 등) 세 곳을 열린 형식으로 바꾼다.
사용법: python3 scripts/fix_ieee1609_asn.py <폴더>
"""
import glob
import re
import sys


def strip_with_components(t):
    out, i = [], 0
    while True:
        m = re.search(r"\(\s*WITH\s+COMPONENTS?\b", t[i:])
        if not m:
            out.append(t[i:])
            return "".join(out)
        s = i + m.start()
        out.append(t[i:s])
        depth, j = 0, s
        while True:
            if t[j] == "(":
                depth += 1
            elif t[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def main(folder):
    for f in sorted(glob.glob(f"{folder}/*.asn")):
        raw = open(f, "rb").read()
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            t = raw.decode("cp1252")
        t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        t = re.sub(r"--.*?(--|$)", "", t, flags=re.M)
        t = re.sub(r"(?m)^([A-Za-z][\w-]*)[ \t]*\n[ \t]+([A-Z][\w-]*[ \t]*::=)", r"\1 \2", t)
        t = strip_with_components(t)
        t = re.sub(r"(CERT-EXT-TYPE\.&(?:Issue|Req)\(\{SetCertExtensions\})\{@\.id\}\)", r"\1)", t)
        t = re.sub(r"(IEEE1609DOT2-HEADERINFO-CONTRIBUTED-EXTENSION\.&Extn\(\{\s*"
                   r"Ieee1609Dot2HeaderInfoContributedExtensions\s*\})\{@\.contributorId\}\)", r"\1)", t)
        open(f, "w", encoding="utf-8").write(t)


if __name__ == "__main__":
    main(sys.argv[1])
