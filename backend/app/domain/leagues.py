"""League structures (FR-1.2): multi-division promotion/relegation and hybrid group stage -> seeded knockout."""
from ..errors import validation_error
from .fixtures import single_elim


def promotion_relegation(final_order: list[str], promote: int, relegate: int) -> dict:
    """final_order: team ids in final standings order. Top `promote` go up, bottom `relegate` go down."""
    n = len(final_order)
    if promote < 0 or relegate < 0 or promote + relegate > n:
        raise validation_error(["promote", "relegate"], "Promotion and relegation places must fit in the division.")
    return {"promoted": final_order[:promote], "relegated": final_order[n - relegate:] if relegate else [],
            "stays": final_order[promote:n - relegate]}


def hybrid_seeds(group_tables: dict[str, list[str]], qualifiers_per_group: int) -> list[str]:
    """Seed order for the knockout: all group winners first, then all runners-up, ... (groups in name order)."""
    if qualifiers_per_group < 1 or any(len(t) < qualifiers_per_group for t in group_tables.values()):
        raise validation_error(["qualifiers_per_group"], "Each group needs at least that many teams.")
    groups = sorted(group_tables)
    seeds = [group_tables[g][pos] for pos in range(qualifiers_per_group) for g in groups]
    if len(set(seeds)) != len(seeds):
        raise validation_error(["groups"], "A team can only be in one group.")
    return seeds


def hybrid_knockout(group_tables: dict[str, list[str]], qualifiers_per_group: int, third_place: bool = False) -> dict:
    """Group stage followed by a seeded single-elimination bracket (winners meet runners-up of other groups)."""
    seeds = hybrid_seeds(group_tables, qualifiers_per_group)
    if len(seeds) < 2:
        raise validation_error(["qualifiers_per_group"], "The knockout needs at least two teams.")
    bracket = single_elim.generate(seeds, {"third_place_match": third_place})
    return {"seeds": seeds, **bracket}
