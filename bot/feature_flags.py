"""Feature flag helpers with optional canary-channel rollout."""


def is_feature_enabled_for_channel(
    enabled: bool,
    canary_channel_ids: list[int],
    channel_id: int,
) -> bool:
    """Return whether a feature is active for the given channel.

    Rules:
    - If the flag is disabled -> False
    - If canary list is empty -> enabled globally
    - Else only enabled for channels in canary list
    """
    if not enabled:
        return False
    if not canary_channel_ids:
        return True
    return channel_id in canary_channel_ids
