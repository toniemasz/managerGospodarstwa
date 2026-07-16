# Odchów i przeniesienia prosiąt

`born_alive` w szczegółach zdarzenia `FARROWING` opisuje biologiczny wynik
oproszenia. Jest wartością historyczną i transfer, upadek ani odsadzenie jej nie
zmieniają.

Bieżący stan odchowu jest liczony centralnie przez
`sows.services.piglet_care.PigletCareService` dla konkretnego zdarzenia
oproszenia:

```text
urodzone żywe + przyjęte - przekazane - upadki przed odsadzeniem - odsadzone
```

Transfer jest jednym rekordem `PigletTransferModel` powiązanym z oproszeniem
źródłowym i docelowym. Zapis blokuje oba oproszenia w transakcji i sprawdza całą
późniejszą chronologię. Ten sam rekord jest prezentowany w historii obu macior.
Anulowanie zachowuje rekord i jest dozwolone tylko wtedy, gdy nie spowoduje
ujemnego stanu w późniejszych operacjach.

Upadek przed odsadzeniem jest jawnym `MortalityReportModel` przypisanym do
maciory i oproszenia, przy którym prosięta znajdowały się w dniu upadku.
Odsadzenie i upadek mogą pomniejszyć wyłącznie rzeczywiście dostępny stan.

Najważniejsze walidacje:

- oba odchowy należą do jednego gospodarstwa i są aktywne w dniu transferu,
- źródło i cel są różnymi maciorami,
- liczba jest dodatnia i nie przekracza dostępnego stanu,
- data nie wyprzedza oproszenia i nie przypada po odsadzeniu,
- edycja lub anulowanie nie może unieważnić późniejszego transferu, upadku ani
  odsadzenia.

Starsze cykle bez jawnych upadków i transferów mogą nadal pokazywać oznaczony
szacunek `urodzone żywe - odsadzone`. Nie jest on używany do bieżącej walidacji
i migracja nie tworzy na jego podstawie domniemanych transferów ani upadków.
