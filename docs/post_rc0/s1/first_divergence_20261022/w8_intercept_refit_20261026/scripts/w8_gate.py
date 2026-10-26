"""W8 census gate, shared by w8_controls_v2.py (which writes it) and w8_refit.py (which enforces it).

B1, B2 and C are one equivalence group: a K8 disagreement, or any K1-K7 failure in any member,
makes the whole group ineligible. B2 is never eligible on its own.
"""
GROUP = ('B1', 'B2', 'C')
SCHEMA = 'w8-controls/2'


class RankError(ValueError):
    pass


def eligibility(failed_by_arm, k8_pass):
    group_ok = k8_pass and all(not failed_by_arm[a] for a in GROUP)
    return [a for a in GROUP if group_ok]


def census_allowed(controls):
    return (controls.get('schema') == SCHEMA and controls.get('k8_pass') is True
            and all(not controls['arms'][a]['failed'] for a in GROUP)
            and sorted(controls.get('census_eligible', [])) == sorted(GROUP)
            and controls.get('K12', {}).get('pass_') is True and controls.get('K13', {}).get('rejected') is True)


def require_full_rank(fit_result):
    if fit_result['rank'] != fit_result['n_cols']:
        raise RankError(f"rank {fit_result['rank']} < {fit_result['n_cols']} columns")
    return fit_result
