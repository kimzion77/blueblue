#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사업상세 .md 파일을 '분야' 값에 따라 자동 분류·정리하는 도구.

  입력 : 사업상세/ 폴더의 *.md 파일
  추출 : 각 파일에서 '분야: <값>' 을 읽음
         (지원 형태 1) <!-- 분야: 디지털전환 -->
         (지원 형태 2) - 분야: 디지털전환
  처리 : 원본은 그대로 두고 출력_분야별/<분야명>/ 하위로 복사(shutil.copy2)
  출력 : 분야별 파일 수를 콘솔에 출력 + 결과_분류현황.csv 저장
         (헤더 '분야명,건수' / 건수 내림차순 / 동률이면 분야명 가나다순 / UTF-8)

사용 예:
  python 분야별_자동분류.py
  python 분야별_자동분류.py --input 사업상세 --output 출력_분야별 --csv 결과_분류현황.csv
  python 분야별_자동분류.py --clean        # 기존 출력 폴더를 지우고 새로 생성

표준 라이브러리(argparse, csv, pathlib, re, shutil, sys)만 사용합니다.
"""

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

# 기본 경로 — 이 스크립트가 있는 폴더를 기준으로 함
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = "사업상세"
DEFAULT_OUTPUT = "출력_분야별"
DEFAULT_CSV = "결과_분류현황.csv"
UNKNOWN_FIELD = "미분류"  # 분야 값을 찾지 못한 파일을 모아두는 폴더명

# '분야:' 값 추출 패턴 (HTML 주석형 → 목록형 순으로 시도)
FIELD_PATTERNS = (
    re.compile(r"<!--\s*분야\s*[:：]\s*(?P<value>[^\-<>]+?)\s*-->"),
    re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*분야\s*[:：]\s*(?P<value>.+?)\s*$", re.MULTILINE),
)

# Windows 파일명에 쓸 수 없는 문자 (분야명을 폴더명으로 쓰기 위한 정리용)
INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def read_text(path: Path) -> str:
    """인코딩이 섞여 있어도 최대한 읽어낸다(UTF-8 → UTF-8 BOM → CP949)."""
    for encoding in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_field(text: str) -> str | None:
    """본문에서 분야 값을 추출한다. 찾지 못하면 None."""
    for pattern in FIELD_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group("value").strip().strip("`*\"' ")
            # 표 형태('| 분야 | 값 |')로 적힌 경우를 대비해 구분자 이후는 버림
            value = value.split("|")[0].strip()
            if value:
                return value
    return None


def safe_folder_name(field: str) -> str:
    """분야명을 폴더명으로 안전하게 변환한다."""
    name = INVALID_CHARS.sub("_", field).strip().strip(".")
    return name or UNKNOWN_FIELD


def unique_destination(dest_dir: Path, filename: str) -> Path:
    """같은 이름이 이미 있으면 '이름 (2).md' 식으로 번호를 붙여 덮어쓰기를 막는다."""
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem, suffix = Path(filename).stem, Path(filename).suffix
    for n in range(2, 1000):
        candidate = dest_dir / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"대상 파일명을 정할 수 없습니다: {dest}")


def classify(input_dir: Path, output_dir: Path, clean: bool):
    """분야별로 복사하고 (분야명 -> 건수) 집계와 경고 목록을 돌려준다."""
    md_files = sorted(p for p in input_dir.glob("*.md") if p.is_file())
    if not md_files:
        raise SystemExit(f"[오류] 입력 폴더에 .md 파일이 없습니다: {input_dir}")

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    warnings: list[str] = []

    for md in md_files:
        field = extract_field(read_text(md))
        if field is None:
            field = UNKNOWN_FIELD
            warnings.append(f"분야 값을 찾지 못해 '{UNKNOWN_FIELD}'로 분류: {md.name}")

        folder = safe_folder_name(field)
        dest_dir = output_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 원본 유지: 이동이 아니라 복사(메타데이터 포함)
        shutil.copy2(md, unique_destination(dest_dir, md.name))
        counts[field] = counts.get(field, 0) + 1

    return counts, warnings, len(md_files)


def sort_counts(counts: dict[str, int]) -> list[tuple[str, int]]:
    """건수 내림차순 → 동률이면 분야명 가나다순(오름차순)."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def write_csv(rows: list[tuple[str, int]], csv_path: Path, use_bom: bool) -> None:
    """결과_분류현황.csv 저장 (헤더: 분야명,건수 / UTF-8)."""
    encoding = "utf-8-sig" if use_bom else "utf-8"
    with csv_path.open("w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["분야명", "건수"])
        writer.writerows(rows)


def print_report(rows, total, input_dir, output_dir, csv_path, warnings) -> None:
    """콘솔 리포트 출력."""
    width = max([len(f) for f, _ in rows] + [6])
    print()
    print("=" * 46)
    print(" 사업상세 파일 분야별 자동 분류 결과")
    print("=" * 46)
    print(f" 입력 폴더 : {input_dir}")
    print(f" 출력 폴더 : {output_dir}")
    print("-" * 46)
    print(f" {'분야명'.ljust(width)} | {'건수':>5}")
    print("-" * 46)
    for field, count in rows:
        bar = "■" * count
        print(f" {field.ljust(width)} | {count:>4}건  {bar}")
    print("-" * 46)
    print(f" {'합계'.ljust(width)} | {total:>4}건 ({len(rows)}개 분야)")
    print("=" * 46)
    for msg in warnings:
        print(f" [경고] {msg}")
    print(f" CSV 저장 완료 : {csv_path}")
    print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="사업상세 .md 파일을 분야별 폴더로 복사·정리하고 분류 현황을 CSV로 저장합니다.",
    )
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help=f"입력 폴더 (기본: {DEFAULT_INPUT})")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help=f"출력 폴더 (기본: {DEFAULT_OUTPUT})")
    parser.add_argument("--csv", "-c", default=DEFAULT_CSV, help=f"결과 CSV 파일 (기본: {DEFAULT_CSV})")
    parser.add_argument("--clean", action="store_true", help="실행 전 출력 폴더를 비움")
    parser.add_argument("--bom", action="store_true", help="CSV를 UTF-8 BOM으로 저장(엑셀에서 한글 깨짐 방지)")
    args = parser.parse_args(argv)

    def resolve(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else BASE_DIR / p

    input_dir, output_dir, csv_path = resolve(args.input), resolve(args.output), resolve(args.csv)

    if not input_dir.is_dir():
        raise SystemExit(f"[오류] 입력 폴더를 찾을 수 없습니다: {input_dir}")

    counts, warnings, total = classify(input_dir, output_dir, args.clean)
    rows = sort_counts(counts)
    write_csv(rows, csv_path, args.bom)
    print_report(rows, total, input_dir, output_dir, csv_path, warnings)
    return 0


if __name__ == "__main__":
    # Windows 콘솔에서 한글이 깨지지 않도록 표준출력을 UTF-8로 재설정
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
