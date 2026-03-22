from aiogram.fsm.state import State, StatesGroup


class ProfileSetupStates(StatesGroup):
    full_name = State()
    email = State()
    birth_date = State()
    district = State()
    organization_label = State()
