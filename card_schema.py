"""Pydantic models for Shadowverse Evolve card DSL JSON.

Matches ABILITY-REFERENCE.md and the encoded output shape in prompt.txt /
merged-deck-cards.json. Use CardList as the structured-output root when the
model should return multiple cards.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


class CardClass(str, Enum):
    FOREST = "forest"
    SWORD = "sword"
    RUNE = "rune"
    DRAGON = "dragon"
    ABYSS = "abyss"
    HAVEN = "haven"
    NEUTRAL = "neutral"
    PORTAL = "portal"


class CardType(str, Enum):
    FOLLOWER = "follower"
    SPELL = "spell"
    AMULET = "amulet"


class PrintingType(str, Enum):
    BASE = "base"
    EVOLVED = "evolved"


class ParseConfidence(str, Enum):
    HIGH = "high"
    REVIEW = "review"
    MANUAL = "manual"
    AUTO = "auto"
    KEYWORD_ONLY = "keyword-only"


# Documented in ABILITY-REFERENCE.md — kept as constants for JSON Schema enums.
TIMINGS: tuple[str, ...] = (
    "fanfare",
    "lastWords",
    "onEvolve",
    "onSuperEvolve",
    "strike",
    "activated",
    "spell",
    "passive",
    "aura",
    "startOfMain",
    "startOfEnd",
    "onCardPlayed",
    "onDiscard",
    "onLeaveField",
    "onDamaged",
    "onAllyEvolve",
    "onAllyFollowerEnter",
    "onReturnToHand",
    "evolve",
)
Timing = Annotated[str, Field(description=f"Trigger timing; one of {', '.join(TIMINGS)}")]


class Keyword(str, Enum):
    ADVANCED = "advanced"
    AURA = "aura"
    EVOLVE = "evolve"
    FANFARE = "fanfare"
    INTIMIDATE = "intimidate"
    LAST_WORDS = "lastWords"
    QUICK = "quick"
    RUSH = "rush"
    STORM = "storm"
    STRIKE = "strike"
    WARD = "ward"


CONDITION_TYPES: tuple[str, ...] = (
    "always",
    "combo",
    "necrocharge",
    "overflow",
    "sanguine",
    "inExArea",
    "sourceInExArea",
    "namedFollowerOnField",
    "namedFollowerOnFieldByName",
    "opponentCemeteryMin",
    "ownCemeteryMin",
    "ownCemeteryTraitMin",
    "ownCemeteryClassMin",
    "exAreaTraitMin",
    "exAreaNamedMin",
    "fieldTraitMin",
    "handMin",
    "handMax",
    "ppMin",
    "earthRite",
    "spellchain",
    "discardedThisTurn",
    "discardedCardType",
    "enteredFromHand",
    "notEnteredFromHand",
    "conditionAny",
)
ConditionType = Annotated[
    str, Field(description=f"Condition discriminator; one of {', '.join(CONDITION_TYPES)}")
]

TARGET_TYPES: tuple[str, ...] = (
    "self",
    "selfLeader",
    "enemyLeader",
    "enemyFollower",
    "enemyFieldCard",
    "selfFollower",
    "allyFieldCard",
    "anyFollower",
    "lastSummoned",
)
TargetType = Annotated[
    str, Field(description=f"Target selector; one of {', '.join(TARGET_TYPES)}")
]

EFFECT_OPS: tuple[str, ...] = (
    "addCounter",
    "addStack",
    "auraAbilityDamageCap",
    "auraGrantKeyword",
    "autoEvolveIf",
    "banish",
    "banishAllFieldAndEx",
    "banishFromCemetery",
    "banishFromDeck",
    "banishFromExArea",
    "banishFromOpponentExArea",
    "banishSelf",
    "banishUpTo",
    "box",
    "buff",
    "buffAllEnemyFollowers",
    "buffDynamic",
    "buffFieldTrait",
    "buryEachOpponentDeck",
    "buryEachOpponentFollowers",
    "buryFieldFollowers",
    "buryFromFieldSelect",
    "buryOpponentMaxAttackFollower",
    "burySelf",
    "cannotAttack",
    "choose",
    "chooseMultiple",
    "clash",
    "damageCap",
    "damageImmunity",
    "dealDamage",
    "dealDamageAllEnemies",
    "dealDamageCompare",
    "dealDamageDynamic",
    "dealDamageFollowerAndLeader",
    "dealDamageOtherFollowers",
    "dealDamageSplit",
    "defAsAttackAura",
    "destroy",
    "destroyAllAmulets",
    "destroyAllEnemyField",
    "destroyAllFollowers",
    "destroyLowestCostEnemyFollowers",
    "discard",
    "discardFromHand",
    "discardHand",
    "discardOptionalDraw",
    "draw",
    "drawDynamic",
    "engage",
    "engageSelf",
    "evolveCostReduction",
    "evolveOtherFollower",
    "exAreaPlayCostReduction",
    "gainEvolutionPoint",
    "grantActRestriction",
    "grantIgnoresWard",
    "grantIndestructible",
    "grantKeyword",
    "grantLastWords",
    "grantLeaderDamageShield",
    "grantNextPlayCostReduction",
    "grantOnAllyFollowerEnter",
    "grantOnCardPlayed",
    "grantOnDamaged",
    "grantOpponentRestriction",
    "grantPlayCostReduction",
    "handResetDraw",
    "healLeader",
    "if",
    "increaseMaxPp",
    "maneuver",
    "mill",
    "millOpponent",
    "millToBanish",
    "moveSourceToExArea",
    "moveToExArea",
    "noop",
    "opponentDiscardEach",
    "opponentTurnStrikeBonus",
    "optionalCost",
    "passiveKeywords",
    "peekDeck",
    "playCostIncrease",
    "playCostReduction",
    "playDeckTopFollower",
    "playFromOpponentCemetery",
    "putAllEnemyFollowersOnDeck",
    "putDeckTopToExArea",
    "putHandCardOnDeck",
    "putOnBottomOfDeck",
    "putOnTopOfDeck",
    "putSameNameTokenToExArea",
    "recoverPp",
    "refresh",
    "removeCounter",
    "returnToHand",
    "revealRandomHandSummonFollowers",
    "reviveSelfFromCemetery",
    "reviveToField",
    "rollDie",
    "searchDeckChoose",
    "searchDeckSummonMultiple",
    "selectEvolveDeckCard",
    "selectFromHand",
    "sequence",
    "setLeaderDef",
    "setStats",
    "shuffleDeck",
    "silence",
    "silenceOpponents",
    "skipNextTurn",
    "spendPp",
    "summon",
    "summonCopyOfTarget",
    "summonFromCemetery",
    "summonFromEvolveDeck",
    "summonFromExArea",
    "summonLastTutoredFromHand",
    "summonSameNameToken",
    "summonSelfFromExArea",
    "swapAtkDef",
    "takeExtraTurn",
    "transferCounters",
    "transform",
    "triggerAbilities",
    "turnEvolveDeck",
    "tutorFromCemetery",
    "tutorFromDeck",
    "tutorFromDeckAny",
    "tutorFromEvolveDeck",
    "winGame",
    "withChosenNumber",
)
EffectOp = Annotated[str, Field(description="Root effect operation from ABILITY-REFERENCE")]

DAMAGE_AMOUNT_OPS: tuple[str, ...] = (
    "handCount",
    "handExAreaTotal",
    "traitFieldCount",
    "namedIdentityFieldCount",
    "selfAttack",
    "selfDefense",
    "targetAttack",
    "maxPp",
    "cemeteryFilterCount",
    "chosenNumber",
)
DamageAmountOp = Annotated[
    str, Field(description=f"Dynamic amount op; one of {', '.join(DAMAGE_AMOUNT_OPS)}")
]


class ActivateFrom(str, Enum):
    FIELD = "field"
    CEMETERY = "cemetery"
    EX_AREA = "exArea"
    HAND = "hand"


class DeckFilter(BaseModel):
    """Filter for tutors, searches, discards (ABILITY-REFERENCE DeckFilter)."""

    model_config = ConfigDict(extra="allow")

    card_no: str | None = Field(default=None, alias="cardNo")
    identity_name: str | None = Field(default=None, alias="identityName")
    trait: str | None = None
    traits_any: list[str] | None = Field(default=None, alias="traitsAny")
    card_class: CardClass | None = Field(default=None, alias="cardClass")
    card_type: CardType | None = Field(default=None, alias="cardType")
    max_cost: int | None = Field(default=None, alias="maxCost")
    min_cost: int | None = Field(default=None, alias="minCost")
    identity_name_contains: str | None = Field(default=None, alias="identityNameContains")
    exclude_identity_name: str | None = Field(default=None, alias="excludeIdentityName")
    exclude_card_class: CardClass | None = Field(default=None, alias="excludeCardClass")


class EarthRiteCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


class ActivatedCost(BaseModel):
    """Cost for timing: activated abilities."""

    model_config = ConfigDict(extra="allow")

    pp: int | None = None
    engage: bool | None = None
    banish_from_cemetery: DeckFilter | None = Field(default=None, alias="banishFromCemetery")
    banish_from_ex_area: DeckFilter | None = Field(default=None, alias="banishFromExArea")
    bury_from_field: DeckFilter | None = Field(default=None, alias="buryFromField")
    bury_self: bool | None = Field(default=None, alias="burySelf")
    banish_self: bool | None = Field(default=None, alias="banishSelf")
    earth_rite: EarthRiteCost | None = Field(default=None, alias="earthRite")


class Condition(BaseModel):
    """Gate for abilities and if/autoEvolveIf effects."""

    model_config = ConfigDict(extra="allow")

    type: ConditionType
    count: int | None = None
    trait: str | None = None
    card_class: CardClass | None = Field(default=None, alias="cardClass")
    card_no: str | None = Field(default=None, alias="cardNo")
    identity_name: str | None = Field(default=None, alias="identityName")
    card_type: CardType | None = Field(default=None, alias="cardType")
    conditions: list[Condition] | None = None


class TargetSelector(BaseModel):
    """targets object on effects (ABILITY-REFERENCE Target selectors)."""

    model_config = ConfigDict(extra="allow")

    type: TargetType
    count: int | None = None
    max_cost: int | None = Field(default=None, alias="maxCost")
    min_cost: int | None = Field(default=None, alias="minCost")
    max_def: int | None = Field(default=None, alias="maxDef")
    exclude_self: bool | None = Field(default=None, alias="excludeSelf")


class DamageAmountExpr(BaseModel):
    """Dynamic damage / amount expression."""

    model_config = ConfigDict(extra="allow")

    op: DamageAmountOp
    trait: str | None = None
    identity_name: str | None = Field(default=None, alias="identityName")
    multiplier: int | None = None
    filter: DeckFilter | None = None
    divisor: int | None = None
    min: int | None = None
    max: int | None = None


DamageAmount = Annotated[Union[int, DamageAmountExpr], Field(discriminator=None)]


class ChooseOption(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str | None = None
    effect: Effect | None = None


class Effect(BaseModel):
    """Recursive effect tree rooted at effect.op (ABILITY-REFERENCE)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    op: EffectOp

    # Common composition fields
    steps: list[Effect] | None = None
    then: Effect | None = None
    else_: Effect | None = Field(default=None, alias="else")
    condition: Condition | None = None
    choices: list[ChooseOption] | None = None
    options: list[ChooseOption] | None = None
    body: Effect | None = None

    # Frequently referenced leaf / shared fields
    count: int | None = None
    amount: DamageAmount | None = None
    targets: TargetSelector | None = None
    filter: DeckFilter | None = None
    keyword: Keyword | str | None = None
    keywords: list[Keyword | str] | None = None
    atk: int | None = None
    def_: int | None = Field(default=None, alias="def")
    trait: str | None = None
    card_class: CardClass | None = Field(default=None, alias="cardClass")
    card_type: CardType | None = Field(default=None, alias="cardType")
    token_card_no: str | None = Field(default=None, alias="tokenCardNo")
    token_name: str | None = Field(default=None, alias="tokenName")
    zone: Literal["field", "exArea", "hand", "cemetery", "deck"] | None = None
    to: Literal["field", "exArea", "hand", "cemetery", "deck"] | None = None
    counter: str | None = None
    exclude_self: bool | None = Field(default=None, alias="excludeSelf")
    other_only: bool | None = Field(default=None, alias="otherOnly")
    trigger_on_evolve: bool | None = Field(default=None, alias="triggerOnEvolve")
    optional: bool | None = None
    play_cost_reduction: int | None = Field(default=None, alias="playCostReduction")
    max_targets: int | None = Field(default=None, alias="maxTargets")
    primary_amount: DamageAmount | None = Field(default=None, alias="primaryAmount")
    secondary_amount: DamageAmount | None = Field(default=None, alias="secondaryAmount")
    damage_target_first: bool | None = Field(default=None, alias="damageTargetFirst")


