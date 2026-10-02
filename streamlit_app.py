"""쇼핑 리스트 (Streamlit 버전)

웹 버전(index.html, style.css, script.js)과 같은 PRD 기능을 Streamlit으로 옮긴 앱이다.
- 데이터는 브라우저 localStorage 대신 같은 폴더의 shopping_list.json 파일에 저장한다.
- 실행: python -m streamlit run streamlit_app.py
"""

import json
import time
import unicodedata
import uuid
from pathlib import Path

import streamlit as st

# ===== 상수 =====
DATA_FILE = Path(__file__).with_name("shopping_list.json")
MAX_NAME_LENGTH = 50
# 삭제 직후 이 시간 안에 들어온 삭제 클릭은 무시한다 (더블클릭으로 2개 삭제 방지)
DELETE_GUARD_SEC = 0.4
ZWJ = "‍"


# ===== 유틸 =====

def split_chars(text: str) -> list[str]:
    """문자열을 사람이 보는 글자 단위로 나눈다.

    결합 문자, 이모지 변형 선택자, 피부색, ZWJ로 이어진 합성 이모지(👨‍👩‍👧)를 한 글자로 센다.
    """
    chars: list[str] = []
    join_next = False
    for ch in text:
        is_modifier = (
            unicodedata.combining(ch)
            or "︀" <= ch <= "️"  # 변형 선택자
            or "\U0001f3fb" <= ch <= "\U0001f3ff"  # 피부색
        )
        if chars and (join_next or is_modifier or ch == ZWJ):
            chars[-1] += ch
        else:
            chars.append(ch)
        join_next = ch == ZWJ
    return chars


def normalize_name(name) -> str:
    """앞뒤 공백 제거 + 글자 단위 최대 50자"""
    chars = split_chars(str(name or "").strip())
    return "".join(chars[:MAX_NAME_LENGTH])


def escape_markdown(text: str) -> str:
    """사용자 입력이 마크다운 서식으로 해석되지 않도록 특수 문자를 이스케이프한다."""
    specials = "\\`*_{}[]()<>#+-.!|~:$"
    return "".join("\\" + ch if ch in specials else ch for ch in text)


def is_valid_item(item) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("name"), str)
        and item["name"].strip() != ""
    )


# ===== 저장소 (F5) =====

def load_items() -> list[dict]:
    """JSON 파일에서 아이템 목록을 불러온다. 손상되었거나 없으면 빈 목록."""
    try:
        saved = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(saved, list):
        return []

    items, seen_ids = [], set()
    for item in filter(is_valid_item, saved):
        # id가 중복된 데이터는 새 id를 발급한다
        item_id = str(uuid.uuid4()) if item["id"] in seen_ids else item["id"]
        seen_ids.add(item_id)
        try:
            created_at = int(item.get("createdAt")) or int(time.time() * 1000)
        except (TypeError, ValueError):
            created_at = int(time.time() * 1000)
        items.append({
            "id": item_id,
            "name": normalize_name(item["name"]),
            "checked": bool(item.get("checked")),
            "createdAt": created_at,
        })
    return items


def save_items() -> None:
    """현재 아이템 목록을 JSON 파일에 저장한다. 실패해도 앱은 계속 동작한다."""
    try:
        DATA_FILE.write_text(
            json.dumps(st.session_state.shopping_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        st.session_state.save_failed = True


# ===== 아이템 조작 (콜백) =====

def find_item(item_id: str):
    return next((it for it in st.session_state.shopping_items if it["id"] == item_id), None)


def add_item() -> None:
    """F1: 입력창 값을 리스트 맨 아래에 추가한다."""
    name = normalize_name(st.session_state.new_item)
    st.session_state.new_item = ""  # 추가 후 입력창 비우기
    if not name:
        return
    st.session_state.shopping_items.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "checked": False,
        "createdAt": int(time.time() * 1000),
    })
    save_items()


def start_editing(item_id: str) -> None:
    """F2: 편집 모드로 전환한다. 다른 아이템을 편집 중이었다면 그 값을 먼저 저장한다."""
    if st.session_state.editing_id and st.session_state.editing_id != item_id:
        save_edit(st.session_state.editing_id)
    item = find_item(item_id)
    if item:
        st.session_state.editing_id = item_id
        st.session_state[f"edit_{item_id}"] = item["name"]


def save_edit(item_id: str) -> None:
    """F2: 수정 저장. 빈 값이면 기존 값을 유지한다."""
    item = find_item(item_id)
    new_name = normalize_name(st.session_state.get(f"edit_{item_id}", ""))
    if item and new_name and new_name != item["name"]:
        item["name"] = new_name
        save_items()
    st.session_state.editing_id = None


