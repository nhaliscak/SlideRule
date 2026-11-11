"""Built-in calculation library.

Modules are grouped by theme rather than strictly by discipline: each calculation declares its own disciplines and
sub-disciplines, and `sliderule.core.taxonomy` defines the allowed names.
"""

from importlib import import_module

from ..core import Calculation
from ..core.taxonomy import SUBDISCIPLINES, TAXONOMY
from .subdisciplines import RETROFIT

_MODULES = (
    # original set
    "civil", "mechanical", "chemical", "electrical", "petroleum", "aerospace", "environmental", "architectural", "industrial", "systems",
    # discipline / sub-discipline coverage
    "civil_ext", "mechanical_ext", "aerospace_ext", "electrical_ext", "electromech", "chemical_ext", "agricultural", "biomedical",
    "materials", "mining", "nuclear", "petroleum_ext", "environmental_ext", "industrial_ext", "systems_ext", "computer", "robotics",
    "emerging_a", "emerging_b", "emerging_c",
    # equations written with derivatives and integrals
    "calculus",
    # physics and chemistry as sciences
    "physics", "chemistry",
    # core undergraduate physics and chemistry (stage 2)
    "physics_core_a", "physics_core_b", "physics_core_c", "chemistry_core_a", "chemistry_core_b", "physics_broad_a", "physics_broad_b", "chemistry_broad_a", "chemistry_broad_b", "thin_a", "thin_b", "thin_c", "thin_d", "thin_e", "mechanics_gaps", "hamiltonian_chaos", "mechanics_formalism", "audit_civil_a", "audit_civil_b", "audit_civil_c", "audit_mech_a", "audit_control", "audit_mech_b", "audit_elec_a", "audit_elec_b", "audit_chem_a", "audit_chem_b", "audit_mat_a", "audit_mat_b", "audit_aero_a", "audit_aero_b", "audit_bio_a", "audit_bio_b", "audit_agri_mine", "audit_petro", "audit_nuclear", "audit_ie_cs", "audit_arch", "audit_phys_a", "audit_phys_b", "audit_chem_emerge",
)


def all_calculations() -> list[Calculation]:
    out: list[Calculation] = []
    for name in _MODULES:
        out.extend(import_module(f"{__package__}.{name}").CALCS)
    by_id = {c.id: c for c in out}
    for cid, (subs, extra_disciplines) in RETROFIT.items():
        c = by_id[cid]
        c.subdisciplines = [*dict.fromkeys([*c.subdisciplines, *subs])]
        for d in extra_disciplines:
            if d not in c.disciplines:
                c.disciplines.append(d)
    # A sub-discipline tag implies the discipline that owns it (unless the calculation already sits under one of its owners).
    heading = {name: did for did, (name, _g, _s) in TAXONOMY.items()}
    for c in out:
        for s in c.subdisciplines:
            owners = SUBDISCIPLINES[s]
            if not set(owners) & set(c.disciplines) and heading.get(s) not in c.disciplines:
                c.disciplines.append(owners[0])
    return out