class Ability(BaseModel):
    """Single entry in card.abilities[]."""

    model_config = ConfigDict(extra="allow")

    timing: Timing
    effect: Effect
    condition: Condition | None = None
    cost: ActivatedCost | None = None
    activate_from: ActivateFrom | None = Field(default=None, alias="activateFrom")
    once_per_turn: bool | None = Field(default=None, alias="oncePerTurn")
    max_per_turn: int | None = Field(default=None, alias="maxPerTurn")
    quick: bool | None = None


class Card(BaseModel):
    """Encoded card definition (output DSL)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    card_no: str | None = Field(default=None, alias="cardNo")
    card_class: CardClass = Field(alias="class")
    printing_type: PrintingType = Field(alias="printingType")
    cost: int | None = None
    card_type: CardType | None = Field(default=None, alias="cardType")
    traits: list[str] = Field(default_factory=list)
    abilities: list[Ability] = Field(default_factory=list)
    attack: int | None = None
    defense: int | None = None
    keywords: list[Keyword | str] = Field(default_factory=list)
    evolves_to: str | None = Field(default=None, alias="evolvesTo")
    evolves_from: str | None = Field(default=None, alias="evolvesFrom")
    evolve_cost: int | None = Field(default=None, alias="evolveCost")
    special_type: str | None = Field(default=None, alias="specialType")
    parse_confidence: ParseConfidence | str | None = Field(
        default=None, alias="parseConfidence"
    )


class CardList(BaseModel):
    """Structured-output root when returning multiple cards as a JSON array."""

    cards: list[Card]


class CardMap(RootModel[dict[str, Card]]):
    """Alternative batch shape: object keyed by cardNo (merged-deck-cards.json)."""


# Resolve forward references for recursive models.
Condition.model_rebuild()
ChooseOption.model_rebuild()
Effect.model_rebuild()


def card_json_schema() -> dict[str, Any]:
    """JSON Schema for a single Card (e.g. OpenAI response_format)."""
    schema = Card.model_json_schema()
    _inject_enum(schema, "Timing", TIMINGS)
    _inject_enum(schema, "ConditionType", CONDITION_TYPES)
    _inject_enum(schema, "TargetType", TARGET_TYPES)
    _inject_enum(schema, "EffectOp", EFFECT_OPS)
    _inject_enum(schema, "DamageAmountOp", DAMAGE_AMOUNT_OPS)
    return schema


def card_list_json_schema() -> dict[str, Any]:
    """JSON Schema for CardList — use when the model returns multiple cards."""
    schema = CardList.model_json_schema()
    _inject_enum(schema, "Timing", TIMINGS)
    _inject_enum(schema, "ConditionType", CONDITION_TYPES)
    _inject_enum(schema, "TargetType", TARGET_TYPES)
    _inject_enum(schema, "EffectOp", EFFECT_OPS)
    _inject_enum(schema, "DamageAmountOp", DAMAGE_AMOUNT_OPS)
    return schema


def _inject_enum(schema: dict[str, Any], def_name: str, values: tuple[str, ...]) -> None:
    defs = schema.get("$defs", {})
    if def_name in defs:
        defs[def_name]["enum"] = list(values)
