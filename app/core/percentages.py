def to_percentages(counts: list[int]) -> list[float]:
    """Converte contagens em percentuais com uma casa decimal que somam exatamente 100."""
    total = sum(counts)
    if total == 0:
        return [0.0] * len(counts)

    tenths = [count * 1000 / total for count in counts]
    rounded = [int(value) for value in tenths]
    missing = 1000 - sum(rounded)
    by_remainder = sorted(
        range(len(counts)), key=lambda index: tenths[index] - rounded[index], reverse=True
    )
    for index in by_remainder[:missing]:
        rounded[index] += 1
    return [value / 10 for value in rounded]
