"""전략 코드 계약(Strategy Contract).

LLM 은 자유 형식 코드를 쓰지 않고 이 계약만 채운다. 계약이 있어야 정적 분석과 런타임 검증이 가능하다.
실제 런타임 구현(Order/Bar/Context)은 하네스와 분리된 프로세스에서 도는 sandbox_runner.py 에 있다.
"""

CONTRACT_DOC = """\
## 전략 코드 계약
- 모듈 최상위에 `class Strategy` 를 정의하고 `def on_bar(self, bar, ctx)` 를 구현한다.
- `on_bar` 는 바마다 호출되며 `Order(...)` 또는 `None` 을 반환한다. `Order` 는 import 없이 사용한다.
- bar: t, open, high, low, close (읽기 전용)
- ctx: symbol, max_weight, position(현재 비중, 0이면 미보유), entry_price, bar_index, closes (읽기 전용)
- Order(side="buy"|"sell", weight=float, stop_loss=float, reason=str) — 키워드 인자만 사용
- 매수는 미보유 상태에서만 종가에 체결된다. 손절은 다음 바부터 저가가 stop_loss 이하이면 체결된다(갭 하락 시 시가).
- 출력: 설명 없이 ```python 코드 블록 하나.
"""
