from ...domain.class_features import CombatProfile, FeatureActionDefinition, FeatureGrant


def build_combat_profile(feature_grants: list[FeatureGrant]) -> CombatProfile:
    profile = CombatProfile()
    for grant in feature_grants:
        if grant.id == "extra_attack":
            attacks = grant.data.get("attacks")
            if isinstance(attacks, int):
                profile.attacks_per_attack_action = max(profile.attacks_per_attack_action, attacks)
        elif grant.id == "second_wind":
            profile.bonus_action_options.add("second_wind")
            profile.feature_actions["second_wind"] = FeatureActionDefinition(
                feature_id="second_wind", label="Second Wind", economy="bonus_action",
                target="self", resolver="second_wind",
            )
            uses = grant.data.get("uses")
            if isinstance(uses, int):
                profile.feature_uses_max["second_wind"] = max(
                    profile.feature_uses_max.get("second_wind", 0), uses
                )
            if grant.source_class == "Fighter" and grant.name == "Second Wind":
                profile.feature_recharge["second_wind"] = {
                    "short_rest": "all" if uses == 1 else 1,
                    "long_rest": "all",
                }
        elif grant.id == "action_surge":
            profile.feature_actions["action_surge"] = FeatureActionDefinition(
                feature_id="action_surge", label="Action Surge", economy="none",
                target="self", resolver="action_surge",
            )
            uses = grant.data.get("uses")
            if isinstance(uses, int):
                profile.feature_uses_max["action_surge"] = max(
                    profile.feature_uses_max.get("action_surge", 0), uses
                )
            profile.feature_recharge["action_surge"] = {
                "short_rest": "all", "long_rest": "all"
            }
    return profile


def build_feature_uses_remaining(combat_profile: CombatProfile) -> dict[str, int]:
    return dict(combat_profile.feature_uses_max)
