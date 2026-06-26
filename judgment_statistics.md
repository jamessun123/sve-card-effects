# Judgment Statistics

Generated from `judgments/batch-*.json`.

2,680 total issue statements across fail and engine-missing cards.

Top issue categories
fail (1,005 issues)

Targets and selection — 28.7%
Keywords / timing labels — 19.6%
Missing or unimplemented effects — 11.3%
Damage, amounts, and counting — 9.5%
Costs — 9.1%
engine-missing (1,675 issues)

Targets and selection — 28.4%
Missing or unimplemented effects — 19.7%
Damage, amounts, and counting — 13.3%
Keywords / timing labels — 10.5%
Conditions and restrictions — 9.0%
## Overview

| Metric | Count |
|--------|------:|
| Judgment batch files | 258 |
| Unique cards judged | 2571 |
| Total issues recorded | 2680 |

## Verdict counts

| Verdict | Cards | Share of judged |
|---------|------:|----------------:|
| `pass` | 1007 | 39.2% |
| `fail` | 642 | 25.0% |
| `engine-missing` | 922 | 35.9% |

**Pass rate:** 39.2%
**Fail rate:** 25.0%
**Engine-missing rate:** 35.9%

## Issue categories — `fail`

Cards with `fail`: **642**. Issues grouped by primary category (1005 issue statements).

| Category | Issues | Share |
|----------|-------:|------:|
| Targets and selection | 288 | 28.7% |
| Keywords / timing labels | 197 | 19.6% |
| Missing or unimplemented effects | 114 | 11.3% |
| Damage, amounts, and counting | 95 | 9.5% |
| Costs (play, activate, optional) | 91 | 9.1% |
| Conditions and restrictions | 69 | 6.9% |
| Other | 53 | 5.3% |
| Search, deck, and zone effects | 42 | 4.2% |
| Wrong ability timing or structure | 36 | 3.6% |
| Evolve and linkage | 13 | 1.3% |
| Choose / branching effects | 7 | 0.7% |

### Example issues by category

#### Targets and selection

- The fanfare should select another follower on the field and give this follower attack equal to that selected follower's attack; encode the chosen target explicitly instead of using buffDynamic with targetAttack and no target selector.
- The fanfare target is "an enemy leader or enemy follower"; change targets from enemyFieldCard to a selector/effect structure that can hit either the enemy leader or an enemy follower.
- The start-of-end-phase buff target is too broad: buffFieldTrait with cardClass "sword" buffs only Swordcraft followers, but the source says "give each follower on your field +1/+1." Encode a buff affecting all followers on your field, not only Swordcraft followers.

#### Keywords / timing labels

- Remove unsupported keyword entries "fanfare" from keywords; only printed keywords "storm", "bane", and "ward" should be in keywords.
- Remove keyword entries "evolve" and "fanfare" from keywords; evolve is already represented by evolveCost/evolvesTo and fanfare by the fanfare ability timing.
- Remove "fanfare" from keywords; Fanfare should be represented only as the ability timing, while Rush remains in keywords.

#### Missing or unimplemented effects

- The card is missing the optional summon-from-hand effect as a direct On Evolve ability; encode it as an optional hand selection to field of a Machina follower with maxCost 2 without any extra condition.
- The start-of-end-phase ability is missing its condition; add condition {"type":"ownCemeteryClassMin","cardClass":"sword","count":7} so it only applies if there are at least 7 Swordcraft followers in your cemetery.
- Missing evolve linkage: add `evolvesTo: "Ancient Alchemist Evolved"` and `evolveCost: 3` to match `[evolve][cost03]: Evolve this follower.`

#### Damage, amounts, and counting

- The activated cemetery ability is encoded as dealDamageAllEnemies for 3, but the source says "Deal 3 damage to each enemy leader"; encode damage to enemy leaders only instead of all enemy followers and leaders.
- Last Words effect is encoded as dealDamageAllEnemies, but the card says 'Deal 3 damage to each enemy leader.' It should deal 3 damage only to enemy leaders, not to followers or other enemies.
- Strike condition is incorrect. 'If there is another Heroic follower on your field' should check for at least one other follower with trait Heroic on your field, not namedFollowerOnFieldByName with identityName 'Heroic'. Encode with a field trait-count style condition that checks Heroic followers on your field and excludes this card.

#### Costs (play, activate, optional)

