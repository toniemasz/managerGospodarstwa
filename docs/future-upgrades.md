# Przyszłe usprawnienia

## Członkostwo wielu użytkowników w gospodarstwie

Obecnie `FarmModel.owner` jest relacją `OneToOneField`, dlatego gospodarstwo ma jednego właściciela, a użytkownik jedno gospodarstwo. W przyszłości można wprowadzić:

```text
FarmMembership
- farm
- user
- role
- is_active
- permissions
```

Bezpieczna kolejność wdrożenia:

1. Zachować istniejące pole `owner`.
2. Dodać `FarmMembership` z unikalnością `(farm, user)`.
3. Migracją danych utworzyć członkostwo właściciela dla każdego gospodarstwa.
4. Dodać wybór aktywnego gospodarstwa i role dostępu.
5. Przepiąć `get_current_farm()` oraz wszystkie publiczne actions i selectors na członkostwo.
6. Pole `owner` usuwać lub zmieniać dopiero w osobnym, późniejszym wdrożeniu.

Przed wdrożeniem potrzebna jest decyzja biznesowa dotycząca ról, zakresu dostępu oraz możliwości pracy użytkownika w kilku gospodarstwach.
