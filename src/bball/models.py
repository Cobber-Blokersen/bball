from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    auth_type: str = ""
    name: str = ""
    role: str = "user"  # "user" or "admin"


@dataclass(slots=True, frozen=True)
class LineupPreferenceDefinition:
    key: str
    name: str
    brief_description: str
    detailed_description: str
    default_enabled: bool = True


BOOLEAN_PREFERENCE_DEFINITIONS: tuple[LineupPreferenceDefinition, ...] = (
    LineupPreferenceDefinition(
        key="half_split_balance",
        name="Balance first and second halves",
        brief_description="Spread playtime evenly between the two halves.",
        detailed_description="Penalizes large first-half versus second-half playtime imbalances for each player.",
    ),
    LineupPreferenceDefinition(
        key="power_combo_objective",
        name="Prefer power combos",
        brief_description="Favor periods where configured strong player combos are together.",
        detailed_description="Adds a soft preference for configured player combos being on the court together.",
    ),
)


def get_boolean_preference_definitions() -> tuple[LineupPreferenceDefinition, ...]:
    return BOOLEAN_PREFERENCE_DEFINITIONS


def build_default_boolean_preferences() -> dict[str, bool]:
    return {definition.key: definition.default_enabled for definition in BOOLEAN_PREFERENCE_DEFINITIONS}


@dataclass(frozen=True)
class NoConsecutiveOffModeOption:
    """A selectable mode for the back-to-back rests preference."""

    value: str
    name: str
    description: str


NO_CONSECUTIVE_OFF_MODE_OPTIONS: tuple[NoConsecutiveOffModeOption, ...] = (
    NoConsecutiveOffModeOption(
        value="off",
        name="Off",
        description="Do not consider back-to-back rests; the solver may sit a player twice in a row.",
    ),
    NoConsecutiveOffModeOption(
        value="preferred",
        name="Preferred",
        description="Prefer to avoid back-to-back rests, but always produce a lineup if some sit consecutively.",
    ),
    NoConsecutiveOffModeOption(
        value="enforced",
        name="Enforced",
        description="Require no player to sit two consecutive periods; can make lineups impossible.",
    ),
)


@dataclass(frozen=True)
class NoConsecutiveOffPreferenceDefinition:
    """Metadata for the back-to-back rests preference, which is tri-state rather than boolean."""

    key: str = "no_consecutive_off"
    name: str = "Avoid back-to-back rests"
    brief_description: str = "Keep each player from sitting in consecutive periods."
    detailed_description: str = (
        "Controls whether players are kept from sitting out two consecutive periods. "
        "Off leaves it unconstrained; Preferred asks the solver to minimize back-to-back rests "
        "while always producing a lineup; Enforced makes it a hard rule that can make lineups "
        "impossible to generate."
    )


NO_CONSECUTIVE_OFF_PREFERENCE: NoConsecutiveOffPreferenceDefinition = NoConsecutiveOffPreferenceDefinition()
NO_CONSECUTIVE_OFF_MODE_DEFAULT = "preferred"


def get_no_consecutive_off_mode_options() -> tuple[NoConsecutiveOffModeOption, ...]:
    return NO_CONSECUTIVE_OFF_MODE_OPTIONS


def is_valid_no_consecutive_off_mode(mode: str) -> bool:
    return any(option.value == mode for option in NO_CONSECUTIVE_OFF_MODE_OPTIONS)


@dataclass(frozen=True)
class TransitionConstraintsModeOption:
    """A selectable mode for the anchor-opening-and-closing-periods preference."""

    value: str
    name: str
    description: str


TRANSITION_CONSTRAINTS_MODE_OPTIONS: tuple[TransitionConstraintsModeOption, ...] = (
    TransitionConstraintsModeOption(
        value="off",
        name="Off",
        description="Do not link the opening lineup to the half break or the end of the game.",
    ),
    TransitionConstraintsModeOption(
        value="preferred",
        name="Preferred",
        description="Anchor opening and closing periods when possible, but always produce a lineup.",
    ),
    TransitionConstraintsModeOption(
        value="enforced",
        name="Enforced",
        description="Require every player to anchor the opening period or the half break, and the opening or final.",
    ),
)