- The Fanfare tutor incorrectly uses maxCost equal to your maximum play points; it should search for a Havencraft follower with cost less than your maximum play points, so encode the cost bound as strictly less than max PP rather than equal-or-less.
- Activated ability should set "activateFrom": "cemetery" because the source says "banish this from your cemetery".
- Activated ability cost is incorrectly encoded with both "banishSelf" and malformed "banishFromCemetery" fields; encode the cost as banishing this card from cemetery rather than as a field/self banish cost.

#### Conditions and restrictions

- The On Evolve ability is incorrectly gated by condition {"type":"enteredFromHand"}; remove that condition because the source text simply says "On Evolve - You may summon a Machina follower that costs 2 or less from your hand."
- The activated cemetery ability's condition is wrong: it should require at least 5 other Heroic cards in your cemetery, so the encoded condition needs to exclude this card rather than counting any 5 Heroic cards.
- The play cost reduction condition is incorrect: it should apply only if the chosen card is a Beast follower that costs 4 or less. Encode the EX-area placement with a conditional reduction restricted to Beast follower and maxCost 4, not unconditional reduction on any chosen Beast card.

#### Other

- The buff effect should affect each Fox of Invitation on your field, including the token just summoned; remove "otherOnly": true.
- The Last Words re-entry is encoded incorrectly: "Put this onto its owner's field" should revive the same card, not summon a token copy named Arctic Chimera. Use reviveToField or equivalent to return this specific card.
- The summoned Draconic Weapon token is encoded to the field, but the source only says 'summon a Draconic Weapon token' and Draconic Weapon is an amulet token that should enter as a field card/amulet via the correct token summon handling. Use the exact token summon representation for that token rather than a generic field follower summon if needed.

#### Search, deck, and zone effects

- The fanfare search effect allows revealing up to 2 Arcana spells, but parsed searchDeckChoose only allows choosing one; encode the ability so up to 2 matching Arcana spells can be added to hand from the top 5, with the rest put on the bottom.
- The On Evolve deck search is incorrect: the source says search your deck for a Crystalian follower that costs 2 or less, put it into your EX area, then shuffle. Replace searchDeckChoose/lookAt 5/remainderTo deckBottom with a full-deck tutor effect to EX area followed by shuffleDeck, with playCostReduction 2.
- The Fanfare ability is encoded as searchDeckChoose lookAt 5, but the source says search your deck for a Commander or Officer card, reveal it, add it to your hand, then shuffle your deck. Encode this as a full-deck tutor to hand with reveal true for a card matching either Commander or Officer, followed by shuffleDeck.

#### Wrong ability timing or structure

- The play-cost reduction clause is incorrectly encoded as a fanfare optionalCost ability; it should be a passive/when-playing cost reduction effect requiring banishing 3 Cute, 3 Cool, and 3 Passion cards from your cemetery as an additional play cost, not a field fanfare ability.
- The spell is incorrectly encoded as clash. It should deal damage to one chosen follower on your field equal to the chosen enemy follower's attack, then deal damage to that enemy follower equal to the first follower's attack; replace the effect with a two-target damage exchange implementation rather than clash.
- The continuous Storm and Assail clause is encoded at the wrong timing and with the wrong semantics. "While this card is on your field, each Pixie token on your field has Storm and Assail" should be a passive/aura ability, not part of fanfare, and should continuously affect Pixie tokens on your field.

#### Evolve and linkage

- On Evolve ability includes unsupported field 'reveal' inside searchDeckChoose per current reference. Encode only the implemented searchDeckChoose fields, or add engine support for a reveal flag on searchDeckChoose if reveal is required.
- The evolve ability is encoded incorrectly; instead of evolving another follower matching this card's name, it should evolve this follower after discarding a card.
- evolvesTo is incorrect; it should link to the evolved form card name, not to the base card name.

#### Choose / branching effects

- The spell effect is split into two separate spell abilities, but the source is one sequential effect. It should be a single spell ability that first buffs the chosen Bayleon follower, then offers the Naterran Great Tree placement option.
- The evolve linkage is incomplete/incorrect: this card has two distinct evolve options, so `evolvesTo` and a single `evolveCost` do not faithfully represent the source. Remove the single `evolvesTo`/`evolveCost` shortcut and encode both evolve abilities with their respective costs: [cost01] for "Celia, Hope's Strategist" and [cost04] for "Celia, Despair's Messenger".
- The spell effect is not a player choice. Replace the choose effect with a sequence or if effect that always summons 1 Draconic Weapon, and if Overflow is active, summons 1 additional Draconic Weapon instead.

