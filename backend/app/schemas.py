"""核心数据模型（Pydantic v2）。

字段约束与《接口契约》保持一致：
- 卡面文案 1~200 字符、标题 1~40
- weight 1~100；SSR 必须携带 risk_balance
- DirectionSpec 为决策 → 生成的解耦契约
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Rarity(str, Enum):
    N = "N"
    R = "R"
    SR = "SR"
    SSR = "SSR"


class CardLabel(str, Enum):
    EVENT = "EVENT"        # 随机事件
    ACTION = "ACTION"      # 角色行动分支
    SCENE = "SCENE"        # 场景/环境转移
    MEETING = "MEETING"    # 引入新角色/关系变化
    FORESHADOW = "FORESHADOW"  # 伏笔


class RiskBalance(BaseModel):
    """SSR 卡必填：张力 + 建议的后续转折，降低"抽到神卡但剧情断线"。"""
    tension: int = Field(ge=1, le=10)
    suggested_turn: str = Field(max_length=80)


class Card(BaseModel):
    card_id: str
    title: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=200)
    label: CardLabel
    rarity: Rarity
    weight: int = Field(ge=1, le=100)
    # 因果规划三件套：仅作正文生成输入的内部字段（不上卡面）。
    # 诱因——这个事件为何发生/破绽如何被察觉；后果——落定后对各方的影响与反应；
    # 悬念——给下一步（落定后的新分歧）留的钩子。
    # 因果规划三件套：仅作正文生成输入的内部字段（不上卡面）。
    # 诱因——这个事件为何发生/破绽如何被察觉；后果——落定后对各方的影响与反应；
    # 悬念——给下一步（落定后的新分歧）留的钩子。schema 层可选以兼容旧存档，
    # 但生成卡池时必须在 DirectionGenerator 里强制每卡齐全（缺失即抛 ModelError）。
    cause: str | None = Field(default=None, max_length=120)
    aftermath: str | None = Field(default=None, max_length=120)
    suspense: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _require_risk_balance_for_ssr(self) -> "Card":
        if self.rarity == Rarity.SSR and self.risk_balance is None:
            raise ValueError("SSR 卡必须携带 risk_balance（张力 + 后续转折建议）")
        return self

    risk_balance: RiskBalance | None = None


class CardPool(BaseModel):
    """分歧点生成的卡池快照（3~5 张）。"""
    decision_no: int = Field(ge=1)
    pool_version: int = Field(default=1, ge=1)
    cards: list[Card] = Field(min_length=1, max_length=5)

    def by_id(self, card_id: str) -> Card | None:
        return next((c for c in self.cards if c.card_id == card_id), None)


class DirectionKind(str, Enum):
    EVENT = "EVENT"
    ACTION = "ACTION"
    SCENE = "SCENE"
    MEETING = "MEETING"
    FORESHADOW = "FORESHADOW"
    CUSTOM = "CUSTOM"


class DirectionSpec(BaseModel):
    """决策输出与正文生成之间的解耦契约。"""
    kind: DirectionKind
    summary: str = Field(min_length=1, max_length=200)
    target_character_id: str | None = None
    scene: str | None = Field(default=None, max_length=120)
    constraints: list[str] = Field(default_factory=list, max_length=5)
    risk_flag: bool = False
    # 来自所选卡的因果规划，随方向喂给正文，避免正文只能现编诱因与后果
    cause: str | None = None
    aftermath: str | None = None
    suspense: str | None = None
    risk_balance: RiskBalance | None = None


class DecisionMode(str, Enum):
    GACHA_PICK = "gacha_pick"   # 明选
    GACHA_DRAW = "gacha_draw"   # 盲抽
    FREE = "free"               # 自由输入


class Decision(BaseModel):
    decision_no: int = Field(ge=1)
    mode: DecisionMode
    card_id: str | None = None
    direction_spec: DirectionSpec
    created_at: str