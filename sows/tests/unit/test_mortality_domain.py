from sows.domain.mortality import calculate_pre_weaning_deaths


def test_pre_weaning_deaths_are_difference_between_born_alive_and_weaned():
    result = calculate_pre_weaning_deaths(12, 10)
    assert result.value == 2
    assert result.is_inconsistent is False


def test_pre_weaning_deaths_are_zero_when_counts_match():
    assert calculate_pre_weaning_deaths(10, 10).value == 0


def test_pre_weaning_deaths_never_become_negative_and_mark_inconsistency():
    result = calculate_pre_weaning_deaths(8, 10)
    assert result.value == 0
    assert result.is_inconsistent is True


def test_pre_weaning_deaths_do_not_treat_missing_value_as_zero():
    assert calculate_pre_weaning_deaths(12, None).value is None
    assert calculate_pre_weaning_deaths(None, 10).value is None