## Issue categories — `engine-missing`

Cards with `engine-missing`: **922**. Issues grouped by primary category (1675 issue statements).

| Category | Issues | Share |
|----------|-------:|------:|
| Targets and selection | 476 | 28.4% |
| Missing or unimplemented effects | 330 | 19.7% |
| Damage, amounts, and counting | 223 | 13.3% |
| Keywords / timing labels | 176 | 10.5% |
| Conditions and restrictions | 151 | 9.0% |
| Costs (play, activate, optional) | 96 | 5.7% |
| Wrong ability timing or structure | 84 | 5.0% |
| Search, deck, and zone effects | 81 | 4.8% |
| Other | 35 | 2.1% |
| Evolve and linkage | 10 | 0.6% |
| Choose / branching effects | 9 | 0.5% |
| Engine capability gaps | 4 | 0.2% |

### Example issues by category

#### Targets and selection

- The fanfare condition is encoded incorrectly as namedFollowerOnFieldByName "iM@S CG follower"; it should check whether you have an iM@S CG follower on your field. Implement a condition for ally follower presence by trait/filter.
- The activated tutor filter should specify a follower with "Shin Sato" in its name, not any card whose name contains Shin Sato; add cardType: "follower" to the deck filter.
- The conditional damage clause is encoded incorrectly as unconditional with condition always and wrong target scope; it should be 'Then, if this follower has at least 5 attack, deal 2 damage to the enemy leader.'

#### Missing or unimplemented effects

- The activated ability is missing the Lesson (1) cost; it should encode [act] [cost01], Lesson (1): give this follower Storm. Implement support for Lesson costs in activated ability cost objects.
- The card is missing its play restriction clause: it can't be played if you've played another A Horrible Night this turn. Implement support for per-name play restrictions based on cards played this turn.
- The spell effect is completely missing; it should create a rest-of-turn leader-loss trigger that whenever your leader loses defense, deals 1 damage to the enemy leader and heals your leader by 1. Implement support for temporary turn-long triggered effects on leader defense loss.

#### Damage, amounts, and counting

- The current effect incorrectly uses dealDamageAllEnemies, which damages enemy followers as well; it should deal damage only to the enemy leader.
- The damage-triggered ability should be during your turn only and only when this follower takes ability damage. The current grantOnDamaged lacks the during-your-turn restriction and does not restrict the damage source to abilities. Encode those conditions correctly; implement support for onDamaged conditions such as controller turn only and ability-damage-only if needed.
- The damage-triggered ability should be during your turn only and only when this follower takes ability damage. The current grantOnDamaged lacks the during-your-turn restriction and does not restrict the damage source to abilities. Encode those conditions correctly; implement support for onDamaged conditions such as controller turn only and ability-damage-only if needed.

#### Keywords / timing labels

- Remove keyword entry "strike" from keywords; Strike should be represented by the strike-timed ability, not as a keyword.
- Remove incorrect keyword entries "fanfare" and "activated" from keywords; this spell has no printed keywords.
- Remove keyword entries "fanfare", "lastWords", and "activated" from keywords; these are ability timings, not printed keywords.

#### Conditions and restrictions

- The cemetery ability is encoded incorrectly; it should be an activated ability from cemetery with cost banishSelf, and its effect should give each One-Tailed Fox on your field Storm, not grant a trigger when playing One-Tailed Fox.
- The activated effect should include shuffling the deck after searching, unless tutorFromDeck inherently handles it; if not inherent, add a shuffle step.
- Implement support for checking this follower's current attack against a threshold (for example, selfAttackMin condition) so the strike condition can be encoded correctly.

#### Costs (play, activate, optional)

- The additional cost to play the spell is encoded incorrectly as an activated ability from hand; it should be a play additional cost of burying 2 cards named One-Tailed Fox before the spell effect resolves. Implement support for additional play costs on spells.
- The activated ability cost is encoded incorrectly with unsupported "discard": 1; it should require discarding a card as part of the activation cost before burying this card. Implement support for discard-a-card activated costs, or encode via an effect/cost form that the engine supports.
- The effect uses optionalCost with selectFromHand to field, but selectFromHand moves a card rather than summoning it and does not clearly bind the granted delayed ability to the chosen card. The encoding should support choosing a matching hand follower, putting it onto your field, and then granting that chosen follower the delayed end-phase return ability.

