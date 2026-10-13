"""patch_file: Self-Healing 시 코드 전체를 다시 쓰지 않고 지정한 줄만 고친다.

에이전트는 직전 코드(줄 번호 표시)와 실패 로그를 보고 패치 목록만 출력하고,
하네스가 패치를 결정론적으로 적용한다. 줄 번호는 1부터, 범위는 양 끝 포함.

    {"op": "replace", "start": 9, "end": 9, "code": "..."}   9~9번 줄을 code 로 교체
    {"op": "insert",  "after": 3, "code": "..."}             3번 줄 뒤에 삽입 (0 = 맨 앞)
    {"op": "delete",  "start": 5, "end": 6}                  5~6번 줄 삭제

형식이 틀리거나 범위가 겹치면 PatchError → 파이프라인이 R-008 위반으로 처리한다(fail-closed).
"""
from __future__ import annotations

import difflib

MAX_PATCHES = 20


class PatchError(ValueError):
    pass


def number_lines(code: str) -> str:
    """에이전트에게 보여줄 줄 번호 표시 코드."""
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(code.splitlines(), 1))


def _int(value, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PatchError(f"{name} 는 정수여야 합니다: {value!r}")
    return value


def _validate(patches: list[dict], n_lines: int) -> list[tuple[float, dict]]:
    if not isinstance(patches, list) or not patches:
        raise PatchError("patches 는 비어 있지 않은 목록이어야 합니다.")
    if len(patches) > MAX_PATCHES:
        raise PatchError(f"패치는 최대 {MAX_PATCHES}개까지 허용됩니다.")

    ranges: list[tuple[int, int]] = []
    inserts: list[int] = []
    anchored: list[tuple[float, dict]] = []
    for i, p in enumerate(patches, 1):
        if not isinstance(p, dict):
            raise PatchError(f"{i}번째 패치가 객체가 아닙니다.")
        op = p.get("op")
        if op in ("replace", "delete"):
            start, end = _int(p.get("start"), "start"), _int(p.get("end"), "end")
            if not 1 <= start <= end <= n_lines:
                raise PatchError(f"{i}번째 패치 범위 {start}~{end} 가 코드 범위(1~{n_lines})를 벗어났습니다.")
            if op == "replace" and not isinstance(p.get("code"), str):
                raise PatchError(f"{i}번째 replace 패치에 code 문자열이 없습니다.")
            ranges.append((start, end))
            anchored.append((float(start), p))
        elif op == "insert":
            after = _int(p.get("after"), "after")
            if not 0 <= after <= n_lines:
                raise PatchError(f"{i}번째 insert 위치 {after} 가 코드 범위(0~{n_lines})를 벗어났습니다.")
            if not isinstance(p.get("code"), str):
                raise PatchError(f"{i}번째 insert 패치에 code 문자열이 없습니다.")
            inserts.append(after)
            anchored.append((after + 0.5, p))
        else:
            raise PatchError(f"{i}번째 패치의 op 가 올바르지 않습니다: {op!r} (replace/insert/delete)")

    ranges.sort()
    for (_, e1), (s2, _) in zip(ranges, ranges[1:], strict=False):
        if s2 <= e1:
            raise PatchError("패치 범위가 서로 겹칩니다.")
    for after in inserts:
        if any(s <= after < e for s, e in ranges):
            raise PatchError(f"insert 위치 {after} 가 교체/삭제 범위 안에 있습니다.")
    return anchored


def apply_patches(code: str, patches: list[dict]) -> str:
    lines = code.splitlines()
    # 아래쪽부터 적용해야 위쪽 줄 번호가 바뀌지 않는다.
    for _, p in sorted(_validate(patches, len(lines)), key=lambda x: x[0], reverse=True):
        new = p.get("code", "").split("\n")  # splitlines() 는 끝의 빈 줄을 버리므로 쓰지 않는다
        if p["op"] == "insert":
            lines[p["after"]:p["after"]] = new
        elif p["op"] == "replace":
            lines[p["start"] - 1:p["end"]] = new
        else:
            del lines[p["start"] - 1:p["end"]]
    return "\n".join(lines) + "\n"


def make_patches(old: str, new: str) -> list[dict]:
    """두 코드의 차이를 최소 패치 목록으로 만든다 (Mock 에이전트와 지표 계산용)."""
    a, b = old.splitlines(), new.splitlines()
    patches: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        code = "\n".join(b[j1:j2])
        if tag == "replace":
            patches.append({"op": "replace", "start": i1 + 1, "end": i2, "code": code})
        elif tag == "delete":
            patches.append({"op": "delete", "start": i1 + 1, "end": i2})
        elif tag == "insert":
            patches.append({"op": "insert", "after": i1, "code": code})
    return patches