def cancel_edit() -> None:
    """F2: 수정 취소"""
    st.session_state.editing_id = None


def toggle_item(item_id: str) -> None:
    """F4: 체크 상태 토글"""
    item = find_item(item_id)
    if item:
        item["checked"] = st.session_state[f"check_{item_id}"]
        save_items()


def delete_item(item_id: str) -> None:
    """F3: 아이템 삭제"""
    now = time.monotonic()
    if now - st.session_state.last_delete_at < DELETE_GUARD_SEC:
        return
    st.session_state.last_delete_at = now
    st.session_state.shopping_items = [it for it in st.session_state.shopping_items if it["id"] != item_id]
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
    save_items()


# ===== 화면 =====

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

# 카드 너비를 웹 버전과 비슷하게 좁히고, 아이템 줄 간격을 정리한다
st.markdown(
    """
    <style>
      .block-container, [data-testid="stMainBlockContainer"] {
        max-width: 560px;
        padding-top: 3rem;
      }
      h1 { text-align: center; }
      @media (max-width: 480px) { h1 { font-size: 1.6rem !important; } }
      .summary { text-align: center; color: #5f6b65; font-size: 0.9rem; }
      .empty { text-align: center; color: #5f6b65; padding: 2.5rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 세션 상태 초기화 (처음 접속할 때 파일에서 불러온다)
if "shopping_items" not in st.session_state:
    st.session_state.shopping_items = load_items()
    st.session_state.editing_id = None
    st.session_state.last_delete_at = 0.0
    st.session_state.save_failed = False

st.title("🛒 쇼핑 리스트")

# 한 줄 배치용 가로 컨테이너: 버튼·체크박스는 내용 크기만큼, 이름·입력창은 남은 공간을 차지한다.
# wrap=False라서 휴대폰 화면에서도 세로로 쌓이지 않는다.
def row():
    return st.container(horizontal=True, wrap=False, vertical_alignment="center", gap="xsmall")


# ----- 입력 폼 (F1) : Enter 또는 [추가] 버튼 -----
with st.form("add_form", border=False, enter_to_submit=True):
    with row():
        st.text_input(
            "추가할 아이템 이름",
            key="new_item",
            max_chars=MAX_NAME_LENGTH * 4,  # 이모지 등은 코드 단위가 길어서 여유를 두고, 실제 제한은 normalize_name에서
            placeholder="아이템 입력...",
            label_visibility="collapsed",
            width="stretch",
        )
        st.form_submit_button("추가", type="primary", on_click=add_item, width="content")

# ----- 아이템 리스트 -----
items = st.session_state.shopping_items

if not items:
    # F6: 빈 상태
    st.markdown('<p class="empty">쇼핑 리스트가 비어 있어요</p>', unsafe_allow_html=True)

for item in items:
    item_id = item["id"]
    if st.session_state.editing_id == item_id:
        # 편집 모드: Enter 또는 [저장] → 저장, [취소] → 취소
        with st.form(f"edit_form_{item_id}", border=False, enter_to_submit=True), row():
            st.text_input(
                f"{item['name']} 이름 수정",
                key=f"edit_{item_id}",
                label_visibility="collapsed",
                width="stretch",
            )
            st.form_submit_button("저장", type="primary", on_click=save_edit, args=(item_id,), width="content")
            st.form_submit_button("취소", type="tertiary", on_click=cancel_edit, width="content")
    else:
        with row():
            st.checkbox(
                f"{item['name']} 구매 완료",
                value=item["checked"],
                key=f"check_{item_id}",
                on_change=toggle_item,
                args=(item_id,),
                label_visibility="collapsed",
                width="content",
            )
            name = escape_markdown(item["name"])
            # F4: 체크된 아이템은 취소선 + 회색
            st.markdown(f":gray[~~{name}~~]" if item["checked"] else name, width="stretch")
            st.button("수정", key=f"edit_btn_{item_id}", type="tertiary", on_click=start_editing, args=(item_id,), width="content")
            st.button("삭제", key=f"del_btn_{item_id}", type="tertiary", on_click=delete_item, args=(item_id,), width="content")

# ----- 하단 요약 (F6) -----
st.divider()
done = sum(1 for it in items if it["checked"])
st.markdown(f'<p class="summary">전체 {len(items)}개 · 완료 {done}개</p>', unsafe_allow_html=True)

if st.session_state.save_failed:
    st.warning("저장에 실패했어요. 이번 접속 동안은 계속 사용할 수 있지만, 새로고침하면 변경 내용이 사라질 수 있어요.")
