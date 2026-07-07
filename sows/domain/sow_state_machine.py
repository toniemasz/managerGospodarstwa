from __future__ import annotations


class SowStateMachine:
    IDLE = 'IDLE'
    INSEMINATED = 'INSEMINATED'
    TO_CHECK = 'TO_CHECK'
    TO_RECHECK = 'TO_RECHECK'
    PREGNANT = 'PREGNANT'
    LACTATING = 'LACTATING'

    INSEMINATION = 'INSEMINATION'
    PREGNANCY_CHECK = 'PREGNANCY_CHECK'
    FARROWING = 'FARROWING'
    WEANING = 'WEANING'
    MISCARRIAGE = 'MISCARRIAGE'
    VACCINATION = 'VACCINATION'

    STATUSES = (
        IDLE,
        INSEMINATED,
        TO_CHECK,
        TO_RECHECK,
        PREGNANT,
        LACTATING,
    )

    EVENT_TYPES = (
        INSEMINATION,
        PREGNANCY_CHECK,
        FARROWING,
        WEANING,
        MISCARRIAGE,
        VACCINATION,
    )

    ALLOWED_TRANSITIONS = {
        IDLE: {INSEMINATION},
        INSEMINATED: {PREGNANCY_CHECK, INSEMINATION},
        TO_CHECK: {PREGNANCY_CHECK, INSEMINATION},
        TO_RECHECK: {PREGNANCY_CHECK, INSEMINATION},
        PREGNANT: {FARROWING, MISCARRIAGE, INSEMINATION},
        LACTATING: {WEANING},
    }

    ERROR_MESSAGES = {
        LACTATING: "Maciora jest karmiąca. Następnym zdarzeniem powinno być odsadzenie.",
        IDLE: "Maciora jest jałowa. Rozpocznij cykl od inseminacji.",
        INSEMINATED: "Po inseminacji można dodać badanie USG albo ponowną inseminację.",
        TO_CHECK: "Maciora oczekuje na badanie USG. Dodaj badanie albo ponowną inseminację.",
        TO_RECHECK: "Maciora jest do rebadania. Dodaj badanie USG albo nową inseminację.",
        PREGNANT: "Maciora jest prośna. Następnym naturalnym zdarzeniem jest oproszenie albo poronienie.",
    }

    FARROWING_WITHOUT_CHECK_STATUSES = {
        INSEMINATED,
        TO_CHECK,
        TO_RECHECK,
    }

    FARROWING_CONFIRMATION_MESSAGE = (
        "Ta maciora nie ma zapisanego badania ciąży z wynikiem TAK. "
        "Czy chcesz mimo to dodać oproszenie?"
    )

    @classmethod
    def can_add_event(cls, status: str, event_type: str) -> bool:
        if event_type == cls.VACCINATION:
            return True
        return event_type in cls.ALLOWED_TRANSITIONS.get(status, set())

    @classmethod
    def get_error_message(cls, status: str) -> str:
        return cls.ERROR_MESSAGES.get(
            status,
            "To zdarzenie nie pasuje do aktualnego statusu maciory.",
        )

    @classmethod
    def requires_confirmation(cls, status: str, event_type: str) -> bool:
        return (
            event_type == cls.FARROWING
            and status in cls.FARROWING_WITHOUT_CHECK_STATUSES
        )

    @classmethod
    def get_confirmation_message(cls, status: str, event_type: str) -> str:
        if cls.requires_confirmation(status, event_type):
            return cls.FARROWING_CONFIRMATION_MESSAGE
        return ''

    @classmethod
    def changes_main_status(cls, event_type: str) -> bool:
        return event_type != cls.VACCINATION