@dataclass(frozen=True)
class TransitionConstraintsPreferenceDefinition:
    """Metadata for the anchor-opening-and-closing-periods preference, which is tri-state rather than boolean."""

    key: str = "transition_constraints"
    name: str = "Anchor opening and closing periods"
    brief_description: str = "Link the opening lineup to the half break and the end of the game."
    detailed_description: str = (
        "Controls how strongly the solver links the opening lineup to the second-half start and the final period. "
        "Off leaves it unconstrained; Preferred asks the solver to anchor opening and closing periods "
        "while always producing a lineup; Enforced makes it a hard rule that can make lineups "
        "impossible to generate."
    )


TRANSITION_CONSTRAINTS_PREFERENCE: TransitionConstraintsPreferenceDefinition = (
    TransitionConstraintsPreferenceDefinition()
)
TRANSITION_CONSTRAINTS_MODE_DEFAULT = "preferred"


def get_transition_constraints_mode_options() -> tuple[TransitionConstraintsModeOption, ...]:
    return TRANSITION_CONSTRAINTS_MODE_OPTIONS


def is_valid_transition_constraints_mode(mode: str) -> bool:
    return any(option.value == mode for option in TRANSITION_CONSTRAINTS_MODE_OPTIONS)


@dataclass(slots=True)
class LineupConfig:
    team: Team
    power_combos: list[list[str]] = field(default_factory=list)
    required_final_period_players: list[str] = field(default_factory=list)
    never_on_first_period_players: list[str] = field(default_factory=list)
    periods_per_half: list[int] = field(default_factory=lambda: [6, 6])
    on_court_per_period: int = 5
    minutes_per_half: int = 20
    boolean_preferences: dict[str, bool] = field(default_factory=build_default_boolean_preferences)
    no_consecutive_off_mode: str = NO_CONSECUTIVE_OFF_MODE_DEFAULT
    transition_constraints_mode: str = TRANSITION_CONSTRAINTS_MODE_DEFAULT


@dataclass(slots=True)
class Player:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""


@dataclass(slots=True)
class Team:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: str = ""
    players: list[Player] = field(default_factory=list)
    lineup_config: LineupConfig | None = None

    def __post_init__(self) -> None:
        if self.lineup_config is None:
            self.lineup_config = LineupConfig(team=self)

    def add_player(self, player: Player) -> None:
        self.players.append(player)

    def get_player_by_name(self, name: str) -> Player | None:
        for player in self.players:
            if player.name == name:
                return player
        return None

    def get_player_names(self) -> list[str]:
        return [player.name for player in self.players]


@dataclass(slots=True)
class LineupSpin:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: int = 1
    players: list[Player] = field(default_factory=list)
    created_at: str | None = None
    solution_snapshot: dict[str, Any] | None = None
    config_snapshot: dict[str, Any] | None = None
    away_players: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Game:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    team_id: str = ""
    date: str = ""
    lineup_spins: list[LineupSpin] = field(default_factory=list)
    selected_lineup_id: str | None = None

    def add_spin(self, spin: LineupSpin) -> None:
        self.lineup_spins.append(spin)

    def renumber_spins(self) -> None:
        for index, spin in enumerate(self.lineup_spins, start=1):
            spin.number = index

    def select_spin(self, spin_id: str) -> None:
        if not any(spin.id == spin_id for spin in self.lineup_spins):
            raise KeyError(f"Unknown lineup spin: {spin_id}")
        self.selected_lineup_id = spin_id

    def get_selected_spin(self) -> LineupSpin | None:
        for spin in self.lineup_spins:
            if spin.id == self.selected_lineup_id:
                return spin
        return None

    def get_next_spin_number(self) -> int:
        if not self.lineup_spins:
            return 1

        existing_numbers = sorted({spin.number for spin in self.lineup_spins if spin.number is not None})
        if 1 not in existing_numbers:
            return 1
        return max(existing_numbers) + 1