#### Wrong ability timing or structure

- The Fanfare ability is incorrectly encoded as grantActRestriction on this card until end of turn; it should target an enemy follower and apply "It can't attack enemies during its controller's next turn." Implement a dedicated operation for attack restriction against enemies on a targeted follower lasting through its controller's next turn, then encode the Fanfare with that target and duration.
- On Evolve is incorrectly encoded as dealDamage to exactly 2 enemy followers; it should be able to select up to 2 enemy followers and deal 5 damage to each. Encode this as a multi-target damage effect with 0-2 or up-to-2 selection if supported; otherwise implement engine support for optional/up-to target counts on enemyFollower targeting or a dedicated up-to-N multi-target damage operation.
- The first fanfare cost is incorrectly encoded as discard exactly 3 cards; it should be discard up to 3 cards. Encode the discard as optional/up-to-3 if supported; otherwise implement engine support for optional variable discard counts.

#### Search, deck, and zone effects

- The summoned follower is encoded with grantLastWords returnToHand, but the card grants 'At the start of your end phase, return this card to its owner's hand.' It should instead grant a delayed start-of-end triggered return-to-hand ability to the summoned follower; implement an effect such as grantStartOfEnd with an embedded returnToHand effect.
- The Last Words effect is incomplete: after putting this card and a Blood Arts token into your EX area, it should also place 2 dormancy counters on this card. Encode the existing EX-area moves, then add a counter-placement step for dormancy on the moved source; this requires implementing support for dormancy counters / adding counters to a card in EX area.
- The Fanfare buff is encoded incorrectly with `buffFieldTrait`, which affects the field. The source says to give each Pixie follower in your EX area +1/+1. Encode an EX-area buff to matching cards instead; this requires implementing an effect that buffs cards in EX area by trait.

#### Other

- The passive Rush aura is encoded too broadly. Source says 'Each Pixie token follower on your field has Rush.' It should apply only to Pixie token followers, not all Pixie followers; implement/support filtering auraGrantKeyword by printingType token.
- The fanfare effect should destroy each other follower on the field, but destroyAllFollowers also destroys Bahamut itself; it should exclude the source follower.
- The passive buff should increase only [attack] by 1 when the destruction event happens, not when an ally follower enters the field.

#### Evolve and linkage

- evolvesTo is incomplete. The source evolve line allows evolving into either Ceryneian Lighthind or Ceryneian Darkhind, but parsed only links to Ceryneian Lighthind Evolved. It should encode a choice between both evolve destinations; the current engine lacks support for multi-destination evolve linkage, so add evolve metadata supporting multiple possible evolves.
- Evolve linkage is incomplete; base Dazzling Healer has evolveCost 1 and should link to its evolved card instead of evolvesTo null.
- The evolve section's granted Ward on evolve is not represented on the evolved side linkage here; ensure Ward is only present on the evolved card.

#### Choose / branching effects

- The spell says "Choose up to 2," so the root effect should use chooseMultiple with min 0 and max 2, not choose with min 1 and max 2.
- The activated ability misses "Choose one that you haven't chosen this turn." Parsed choose allows repeating options. It should track which options were chosen this turn and forbid choosing the same one again; implement per-option once-per-turn choice memory for choose abilities.
- The choose effect is encoded incorrectly: this card says 'Choose one of the following', so choose must be exactly one option with max 1, not max 2.

#### Engine capability gaps

- The source says "When this card leaves the field," but onLeaveField may not preserve the card's counters after leaving. The effect should reference the number of prayer counters that were on this card as it left; implement support for last-known counter values on leave-field triggers if needed.
- The token summon is incorrect and incomplete: the source says "Each player summons a Lococo's Teddy Bear token for every follower on their field destroyed this way," not a single token total. Encode token counts based on the number of followers each player had destroyed by this effect; implement support for "destroy all other followers" and for summoning tokens proportional to cards destroyed this way for each player if unavailable.
- Second fanfare ability `destroyAllFollowers` is wrong; the source says 'Destroy each follower summoned this way,' meaning only the followers summoned by the previous effect should be destroyed. Encode destruction limited to the followers summoned by this effect, and implement support for referring to cards summoned by the immediately preceding effect if needed.
